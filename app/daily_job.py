from __future__ import annotations

import logging
import re
from datetime import datetime, date, timezone as _tz
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.cpo_agent import CPOAgent
from app.db import CPOTask, DailyJobConfig, User
from app.google_docs import read_document, append_to_document

logger = logging.getLogger("daily_job")

DEAR_CPO_PATTERN = re.compile(r"(?i)\bdear\s+cpo\b")

TASK_PATTERN = re.compile(r"(?i)(?:task|assign)\s*:\s*(.+?)(?:\n|$)")
DONE_PATTERN = re.compile(r"(?i)(?:done|completed|finished)\s*:\s*(.+?)(?:\n|$)")
DUE_PATTERN = re.compile(r"(?i)\b(?:by|due)\s+(\w+\s+\d{1,2}(?:,?\s*\d{4})?|\d{4}-\d{2}-\d{2}|\w+day|\w+\s+\d{1,2})\b")

CPO_OUTPUT_MARKERS = [
    "### Daily Recap",
    "### Daily CPO Brief",
    "### CPO Question for Founder",
]

RECAP_HEADING = "### Daily Recap"
BRIEF_HEADING = "### Daily CPO Brief"
QUESTION_HEADING = "### CPO Question for Founder"


def _extract_new_notes(full_text: str, last_run_date: str) -> str:
    matches = list(DEAR_CPO_PATTERN.finditer(full_text))
    if not matches:
        return ""

    blocks = []
    for i, match in enumerate(matches):
        start = match.start()
        if i + 1 < len(matches):
            end = matches[i + 1].start()
        else:
            end = len(full_text)

        block = full_text[start:end]

        for marker in CPO_OUTPUT_MARKERS:
            marker_idx = block.find(marker)
            if marker_idx != -1:
                block = block[:marker_idx]
                break

        block = block.strip()
        if block:
            blocks.append(block)

    return "\n\n".join(blocks)


def _check_already_ran_today(full_text: str, today_str: str) -> bool:
    pattern = rf"{re.escape(RECAP_HEADING)}\s*—\s*{re.escape(today_str)}"
    return bool(re.search(pattern, full_text))


def _extract_question(brief_text: str) -> Optional[str]:
    for line in brief_text.splitlines():
        stripped = line.strip().lstrip("-•*").strip()
        lower = stripped.lower()
        if lower.startswith("one question for founder"):
            question = stripped.split(":", 1)[1].strip() if ":" in stripped else ""
            if question:
                return question
    return None


def _parse_due_date(text: str) -> str:
    from dateutil import parser as date_parser
    due_match = DUE_PATTERN.search(text)
    if not due_match:
        return ""
    raw = due_match.group(1).strip()
    try:
        parsed = date_parser.parse(raw, fuzzy=True)
        return parsed.strftime("%Y-%m-%d")
    except Exception:
        return ""


def _extract_and_save_tasks(new_notes: str, user_id: int, db: Session) -> list:
    task_matches = TASK_PATTERN.findall(new_notes)
    created = []
    for raw_title in task_matches:
        title = raw_title.strip().rstrip(".")
        if not title or len(title) < 3:
            continue
        existing = db.query(CPOTask).filter(
            CPOTask.user_id == user_id,
            CPOTask.title == title,
            CPOTask.status == "open",
        ).first()
        if existing:
            continue
        due = _parse_due_date(raw_title)
        task = CPOTask(
            user_id=user_id,
            title=title,
            due_date=due,
            source_text=raw_title.strip(),
        )
        db.add(task)
        created.append(task)
        logger.info(f"Created task for user {user_id}: '{title}' (due: {due or 'none'})")
    if created:
        db.flush()
    return created


def _process_completions(new_notes: str, user_id: int, db: Session) -> list:
    done_matches = DONE_PATTERN.findall(new_notes)
    completed = []
    for raw in done_matches:
        search_term = raw.strip().rstrip(".").lower()
        if not search_term or len(search_term) < 3:
            continue
        open_tasks = db.query(CPOTask).filter(
            CPOTask.user_id == user_id,
            CPOTask.status == "open",
        ).all()
        for task in open_tasks:
            if search_term in task.title.lower() or task.title.lower() in search_term:
                task.status = "done"
                task.completed_at = datetime.now(_tz.utc)
                completed.append(task)
                logger.info(f"Marked task done for user {user_id}: '{task.title}'")
                break
    if completed:
        db.flush()
    return completed


