from __future__ import annotations

from typing import List, Dict
import numpy as np
from faker import Faker
from sqlalchemy import insert, select, func

from .db import (
    get_engine,
    init_db,
    locations,
    location_geo,
    items,
    inventory,
    suppliers,
    supplier_metrics,
    poct_tests,
)


fake = Faker()


def seed_core(seed: int = 42, num_locations: int = 100) -> None:
    rng = np.random.default_rng(seed)
    engine = get_engine()
    init_db(engine)

    with engine.begin() as conn:
        # Locations (seed 100 with coordinates around Thailand)
        base_locations: List[str] = [
            "Bangkok Central",
            "Chiang Mai North",
            "Phuket South",
            "Pattaya East",
            "Khon Kaen Northeast",
            "Hat Yai Deep South",
        ]
        existing = conn.execute(select(func.count()).select_from(locations)).scalar_one()
        if existing == 0:
            # Start from known cities then add synthetic branches
            names: List[str] = base_locations[:]
            while len(names) < num_locations:
                names.append(f"Branch {len(names)+1} - {fake.city()}")
            conn.execute(insert(locations), [{"name": n, "region": None} for n in names])

            # Coordinates roughly within Thailand bbox
            # Lat: 5.6 to 20.5, Lon: 97.4 to 105.6
            loc_rows = conn.execute(select(locations.c.id)).all()
            coords = []
            for (loc_id,) in loc_rows:
                lat = float(np.round(rng.uniform(5.6, 20.5), 6))
                lon = float(np.round(rng.uniform(97.4, 105.6), 6))
                coords.append({"location_id": loc_id, "lat": lat, "lon": lon})
            conn.execute(insert(location_geo), coords)

        # Items
        inventory_items: List[Dict[str, int]] = [
            {"name": "HbA1c Test Strips", "min_stock": 200, "cost_thb": 2500},
            {"name": "Control Solutions", "min_stock": 50, "cost_thb": 150},
            {"name": "Lancets", "min_stock": 500, "cost_thb": 800},
            {"name": "Cartridges", "min_stock": 100, "cost_thb": 1200},
            {"name": "Quality Controls", "min_stock": 75, "cost_thb": 450},
        ]
        existing = conn.execute(select(func.count()).select_from(items)).scalar_one()
        if existing == 0:
            conn.execute(insert(items), inventory_items)

        # Inventory for each location x item
        existing = conn.execute(select(func.count()).select_from(inventory)).scalar_one()
        if existing == 0:
            loc_rows = conn.execute(select(locations.c.id, locations.c.name)).all()
            item_rows = conn.execute(select(items.c.id, items.c.min_stock)).all()
            inv_rows = []
            for loc_id, _ in loc_rows:
                for item_id, min_stock in item_rows:
                    current = int(rng.integers(low=max(0, min_stock - 120), high=min_stock + 300))
                    inv_rows.append({
                        "location_id": loc_id,
                        "item_id": item_id,
                        "current_stock": max(0, current),
                    })
            conn.execute(insert(inventory), inv_rows)

        # Suppliers
        existing = conn.execute(select(func.count()).select_from(suppliers)).scalar_one()
        if existing == 0:
            supplier_rows = [{"name": fake.company()} for _ in range(8)]
            conn.execute(insert(suppliers), supplier_rows)

        # Supplier metrics
        existing = conn.execute(select(func.count()).select_from(supplier_metrics)).scalar_one()
        if existing == 0:
            sup_ids = [r[0] for r in conn.execute(select(suppliers.c.id)).all()]
            metric_rows = []
            for sid in sup_ids:
                on_time = float(np.round(rng.uniform(88, 100), 1))
                defect = float(np.round(rng.uniform(0.2, 2.5), 2))
                lead = float(np.round(rng.uniform(2, 9), 1))
                score = np.clip(0.7 * on_time - 8 * defect - 1.5 * lead + 30, 0, 100)
                metric_rows.append({
                    "supplier_id": sid,
                    "on_time_pct": on_time,
                    "defect_rate_pct": defect,
                    "lead_time_days": lead,
                    "performance_score": float(np.round(score, 1)),
                })
            conn.execute(insert(supplier_metrics), metric_rows)

        # 12 months of POCT HbA1c tests (simulate ~50,000+ tests across 100 locations)
        existing = conn.execute(select(func.count()).select_from(poct_tests)).scalar_one()
        if existing == 0:
            from datetime import date, timedelta
            loc_ids = [r[0] for r in conn.execute(select(locations.c.id)).all()]
            start = date.today().replace(day=1) - timedelta(days=365)
            # Approx 50k tests over a year ~ 137/day
            rows = []
            for loc_id in loc_ids:
                # Average ~1-2 tests per day per location, randomize
                for month_offset in range(0, 12):
                    month_start = (start.replace(day=1) + timedelta(days=30 * month_offset))
                    for d in range(0, 28):
                        if rng.uniform() < 0.5:  # ~14 days active per month per location
                            daily_tests = int(rng.integers(1, 6))  # 1-5 tests
                            for _ in range(daily_tests):
                                result = float(np.round(rng.normal(6.2, 1.0), 2))  # HbA1c ~6.2% +/-
                                rows.append({
                                    "location_id": loc_id,
                                    "test_date": month_start + timedelta(days=d),
                                    "hba1c_result": result,
                                })
            if rows:
                # Insert in chunks to avoid large single statement
                chunk = 5000
                for i in range(0, len(rows), chunk):
                    conn.execute(insert(poct_tests), rows[i : i + chunk])


if __name__ == "__main__":
    seed_core()



