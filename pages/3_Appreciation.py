import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from pathlib import Path

st.title("Historical Appreciation (Zillow ZHVI)")
st.caption("Zillow Home Value Index — Condo/Co-op by neighborhood, 2000-2026")

st.info(
    "**Data & Methodology:** Zillow Home Value Index (ZHVI) for condos, annual values by zip code (2000-2026). "
    "ZHVI is Zillow's smoothed, seasonally adjusted estimate of typical home value. "
    "CAGR computed over 3-, 5-, 10-year, and full windows. YoY heatmap shows annual percent change."
)

DATA = st.session_state.get("DATA", Path(__file__).resolve().parent.parent / "data")


@st.cache_data
def load_zhvi():
    df = pd.read_csv(DATA / "zhvi_condo.csv", dtype={"zip": str})
    year_cols = [c for c in df.columns if c.startswith("zhvi_")]
    long = df.melt(id_vars=["zip", "jurisdiction", "neighborhood"],
                   value_vars=year_cols, var_name="year_col", value_name="value")
    long["year"] = long["year_col"].str.extract(r"(\d{4})").astype(int)
    return long.dropna(subset=["value"]).drop(columns="year_col"), df


zhvi_long, zhvi_wide = load_zhvi()

with st.sidebar:
    st.header("Settings")
    all_nh = sorted(zhvi_long["neighborhood"].unique().tolist())
    top8 = (zhvi_long[zhvi_long["year"] == zhvi_long["year"].max()]
            .nlargest(8, "value")["neighborhood"].tolist())
    sel_nh = st.multiselect("Neighborhoods", all_nh, default=top8)
    inflation_rate = st.slider("Inflation rate (%)", 0.0, 8.0, 3.0, 0.5)
    show_real = st.checkbox("Show inflation-adjusted (real)", value=False)
    show_growth = st.checkbox("Show annualized growth rates", value=True)

if not sel_nh:
    st.info("Select neighborhoods from the sidebar.")
    st.stop()

zh_plot = zhvi_long[zhvi_long["neighborhood"].isin(sel_nh)].copy()
base_year = zh_plot["year"].min()

if show_real:
    zh_plot["value"] = zh_plot.apply(
        lambda r: r["value"] / (1 + inflation_rate / 100) ** (r["year"] - base_year), axis=1
    )

fig = px.line(zh_plot, x="year", y="value", color="neighborhood",
              labels={"value": "ZHVI ($)", "year": ""},
              title="Condo ZHVI — " + ("Real" if show_real else "Nominal"),
              height=480)
fig.update_layout(
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
    yaxis_tickformat="$,.0f",
)
st.plotly_chart(fig, use_container_width=True)

st.subheader("Indexed Performance (Base Year = 100)")
idx_plot = zhvi_long[zhvi_long["neighborhood"].isin(sel_nh)].copy()
base_vals = idx_plot.groupby("neighborhood")["value"].transform("first")
idx_plot["indexed"] = idx_plot["value"] / base_vals * 100

fig_idx = px.line(idx_plot, x="year", y="indexed", color="neighborhood",
                  labels={"indexed": "Index (base=100)", "year": ""},
                  height=400)
fig_idx.add_hline(y=100, line_dash="dash", line_color="grey")
fig_idx.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02))
st.plotly_chart(fig_idx, use_container_width=True)

if show_growth:
    st.subheader("Annualized Growth Rates")
    records = []
    for nh in sel_nh:
        nh_data = zhvi_long[zhvi_long["neighborhood"] == nh].sort_values("year")
        if len(nh_data) < 2:
            continue
        latest = nh_data.iloc[-1]
        latest_val = latest["value"]
        latest_yr = latest["year"]

        for window, label in [(3, "3yr"), (5, "5yr"), (10, "10yr"), (None, "All")]:
            if window:
                start = nh_data[nh_data["year"] == latest_yr - window]
            else:
                start = nh_data.head(1)
            if start.empty:
                continue
            start_val = start.iloc[0]["value"]
            start_yr = start.iloc[0]["year"]
            n_years = latest_yr - start_yr
            if n_years > 0 and start_val > 0:
                cagr = (latest_val / start_val) ** (1 / n_years) - 1
                records.append({"Neighborhood": nh, "Period": label, "CAGR": cagr,
                                "Start Value": start_val, "End Value": latest_val})

    if records:
        gr_df = pd.DataFrame(records)
        pivot = gr_df.pivot(index="Neighborhood", columns="Period", values="CAGR")
        for col in ["3yr", "5yr", "10yr", "All"]:
            if col in pivot.columns:
                pivot[col] = pivot[col].map(lambda x: f"{x:.1%}" if pd.notna(x) else "N/A")
        cols_order = [c for c in ["3yr", "5yr", "10yr", "All"] if c in pivot.columns]
        st.dataframe(pivot[cols_order], use_container_width=True)

st.subheader("Year-over-Year Change Heatmap")
yoy_records = []
for nh in sel_nh:
    nh_data = zhvi_long[zhvi_long["neighborhood"] == nh].sort_values("year")
    vals = nh_data.set_index("year")["value"]
    yoy = vals.pct_change()
    for yr, v in yoy.items():
        if pd.notna(v):
            yoy_records.append({"Neighborhood": nh, "Year": yr, "YoY": v})

if yoy_records:
    yoy_df = pd.DataFrame(yoy_records)
    pivot_yoy = yoy_df.pivot(index="Neighborhood", columns="Year", values="YoY")

    fig_yoy = go.Figure(go.Heatmap(
        z=pivot_yoy.values * 100,
        x=[str(c) for c in pivot_yoy.columns],
        y=pivot_yoy.index.tolist(),
        text=[[f"{v:.1f}%" if pd.notna(v) else "" for v in row] for row in pivot_yoy.values * 100],
        texttemplate="%{text}",
        textfont=dict(size=9),
        colorscale=[[0, "#d73027"], [0.5, "#ffffbf"], [1, "#1a9850"]],
        zmid=0,
        colorbar=dict(title="%"),
    ))
    fig_yoy.update_layout(
        height=max(250, len(sel_nh) * 35),
        margin=dict(l=140, t=20, b=40),
        xaxis=dict(tickangle=-45),
    )
    st.plotly_chart(fig_yoy, use_container_width=True)
