from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.auth import (
    get_user_by_api_key,
    hash_password,
    new_api_key,
    require_api_key,
    verify_password,
)
from app.cpo_agent import CPOAgent
from app.db import (
    CPOTask, Company, DailyJobConfig, GeneratedDoc, ICPProfile, MetricsSnapshot, PMFSignal,
    ProductBrief, User, get_db, init_db,
)
from app.daily_job import run_daily_job

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = REPO_ROOT / "templates"
MEMORY_PRODUCT_BRIEF = REPO_ROOT / "memory" / "product_brief.md"

app = FastAPI(title="AI CPO Agent (Gemini) MVP", version="0.2.0")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

_agent: Optional[CPOAgent] = None

DOC_TYPES = "prd|roadmap|sprint|recap|feature_spec|user_stories|technical_handoff|release_notes|strategy_memo"


def get_agent() -> CPOAgent:
    global _agent
    if _agent is None:
        _agent = CPOAgent()
    return _agent


def default_product_brief() -> str:
    if MEMORY_PRODUCT_BRIEF.exists():
        return MEMORY_PRODUCT_BRIEF.read_text(encoding="utf-8")
    return "Describe your SaaS (ICP, value prop, pricing, users, workflows, success metrics)."


def build_context(user: User, db: Session) -> Dict[str, Any]:
    ctx: Dict[str, Any] = {}
    if user.icp_profile:
        icp = user.icp_profile
        ctx["icp"] = {
            "target_market": icp.target_market,
            "customer_segments": icp.customer_segments,
            "pain_points": icp.pain_points,
            "value_proposition": icp.value_proposition,
            "differentiators": icp.differentiators,
            "pricing_model": icp.pricing_model,
        }
    signals = (
        db.query(PMFSignal)
        .filter(PMFSignal.user_id == user.id)
        .order_by(PMFSignal.created_at.desc())
        .limit(20)
        .all()
    )
    if signals:
        ctx["pmf_signals"] = [
            {"type": s.signal_type, "content": s.content, "source": s.source, "sentiment": s.sentiment}
            for s in signals
        ]
    snapshots = (
        db.query(MetricsSnapshot)
        .filter(MetricsSnapshot.user_id == user.id)
        .order_by(MetricsSnapshot.created_at.desc())
        .limit(6)
        .all()
    )
    if snapshots:
        ctx["metrics"] = [
            {
                "period": m.period,
                "activation_rate": m.activation_rate,
                "retention_rate": m.retention_rate,
                "churn_rate": m.churn_rate,
                "revenue": m.revenue,
                "mrr": m.mrr,
                "active_users": m.active_users,
                "notes": m.notes,
            }
            for m in snapshots
        ]
    return ctx


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    TEMPLATES_DIR.mkdir(exist_ok=True)

    from app.scheduler import start_scheduler
    start_scheduler()


@app.on_event("shutdown")
def on_shutdown() -> None:
    from app.scheduler import stop_scheduler
    stop_scheduler()


def _html_response(request: Request, template: str, ctx: dict = None):
    context = {"request": request}
    if ctx:
        context.update(ctx)
    resp = templates.TemplateResponse(template, context)
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return RedirectResponse(url="/app/agents", status_code=302)


@app.get("/app/agents", response_class=HTMLResponse)
def page_agents(request: Request):
    return _html_response(request, "agents.html")


@app.get("/app/auth", response_class=HTMLResponse)
def page_auth(request: Request):
    return _html_response(request, "auth.html")


@app.get("/app/dashboard", response_class=HTMLResponse)
def page_dashboard(request: Request):
    return _html_response(request, "dashboard.html")


@app.get("/app/generate", response_class=HTMLResponse)
def page_generate(request: Request):
    return _html_response(request, "generate.html")


@app.get("/app/documents", response_class=HTMLResponse)
def page_documents(request: Request):
    return _html_response(request, "documents.html")


@app.get("/app/documents/{doc_id}", response_class=HTMLResponse)
def page_document_detail(request: Request, doc_id: int):
    return _html_response(request, "document_detail.html", {"doc_id": doc_id})


@app.get("/app/brief", response_class=HTMLResponse)
def page_brief(request: Request):
    return _html_response(request, "brief.html")


@app.get("/app/icp", response_class=HTMLResponse)
def page_icp(request: Request):
    return _html_response(request, "icp.html")


