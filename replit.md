# AI CPO Agent

## Overview
An AI-powered Chief Product Officer built for SaaS founders (The Six SaaS). It acts as an always-available executive that translates founder vision into structured product strategy using Google Gemini AI. The MVP focuses on automated daily Google Doc processing — reading founder notes and writing back a Daily Recap and Daily CPO Brief.

## Product Vision — The Six AI Agent C-Suite SaaS
The AI CPO is one agent in a broader AI C-suite. Its core job: turn founder ideas into actionable, structured product strategy.

### MVP Focus: Daily CPO Automation
The primary feature is an automated daily job that:
1. Reads the founder's connected Google Doc ("Source of Truth")
2. Identifies new founder entries since last run
3. Generates a Daily Recap (what happened)
4. Generates a Daily CPO Brief (focus + next actions)
5. Appends both outputs to the Google Doc under dated headings
6. Stores last_run state for incremental processing

### All Capabilities (some hidden in MVP)
- **Active:** Daily CPO Automation, Google Docs read/write, Settings/Toggle, Manual Run
- **Hidden:** PRD, Roadmap, Sprint, Feature Spec, User Stories, Technical Handoff, Release Notes, Strategy Memo generation, ICP, PMF Signals, Metrics Dashboard, Executive Challenge Mode

## Recent Changes
- 2026-03-07: Real-time chat interface — "Chat with CPO" page with conversation memory, streaming responses via SSE, multi-turn Gemini chat sessions, full product context injection (brief, tasks, ICP, status); CPOConversation + CPOMessage DB models; sidebar nav link; conversation list with create/delete
- 2026-03-07: Hardwired full CPO executive role — comprehensive system prompt covering product strategy, vision, innovation, design, development, project management, and product marketing; policies define scope of authority, decision-making framework, strategic guardrails; all generation prompts (recap, brief, customer recap, challenge, metrics) now inject full system prompt and frame each task as CPO executive action
- 2026-03-07: Improved monitor sync — two-layer hash detection (full doc hash + notes hash) prevents re-triggering on CPO's own writes; CPO output sections stripped before hashing source doc; recap duplicate check logs when already sent; dashboard timing more accurate
- 2026-02-28: Render.com deployment support — added render.yaml, Procfile, gunicorn; DATABASE_URL postgres:// prefix fix in db.py; google_docs.py now supports both Replit connector and Google Service Account (GOOGLE_SERVICE_ACCOUNT_JSON env var); README.md with full Render deployment guide
- 2026-02-27: Tighter CPO output structure — Recap now has "Outcome of the day" (one sentence), one decision (or proposed decision), "Non-core topics" separation; Brief now has single "Next action" instead of 3 bullets, "Non-core topics" section; both outputs more focused and actionable
- 2026-02-27: Task management — founder can assign tasks via "Dear CPO, task: ..." with optional "by [date]" deadlines; mark done via "done: [task]"; CPOTask DB model; tasks shown on dashboard with overdue highlighting; CPO Brief references open/overdue tasks; API endpoints GET/POST/DELETE /me/tasks
- 2026-02-27: CPO Recap Doc — new customer-facing daily product update; third Google Doc (recap_doc_id) with configurable time (recap_time, default 18:00); scheduler checks every 5min and runs once daily at user's chosen time; polished external tone (no internal strategy/blockers); stored as last_recap_date to prevent duplicates
- 2026-02-27: "Dear CPO" trigger — replaced rigid heading-based doc structure with natural "Dear CPO" message detection; founder writes "Dear CPO" anywhere in their Google Doc and the AI picks it up; case-insensitive; no required headings; removed forced doc structure; updated all UI text (dashboard, guide) to reflect the new approach
- 2026-02-27: Global timezone display — user's configured timezone now shown as a live clock in the sidebar, updated every minute; all timestamps across the SaaS (documents, document detail, PMF, dashboard, schedule) use timezone-aware formatDate()/formatDateTime() helpers from base.html; timezone stored in localStorage and bootstrapped on first page load; API endpoints return pre-formatted timezone-aware display strings (last_run_display, next_run)
- 2026-02-27: Added floating toast notification system — global showToast() in base.html replaces inline alert divs; used for profile save, team invite, CPO settings save, monitoring interval save; auto-dismisses after 3 seconds
- 2026-02-26: Added Getting Started guide page (/app/guide) with full founder onboarding: quick start, Google Doc setup, how CPO works, doc format, output format, settings guide, team, FAQ; accessible from sidebar
- 2026-02-26: Moved CPO-specific settings (automation, docs, monitoring, timezone) from shared Settings to CPO Dashboard; Settings page now only has Profile and Team (shared across all agents); each agent will have its own settings on its dashboard
- 2026-02-26: Added C-Suite agents landing page — /app/agents shows all 6 AI agents (CPO active, COO/CFO/CTO/CMO/CHRO coming soon); post-login redirects here; sidebar updated with "AI C-Suite" nav link
- 2026-02-26: Added timezone support and source doc protection — per-user timezone (default US/Eastern) for output timestamps; source doc is read-only (only CPO question appended); recap/brief always go to output doc; structure headings no longer written to source doc
- 2026-02-26: Added configurable polling interval — founder picks from 5/10/15/20/25/30/45/60min or custom (5–1440min); scheduler ticks every 5min and respects per-user interval via last_checked_at
- 2026-02-26: Changed to always-on monitoring — AI CPO polls source doc, detects new notes via content hash, runs automatically when changes found; removed Run Now button; dashboard shows monitoring status
- 2026-02-26: Added separate output Google Doc support — source doc for reading, output doc for writing recap/brief (falls back to source doc if not set)
- 2026-02-26: Added Company model and co-founder/team support: User gains first_name, role, company_id; signup captures first_name and company_name; new endpoints for profile (GET/POST /me/profile), team management (GET /me/team, POST /me/team/invite, DELETE /me/team/{id})
- 2026-02-26: Dashboard shows personalized greeting (Role: FirstName + company name), setup card when no Google Doc connected, and inline Active/Paused toggle
- 2026-02-26: Sidebar brand personalizes with company logo and name from localStorage
- 2026-02-26: Settings page unified: profile (name, company, logo), daily CPO automation, team invite/management, autonomous schedule info
- 2026-02-26: Built daily CPO automation — automated daily job that reads Google Doc, generates recap + brief, appends back
- 2026-02-26: Added DailyJobConfig DB table (google_doc_id, ai_cpo_enabled, last_run_at, last_run_date)
- 2026-02-26: Added POST /jobs/daily_doc_run secured endpoint (X-Job-Secret header auth)
- 2026-02-26: Added settings page for Google Doc ID and active/paused toggle
- 2026-02-26: Added manual "Run Now" button on dashboard
- 2026-02-26: Added read_document function to Google Docs integration
- 2026-02-26: Simplified dashboard and sidebar to MVP-only features
- 2026-02-13: Built all remaining CPO capabilities (hidden for MVP)
- 2026-02-13: Initial Replit setup — configured PostgreSQL, port 5000

