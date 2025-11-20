"""Database models for EPD Compliance Risk Screener"""

from datetime import datetime
from typing import Optional
from sqlalchemy import Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import db


class Scan(db.Model):
    __tablename__ = "scans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    source: Mapped[Optional[str]] = mapped_column(String(64), default="local_index", nullable=True)
    input_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    high_risk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    medium_risk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    low_risk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    results: Mapped[list["ScanResult"]] = relationship(
        back_populates="scan", cascade="all, delete-orphan"
    )


class ScanResult(db.Model):
    __tablename__ = "scan_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("scans.id"), nullable=False)

    # Input identifiers
    input_product_id: Mapped[str] = mapped_column(String(128), nullable=False)

    # Basic product snapshot (for report reproducibility)
    product_name: Mapped[Optional[str]] = mapped_column(String(512))
    manufacturer_name: Mapped[Optional[str]] = mapped_column(String(256))

    # EPD-related raw fields used by rule engine
    epd_url: Mapped[Optional[str]] = mapped_column(Text)
    epd_issue_date: Mapped[Optional[str]] = mapped_column(String(64))

    # Risk evaluation
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)  # Red/Yellow/Green
    reasons: Mapped[str] = mapped_column(Text, nullable=False)  # JSON-encoded list of strings
    advisories: Mapped[str] = mapped_column(Text, nullable=True)  # JSON-encoded list of strings

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    scan: Mapped[Scan] = relationship(back_populates="results")