def _update_overdue_tasks(user_id: int, db: Session, today_str: str) -> list:
    open_tasks = db.query(CPOTask).filter(
        CPOTask.user_id == user_id,
        CPOTask.status == "open",
        CPOTask.due_date != "",
    ).all()
    overdue = []
    for task in open_tasks:
        if task.due_date and task.due_date < today_str:
            task.status = "overdue"
            overdue.append(task)
            logger.info(f"Task overdue for user {user_id}: '{task.title}' (due {task.due_date})")
    if overdue:
        db.flush()
    return overdue


def _build_task_summary(user_id: int, db: Session) -> str:
    tasks = db.query(CPOTask).filter(
        CPOTask.user_id == user_id,
        CPOTask.status.in_(["open", "overdue"]),
    ).all()
    if not tasks:
        return ""
    lines = []
    overdue = [t for t in tasks if t.status == "overdue"]
    open_tasks = [t for t in tasks if t.status == "open"]
    if overdue:
        lines.append("OVERDUE TASKS:")
        for t in overdue:
            lines.append(f"  - {t.title} (was due {t.due_date})")
    if open_tasks:
        lines.append("OPEN TASKS:")
        for t in open_tasks:
            due_info = f" (due {t.due_date})" if t.due_date else ""
            lines.append(f"  - {t.title}{due_info}")
    return "\n".join(lines)


def _generate_recap(agent: CPOAgent, product_brief: str, new_notes: str) -> str:
    prompt = f"""
SYSTEM:
You are the AI CPO (Chief Product Officer) for a SaaS company. The founder writes to you using "Dear CPO" messages in their Google Doc. You are their trusted product executive.

Write in plain language. Be warm but direct. Every word should be useful.

PRODUCT BRIEF:
{product_brief if product_brief else "No product brief provided yet."}

FOUNDER'S "DEAR CPO" MESSAGES:
{new_notes if new_notes else "No new messages from the founder."}

Generate a Daily Recap — a clear summary of what the founder told you today. Be faithful to what they wrote — do NOT invent events or add information they didn't share.

If no new messages, write: "No new messages from you today. When you're ready, just write 'Dear CPO' in your doc and I'll pick it up."

OUTPUT FORMAT (plain text, not JSON):

Outcome of the day: One sentence summarizing what today moved forward and toward what goal. Be specific.
Example: "Moved MVP closer to onboarding 3 beta users by finalizing the signup flow and confirming the first demo call."

What happened:
- For each item, write 1-2 sentences explaining what happened and why it matters. Include 3-7 items based on how much the founder shared.

Decision made:
- State the single most important decision the founder made or implied today. Explain the reasoning if they mentioned it.
- If no decision was made, PROPOSE one: "No decision was called out today. Proposed decision: [specific, actionable decision the founder should consider based on what they shared, with a brief reason why]."
- Only include ONE decision or proposed decision.

Non-core topics:
- List anything the founder mentioned that is NOT directly related to the current core product priority. This helps the founder see what might be a distraction.
- If everything was core, write "Everything today was on-target for the current priority."

Blockers & risks:
- For each blocker, explain what's stuck and what impact it could have. Include 0-3 items.
- If none mentioned, write "No blockers flagged today."

Rules:
- Use "-" prefix for list items
- Write in complete sentences, not fragments
- Label each section clearly with the labels above
- Keep it tight — no filler sentences
"""
    resp = agent.model.generate_content(prompt)
    return (resp.text or "").strip()


