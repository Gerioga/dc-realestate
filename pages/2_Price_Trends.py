import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from pathlib import Path

st.title("Price Trends")
st.caption("Redfin time-series data — median price, $/sqft, days on market")

st.info(
    "**Data & Methodology:** Redfin Market Tracker quarterly data by zip code (2012-present). "
    "Trends show median values aggregated by jurisdiction or neighborhood. "
    "Inflation adjustment uses a fixed 4% annual rate deflated to 2024 dollars. Forward projections use trailing 5-year CAGR."
)

DATA = st.session_state.get("DATA", Path(__file__).resolve().parent.parent / "data")

JURIS_COLORS = {
    "Washington DC": "#002245", "Arlington": "#0071BC",
    "Alexandria": "#EC553A",
}
PTYPE_COLORS = {
    "Condo/Co-op": "#0071BC", "Townhouse": "#EC553A",
    "Single Family Residential": "#4CBB88", "Multi-Family (2-4 Unit)": "#862C8E",
}

ZIP_LABELS = {
    "20001": "Shaw", "20002": "Capitol Hill NE", "20003": "Capitol Hill SE",
    "20007": "Georgetown", "20008": "Cleveland Pk", "20009": "Adams Morgan",
    "20010": "Columbia Hts", "20011": "Petworth", "20015": "Chevy Chase",
    "20016": "Tenleytown", "20024": "SW Waterfront", "20036": "Dupont",
    "22201": "Clarendon", "22202": "Crystal City", "22203": "Ballston",
    "22204": "Columbia Pike", "22206": "Fairlington", "22209": "Rosslyn",
    "22301": "Del Ray", "22314": "Old Town",
}

INFL_RATE = 0.04
CPI_RAW = {y: 100 / (1 + INFL_RATE) ** (2024 - y) for y in range(2012, 2025)}
CPI_BASE = CPI_RAW[2024]
CPI_DEFLATOR = {y: CPI_BASE / v for y, v in CPI_RAW.items()}


def zip_jurisdiction(zc):
    if zc.startswith("200"):
        return "Washington DC"
    if zc.startswith("222"):
        return "Arlington"
    if zc.startswith("223"):
        return "Alexandria"
    return "Other"


