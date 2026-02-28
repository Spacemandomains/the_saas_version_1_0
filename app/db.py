from __future__ import annotations

import os
from datetime import datetime
from typing import Generator

from sqlalchemy import create_engine, String, Text, DateTime, Integer, Boolean, ForeignKey
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Mapped, mapped_column, relationship

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./ai_cpo.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    logo_url: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    members: Mapped[list["User"]] = relationship("User", back_populates="company")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    api_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    first_name: Mapped[str] = mapped_column(String(100), default="")
    role: Mapped[str] = mapped_column(String(50), default="CEO")
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    company: Mapped["Company"] = relationship("Company", back_populates="members")
    product_brief: Mapped["ProductBrief"] = relationship(
        "ProductBrief", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    icp_profile: Mapped["ICPProfile"] = relationship(
        "ICPProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    pmf_signals: Mapped[list["PMFSignal"]] = relationship(
        "PMFSignal", back_populates="user", cascade="all, delete-orphan"
    )
    metrics_snapshots: Mapped[list["MetricsSnapshot"]] = relationship(
        "MetricsSnapshot", back_populates="user", cascade="all, delete-orphan"
    )
    docs: Mapped[list["GeneratedDoc"]] = relationship(
        "GeneratedDoc", back_populates="user", cascade="all, delete-orphan"
    )
    cpo_tasks: Mapped[list["CPOTask"]] = relationship(
        "CPOTask", back_populates="user", cascade="all, delete-orphan"
    )
    daily_job_config: Mapped["DailyJobConfig"] = relationship(
        "DailyJobConfig", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class ProductBrief(Base):
    __tablename__ = "product_briefs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    content: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped[User] = relationship("User", back_populates="product_brief")


class ICPProfile(Base):
    __tablename__ = "icp_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    target_market: Mapped[str] = mapped_column(Text, default="")
    customer_segments: Mapped[str] = mapped_column(Text, default="")
    pain_points: Mapped[str] = mapped_column(Text, default="")
    value_proposition: Mapped[str] = mapped_column(Text, default="")
    differentiators: Mapped[str] = mapped_column(Text, default="")
    pricing_model: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped[User] = relationship("User", back_populates="icp_profile")


class PMFSignal(Base):
    __tablename__ = "pmf_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    signal_type: Mapped[str] = mapped_column(String(50))
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(200), default="")
    sentiment: Mapped[str] = mapped_column(String(20), default="neutral")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped[User] = relationship("User", back_populates="pmf_signals")


class MetricsSnapshot(Base):
    __tablename__ = "metrics_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    period: Mapped[str] = mapped_column(String(50))
    activation_rate: Mapped[str] = mapped_column(String(50), default="")
    retention_rate: Mapped[str] = mapped_column(String(50), default="")
    churn_rate: Mapped[str] = mapped_column(String(50), default="")
    revenue: Mapped[str] = mapped_column(String(100), default="")
    mrr: Mapped[str] = mapped_column(String(100), default="")
    active_users: Mapped[str] = mapped_column(String(50), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped[User] = relationship("User", back_populates="metrics_snapshots")


class DailyJobConfig(Base):
    __tablename__ = "daily_job_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    google_doc_id: Mapped[str] = mapped_column(String(200), default="")
    output_doc_id: Mapped[str] = mapped_column(String(200), default="")
    recap_doc_id: Mapped[str] = mapped_column(String(200), default="")
    recap_time: Mapped[str] = mapped_column(String(5), default="18:00")
    last_recap_date: Mapped[str] = mapped_column(String(10), default="")
    ai_cpo_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    last_run_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    last_run_date: Mapped[str] = mapped_column(String(10), default="")
    last_notes_hash: Mapped[str] = mapped_column(String(64), default="")
    last_doc_revision: Mapped[str] = mapped_column(String(200), default="")
    poll_interval_minutes: Mapped[int] = mapped_column(Integer, default=30)
    last_checked_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    timezone: Mapped[str] = mapped_column(String(50), default="US/Eastern")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped[User] = relationship("User", back_populates="daily_job_config")


class GeneratedDoc(Base):
    __tablename__ = "generated_docs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    agent: Mapped[str] = mapped_column(String(20), default="cpo", server_default="cpo")
    doc_type: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(200))
    content_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped[User] = relationship("User", back_populates="docs")


class CPOTask(Base):
    __tablename__ = "cpo_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    details: Mapped[str] = mapped_column(Text, default="")
    due_date: Mapped[str] = mapped_column(String(10), default="")
    status: Mapped[str] = mapped_column(String(20), default="open")
    source_text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    user: Mapped[User] = relationship("User", back_populates="cpo_tasks")


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        from sqlalchemy import text, inspect
        insp = inspect(engine)
        cols = [c["name"] for c in insp.get_columns("daily_job_configs")]
        if "recap_doc_id" not in cols:
            conn.execute(text("ALTER TABLE daily_job_configs ADD COLUMN recap_doc_id VARCHAR(200) DEFAULT ''"))
        if "recap_time" not in cols:
            conn.execute(text("ALTER TABLE daily_job_configs ADD COLUMN recap_time VARCHAR(5) DEFAULT '18:00'"))
        if "last_recap_date" not in cols:
            conn.execute(text("ALTER TABLE daily_job_configs ADD COLUMN last_recap_date VARCHAR(10) DEFAULT ''"))
        conn.commit()


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