def _generate_brief(agent: CPOAgent, product_brief: str, new_notes: str, last_brief: str, task_summary: str) -> str:
    prompt = f"""
SYSTEM:
You are the AI CPO (Chief Product Officer) for a SaaS company. The founder writes to you using "Dear CPO" messages. You are their trusted product executive who tells them what to focus on and what to ignore.

Be direct. Every sentence must be useful. Explain WHY, not just what.

PRODUCT BRIEF:
{product_brief if product_brief else "No product brief provided yet."}

FOUNDER'S "DEAR CPO" MESSAGES:
{new_notes if new_notes else "No new messages from the founder."}

{"PREVIOUS CPO BRIEF:" + chr(10) + last_brief if last_brief else ""}

{("FOUNDER'S ASSIGNED TASKS:" + chr(10) + task_summary) if task_summary else ""}

Generate a Daily CPO Brief — your strategic guidance for the founder.
If no new messages, restate current focus and give the single next action based on previous brief.

OUTPUT FORMAT (plain text, not JSON):

Focus (next 14 days): 2-3 sentences on the single most important priority and WHY it matters right now.

Next action: ONE specific, executable thing the founder should do next. Not 3 bullets — one clear action with a reason why it's the right move right now. Make it concrete enough that the founder can start immediately.
Example: "Send a 3-question survey to your 5 most active users asking what almost made them cancel — this will surface the retention risk before you scale."

One metric to watch: Name the metric and explain why this one matters most right now (1-2 sentences).

Kill list (today):
- For each item (max 3), name what to deprioritize and explain why it's a distraction right now.

Non-core topics:
- If the founder mentioned topics outside the current core priority, list them here so they're acknowledged but separated from the main strategic guidance.
- If everything was on-target, write "All founder input today was aligned with the core priority."

{"Task status:" + chr(10) + "- Comment on any overdue or upcoming tasks. Remind the founder about deadlines and suggest priorities." if task_summary else ""}

One question for founder: Ask one strategic question and explain why you're asking it (what decision it will help with). Write this as a full thought.

IMPORTANT: The "One question for founder" MUST be on its own final line starting with
"One question for founder:" — this will be extracted separately and added to the founder's
source doc for easy visibility. Always include exactly one question.

Rules:
- ONE focus, ONE next action, ONE metric, ONE question
- Kill list max 3 items
- Write in complete sentences with reasoning
- Label each section clearly with the labels above
- No markdown headers (no ###), just use the label text followed by a colon
- No filler — every sentence should earn its place
"""
    resp = agent.model.generate_content(prompt)
    return (resp.text or "").strip()


CUSTOMER_RECAP_HEADING = "### CPO Recap"


def _generate_customer_recap(agent: CPOAgent, product_brief: str, new_notes: str, recap_text: str, brief_text: str) -> str:
    prompt = f"""
SYSTEM:
You are the AI CPO (Chief Product Officer) writing a customer-facing product update.
This recap is shared externally — it should be polished, positive, and professional.
Write like a friendly product leader giving customers an exciting update on what's happening.

ABSOLUTE RULES — NEVER INCLUDE:
- Internal strategy, blockers, kill lists, or founder-only details
- References to "Dear CPO" messages or internal processes
- Mentions of team hiring, internal debates, or budget concerns
- Raw metrics or internal KPIs

PRODUCT BRIEF:
{product_brief if product_brief else "No product brief provided yet."}

TODAY'S INTERNAL RECAP (for context only — do NOT copy verbatim):
{recap_text if recap_text else "No internal recap available."}

TODAY'S INTERNAL CPO BRIEF (for context only — do NOT copy verbatim):
{brief_text if brief_text else "No internal brief available."}

FOUNDER'S MESSAGES (for additional context):
{new_notes if new_notes else "No new messages today."}

Generate a CPO Recap for customers. This is a daily product update that customers see.

OUTPUT FORMAT (plain text, not JSON):

What shipped or improved:
- For each item (2-5), describe what was built or improved and briefly explain how it benefits customers. Write 1-2 sentences per item.
- Example: "Streamlined onboarding flow — new users can now get set up in under 2 minutes, down from 5. This means you'll spend less time configuring and more time getting value."

What's coming next:
- For each item (1-3), describe what's being worked on and why customers should be excited about it. Write 1-2 sentences.

Highlight of the day: One standout achievement or milestone, written as a complete sentence that celebrates progress (e.g., "We crossed 100 active users this week — a milestone that shows real demand for what we're building.").

Rules:
- Use "-" prefix for each item
- Write in complete, friendly sentences — not fragments
- Tone: confident, customer-friendly, exciting but honest
- If nothing shipped today, focus on progress being made and what's coming soon
- Label each section clearly
"""
    resp = agent.model.generate_content(prompt)
    return (resp.text or "").strip()


