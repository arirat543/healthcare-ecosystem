import time
from dataclasses import dataclass
from typing import List, Dict

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from faker import Faker
from streamlit_autorefresh import st_autorefresh
from sqlalchemy import select, func, insert

from app_core.db import (
    get_engine,
    init_db,
    locations as t_locations,
    items as t_items,
    inventory as t_inventory,
    suppliers as t_suppliers,
    supplier_metrics as t_supplier_metrics,
    orders as t_orders,
    order_lines as t_order_lines,
)
from app_core.seed import seed_core


# ----------------------------
# Page configuration & theme
# ----------------------------
st.set_page_config(
    page_title="POCT HbA1c Supply Chain",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Color palette for a clean healthcare look
PRIMARY_BLUE = "#2563EB"  # Tailwind blue-600
PRIMARY_GREEN = "#10B981"  # emerald-500
LIGHT_BG = "#F8FAFC"  # slate-50
BORDER = "#E2E8F0"  # slate-200

st.markdown(
    f"""
    <style>
    .main {{ background-color: {LIGHT_BG}; }}
    .stMetric label {{ color: #0f172a; font-weight: 600; }}
    .stMetric {{ background: white; border: 1px solid {BORDER}; border-radius: 12px; padding: 8px 12px; }}
    .section-card {{ background: white; border: 1px solid {BORDER}; border-radius: 16px; padding: 16px 16px; }}
    .low-stock {{ color: #b91c1c; font-weight: 700; }}
    </style>
    """,
    unsafe_allow_html=True,
)


# ----------------------------
# Sample data
# ----------------------------
fake = Faker()

locations: List[str] = [
    "Bangkok Central",
    "Chiang Mai North",
    "Phuket South",
    "Pattaya East",
    "Khon Kaen Northeast",
    "Hat Yai Deep South",
]

inventory_items: List[Dict[str, int]] = [
    {"item": "HbA1c Test Strips", "current": 450, "min": 200, "cost": 2500},
    {"item": "Control Solutions", "current": 89, "min": 50, "cost": 150},
    {"item": "Lancets", "current": 1200, "min": 500, "cost": 800},
    {"item": "Cartridges", "current": 67, "min": 100, "cost": 1200},
    {"item": "Quality Controls", "current": 145, "min": 75, "cost": 450},
]


# ----------------------------
# Data generation utilities
# ----------------------------
@st.cache_data(show_spinner=False)
def generate_inventory_df(seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for loc in locations:
        for item in inventory_items:
            current_stock = int(rng.integers(low=max(0, item["min"] - 120), high=item["current"] + 120))
            rows.append(
                {
                    "Location": loc,
                    "Item": item["item"],
                    "Current Stock": max(0, current_stock),
                    "Minimum Required": item["min"],
                    "Cost per Unit (THB)": item["cost"],
                }
            )
    df = pd.DataFrame(rows)
    df["Total Value (THB)"] = df["Current Stock"] * df["Cost per Unit (THB)"]
    df["Below Min"] = df["Current Stock"] < df["Minimum Required"]
    return df


@st.cache_data(show_spinner=False)
def generate_supplier_df(seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    supplier_names = [fake.company() for _ in range(8)]
    df = pd.DataFrame(
        {
            "Supplier": supplier_names,
            "On-time Delivery %": np.round(rng.uniform(88, 100, len(supplier_names)), 1),
            "Defect Rate %": np.round(rng.uniform(0.2, 2.5, len(supplier_names)), 2),
            "Average Lead Time (days)": np.round(rng.uniform(2, 9, len(supplier_names)), 1),
        }
    )
    # Composite score (simple illustrative formula)
    df["Performance Score"] = np.round(
        0.7 * df["On-time Delivery %"] - 8 * df["Defect Rate %"] - 1.5 * df["Average Lead Time (days)"] + 30,
        1,
    ).clip(0, 100)
    return df


@st.cache_data(show_spinner=False)
def generate_forecast_df(inventory_df: pd.DataFrame, seed: int = 99) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    group = inventory_df.groupby("Item")["Current Stock"].sum().reset_index()
    base = group.rename(columns={"Current Stock": "Current Total"})
    base["Predicted Next 30d"] = (base["Current Total"] * rng.uniform(0.9, 1.3, len(base))).astype(int)
    base["Confidence %"] = np.round(rng.uniform(75, 95, len(base)), 1)
    return base


# ----------------------------
# Sidebar controls
# ----------------------------
with st.sidebar:
    st.header("Filters")
    selected_locations = st.multiselect("Locations", options=locations, default=locations)
    refresh_seconds = st.slider("Auto-refresh (seconds)", 0, 60, 15)
    seed = st.number_input("Randomization seed", min_value=1, max_value=10_000, value=42, step=1)

    st.markdown("---")
    st.caption("Tip: Set auto-refresh > 0 to simulate real-time dashboards.")


# Auto-refresh
if refresh_seconds and refresh_seconds > 0:
    st_autorefresh(interval=int(refresh_seconds * 1000), key="supply_chain_autorefresh")


# ----------------------------
# Data prep (filtered)
# ----------------------------
# Ensure DB exists and is seeded
engine = get_engine()
init_db(engine)

from sqlalchemy.exc import OperationalError

try:
    with engine.begin() as conn:
        # Seed if empty
        count_items = conn.execute(select(func.count()).select_from(t_items)).scalar_one()
        if count_items == 0:
            seed_core(seed)

        # Load inventory joined data
        inv_rows = conn.execute(
            select(
                t_locations.c.name.label("Location"),
                t_items.c.name.label("Item"),
                t_inventory.c.current_stock.label("Current Stock"),
                t_items.c.min_stock.label("Minimum Required"),
                t_items.c.cost_thb.label("Cost per Unit (THB)"),
            ).select_from(t_inventory.join(t_locations, t_inventory.c.location_id == t_locations.c.id).join(t_items, t_inventory.c.item_id == t_items.c.id))
        ).mappings().all()

        inv_df = pd.DataFrame(inv_rows)
        inv_df = inv_df[inv_df["Location"].isin(selected_locations)]
        inv_df["Total Value (THB)"] = inv_df["Current Stock"] * inv_df["Cost per Unit (THB)"]
        inv_df["Below Min"] = inv_df["Current Stock"] < inv_df["Minimum Required"]

        # Supplier metrics
        sup_rows = conn.execute(
            select(
                t_suppliers.c.name.label("Supplier"),
                t_supplier_metrics.c.performance_score.label("Performance Score"),
                t_supplier_metrics.c.on_time_pct.label("On-time Delivery %"),
                t_supplier_metrics.c.defect_rate_pct.label("Defect Rate %"),
                t_supplier_metrics.c.lead_time_days.label("Average Lead Time (days)"),
            ).join(t_supplier_metrics, t_supplier_metrics.c.supplier_id == t_suppliers.c.id)
        ).mappings().all()
        supplier_df = pd.DataFrame(sup_rows)
except OperationalError:
    st.error("Database connection error. Please restart the app.")
    st.stop()

forecast_df = generate_forecast_df(inv_df, seed)


# ----------------------------
# KPIs header
# ----------------------------
st.markdown(f"<h2 style='margin-top:0;'>POCT HbA1c Supply Chain</h2>", unsafe_allow_html=True)

total_value_thb = int(inv_df["Total Value (THB)"].sum())
pending_orders = 23  # per spec
supplier_perf = 94.3  # per spec

col1, col2, col3 = st.columns(3)
col1.metric("Inventory Value", f"฿{total_value_thb:,.0f}")
col2.metric("Pending Orders", f"{pending_orders}")
col3.metric("Supplier Performance", f"{supplier_perf:.1f}%")


# ----------------------------
# Inventory section
# ----------------------------
st.markdown("<div class='section-card'>", unsafe_allow_html=True)
st.subheader("Real-time Inventory Levels")

low_stock_df = inv_df[(inv_df["Below Min"])]
low_count = len(low_stock_df)
if low_count:
    st.markdown(f"<span class='low-stock'>Alerts: {low_count} low-stock line items</span>", unsafe_allow_html=True)

fig_inv = px.bar(
    inv_df,
    x="Item",
    y="Current Stock",
    color="Location",
    barmode="group",
    height=420,
    color_discrete_sequence=px.colors.sequential.Blues_r,
)
fig_inv.update_layout(margin=dict(l=10, r=10, t=30, b=10))
st.plotly_chart(fig_inv, use_container_width=True)

with st.expander("View inventory table", expanded=False):
    st.dataframe(
        inv_df.sort_values(["Item", "Location"]).reset_index(drop=True),
        use_container_width=True,
        hide_index=True,
    )
st.markdown("</div>", unsafe_allow_html=True)


# ----------------------------
# Forecasting section
# ----------------------------
st.markdown("<div class='section-card'>", unsafe_allow_html=True)
st.subheader("AI Predictions for Demand Forecasting")
fig_fc = px.line(
    forecast_df,
    x="Item",
    y=["Current Total", "Predicted Next 30d"],
    markers=True,
    color_discrete_map={"Current Total": PRIMARY_BLUE, "Predicted Next 30d": PRIMARY_GREEN},
    height=380,
)
fig_fc.update_layout(legend_title_text="Series", margin=dict(l=10, r=10, t=30, b=10))
st.plotly_chart(fig_fc, use_container_width=True)

st.dataframe(
    forecast_df.assign(**{"Demand Gap": forecast_df["Predicted Next 30d"] - forecast_df["Current Total"]}),
    use_container_width=True,
    hide_index=True,
)
st.markdown("</div>", unsafe_allow_html=True)


# ----------------------------
# Geo section: Locations map (aggregated counts)
# ----------------------------
st.markdown("<div class='section-card'>", unsafe_allow_html=True)
st.subheader("Locations Map (inventory lines per location)")
with engine.begin() as conn:
    geo_rows = conn.execute(
        select(
            t_locations.c.name.label("Location"),
            func.count().label("Lines"),
        ).select_from(
            t_inventory.join(t_locations, t_inventory.c.location_id == t_locations.c.id)
        ).group_by(t_locations.c.name)
    ).mappings().all()
    # Join with geo table if it exists
    # Note: import inside block to avoid circulars
    from app_core.db import location_geo as t_geo
    coords = conn.execute(
        select(t_locations.c.name, t_geo.c.lat, t_geo.c.lon).join(t_geo, t_geo.c.location_id == t_locations.c.id)
    ).all()

geo_df = pd.DataFrame(geo_rows)
coord_df = pd.DataFrame(coords, columns=["Location", "lat", "lon"])
if not geo_df.empty and not coord_df.empty:
    merged = pd.merge(geo_df, coord_df, on="Location", how="inner")
    st.map(merged.rename(columns={"lon": "longitude", "lat": "latitude"})[["latitude", "longitude"]])
else:
    st.caption("Map will appear once data is available.")
st.markdown("</div>", unsafe_allow_html=True)

# ----------------------------
# Automated ordering section
# ----------------------------
st.markdown("<div class='section-card'>", unsafe_allow_html=True)
st.subheader("Automated Ordering and Approvals")

to_order = inv_df[inv_df["Current Stock"] < inv_df["Minimum Required"]].copy()
if to_order.empty:
    st.success("All items are above minimum stock levels across selected locations.")
else:
    to_order["Recommended Order Qty"] = (
        (to_order["Minimum Required"] * 1.5).round().astype(int) - to_order["Current Stock"]
    ).clip(lower=0)
    st.write("Items below minimum stock levels:")
    st.dataframe(
        to_order[[
            "Location",
            "Item",
            "Current Stock",
            "Minimum Required",
            "Recommended Order Qty",
        ]].reset_index(drop=True),
        use_container_width=True,
        hide_index=True,
    )

    with st.form("generate_orders_form"):
        approver = st.selectbox("Select approver", ["Regional Manager", "Ops Director", "Pharmacy Lead"])
        urgent = st.checkbox("Mark urgent")
        submitted = st.form_submit_button("Generate Orders")
        if submitted:
            # Persist one order per location with relevant lines
            with engine.begin() as conn:
                for loc in to_order["Location"].unique():
                    order_id = conn.execute(
                        insert(t_orders).values(location_id=conn.execute(select(t_locations.c.id).where(t_locations.c.name == loc)).scalar_one(), approver=approver, urgent=urgent)
                    ).inserted_primary_key[0]
                    subset = to_order[to_order["Location"] == loc]
                    for _, r in subset.iterrows():
                        item_id = conn.execute(select(t_items.c.id).where(t_items.c.name == r["Item"]))
                        item_id = item_id.scalar_one()
                        qty = int(r["Recommended Order Qty"])
                        if qty > 0:
                            conn.execute(insert(t_order_lines).values(order_id=order_id, item_id=item_id, qty=qty))
            st.success(
                f"Orders created and sent to {approver} for approval." + (" Urgent flag applied." if urgent else "")
            )

    # Recent orders
    with st.expander("Recent orders"):
        with engine.begin() as conn:
            rows = conn.execute(
                select(
                    t_orders.c.id,
                    t_orders.c.created_at,
                    t_locations.c.name.label("Location"),
                    t_orders.c.approver,
                    t_orders.c.urgent,
                ).join(t_locations, t_orders.c.location_id == t_locations.c.id).order_by(t_orders.c.id.desc()).limit(10)
            ).mappings().all()
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.caption("No orders yet.")
st.markdown("</div>", unsafe_allow_html=True)


# ----------------------------
# Supplier performance section
# ----------------------------
st.markdown("<div class='section-card'>", unsafe_allow_html=True)
st.subheader("Supplier Performance Tracking")

supplier_df = generate_supplier_df(7)

fig_sup = px.bar(
    supplier_df,
    x="Supplier",
    y="Performance Score",
    color="Performance Score",
    color_continuous_scale="Viridis",
    height=420,
)
fig_sup.update_layout(margin=dict(l=10, r=10, t=30, b=10))
st.plotly_chart(fig_sup, use_container_width=True)

with st.expander("Supplier metrics"):
    st.dataframe(
        supplier_df.sort_values("Performance Score", ascending=False).reset_index(drop=True),
        use_container_width=True,
        hide_index=True,
    )
st.markdown("</div>", unsafe_allow_html=True)


# Footer spacing
st.caption("Demo only: simulated data for training and prototyping.")


