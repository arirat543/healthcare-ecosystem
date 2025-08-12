import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import select, func

from app_core.db import get_engine, init_db, poct_tests as t_tests, locations as t_locations
from app_core.seed import seed_core


st.set_page_config(page_title="POCT Operations", page_icon="🧫", layout="wide")
st.title("POCT HbA1c Operations")

engine = get_engine()
init_db(engine)

# Ensure seeded
with engine.begin() as conn:
    num = conn.execute(select(func.count()).select_from(t_tests)).scalar_one()
    if num == 0:
        seed_core()

with st.sidebar:
    st.header("Filters")
    # Load locations for filter
    with engine.begin() as conn:
        locs = [r[0] for r in conn.execute(select(t_locations.c.name).order_by(t_locations.c.name)).all()]
    selected = st.multiselect("Locations", options=locs, default=locs[:10])
    months = st.slider("Months back", 3, 12, 12)

# Query tests
query = (
    select(
        t_tests.c.test_date,
        t_tests.c.hba1c_result,
        t_locations.c.name.label("Location"),
    )
    .select_from(t_tests.join(t_locations, t_tests.c.location_id == t_locations.c.id))
)

with engine.begin() as conn:
    df = pd.DataFrame(conn.execute(query).mappings().all())

if df.empty:
    st.info("No POCT test data available.")
    st.stop()

df["test_date"] = pd.to_datetime(df["test_date"])
cutoff = df["test_date"].max() - pd.DateOffset(months=months)
df = df[df["test_date"] >= cutoff]
if selected:
    df = df[df["Location"].isin(selected)]

col1, col2, col3 = st.columns(3)
col1.metric("Total tests", f"{len(df):,}")
col2.metric("Avg HbA1c", f"{df['hba1c_result'].mean():.2f}%")
col3.metric(
    ">% 7% HbA1c",
    f"{(df['hba1c_result'] > 7.0).mean() * 100:.1f}%",
)

st.markdown("---")
# Monthly volume
st.subheader("Monthly testing volume")
monthly = (
    df.assign(month=df["test_date"].dt.to_period("M").dt.to_timestamp())
    .groupby(["month", "Location"], as_index=False)
    ["hba1c_result"].count()
    .rename(columns={"hba1c_result": "tests"})
)
fig_vol = px.bar(monthly, x="month", y="tests", color="Location", barmode="stack", height=420)
fig_vol.update_layout(margin=dict(l=10, r=10, t=30, b=10))
st.plotly_chart(fig_vol, use_container_width=True)

# Control chart (daily mean HbA1c) with ±3σ
st.subheader("Daily HbA1c control chart (mean ± 3σ)")
daily = df.groupby(df["test_date"].dt.date)["hba1c_result"].mean().reset_index()
daily.columns = ["date", "mean_hba1c"]
mu = daily["mean_hba1c"].mean()
sigma = daily["mean_hba1c"].std(ddof=0)

fig_cc = px.line(daily, x="date", y="mean_hba1c", markers=True, height=420)
fig_cc.add_hline(y=mu, line_dash="dash", line_color="#2563EB", annotation_text="Mean")
fig_cc.add_hline(y=mu + 3 * sigma, line_dash="dot", line_color="#ef4444", annotation_text="UCL")
fig_cc.add_hline(y=mu - 3 * sigma, line_dash="dot", line_color="#ef4444", annotation_text="LCL")
fig_cc.update_layout(margin=dict(l=10, r=10, t=30, b=10), yaxis_title="HbA1c %")
st.plotly_chart(fig_cc, use_container_width=True)

# Table of recent tests
with st.expander("Recent tests (sample)"):
    st.dataframe(
        df.sort_values("test_date", ascending=False).head(200).reset_index(drop=True),
        use_container_width=True,
        hide_index=True,
    )

import streamlit as st

st.set_page_config(page_title="POCT Operations", page_icon="🧫", layout="wide")
st.title("POCT Operations - Prototype")
st.info("Placeholder: Real-time HbA1c workflow management, QC automation, equipment tracking, patient flow.")