def run_customer_recap_job(user: User, db: Session, agent: CPOAgent) -> Dict[str, Any]:
    config = user.daily_job_config
    if not config:
        return {"status": "error", "message": "No daily job configuration found."}

    if not config.ai_cpo_enabled:
        return {"status": "paused", "message": "AI CPO is paused."}

    if not config.recap_doc_id:
        return {"status": "skipped", "message": "No CPO Recap doc configured."}

    user_now = _get_user_now(config)
    utc_now = datetime.now(_tz.utc)
    today_str = user_now.strftime("%Y-%m-%d")
    timestamp_str = user_now.strftime("%Y-%m-%d %H:%M")
    tz_abbr = user_now.strftime("%Z") or (config.timezone or "ET")

    if config.last_recap_date == today_str:
        return {"status": "skipped", "message": f"Customer recap already generated for {today_str}."}

    logger.info(f"Customer recap job starting for user {user.id}, recap_doc={config.recap_doc_id}, tz={config.timezone}")

    source_doc_id = config.google_doc_id
    output_doc_id = config.output_doc_id or source_doc_id

    full_text = ""
    if source_doc_id:
        try:
            doc_data = read_document(source_doc_id)
            full_text = doc_data.get("text", "")
        except Exception as e:
            logger.warning(f"Could not read source doc for customer recap: {e}")

    output_full_text = ""
    if output_doc_id:
        try:
            output_doc_data = read_document(output_doc_id)
            output_full_text = output_doc_data.get("text", "")
        except Exception as e:
            logger.warning(f"Could not read output doc for customer recap: {e}")

    product_brief = ""
    if user.product_brief:
        product_brief = user.product_brief.content

    new_notes = _extract_new_notes(full_text, config.last_run_date or "") if full_text else ""

    today_recap_pattern = rf"{re.escape(RECAP_HEADING)}\s*—\s*{re.escape(today_str)}"
    today_recap = ""
    recap_match = re.search(today_recap_pattern, output_full_text)
    if recap_match:
        start = recap_match.start()
        next_heading = output_full_text.find("###", start + len(recap_match.group()))
        today_recap = output_full_text[start:next_heading].strip() if next_heading != -1 else output_full_text[start:].strip()

    today_brief_pattern = rf"{re.escape(BRIEF_HEADING)}\s*—\s*{re.escape(today_str)}"
    today_brief = ""
    brief_match = re.search(today_brief_pattern, output_full_text)
    if brief_match:
        start = brief_match.start()
        next_heading = output_full_text.find("###", start + len(brief_match.group()))
        today_brief = output_full_text[start:next_heading].strip() if next_heading != -1 else output_full_text[start:].strip()

    try:
        customer_recap_text = _generate_customer_recap(agent, product_brief, new_notes, today_recap, today_brief)
    except Exception as e:
        logger.error(f"Failed to generate customer recap: {e}")
        return {"status": "error", "message": f"AI generation failed (customer recap): {str(e)}"}

    output_block = f"\n\n{CUSTOMER_RECAP_HEADING} — {timestamp_str} {tz_abbr}\n{customer_recap_text}\n"

    try:
        append_to_document(config.recap_doc_id, output_block)
        logger.info(f"Appended customer recap to recap doc ({config.recap_doc_id}).")
    except Exception as e:
        logger.error(f"Failed to write to recap Google Doc: {e}")
        return {"status": "error", "message": f"Failed to write to recap doc: {str(e)}"}

    config.last_recap_date = today_str
    config.updated_at = utc_now
    db.commit()

    logger.info(f"Customer recap job completed for user {user.id}")

    return {
        "status": "success",
        "message": f"CPO Recap ({timestamp_str} {tz_abbr}) appended to recap doc.",
        "date": today_str,
        "recap_length": len(customer_recap_text),
    }


def _find_last_brief(full_text: str) -> str:
    pattern = rf"{re.escape(BRIEF_HEADING)}\s*—\s*\d{{4}}-\d{{2}}-\d{{2}}"
    matches = list(re.finditer(pattern, full_text))
    if not matches:
        return ""
    last_match = matches[-1]
    start = last_match.start()
    next_heading = full_text.find("###", start + len(last_match.group()))
    if next_heading == -1:
        return full_text[start:].strip()
    return full_text[start:next_heading].strip()


def _get_user_now(config: DailyJobConfig) -> datetime:
    tz_name = config.timezone or "US/Eastern"
    try:
        user_tz = ZoneInfo(tz_name)
    except Exception:
        user_tz = ZoneInfo("US/Eastern")
    return datetime.now(user_tz)