## Project Architecture
- **Language**: Python 3.11
- **Framework**: FastAPI with Jinja2 templates
- **Database**: PostgreSQL (Replit built-in, via SQLAlchemy ORM)
- **AI**: Google Gemini API (requires GEMINI_API_KEY secret)
- **Google Docs**: Replit connector integration for reading/writing documents
- **Port**: 5000
- **Auth**: API key stored in browser localStorage, bcrypt password hashing
- **Scheduler**: APScheduler (BackgroundScheduler) — base tick every 5 min, per-user configurable polling interval (default 30 min, range 5–1440)
- **Job Auth**: JOB_SECRET env var, required via X-Job-Secret header (fallback API endpoint)

### Structure
```
app/
  main.py          - FastAPI entrypoint, API + page routes, daily job endpoints
  scheduler.py     - APScheduler background scheduler (interval-based doc monitoring)
  cpo_agent.py     - Gemini AI agent orchestration (generate, challenge, analyze)
  daily_job.py     - Daily automation pipeline (read doc, generate recap+brief, append)
  db.py            - SQLAlchemy models (User, ProductBrief, DailyJobConfig, etc.)
  auth.py          - API key auth, password hashing (direct bcrypt)
  tools.py         - Scoring utilities (RICE/ICE)
  google_docs.py   - Google Docs API integration via Replit connector (read + write)
templates/
  base.html        - Shared layout with sidebar nav (AI C-Suite, Settings, Getting Started, Documents)
  auth.html        - Login/signup page
  agents.html      - C-Suite agents landing page (CPO active, others coming soon)
  dashboard.html   - CPO dashboard with status, how-it-works, and CPO-specific settings (automation, docs, timezone, monitoring)
  guide.html       - Getting Started guide for founders (setup, doc format, FAQ)
  settings.html    - Shared C-Suite settings: profile and team management
  generate.html    - Document generation form (hidden in MVP)
  documents.html   - Document list view with per-agent tabs (All, CPO, CTO, CFO, COO, CMO, CHRO)
  document_detail.html - Single document viewer
  brief.html       - Product brief editor (hidden in MVP)
  icp.html         - ICP editor (hidden in MVP)
  pmf.html         - PMF Signal capture (hidden in MVP)
  metrics.html     - Metrics dashboard (hidden in MVP)
static/
  AI_CPO_Agent_Capabilities.txt - Downloadable capabilities list
```