@app.get("/app/pmf", response_class=HTMLResponse)
def page_pmf(request: Request):
    return _html_response(request, "pmf.html")


@app.get("/app/metrics", response_class=HTMLResponse)
def page_metrics(request: Request):
    return _html_response(request, "metrics.html")


# -----------------------
# Auth
# -----------------------

class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    first_name: str = Field(default="", max_length=100)
    company_name: str = Field(default="", max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


def _user_profile(user: User) -> dict:
    tz = "US/Eastern"
    if user.daily_job_config:
        tz = user.daily_job_config.timezone or "US/Eastern"
    return {
        "api_key": user.api_key,
        "first_name": user.first_name or "",
        "role": user.role or "CEO",
        "email": user.email,
        "company_name": user.company.name if user.company else "",
        "company_logo": user.company.logo_url if user.company else "",
        "timezone": tz,
    }


@app.post("/auth/signup")
def signup(payload: SignupRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        if existing.first_name == "" and existing.company_id is not None:
            existing.password_hash = hash_password(payload.password)
            existing.api_key = new_api_key()
            existing.first_name = payload.first_name.strip()
            db.commit()
            return _user_profile(existing)
        raise HTTPException(status_code=400, detail="Email already registered")

    company = None
    if payload.company_name.strip():
        company = Company(name=payload.company_name.strip(), created_at=datetime.utcnow())
        db.add(company)
        db.flush()

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        api_key=new_api_key(),
        first_name=payload.first_name.strip(),
        role="CEO",
        company_id=company.id if company else None,
        created_at=datetime.utcnow(),
    )
    db.add(user)
    db.flush()

    db.add(
        ProductBrief(
            user_id=user.id,
            content=default_product_brief(),
            updated_at=datetime.utcnow(),
        )
    )
    db.commit()

    return _user_profile(user)


@app.post("/auth/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return _user_profile(user)


# -----------------------
# Product brief
# -----------------------

class ProductBriefUpsert(BaseModel):
    content: str = Field(min_length=20)


@app.get("/me/product-brief")
def get_product_brief(api_key: str = Depends(require_api_key), db: Session = Depends(get_db)):
    user = get_user_by_api_key(db, api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")
    content = user.product_brief.content if user.product_brief else default_product_brief()
    return {"content": content}


@app.post("/me/product-brief")
def upsert_product_brief(
    payload: ProductBriefUpsert,
    api_key: str = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    user = get_user_by_api_key(db, api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if user.product_brief:
        user.product_brief.content = payload.content
        user.product_brief.updated_at = datetime.utcnow()
    else:
        db.add(ProductBrief(user_id=user.id, content=payload.content, updated_at=datetime.utcnow()))

    db.commit()
    return {"ok": True}


# -----------------------
# ICP & Value Proposition
# -----------------------

class ICPUpsert(BaseModel):
    target_market: str = ""
    customer_segments: str = ""
    pain_points: str = ""
    value_proposition: str = ""
    differentiators: str = ""
    pricing_model: str = ""


@app.get("/me/icp")
def get_icp(api_key: str = Depends(require_api_key), db: Session = Depends(get_db)):
    user = get_user_by_api_key(db, api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")
    icp = user.icp_profile
    if not icp:
        return {"target_market": "", "customer_segments": "", "pain_points": "",
                "value_proposition": "", "differentiators": "", "pricing_model": ""}
    return {
        "target_market": icp.target_market,
        "customer_segments": icp.customer_segments,
        "pain_points": icp.pain_points,
        "value_proposition": icp.value_proposition,
        "differentiators": icp.differentiators,
        "pricing_model": icp.pricing_model,
    }


@app.post("/me/icp")
def upsert_icp(
    payload: ICPUpsert,
    api_key: str = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    user = get_user_by_api_key(db, api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if user.icp_profile:
        for field in ["target_market", "customer_segments", "pain_points",
                       "value_proposition", "differentiators", "pricing_model"]:
            setattr(user.icp_profile, field, getattr(payload, field))
        user.icp_profile.updated_at = datetime.utcnow()
    else:
        db.add(ICPProfile(
            user_id=user.id,
            target_market=payload.target_market,
            customer_segments=payload.customer_segments,
            pain_points=payload.pain_points,
            value_proposition=payload.value_proposition,
            differentiators=payload.differentiators,
            pricing_model=payload.pricing_model,
            updated_at=datetime.utcnow(),
        ))
    db.commit()
    return {"ok": True}


# -----------------------
# PMF Signals
# -----------------------

class PMFSignalCreate(BaseModel):
    signal_type: str = Field(pattern="^(feedback|metric|pattern|interview|support|other)$")
    content: str = Field(min_length=5)
    source: str = ""
    sentiment: str = Field(default="neutral", pattern="^(positive|negative|neutral)$")


@app.get("/me/pmf-signals")
def list_pmf_signals(api_key: str = Depends(require_api_key), db: Session = Depends(get_db)):
    user = get_user_by_api_key(db, api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")
    rows = (
        db.query(PMFSignal)
        .filter(PMFSignal.user_id == user.id)
        .order_by(PMFSignal.created_at.desc())
        .limit(50)
        .all()
    )
    return [
        {"id": r.id, "signal_type": r.signal_type, "content": r.content,
         "source": r.source, "sentiment": r.sentiment, "created_at": r.created_at.isoformat()}
        for r in rows
    ]


@app.post("/me/pmf-signals")
def add_pmf_signal(
    payload: PMFSignalCreate,
    api_key: str = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    user = get_user_by_api_key(db, api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")
    signal = PMFSignal(
        user_id=user.id,
        signal_type=payload.signal_type,
        content=payload.content,
        source=payload.source,
        sentiment=payload.sentiment,
        created_at=datetime.utcnow(),
    )
    db.add(signal)
    db.commit()
    return {"id": signal.id, "ok": True}


@app.delete("/me/pmf-signals/{signal_id}")
def delete_pmf_signal(
    signal_id: int,
    api_key: str = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    user = get_user_by_api_key(db, api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")
    row = db.query(PMFSignal).filter(PMFSignal.id == signal_id, PMFSignal.user_id == user.id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Signal not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


# -----------------------
# Metrics
# -----------------------

class MetricsCreate(BaseModel):
    period: str = Field(min_length=1)
    activation_rate: str = ""
    retention_rate: str = ""
    churn_rate: str = ""
    revenue: str = ""
    mrr: str = ""
    active_users: str = ""
    notes: str = ""


@app.get("/me/metrics")
def list_metrics(api_key: str = Depends(require_api_key), db: Session = Depends(get_db)):
    user = get_user_by_api_key(db, api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")
    rows = (
        db.query(MetricsSnapshot)
        .filter(MetricsSnapshot.user_id == user.id)
        .order_by(MetricsSnapshot.created_at.desc())
        .limit(24)
        .all()
    )
    return [
        {"id": r.id, "period": r.period, "activation_rate": r.activation_rate,
         "retention_rate": r.retention_rate, "churn_rate": r.churn_rate,
         "revenue": r.revenue, "mrr": r.mrr, "active_users": r.active_users,
         "notes": r.notes, "created_at": r.created_at.isoformat()}
        for r in rows
    ]


@app.post("/me/metrics")
def add_metrics(
    payload: MetricsCreate,
    api_key: str = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    user = get_user_by_api_key(db, api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")
    snap = MetricsSnapshot(
        user_id=user.id,
        period=payload.period,
        activation_rate=payload.activation_rate,
        retention_rate=payload.retention_rate,
        churn_rate=payload.churn_rate,
        revenue=payload.revenue,
        mrr=payload.mrr,
        active_users=payload.active_users,
        notes=payload.notes,
        created_at=datetime.utcnow(),
    )
    db.add(snap)
    db.commit()
    return {"id": snap.id, "ok": True}


@app.delete("/me/metrics/{metric_id}")
def delete_metrics(
    metric_id: int,
    api_key: str = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    user = get_user_by_api_key(db, api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")
    row = db.query(MetricsSnapshot).filter(MetricsSnapshot.id == metric_id, MetricsSnapshot.user_id == user.id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Metric not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


@app.post("/api/metrics/insights")
def metrics_insights(
    api_key: str = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    user = get_user_by_api_key(db, api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")

    product_brief = user.product_brief.content if user.product_brief else default_product_brief()
    ctx = build_context(user, db)

    metrics_data = ctx.get("metrics", [])
    pmf_data = ctx.get("pmf_signals", [])

    if not metrics_data and not pmf_data:
        raise HTTPException(status_code=400, detail="Add metrics or PMF signals first to get AI insights")

    try:
        result = get_agent().analyze_metrics(
            product_brief=product_brief,
            metrics=metrics_data,
            pmf_signals=pmf_data,
            context=ctx,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis error: {str(e)}")


# -----------------------
# Agent API
# -----------------------

class AgentRequest(BaseModel):
    doc_type: str = Field(pattern=f"^({DOC_TYPES})$")
    title: Optional[str] = None
    inputs: Dict[str, Any] = Field(default_factory=dict)
    export_to_gdoc: bool = False
    gdoc_document_id: Optional[str] = None


@app.post("/api/agent")
def api_agent(
    payload: AgentRequest,
    api_key: str = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    user = get_user_by_api_key(db, api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")

    product_brief = user.product_brief.content if user.product_brief else default_product_brief()
    title = payload.title or f"{payload.doc_type.upper()} generated"
    context = build_context(user, db)

    try:
        output = get_agent().generate(
            doc_type=payload.doc_type,
            product_brief=product_brief,
            inputs=payload.inputs,
            context=context,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")

    doc = GeneratedDoc(
        user_id=user.id,
        doc_type=payload.doc_type,
        title=title,
        content_json=json.dumps(output, ensure_ascii=False),
        created_at=datetime.utcnow(),
    )
    db.add(doc)
    db.commit()

    result: Dict[str, Any] = {"doc_type": payload.doc_type, "title": title, "output": output}

    if payload.export_to_gdoc:
        try:
            from app.google_docs import create_and_write, append_to_document, format_doc_content
            text_content = format_doc_content(payload.doc_type, title, output)
            if payload.gdoc_document_id:
                gdoc = append_to_document(payload.gdoc_document_id, text_content)
            else:
                gdoc = create_and_write(title, text_content)
            result["google_doc"] = gdoc
        except Exception as e:
            result["google_doc_error"] = str(e)

    return result


# -----------------------
# Executive Challenge
# -----------------------

class ChallengeRequest(BaseModel):
    doc_type: str = Field(pattern=f"^({DOC_TYPES})$")
    inputs: Dict[str, Any] = Field(default_factory=dict)


@app.post("/api/challenge")
def api_challenge(
    payload: ChallengeRequest,
    api_key: str = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    user = get_user_by_api_key(db, api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")

    product_brief = user.product_brief.content if user.product_brief else default_product_brief()
    context = build_context(user, db)

    try:
        result = get_agent().challenge(
            doc_type=payload.doc_type,
            product_brief=product_brief,
            inputs=payload.inputs,
            context=context,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Challenge error: {str(e)}")


# -----------------------
# Documents
# -----------------------

@app.get("/me/docs")
def list_docs(agent: str = None, api_key: str = Depends(require_api_key), db: Session = Depends(get_db)):
    user = get_user_by_api_key(db, api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")

    query = db.query(GeneratedDoc).filter(GeneratedDoc.user_id == user.id)
    if agent:
        query = query.filter(GeneratedDoc.agent == agent)
    rows = query.order_by(GeneratedDoc.created_at.desc()).limit(50).all()

    return [
        {
            "id": r.id,
            "agent": getattr(r, "agent", "cpo"),
            "doc_type": r.doc_type,
            "title": r.title,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@app.get("/me/docs/{doc_id}")
def get_doc(doc_id: int, api_key: str = Depends(require_api_key), db: Session = Depends(get_db)):
    user = get_user_by_api_key(db, api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")

    r = db.query(GeneratedDoc).filter(GeneratedDoc.id == doc_id, GeneratedDoc.user_id == user.id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Not found")

    return {
        "id": r.id,
        "doc_type": r.doc_type,
        "title": r.title,
        "created_at": r.created_at.isoformat(),
        "content": json.loads(r.content_json),
    }


# -----------------------
# Google Docs Export
# -----------------------

class ExportRequest(BaseModel):
    doc_id: int
    gdoc_document_id: Optional[str] = None


@app.post("/api/export-gdoc")
def export_to_gdoc(
    payload: ExportRequest,
    api_key: str = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    user = get_user_by_api_key(db, api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")

    r = db.query(GeneratedDoc).filter(
        GeneratedDoc.id == payload.doc_id, GeneratedDoc.user_id == user.id
    ).first()
    if not r:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        from app.google_docs import create_and_write, append_to_document, format_doc_content
        content = json.loads(r.content_json)
        text_content = format_doc_content(r.doc_type, r.title, content)
        if payload.gdoc_document_id:
            gdoc = append_to_document(payload.gdoc_document_id, text_content)
        else:
            gdoc = create_and_write(r.title, text_content)
        return gdoc
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


# -----------------------
# Profile & Company
# -----------------------

class ProfileUpdate(BaseModel):
    first_name: Optional[str] = None
    company_name: Optional[str] = None
    company_logo: Optional[str] = None
    timezone: Optional[str] = None


@app.get("/me/profile")
def get_profile(api_key: str = Depends(require_api_key), db: Session = Depends(get_db)):
    user = get_user_by_api_key(db, api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return _user_profile(user)


@app.post("/me/profile")
def update_profile(
    payload: ProfileUpdate,
    api_key: str = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    user = get_user_by_api_key(db, api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if payload.first_name is not None:
        user.first_name = payload.first_name.strip()

    if payload.company_name is not None or payload.company_logo is not None:
        if not user.company:
            company = Company(name="", created_at=datetime.utcnow())
            db.add(company)
            db.flush()
            user.company_id = company.id
            user.company = company
        if payload.company_name is not None:
            user.company.name = payload.company_name.strip()
        if payload.company_logo is not None:
            user.company.logo_url = payload.company_logo.strip()

    if payload.timezone is not None:
        from zoneinfo import ZoneInfo
        tz_val = payload.timezone.strip()
        try:
            ZoneInfo(tz_val)
            config = user.daily_job_config
            if not config:
                config = DailyJobConfig(user_id=user.id)
                db.add(config)
                db.flush()
            config.timezone = tz_val
        except Exception:
            raise HTTPException(status_code=400, detail=f"Invalid timezone: {tz_val}")

    db.commit()
    return _user_profile(user)


@app.get("/me/team")
def get_team(api_key: str = Depends(require_api_key), db: Session = Depends(get_db)):
    user = get_user_by_api_key(db, api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")
    if not user.company:
        return {"members": []}
    members = db.query(User).filter(User.company_id == user.company_id).all()
    return {
        "members": [
            {"id": m.id, "email": m.email, "first_name": m.first_name, "role": m.role}
            for m in members
        ]
    }


class InviteRequest(BaseModel):
    email: EmailStr
    role: str = Field(default="Co-Founder", pattern="^(Co-Founder|Advisor|Team Member)$")


@app.post("/me/team/invite")
def invite_cofounder(
    payload: InviteRequest,
    api_key: str = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    user = get_user_by_api_key(db, api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if not user.company:
        company = Company(name="", created_at=datetime.utcnow())
        db.add(company)
        db.flush()
        user.company_id = company.id
        db.commit()

    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        if existing.company_id == user.company_id:
            raise HTTPException(status_code=400, detail="This person is already on your team.")
        existing.company_id = user.company_id
        existing.role = payload.role
        db.commit()
        return {"ok": True, "message": f"{payload.email} added to your team as {payload.role}."}

    invited_user = User(
        email=payload.email,
        password_hash=hash_password(new_api_key()[:16]),
        api_key=new_api_key(),
        first_name="",
        role=payload.role,
        company_id=user.company_id,
        created_at=datetime.utcnow(),
    )
    db.add(invited_user)
    db.flush()
    db.add(ProductBrief(user_id=invited_user.id, content=default_product_brief(), updated_at=datetime.utcnow()))
    db.commit()
    return {"ok": True, "message": f"Added {payload.email} as {payload.role}. They will appear on your team once they sign up with that email."}


@app.delete("/me/team/{member_id}")
def remove_team_member(
    member_id: int,
    api_key: str = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    user = get_user_by_api_key(db, api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")
    if user.role != "CEO":
        raise HTTPException(status_code=403, detail="Only the CEO can remove team members.")
    if member_id == user.id:
        raise HTTPException(status_code=400, detail="You cannot remove yourself.")
    member = db.query(User).filter(User.id == member_id, User.company_id == user.company_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Team member not found.")
    member.company_id = None
    db.commit()
    return {"ok": True}


# -----------------------
# Daily Job
# -----------------------

import hmac
import logging
logger = logging.getLogger("daily_job")
logging.basicConfig(level=logging.INFO)


def _extract_bearer_token(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return ""


@app.post("/jobs/daily_doc_run")
def daily_doc_run(request: Request, db: Session = Depends(get_db)):
    job_secret = os.getenv("JOB_SECRET", "")
    provided_secret = _extract_bearer_token(request)
    if not job_secret or not hmac.compare_digest(provided_secret, job_secret):
        raise HTTPException(status_code=403, detail="Invalid or missing Authorization: Bearer <secret> header")

    configs = db.query(DailyJobConfig).filter(DailyJobConfig.ai_cpo_enabled == True).all()
    if not configs:
        return {"status": "no_active_users", "message": "No users have AI CPO enabled."}

    results = []
    agent = get_agent()
    for config in configs:
        user = config.user
        try:
            result = run_daily_job(user, db, agent)
            results.append({"user_id": user.id, **result})
        except Exception as e:
            logger.error(f"Daily job failed for user {user.id}: {e}")
            results.append({"user_id": user.id, "status": "error", "message": str(e)})

    return {"results": results}


# -----------------------
# Daily Job Settings (User)
# -----------------------

class DailyJobSettingsUpdate(BaseModel):
    google_doc_id: Optional[str] = None
    output_doc_id: Optional[str] = None
    recap_doc_id: Optional[str] = None
    recap_time: Optional[str] = None
    ai_cpo_enabled: Optional[bool] = None
    poll_interval_minutes: Optional[int] = None
    timezone: Optional[str] = None


@app.get("/me/daily-job")
def get_daily_job_settings(api_key: str = Depends(require_api_key), db: Session = Depends(get_db)):
    user = get_user_by_api_key(db, api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")
    config = user.daily_job_config
    if not config:
        return {"google_doc_id": "", "output_doc_id": "", "recap_doc_id": "", "recap_time": "18:00", "ai_cpo_enabled": False, "last_run_at": None, "last_run_display": "", "last_run_date": "", "poll_interval_minutes": 30, "timezone": "US/Eastern"}
    from zoneinfo import ZoneInfo
    tz_name = config.timezone or "US/Eastern"
    try:
        user_tz = ZoneInfo(tz_name)
    except Exception:
        user_tz = ZoneInfo("US/Eastern")
    last_run_display = ""
    if config.last_run_at:
        utc_time = config.last_run_at.replace(tzinfo=ZoneInfo("UTC")) if config.last_run_at.tzinfo is None else config.last_run_at
        local_time = utc_time.astimezone(user_tz)
        tz_abbr = local_time.strftime("%Z") or tz_name
        last_run_display = local_time.strftime("%b %d, %Y at %I:%M %p") + " " + tz_abbr
    return {
        "google_doc_id": config.google_doc_id or "",
        "output_doc_id": config.output_doc_id or "",
        "recap_doc_id": config.recap_doc_id or "",
        "recap_time": config.recap_time or "18:00",
        "ai_cpo_enabled": config.ai_cpo_enabled,
        "last_run_at": config.last_run_at.isoformat() if config.last_run_at else None,
        "last_run_display": last_run_display,
        "last_run_date": config.last_run_date or "",
        "poll_interval_minutes": config.poll_interval_minutes or 30,
        "timezone": config.timezone or "US/Eastern",
    }


@app.post("/me/daily-job")
def update_daily_job_settings(
    payload: DailyJobSettingsUpdate,
    api_key: str = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    user = get_user_by_api_key(db, api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")

    config = user.daily_job_config
    if not config:
        config = DailyJobConfig(user_id=user.id, updated_at=datetime.utcnow())
        db.add(config)

    import re as _re

    if payload.google_doc_id is not None:
        doc_id = payload.google_doc_id.strip()
        match = _re.search(r"/document/d/([a-zA-Z0-9_-]+)", doc_id)
        if match:
            doc_id = match.group(1)
        config.google_doc_id = doc_id

    if payload.output_doc_id is not None:
        out_id = payload.output_doc_id.strip()
        match = _re.search(r"/document/d/([a-zA-Z0-9_-]+)", out_id)
        if match:
            out_id = match.group(1)
        config.output_doc_id = out_id

    if payload.recap_doc_id is not None:
        recap_id = payload.recap_doc_id.strip()
        match = _re.search(r"/document/d/([a-zA-Z0-9_-]+)", recap_id)
        if match:
            recap_id = match.group(1)
        config.recap_doc_id = recap_id

    if payload.recap_time is not None:
        rt = payload.recap_time.strip()
        if _re.match(r"^\d{1,2}:\d{2}$", rt):
            parts = rt.split(":")
            h, m = int(parts[0]), int(parts[1])
            if 0 <= h <= 23 and 0 <= m <= 59:
                config.recap_time = f"{h:02d}:{m:02d}"

    if payload.ai_cpo_enabled is not None:
        config.ai_cpo_enabled = payload.ai_cpo_enabled

    if payload.poll_interval_minutes is not None:
        val = max(5, min(1440, payload.poll_interval_minutes))
        config.poll_interval_minutes = val

    if payload.timezone is not None:
        from zoneinfo import ZoneInfo
        tz_val = payload.timezone.strip()
        try:
            ZoneInfo(tz_val)
            config.timezone = tz_val
        except Exception:
            raise HTTPException(status_code=400, detail=f"Invalid timezone: {tz_val}")

    config.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "google_doc_id": config.google_doc_id, "output_doc_id": config.output_doc_id, "recap_doc_id": config.recap_doc_id, "recap_time": config.recap_time, "ai_cpo_enabled": config.ai_cpo_enabled, "poll_interval_minutes": config.poll_interval_minutes, "timezone": config.timezone}


@app.post("/me/daily-job/run-now")
def run_daily_job_manual(
    api_key: str = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    user = get_user_by_api_key(db, api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")

    config = user.daily_job_config
    if not config or not config.google_doc_id:
        raise HTTPException(status_code=400, detail="Configure your Google Doc ID first.")

    if not config.ai_cpo_enabled:
        config.ai_cpo_enabled = True
        db.commit()

    try:
        result = run_daily_job(user, db, get_agent())
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Daily job failed: {str(e)}")


@app.get("/me/daily-job/schedule")
def get_daily_job_schedule(api_key: str = Depends(require_api_key), db: Session = Depends(get_db)):
    user = get_user_by_api_key(db, api_key)
    config = user.daily_job_config if user else None
    user_interval = config.poll_interval_minutes if config and config.poll_interval_minutes else 30
    from zoneinfo import ZoneInfo
    tz_name = (config.timezone if config and config.timezone else None) or "US/Eastern"
    try:
        user_tz = ZoneInfo(tz_name)
    except Exception:
        user_tz = ZoneInfo("US/Eastern")
    next_check = ""
    if config and config.last_checked_at:
        from datetime import timedelta, timezone
        last = config.last_checked_at.replace(tzinfo=timezone.utc) if config.last_checked_at.tzinfo is None else config.last_checked_at
        nxt = last + timedelta(minutes=user_interval)
        now = datetime.now(timezone.utc)
        if nxt < now:
            next_check = "Next tick"
        else:
            local_nxt = nxt.astimezone(user_tz)
            tz_abbr = local_nxt.strftime("%Z") or tz_name
            next_check = local_nxt.strftime("%b %d at %I:%M %p") + " " + tz_abbr
    else:
        next_check = "Next tick"
    return {
        "mode": "monitoring",
        "user_interval_minutes": user_interval,
        "next_run": next_check,
        "timezone": tz_name,
    }


@app.get("/me/tasks")
def get_tasks(
    status: Optional[str] = None,
    api_key: str = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    user = get_user_by_api_key(db, api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")
    query = db.query(CPOTask).filter(CPOTask.user_id == user.id)
    if status:
        query = query.filter(CPOTask.status == status)
    tasks = query.order_by(CPOTask.created_at.desc()).all()
    return [
        {
            "id": t.id,
            "title": t.title,
            "details": t.details,
            "due_date": t.due_date or "",
            "status": t.status,
            "source_text": t.source_text,
            "created_at": t.created_at.isoformat() if t.created_at else "",
            "completed_at": t.completed_at.isoformat() if t.completed_at else "",
        }
        for t in tasks
    ]


@app.post("/me/tasks/{task_id}/complete")
def complete_task(
    task_id: int,
    api_key: str = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    user = get_user_by_api_key(db, api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")
    task = db.query(CPOTask).filter(CPOTask.id == task_id, CPOTask.user_id == user.id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.status = "done"
    task.completed_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "id": task.id, "status": "done"}


@app.delete("/me/tasks/{task_id}")
def delete_task(
    task_id: int,
    api_key: str = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    user = get_user_by_api_key(db, api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")
    task = db.query(CPOTask).filter(CPOTask.id == task_id, CPOTask.user_id == user.id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    db.delete(task)
    db.commit()
    return {"ok": True, "id": task_id}


@app.get("/app/guide", response_class=HTMLResponse)
def page_guide(request: Request):
    return _html_response(request, "guide.html")


@app.get("/app/settings", response_class=HTMLResponse)
def page_settings(request: Request):
    return _html_response(request, "settings.html")


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "5000"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