def run_daily_job(user: User, db: Session, agent: CPOAgent, prefetched_text: Optional[str] = None) -> Dict[str, Any]:
    config = user.daily_job_config
    if not config:
        return {"status": "error", "message": "No daily job configuration found for this user."}

    if not config.ai_cpo_enabled:
        return {"status": "paused", "message": "AI CPO is paused. Enable it from the dashboard."}

    if not config.google_doc_id:
        return {"status": "error", "message": "No Google Doc ID configured. Set it from the dashboard."}

    user_now = _get_user_now(config)
    utc_now = datetime.now(_tz.utc)
    today_str = user_now.strftime("%Y-%m-%d")
    timestamp_str = user_now.strftime("%Y-%m-%d %H:%M")
    tz_abbr = user_now.strftime("%Z") or (config.timezone or "ET")
    source_doc_id = config.google_doc_id
    output_doc_id = config.output_doc_id or source_doc_id

    logger.info(f"CPO job starting for user {user.id}, source_doc={source_doc_id}, output_doc={output_doc_id}, tz={config.timezone}")

    if prefetched_text is not None:
        full_text = prefetched_text
        logger.info(f"Using prefetched source doc, text length={len(full_text)}")
    else:
        try:
            doc_data = read_document(source_doc_id)
        except Exception as e:
            logger.error(f"Failed to read source Google Doc {source_doc_id}: {e}")
            return {"status": "error", "message": f"Failed to read source Google Doc: {str(e)}"}
        full_text = doc_data.get("text", "")
        logger.info(f"Read source doc, text length={len(full_text)}")

    output_full_text = full_text
    if output_doc_id != source_doc_id:
        try:
            output_doc_data = read_document(output_doc_id)
            output_full_text = output_doc_data.get("text", "")
            logger.info(f"Read output doc, text length={len(output_full_text)}")
        except Exception as e:
            logger.error(f"Failed to read output Google Doc {output_doc_id}: {e}")
            return {"status": "error", "message": f"Failed to read output Google Doc: {str(e)}"}

    product_brief = ""
    if user.product_brief:
        product_brief = user.product_brief.content

    new_notes = _extract_new_notes(full_text, config.last_run_date or "")
    dear_cpo_count = len(DEAR_CPO_PATTERN.findall(full_text))
    logger.info(f"Found {dear_cpo_count} 'Dear CPO' message(s), extracted notes length={len(new_notes)}")

    _process_completions(new_notes, user.id, db)
    _extract_and_save_tasks(new_notes, user.id, db)
    _update_overdue_tasks(user.id, db, today_str)
    task_summary = _build_task_summary(user.id, db)
    if task_summary:
        logger.info(f"Task summary for user {user.id}:\n{task_summary}")

    last_brief = _find_last_brief(output_full_text)
    if not last_brief and output_doc_id != source_doc_id:
        last_brief = _find_last_brief(full_text)

    try:
        recap_text = _generate_recap(agent, product_brief, new_notes)
    except Exception as e:
        logger.error(f"Failed to generate recap: {e}")
        return {"status": "error", "message": f"AI generation failed (recap): {str(e)}"}

    try:
        brief_text = _generate_brief(agent, product_brief, new_notes, last_brief, task_summary)
    except Exception as e:
        logger.error(f"Failed to generate brief: {e}")
        return {"status": "error", "message": f"AI generation failed (brief): {str(e)}"}

    output_block = f"\n\n{RECAP_HEADING} — {timestamp_str} {tz_abbr}\n{recap_text}\n\n{BRIEF_HEADING} — {timestamp_str} {tz_abbr}\n{brief_text}\n"

    try:
        append_to_document(output_doc_id, output_block)
        logger.info(f"Appended daily output to output doc ({output_doc_id}).")
    except Exception as e:
        logger.error(f"Failed to write to output Google Doc: {e}")
        return {"status": "error", "message": f"Failed to write to output Google Doc: {str(e)}"}

    question = _extract_question(brief_text)
    if question and source_doc_id != output_doc_id:
        question_block = f"\n\n{QUESTION_HEADING} — {timestamp_str} {tz_abbr}\n{question}\n"
        try:
            append_to_document(source_doc_id, question_block)
            logger.info(f"Appended CPO question to source doc ({source_doc_id}).")
        except Exception as e:
            logger.warning(f"Failed to append question to source doc: {e}")

    config.last_run_at = utc_now
    config.last_run_date = today_str
    config.updated_at = utc_now
    db.commit()

    logger.info(f"CPO job completed successfully for user {user.id}")

    return {
        "status": "success",
        "message": f"Daily Recap and CPO Brief ({timestamp_str} {tz_abbr}) appended to output Google Doc.",
        "date": today_str,
        "notes_length": len(new_notes),
        "recap_length": len(recap_text),
        "brief_length": len(brief_text),
    }
