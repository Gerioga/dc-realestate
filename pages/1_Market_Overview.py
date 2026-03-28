import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import json
from pathlib import Path

st.title("Market Overview")
st.caption("Redfin market data — DC / Arlington / Alexandria")

st.info(
    "**Data & Methodology:** Redfin Market Tracker quarterly zip-level aggregates (2012-present). "
    "Metrics include median sale price, $/sqft, days on market, and sale-to-list ratio. "
    "Rent estimates from HUD FY2025 Fair Market Rents. Choropleth maps use ZCTA boundaries."
)

DATA = st.session_state.get("DATA", Path(__file__).resolve().parent.parent / "data")

JURIS_COLORS = {
    "Washington DC": "#002245", "Arlington": "#0071BC",
    "Alexandria": "#EC553A", "Richmond": "#795548",
}

ZIP_LABELS = {
    "20001": "Shaw / U St", "20002": "Capitol Hill NE", "20003": "Capitol Hill SE",
    "20004": "Penn Quarter", "20005": "Downtown", "20006": "Foggy Bottom",
    "20007": "Georgetown", "20008": "Cleveland Pk", "20009": "Adams Morgan",
    "20010": "Columbia Heights", "20011": "Petworth", "20012": "Shepherd Park",
    "20015": "Chevy Chase DC", "20016": "Tenleytown", "20017": "Brookland",
    "20018": "Woodridge", "20019": "Deanwood", "20020": "Anacostia",
    "20024": "SW Waterfront", "20032": "Congress Hts", "20036": "Dupont Circle",
    "20037": "West End",
    "22201": "Clarendon", "22202": "Crystal City", "22203": "Ballston",
    "22204": "Columbia Pike", "22205": "Westover", "22206": "Fairlington",
    "22207": "Chain Bridge", "22209": "Rosslyn",
    "22301": "Del Ray", "22302": "Jefferson Park", "22303": "Groveton",
    "22304": "Seminary", "22305": "Arlandria", "22306": "Belle View",
    "22307": "Fort Hunt", "22308": "Waynewood", "22309": "Mt Vernon S",
    "22310": "Franconia", "22311": "Lincolnia", "22312": "Pinecrest",
    "22314": "Old Town", "22315": "Kingstowne",
}


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
    for col in df.columns:
        if col not in ("zip", "region", "city", "state", "state_code", "property_type",
                       "period_begin", "period_end", "last_updated", "is_seasonally_adjusted",
                       "parent_metro_region", "region_type", "region_type_id",
                       "table_id", "property_type_id", "period_duration", "jurisdiction"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["period_begin"] = pd.to_datetime(df["period_begin"], errors="coerce")
    df["period_end"] = pd.to_datetime(df["period_end"], errors="coerce")
    return df


@st.cache_data
def load_yield():
    return pd.read_csv(DATA / "yield_analysis.csv", dtype={"zip": str})


@st.cache_data
def load_geojson():
    with open(DATA / "dc_zcta.geojson") as f:
        return json.load(f)


@st.cache_data
def load_fmr():
    return pd.read_csv(DATA / "hud_fmr_2025.csv", dtype={"zip": str})


mkt = load_market()
yld = load_yield()
fmr = load_fmr()

with st.sidebar:
    st.header("Filters")
    ptypes = sorted(mkt["property_type"].dropna().unique().tolist())
    sel_ptype = st.selectbox("Property Type", ptypes,
                             index=ptypes.index("Condo/Co-op") if "Condo/Co-op" in ptypes else 0)
    jurisdictions = sorted(mkt["jurisdiction"].dropna().unique().tolist())
    sel_juris = st.multiselect("Jurisdictions", jurisdictions, default=jurisdictions)
    bedroom_opts = {"All": None, "Studio/0BR": "fmr_0br", "1BR": "fmr_1br",
                    "2BR": "fmr_2br", "3BR": "fmr_3br", "4BR": "fmr_4br"}
    sel_bedroom = st.selectbox("Bedroom Type (for rent estimates)", list(bedroom_opts.keys()))

latest_q = mkt["period_end"].max()
snap = mkt[
    (mkt["period_end"] == latest_q)
    & (mkt["property_type"] == sel_ptype)
    & (mkt["jurisdiction"].isin(sel_juris))
].copy()
snap["neighborhood"] = snap["zip"].map(ZIP_LABELS).fillna(snap["zip"])

bedroom_label = sel_bedroom if sel_bedroom != "All" else "All bedrooms"
st.markdown(f"**Latest period:** {latest_q.strftime('%B %Y')} · **{sel_ptype}** · **{bedroom_label}**")

fmr_col = bedroom_opts[sel_bedroom]
if fmr_col and fmr_col in fmr.columns:
    snap = snap.merge(fmr[["zip", fmr_col]].rename(columns={fmr_col: "fmr_rent"}),
                      on="zip", how="left")
    snap["fmr_rent"] = pd.to_numeric(snap["fmr_rent"], errors="coerce")

mc = st.columns(5)


def _metric(col_w, label, series, fmt, delta_series=None):
    v = series.median()
    if pd.isna(v):
        col_w.metric(label, "N/A")
        return
    delta = None
    if delta_series is not None:
        dv = delta_series.median()
        if pd.notna(dv):
            delta = f"{dv:.1%}"
    col_w.metric(label, fmt.format(v), delta=delta)


_metric(mc[0], "Median Price", snap["median_sale_price"], "${:,.0f}")
_metric(mc[1], "Median $/sqft", snap["median_ppsf"], "${:,.0f}")
_metric(mc[2], "Days on Market", snap["median_dom"], "{:.0f} days")
_metric(mc[3], "Sale-to-List", snap["avg_sale_to_list"], "{:.1%}")
if fmr_col and "fmr_rent" in snap.columns:
    _metric(mc[4], f"FMR Rent ({sel_bedroom})", snap["fmr_rent"], "${:,.0f}")
else:
    _metric(mc[4], "YoY Price Change", snap["median_sale_price_yoy"], "{:+.1%}",
            snap["median_sale_price_yoy"])

st.divider()

ca, cb = st.columns(2)

with ca:
    st.subheader("Median Sale Price by Neighborhood")
    price_bar = snap.dropna(subset=["median_sale_price", "neighborhood"]).sort_values("median_sale_price")
    colors = [JURIS_COLORS.get(zip_jurisdiction(z), "#999") for z in price_bar["zip"]]
    fig_pb = go.Figure(go.Bar(
        y=price_bar["neighborhood"], x=price_bar["median_sale_price"],
        orientation="h", marker_color=colors,
        text=price_bar["median_sale_price"].map("${:,.0f}".format),
        textposition="outside",
    ))
    fig_pb.update_layout(
        xaxis_title="$", height=max(350, len(price_bar) * 22),
        margin=dict(l=140, r=60, t=20, b=40),
    )
    st.plotly_chart(fig_pb, use_container_width=True)

with cb:
    st.subheader("Market Heat by Neighborhood")
    heat_cols = ["median_dom", "avg_sale_to_list", "sold_above_list", "off_market_in_two_weeks"]
    heat_cols = [c for c in heat_cols if c in snap.columns]
    col_labels = {
        "median_dom": "Days on Mkt", "avg_sale_to_list": "Sale / List",
        "sold_above_list": "% Above List", "off_market_in_two_weeks": "Off Mkt <2wk",
    }
    higher_better = {
        "median_dom": False, "avg_sale_to_list": True,
        "sold_above_list": True, "off_market_in_two_weeks": True,
    }
    heat_src = snap[["neighborhood"] + heat_cols].dropna(subset=["median_dom"])
    if not heat_src.empty:
        z_matrix, text_matrix, col_names, row_names = [], [], [], heat_src["neighborhood"].tolist()
        for col in heat_cols:
            vals = pd.to_numeric(heat_src[col], errors="coerce")
            mn, mx = vals.min(), vals.max()
            norm = (vals - mn) / (mx - mn + 1e-9)
            if not higher_better[col]:
                norm = 1 - norm
            z_matrix.append(norm.fillna(0.5).tolist())
            fmt = "{:.0f}" if col == "median_dom" else "{:.0%}"
            text_matrix.append([fmt.format(v) if pd.notna(v) else "" for v in vals])
            col_names.append(col_labels[col])

        fig_heat = go.Figure(go.Heatmap(
            z=z_matrix, x=row_names, y=col_names,
            text=text_matrix, texttemplate="%{text}", textfont=dict(size=10),
            colorscale=[[0, "#d73027"], [0.5, "#ffffbf"], [1, "#1a9850"]],
            showscale=True, zmin=0, zmax=1,
            colorbar=dict(title="Hot ->", tickvals=[0, 0.5, 1],
                          ticktext=["Cold", "Mid", "Hot"], len=0.6),
        ))
        fig_heat.update_layout(
            xaxis=dict(tickangle=-40, tickfont=dict(size=10)),
            yaxis=dict(tickfont=dict(size=11)),
            height=280, margin=dict(l=110, b=100, t=20),
        )
        st.plotly_chart(fig_heat, use_container_width=True)

st.divider()

st.subheader("Choropleth Map")

try:
    gj = load_geojson()
    map_opts = {
        "Median Price ($)": "median_sale_price",
        "Days on Market": "median_dom",
        "Sale-to-List": "avg_sale_to_list",
        "YoY Change": "median_sale_price_yoy",
    }
    sel_map = st.selectbox("Color by", list(map_opts.keys()))
    map_col = map_opts[sel_map]

    map_df = snap.dropna(subset=[map_col, "zip"]).copy()
    yld_zip = yld[yld["property_type"] == sel_ptype].groupby("zip")["gross_yield"].mean().reset_index()
    map_df = map_df.merge(yld_zip, on="zip", how="left")

    fig_map = px.choropleth(
        map_df, geojson=gj, locations="zip",
        featureidkey="properties.ZCTA5CE20",
        color=map_col,
        color_continuous_scale="RdYlGn" if "yoy" in map_col or "sale_to" in map_col else "Blues",
        hover_name="neighborhood",
        hover_data={"zip": True, "median_sale_price": ":$,.0f",
                    "median_dom": ":.0f", "gross_yield": ":.1%"},
        labels={map_col: sel_map},
        fitbounds="locations", basemap_visible=False, height=520,
    )
    fig_map.update_geos(visible=False)
    st.plotly_chart(fig_map, use_container_width=True)
except FileNotFoundError:
    st.warning("GeoJSON file not found — map unavailable.")