@st.cache_data
def load_market():
    df = pd.read_csv(DATA / "dc_arl_alex.tsv", sep="\t", low_memory=False)
    df.columns = df.columns.str.lower().str.strip()
    df["zip"] = df["region"].str.extract(r"(\d{5})").astype(str)
    df["jurisdiction"] = df["zip"].map(zip_jurisdiction)
    df["neighborhood"] = df["zip"].map(ZIP_LABELS).fillna(df["zip"])
    for col in df.columns:
        if col not in ("zip", "region", "city", "state", "state_code", "property_type",
                       "period_begin", "period_end", "last_updated", "is_seasonally_adjusted",
                       "parent_metro_region", "region_type", "region_type_id",
                       "table_id", "property_type_id", "period_duration",
                       "jurisdiction", "neighborhood"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["period_begin"] = pd.to_datetime(df["period_begin"], errors="coerce")
    df["period_end"] = pd.to_datetime(df["period_end"], errors="coerce")
    df["year"] = df["period_begin"].dt.year
    return df


mkt = load_market()

with st.sidebar:
    st.header("Filters")
    view_mode = st.radio("View by", ["Jurisdiction", "Neighborhood"])
    ptypes = sorted(mkt["property_type"].dropna().unique().tolist())
    sel_ptypes = st.multiselect("Property Type", ptypes,
                                default=["Condo/Co-op"] if "Condo/Co-op" in ptypes else ptypes[:1])
    adjust_inflation = st.checkbox("Adjust for inflation (4% annual, 2024$)", value=False)

    if view_mode == "Neighborhood":
        all_zips = sorted(mkt["zip"].unique().tolist())
        labels = [f"{z} — {ZIP_LABELS.get(z, z)}" for z in all_zips]
        sel_labels = st.multiselect("Neighborhoods", labels,
                                    default=[l for l in labels if any(k in l for k in ["Clarendon", "Georgetown", "Old Town", "Dupont"])])
        sel_zips = [l.split(" — ")[0] for l in sel_labels]
    else:
        jurisdictions = sorted(mkt["jurisdiction"].dropna().unique().tolist())
        sel_juris = st.multiselect("Jurisdictions", jurisdictions, default=jurisdictions)

df = mkt[mkt["property_type"].isin(sel_ptypes)].copy()
if view_mode == "Neighborhood":
    df = df[df["zip"].isin(sel_zips)]
else:
    df = df[df["jurisdiction"].isin(sel_juris)]

if df.empty:
    st.warning("No data for current selection.")
    st.stop()


def deflate(series, years):
    if not adjust_inflation:
        return series
    deflators = years.map(CPI_DEFLATOR).fillna(1.0)
    return series * deflators


st.subheader("Median Sale Price Over Time")

if view_mode == "Jurisdiction":
    agg = df.groupby(["period_begin", "jurisdiction"]).agg(
        median_price=("median_sale_price", "median"),
        year=("year", "first"),
    ).reset_index()
    agg["median_price"] = deflate(agg["median_price"], agg["year"])
    fig1 = px.line(agg, x="period_begin", y="median_price", color="jurisdiction",
                   color_discrete_map=JURIS_COLORS,
                   labels={"median_price": "Median Sale Price ($)", "period_begin": ""},
                   height=450)
else:
    agg = df.groupby(["period_begin", "neighborhood"]).agg(
        median_price=("median_sale_price", "median"),
        year=("year", "first"),
    ).reset_index()
    agg["median_price"] = deflate(agg["median_price"], agg["year"])
    fig1 = px.line(agg, x="period_begin", y="median_price", color="neighborhood",
                   labels={"median_price": "Median Sale Price ($)", "period_begin": ""},
                   height=450)

suffix = " (2024$)" if adjust_inflation else ""
fig1.update_layout(
    title=f"Median Sale Price{suffix}",
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
)
st.plotly_chart(fig1, use_container_width=True)

st.subheader("Median Price per Square Foot")
group_col = "jurisdiction" if view_mode == "Jurisdiction" else "neighborhood"
agg2 = df.groupby(["period_begin", group_col]).agg(
    ppsf=("median_ppsf", "median"),
    year=("year", "first"),
).reset_index()
agg2["ppsf"] = deflate(agg2["ppsf"], agg2["year"])

fig2 = px.line(agg2, x="period_begin", y="ppsf", color=group_col,
               color_discrete_map=JURIS_COLORS if view_mode == "Jurisdiction" else None,
               labels={"ppsf": "$/sqft", "period_begin": ""},
               height=400)
fig2.update_layout(
    title=f"Median $/sqft{suffix}",
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
)
st.plotly_chart(fig2, use_container_width=True)

st.subheader("Year-over-Year Price Change (%)")
agg3 = df.groupby(["period_begin", group_col]).agg(
    yoy=("median_sale_price_yoy", "median"),
).reset_index()

fig3 = px.line(agg3, x="period_begin", y="yoy", color=group_col,
               color_discrete_map=JURIS_COLORS if view_mode == "Jurisdiction" else None,
               labels={"yoy": "YoY Change", "period_begin": ""},
               height=400)
fig3.add_hline(y=0, line_dash="dash", line_color="grey", line_width=1)
fig3.update_layout(
    title="YoY Median Sale Price Change",
    yaxis_tickformat=".0%",
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
)
st.plotly_chart(fig3, use_container_width=True)

st.subheader("Market Activity")
agg4 = df.groupby(["period_begin", group_col]).agg(
    dom=("median_dom", "median"),
).reset_index()
fig4 = px.line(agg4, x="period_begin", y="dom", color=group_col,
               color_discrete_map=JURIS_COLORS if view_mode == "Jurisdiction" else None,
               labels={"dom": "Days", "period_begin": ""}, height=400)
fig4.update_layout(title="Median Days on Market",
                   legend=dict(orientation="h", yanchor="bottom", y=1.02))
st.plotly_chart(fig4, use_container_width=True)

st.divider()
st.subheader("Forward-Looking Appreciation Projection (10 years)")
st.caption("Based on trailing 5-year CAGR from Redfin data, projected forward. Real values use 2.7% inflation.")

PROJ_YEARS = 10
PROJ_INFL = 0.027

latest_date = df["period_begin"].max()
five_yr_ago = latest_date - pd.DateOffset(years=5)

latest_prices = df[df["period_begin"] == latest_date].groupby(group_col)["median_sale_price"].median()
past_df = df[df["period_begin"] <= five_yr_ago].sort_values("period_begin")
past_prices = past_df.groupby(group_col).last()["median_sale_price"] if not past_df.empty else pd.Series(dtype=float)

proj_records = []
for grp in latest_prices.index:
    if grp not in past_prices.index or pd.isna(past_prices[grp]) or past_prices[grp] <= 0:
        continue
    current = latest_prices[grp]
    past = past_prices[grp]
    cagr = (current / past) ** (1 / 5) - 1

    for yr in range(0, PROJ_YEARS + 1):
        nominal = current * (1 + cagr) ** yr
        real = nominal / (1 + PROJ_INFL) ** yr
        proj_records.append({
            "group": grp, "year": latest_date.year + yr,
            "nominal": nominal, "real": real, "cagr": cagr,
        })

if proj_records:
    proj_df = pd.DataFrame(proj_records)

    fig_proj = go.Figure()
    groups = proj_df["group"].unique()
    color_map = JURIS_COLORS if view_mode == "Jurisdiction" else {}
    colors = px.colors.qualitative.Set2

    for i, grp in enumerate(groups):
        gd = proj_df[proj_df["group"] == grp]
        c = color_map.get(grp, colors[i % len(colors)])
        cagr_pct = gd["cagr"].iloc[0] * 100
        fig_proj.add_trace(go.Scatter(
            x=gd["year"], y=gd["nominal"], name=f"{grp} nominal ({cagr_pct:+.1f}%/yr)",
            line=dict(color=c, width=2), mode="lines",
        ))
        fig_proj.add_trace(go.Scatter(
            x=gd["year"], y=gd["real"], name=f"{grp} real",
            line=dict(color=c, width=2, dash="dot"), mode="lines",
        ))

    fig_proj.update_layout(
        title=f"10-Year Price Projection — {sel_ptypes[0] if sel_ptypes else 'All'} (solid=nominal, dotted=real @ 2.7% inflation)",
        yaxis_title="Projected Median Price ($)",
        yaxis_tickformat="$,.0f",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        height=480,
    )
    st.plotly_chart(fig_proj, use_container_width=True)
else:
    st.info("Not enough historical data to compute projections.")

if len(sel_ptypes) > 1:
    st.divider()
    st.subheader("Property Type Comparison (Latest Period)")
    latest = mkt[mkt["period_end"] == mkt["period_end"].max()].copy()
    if view_mode == "Jurisdiction":
        latest = latest[latest["jurisdiction"].isin(sel_juris)]
    else:
        latest = latest[latest["zip"].isin(sel_zips)]
    latest = latest[latest["property_type"].isin(sel_ptypes)]

    comp = latest.groupby("property_type").agg(
        median_price=("median_sale_price", "median"),
        median_ppsf=("median_ppsf", "median"),
        median_dom=("median_dom", "median"),
        sale_to_list=("avg_sale_to_list", "median"),
        yoy=("median_sale_price_yoy", "median"),
    ).reset_index()
    comp.columns = ["Property Type", "Median Price", "$/sqft", "Days on Market",
                     "Sale-to-List", "YoY Change"]
    fmt = {
        "Median Price": "${:,.0f}",
        "$/sqft": "${:,.0f}",
        "Days on Market": "{:.0f}",
        "Sale-to-List": "{:.1%}",
        "YoY Change": "{:+.1%}",
    }
    for col, f in fmt.items():
        comp[col] = comp[col].map(lambda x, _f=f: _f.format(x) if pd.notna(x) else "N/A")
    st.dataframe(comp, use_container_width=True, hide_index=True)
