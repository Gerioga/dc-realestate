import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from pathlib import Path

st.title("Investment Yield Analysis")
st.caption("Yield estimates based on Redfin median prices & HUD FMR 2025 rents")

st.info(
    "**Data & Methodology:** Yields computed from Redfin median sale prices and HUD FY2025 Fair Market Rents. "
    "Gross yield = annual rent / price. Net yield deducts HOA (~3% of price), property tax (~1%), and maintenance (~1%). "
    "Scatter plots sized by transaction volume; rankings filterable by budget, bedroom type, and jurisdiction."
)

DATA = st.session_state.get("DATA", Path(__file__).resolve().parent.parent / "data")

JURIS_COLORS = {
    "Washington DC": "#002245", "Arlington": "#0071BC",
    "Alexandria": "#EC553A",
}


def compute_net_yield(price, monthly_rent):
    if price <= 0:
        return 0.0
    expense_pct = 5.0
    return (monthly_rent * 12 - price * expense_pct / 100) / price * 100


@st.cache_data
def load_yield():
    yld = pd.read_csv(DATA / "yield_analysis.csv", dtype={"zip": str})
    fmr = pd.read_csv(DATA / "hud_fmr_2025.csv", dtype={"zip": str})
    return yld.merge(fmr[["zip", "fmr_0br", "fmr_1br", "fmr_2br", "fmr_3br", "fmr_4br"]],
                     on="zip", how="left")