### Database Tables
- `users` — User accounts with email, password hash, API key
- `daily_job_configs` — Per-user daily job state (google_doc_id, output_doc_id, recap_doc_id, recap_time, last_recap_date, ai_cpo_enabled, last_run_at, last_run_date)
- `product_briefs` — Product context (one per user)
- `icp_profiles` — ICP & Value Proposition data (one per user)
- `pmf_signals` — Product-market fit signals (many per user)
- `metrics_snapshots` — Historical metrics data (many per user)
- `generated_docs` — All generated documents (many per user)
- `cpo_tasks` — CPO-tracked tasks (many per user): title, details, due_date, status (open/done/overdue), source_text
- `cpo_conversations` — Chat conversations (many per user): title, created_at, updated_at
- `cpo_messages` — Chat messages (many per conversation): role (user/assistant), content, created_at

### Key Endpoints (MVP)
**Pages (GET):**
- `/` — Redirects to dashboard
- `/app/auth` — Login/signup page
- `/app/dashboard` — Dashboard with daily automation status
- `/app/settings` — Configure Google Doc ID and toggle
- `/app/documents` — List generated documents

**API (MVP):**
- `POST /auth/signup` — Create account
- `POST /auth/login` — Login
- `GET /me/daily-job` — Get daily job settings
- `POST /me/daily-job` — Update daily job settings (doc ID, toggle)
- `GET /me/daily-job/schedule` — Get next scheduled monitor check
- `POST /jobs/daily_doc_run` — Fallback API trigger (requires X-Job-Secret header)
- `GET /me/tasks` — List CPO tasks (optional ?status=open|done|overdue)
- `POST /me/tasks/{id}/complete` — Mark task as done
- `DELETE /me/tasks/{id}` — Remove a task

### Daily Job Output Format
Appended to Google Doc under "CPO Output (Auto)" section:
```
### Daily Recap — YYYY-MM-DD
- Outcome of the day: one sentence (what moved forward, toward what goal)
- What happened (3-7 bullets, 1-2 sentences each)
- Decision made: one decision or proposed decision with reasoning
- Non-core topics: anything mentioned outside the core priority
- Blockers & risks (0-3 bullets)

### Daily CPO Brief — YYYY-MM-DD
- Focus (next 14 days): 2-3 sentences with reasoning
- Next action: ONE executable action with reason
- One metric to watch: metric + why it matters
- Kill list (today): max 3 items with reasoning
- Non-core topics: acknowledged but separated
- Task status (if tasks exist): overdue/upcoming reminders
- One question for founder: question + why it matters
```

### CPO Recap Output Format (Customer-Facing)
Appended daily to the Recap Doc at the configured time (default 6 PM):
```
### CPO Recap — YYYY-MM-DD HH:MM TZ
- What shipped or improved (2-5 bullets)
- What's coming next (1-3 bullets)
- Highlight of the day (1 line)
```

### "Dear CPO" Trigger
The founder writes "Dear CPO" anywhere in their source Google Doc followed by their message. No special headings or structure required — just natural writing. The AI CPO scans the entire doc for "Dear CPO" entries (case-insensitive) and extracts all messages up to the next "Dear CPO" or CPO output heading.

### Always-On Monitoring
The AI CPO monitors the source Google Doc via APScheduler (default every 30 minutes, configurable 5min–24hr). When new "Dear CPO" messages are detected (via SHA-256 content hash comparison), it automatically generates a Recap + CPO Brief and appends them to the output doc. No manual triggers needed — the founder just writes "Dear CPO" and the AI handles the rest.

### Running
```
python -m uvicorn app.main:app --host 0.0.0.0 --port 5000 --reload
```

## User Preferences
- Product: The Six SaaS
- Wants AI CPO to operate autonomously as C-suite Chief Product Officer
- MVP focus: Daily automated Google Doc processing
- User credentials: founder@thesixsaas.com
