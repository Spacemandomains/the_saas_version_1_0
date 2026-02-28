from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone as tz, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.db import SessionLocal, DailyJobConfig
from app.cpo_agent import CPOAgent
from app.daily_job import run_daily_job, run_customer_recap_job, _extract_new_notes
from app.google_docs import read_document

logger = logging.getLogger("scheduler")

scheduler = BackgroundScheduler(daemon=True, timezone=tz.utc)

BASE_TICK_MINUTES = 5
MIN_INTERVAL = 5
MAX_INTERVAL = 1440


def _compute_notes_hash(notes_text: str) -> str:
    return hashlib.sha256(notes_text.strip().encode()).hexdigest()


def _monitor_and_run():
    logger.info("Monitor: tick — checking all enabled users")
    db = SessionLocal()
    now = datetime.now(tz.utc)
    try:
        configs = (
            db.query(DailyJobConfig)
            .filter(DailyJobConfig.ai_cpo_enabled == True)
            .filter(DailyJobConfig.google_doc_id != "")
            .all()
        )
        if not configs:
            logger.info("Monitor: no active users with docs configured")
            return

        agent = None

        for config in configs:
            user = config.user
            interval = config.poll_interval_minutes or 30
            interval = max(MIN_INTERVAL, min(MAX_INTERVAL, interval))

            if config.last_checked_at:
                last_tz = config.last_checked_at.replace(tzinfo=tz.utc) if config.last_checked_at.tzinfo is None else config.last_checked_at
                next_check = last_tz + timedelta(minutes=interval)
                if now < next_check:
                    from zoneinfo import ZoneInfo
                    tz_name = config.timezone or "US/Eastern"
                    try:
                        user_tz = ZoneInfo(tz_name)
                    except Exception:
                        user_tz = ZoneInfo("US/Eastern")
                    local_next = next_check.astimezone(user_tz)
                    tz_abbr = local_next.strftime("%Z") or tz_name
                    logger.info(f"Monitor: user {user.id} — next check at {local_next.strftime('%I:%M %p')} {tz_abbr} (every {interval}min), skipping")
                    continue

            try:
                logger.info(f"Monitor: user {user.id} — reading source doc {config.google_doc_id}")
                doc_data = read_document(config.google_doc_id)
                full_text = doc_data.get("text", "")
                logger.info(f"Monitor: user {user.id} — source doc read OK, length={len(full_text)}")
                new_notes = _extract_new_notes(full_text, config.last_run_date or "")
                current_hash = _compute_notes_hash(new_notes)

                config.last_checked_at = now
                db.commit()

                if current_hash == config.last_notes_hash and config.last_notes_hash:
                    logger.info(f"Monitor: user {user.id} — no new 'Dear CPO' messages (hash match), notes_len={len(new_notes.strip())}")
                    continue

                if not new_notes.strip():
                    logger.info(f"Monitor: user {user.id} — no 'Dear CPO' messages found in doc, skipping")
                    continue

                logger.info(f"Monitor: user {user.id} — new 'Dear CPO' message(s) detected, notes_len={len(new_notes.strip())}, running CPO job")

                if agent is None:
                    agent = CPOAgent()

                result = run_daily_job(user, db, agent, prefetched_text=full_text)
                logger.info(f"Monitor: user {user.id} — {result.get('status')}: {result.get('message', '')}")

                if result.get("status") == "success":
                    config.last_notes_hash = current_hash
                    db.commit()

            except Exception as e:
                logger.error(f"Monitor: failed for user {user.id}: {e}")
    except Exception as e:
        logger.error(f"Monitor: unexpected error: {e}")
    finally:
        db.close()


def _check_recap_jobs():
    logger.info("Recap check: tick — checking for 6pm recap jobs")
    db = SessionLocal()
    now = datetime.now(tz.utc)
    try:
        configs = (
            db.query(DailyJobConfig)
            .filter(DailyJobConfig.ai_cpo_enabled == True)
            .filter(DailyJobConfig.recap_doc_id != "")
            .filter(DailyJobConfig.recap_doc_id != None)
            .all()
        )
        if not configs:
            logger.info("Recap check: no users with recap doc configured")
            return

        agent = None

        for config in configs:
            user = config.user
            from zoneinfo import ZoneInfo
            tz_name = config.timezone or "US/Eastern"
            try:
                user_tz = ZoneInfo(tz_name)
            except Exception:
                user_tz = ZoneInfo("US/Eastern")

            user_now = datetime.now(user_tz)
            today_str = user_now.strftime("%Y-%m-%d")

            if config.last_recap_date == today_str:
                continue

            recap_time = config.recap_time or "18:00"
            try:
                target_hour, target_minute = map(int, recap_time.split(":"))
            except Exception:
                target_hour, target_minute = 18, 0

            if user_now.hour < target_hour or (user_now.hour == target_hour and user_now.minute < target_minute):
                logger.info(f"Recap check: user {user.id} — not yet {recap_time} in {tz_name} (currently {user_now.strftime('%H:%M')}), skipping")
                continue

            logger.info(f"Recap check: user {user.id} — it's past {recap_time} in {tz_name}, running customer recap")

            if agent is None:
                agent = CPOAgent()

            try:
                result = run_customer_recap_job(user, db, agent)
                logger.info(f"Recap check: user {user.id} — {result.get('status')}: {result.get('message', '')}")
            except Exception as e:
                logger.error(f"Recap check: failed for user {user.id}: {e}")
    except Exception as e:
        logger.error(f"Recap check: unexpected error: {e}")
    finally:
        db.close()


def start_scheduler():
    if scheduler.running:
        logger.info("Scheduler already running")
        return

    scheduler.add_job(
        _monitor_and_run,
        trigger=IntervalTrigger(minutes=BASE_TICK_MINUTES),
        id="cpo_doc_monitor",
        name="CPO Doc Monitor",
        replace_existing=True,
        misfire_grace_time=600,
        next_run_time=datetime.now(tz.utc),
    )
    scheduler.add_job(
        _check_recap_jobs,
        trigger=IntervalTrigger(minutes=BASE_TICK_MINUTES),
        id="cpo_recap_check",
        name="CPO Recap Check",
        replace_existing=True,
        misfire_grace_time=600,
        next_run_time=datetime.now(tz.utc) + timedelta(minutes=1),
    )
    scheduler.start()

    next_run = scheduler.get_job("cpo_doc_monitor").next_run_time
    logger.info(f"Scheduler started — base tick every {BASE_TICK_MINUTES} min, next tick: {next_run}")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")