@st.cache_data
def load_market():
    df = pd.read_csv(DATA / "dc_arl_alex.tsv", sep="\t", low_memory=False)
    df.columns = df.columns.str.lower().str.strip()
    df["zip"] = df["region"].str.extract(r"(\d{5})").astype(str)
    for col in df.columns:
        if col not in ("zip", "region", "city", "state", "state_code", "property_type",
                       "period_begin", "period_end", "last_updated", "is_seasonally_adjusted",
                       "parent_metro_region", "region_type", "region_type_id",
                       "table_id", "property_type_id", "period_duration"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["period_end"] = pd.to_datetime(df["period_end"], errors="coerce")
    return df


yld = load_yield()
mkt = load_market()

BR_TO_FMR = {"0BR/Studio": "fmr_0br", "1BR": "fmr_1br", "2BR": "fmr_2br",
             "3BR": "fmr_3br", "4BR": "fmr_4br"}

with st.sidebar:
    st.header("Investment Parameters")
    inv_budget = st.slider("Max Budget ($)", 100_000, 2_000_000, 700_000, 25_000, format="$%d")
    inv_bedroom = st.selectbox("Bedroom Preference", list(BR_TO_FMR.keys()), index=1)
    st.divider()
    all_ptypes = sorted(yld["property_type"].dropna().unique().tolist())
    sel_ptypes = st.multiselect("Property Type", all_ptypes,
                                default=["Condo/Co-op"] if "Condo/Co-op" in all_ptypes else all_ptypes[:1])
    all_juris = sorted(yld["jurisdiction"].dropna().unique().tolist())
    sel_juris = st.multiselect("Jurisdiction", all_juris, default=all_juris)

    fmr_col = BR_TO_FMR[inv_bedroom]
    default_rent = int(yld[fmr_col].median()) if fmr_col in yld.columns and yld[fmr_col].notna().any() else 2000
    inv_rent = st.number_input("Monthly Rent Override ($)", 500, 10_000, default_rent, 50,
                               help="Defaults to HUD FMR median. Edit to override.")

opp = yld.copy()
if sel_ptypes:
    opp = opp[opp["property_type"].isin(sel_ptypes)]
if sel_juris:
    opp = opp[opp["jurisdiction"].isin(sel_juris)]
opp = opp[opp["price"] <= inv_budget].copy()

if opp.empty:
    st.warning("No properties match the current filters. Try raising the budget.")
    st.stop()

opp["monthly_rent_used"] = inv_rent
opp["gross_yield_calc"] = (inv_rent * 12 / opp["price"] * 100).round(2)
opp["net_yield_calc"] = opp.apply(
    lambda r: compute_net_yield(r["price"], inv_rent), axis=1
).round(2)
opp["price_to_rent"] = (opp["price"] / (inv_rent * 12)).round(1)

latest_q = mkt["period_end"].max()
snap = mkt[mkt["period_end"] == latest_q].copy()
mkt_snap = snap[["zip", "median_dom", "avg_sale_to_list", "homes_sold", "median_ppsf"]].copy()
opp = opp.merge(mkt_snap, on="zip", how="left")
opp = opp.sort_values("net_yield_calc", ascending=False).reset_index(drop=True)

st.markdown(
    f"**Budget:** ${inv_budget:,.0f} · **Bedroom:** {inv_bedroom} · "
    f"**Rent:** ${inv_rent:,.0f}/mo"
)

mc = st.columns(4)
mc[0].metric("Neighborhoods Found", len(opp))
mc[1].metric("Avg Gross Yield", f"{opp['gross_yield_calc'].mean():.1f}%")
mc[2].metric("Avg Net Yield", f"{opp['net_yield_calc'].mean():.1f}%")
mc[3].metric("Avg Price-to-Rent", f"{opp['price_to_rent'].mean():.1f}x")

st.divider()

st.subheader("Neighborhood Yield Rankings")

rank_opts = {
    "Net Yield (%)": "net_yield_calc",
    "Gross Yield (%)": "gross_yield_calc",
    "Price-to-Rent (lower = better)": "price_to_rent",
}
sel_rank = st.selectbox("Rank by", list(rank_opts.keys()))
rank_col = rank_opts[sel_rank]
ascending_rank = "Price-to-Rent" in sel_rank

rank_df = (opp.groupby(["neighborhood", "jurisdiction"])
           .agg(**{rank_col: (rank_col, "mean")})
           .reset_index()
           .sort_values(rank_col, ascending=ascending_rank)
           .head(20))

color_scale = "RdYlGn_r" if ascending_rank else "RdYlGn"
bar_colors = px.colors.sample_colorscale(
    color_scale,
    ((rank_df[rank_col] - rank_df[rank_col].min()) /
     (rank_df[rank_col].max() - rank_df[rank_col].min() + 1e-9)).tolist()
)

fig_rank = go.Figure(go.Bar(
    y=rank_df["neighborhood"], x=rank_df[rank_col],
    orientation="h", marker_color=bar_colors,
    text=rank_df[rank_col].map("{:.1f}".format), textposition="outside",
    customdata=rank_df["jurisdiction"],
    hovertemplate="%{y} (%{customdata})<br>" + sel_rank + ": %{x:.2f}<extra></extra>",
))
fig_rank.update_layout(
    title=f"Top Neighborhoods by {sel_rank}",
    xaxis_title=sel_rank,
    height=max(350, len(rank_df) * 22),
    margin=dict(l=160, r=60, t=40, b=40),
)
st.plotly_chart(fig_rank, use_container_width=True)

st.subheader("Price vs Net Yield")

fig_sc = px.scatter(
    opp.dropna(subset=["net_yield_calc", "price"]),
    x="price", y="net_yield_calc",
    color="jurisdiction", color_discrete_map=JURIS_COLORS,
    size=opp["homes_sold"].clip(lower=1).fillna(1),
    size_max=25,
    hover_name="neighborhood",
    hover_data={"zip": True, "property_type": True,
                "price": ":$,.0f", "net_yield_calc": ":.2f%"},
    labels={"price": "Median Price ($)", "net_yield_calc": "Net Yield (%)"},
    height=460,
)
fig_sc.add_vline(x=inv_budget, line_dash="dash", line_color="red",
                 annotation_text=f"Budget ${inv_budget:,.0f}")
fig_sc.add_hline(y=0, line_color="grey", line_width=0.5)
fig_sc.update_layout(title="Each point = zip x property type · size = transaction volume")
st.plotly_chart(fig_sc, use_container_width=True)

st.subheader("Net Yield vs Days on Market")
dom_data = opp.dropna(subset=["net_yield_calc", "median_dom"])
if not dom_data.empty:
    fig_dom = px.scatter(
        dom_data, x="median_dom", y="net_yield_calc",
        color="jurisdiction", color_discrete_map=JURIS_COLORS,
        hover_name="neighborhood",
        labels={"median_dom": "Days on Market", "net_yield_calc": "Net Yield (%)"},
        height=400,
    )
    fig_dom.add_hline(y=0, line_color="grey", line_width=0.5)
    fig_dom.update_layout(title="Longer DOM may signal negotiation opportunity")
    st.plotly_chart(fig_dom, use_container_width=True)

st.divider()
st.subheader("Opportunity Details")
tbl_cols = ["neighborhood", "zip", "jurisdiction", "property_type",
            "price", "sqft", "monthly_rent_used",
            "gross_yield_calc", "net_yield_calc", "price_to_rent",
            "median_dom", "avg_sale_to_list"]
tbl_cols = [c for c in tbl_cols if c in opp.columns]
tbl = opp[tbl_cols].copy()

fmt = {
    "price": "${:,.0f}", "sqft": "{:,.0f}", "monthly_rent_used": "${:,.0f}",
    "gross_yield_calc": "{:.1f}%", "net_yield_calc": "{:.1f}%",
    "price_to_rent": "{:.1f}x", "median_dom": "{:.0f}", "avg_sale_to_list": "{:.1%}",
}
for col, f in fmt.items():
    if col in tbl.columns:
        tbl[col] = tbl[col].map(lambda x, _f=f: _f.format(x) if pd.notna(x) else "N/A")


def _row_color(row):
    try:
        v = float(str(opp.loc[row.name, "net_yield_calc"]))
    except Exception:
        return [""] * len(row)
    color = "#d4edda" if v >= 5 else "#fff3cd" if v >= 3 else "#f8d7da"
    return [f"background-color: {color}"] * len(row)


tbl = tbl.rename(columns={
    "neighborhood": "Neighborhood", "zip": "Zip", "jurisdiction": "Jurisdiction",
    "property_type": "Type", "price": "Price", "sqft": "Sqft",
    "monthly_rent_used": "Rent/mo", "gross_yield_calc": "Gross Yield",
    "net_yield_calc": "Net Yield", "price_to_rent": "P/R Ratio",
    "median_dom": "DOM", "avg_sale_to_list": "Sale/List",
})
st.caption("Row colors: green >= 5% net yield · yellow 3-5% · red < 3%")
st.dataframe(tbl.style.apply(_row_color, axis=1), use_container_width=True)
