from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    Date,
    ForeignKey,
    MetaData,
    Table,
    create_engine,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.sql import select
from datetime import datetime


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DB_PATH = DATA_DIR / "healthcare.db"


def get_engine(echo: bool = False) -> Engine:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{DB_PATH}", echo=echo, future=True)
    return engine


metadata = MetaData()

locations = Table(
    "locations",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(128), nullable=False, unique=True),
    Column("region", String(64), nullable=True),
)

location_geo = Table(
    "location_geo",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("location_id", Integer, ForeignKey("locations.id"), nullable=False, unique=True),
    Column("lat", Float, nullable=False),
    Column("lon", Float, nullable=False),
)

items = Table(
    "items",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(128), nullable=False, unique=True),
    Column("min_stock", Integer, nullable=False, default=0),
    Column("cost_thb", Integer, nullable=False, default=0),
)

inventory = Table(
    "inventory",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("location_id", Integer, ForeignKey("locations.id"), nullable=False),
    Column("item_id", Integer, ForeignKey("items.id"), nullable=False),
    Column("current_stock", Integer, nullable=False, default=0),
)

suppliers = Table(
    "suppliers",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(128), nullable=False, unique=True),
)

supplier_metrics = Table(
    "supplier_metrics",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("supplier_id", Integer, ForeignKey("suppliers.id"), nullable=False),
    Column("on_time_pct", Float, nullable=False),
    Column("defect_rate_pct", Float, nullable=False),
    Column("lead_time_days", Float, nullable=False),
    Column("performance_score", Float, nullable=False),
)

orders = Table(
    "orders",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("created_at", DateTime, nullable=False, default=datetime.utcnow),
    Column("location_id", Integer, ForeignKey("locations.id"), nullable=False),
    Column("approver", String(64), nullable=True),
    Column("urgent", Boolean, nullable=False, default=False),
)

order_lines = Table(
    "order_lines",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("order_id", Integer, ForeignKey("orders.id"), nullable=False),
    Column("item_id", Integer, ForeignKey("items.id"), nullable=False),
    Column("qty", Integer, nullable=False),
)


# POCT HbA1c testing history (for 12 months+)
poct_tests = Table(
    "poct_tests",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("location_id", Integer, ForeignKey("locations.id"), nullable=False),
    Column("test_date", Date, nullable=False),
    Column("hba1c_result", Float, nullable=True),
)


def init_db(engine: Optional[Engine] = None) -> None:
    if engine is None:
        engine = get_engine()
    metadata.create_all(engine)


def is_seeded(engine: Optional[Engine] = None) -> bool:
    if engine is None:
        engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(text("SELECT COUNT(1) FROM items"))
        count = result.scalar_one()
        return count > 0



