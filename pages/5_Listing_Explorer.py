import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import csv
from pathlib import Path

st.title("Listing Explorer")
st.caption("Individual Redfin listings — filter, sort, and explore")

st.info(
    "**Data & Methodology:** Active listings scraped from Redfin (DC, Arlington, Alexandria, Richmond). "
    "Rent estimates from HUD FY2025 Fair Market Rents by zip and bedroom count. "
    "Yield metrics range from quick gross yield to a full after-tax model with depreciation, debt service, and appreciation."
)

DATA = st.session_state.get("DATA", Path(__file__).resolve().parent.parent / "data")

AREA_COLORS = {
    "NW DC": "#0071BC", "Arlington": "#2E7D32",
    "Alexandria": "#C62828", "Richmond": "#795548",
}

PROP_TAX_RATES = {
    "Washington": 0.0085, "Arlington": 0.01036, "Alexandria": 0.01110,
    "Falls Church": 0.01225, "Fairfax": 0.01110, "Richmond": 0.0120,
    "Henrico": 0.0087, "Chesterfield": 0.0095,
}


def get_prop_tax_rate(city, state):
    city_clean = city.strip().title() if city else ""
    if state == "DC":
        return PROP_TAX_RATES["Washington"]
    for key in PROP_TAX_RATES:
        if key.lower() in city_clean.lower():
            return PROP_TAX_RATES[key]
    if state == "VA":
        return 0.0107
    return 0.01


@st.cache_data
def load_fmr():
    fmr = {}
    for src in [DATA / "hud_fmr_2025.csv", DATA / "hud_fmr_new_metros.csv"]:
        if src.exists():
            with open(src) as f:
                for r in csv.DictReader(f):
                    fmr[r["zip"]] = r
    return fmr


def estimate_rent(fmr, zc, beds, ptype):
    if zc not in fmr:
        return None
    f = fmr[zc]
    br = max(1, min(beds, 4))
    if ptype == "Townhouse":
        br = max(2, br)
    key = f"fmr_{br}br"
    val = f.get(key)
    return int(val) if val else None


@st.cache_data
def load_listings():
    areas = {
        "Alexandria": DATA / "redfin_alexandria_new.csv",
        "Arlington": DATA / "redfin_arlington_new.csv",
        "NW DC": DATA / "redfin_dc_new.csv",
        "Richmond": DATA / "redfin_richmond_new.csv",
    }
    fmr = load_fmr()
    records = []
    for area_name, path in areas.items():
        if not path.exists():
            continue
        with open(path) as f:
            for r in csv.DictReader(f):
                if r.get("SALE TYPE", "").startswith("In accordance"):
                    continue
                try:
                    price = float(r.get("PRICE", 0))
                except (ValueError, TypeError):
                    continue
                if price <= 0:
                    continue

                beds = 0
                try:
                    beds = int(float(r.get("BEDS", 0)))
                except (ValueError, TypeError):
                    pass
                baths = 0
                try:
                    baths = float(r.get("BATHS", 0))
                except (ValueError, TypeError):
                    pass
                sqft = 0
                try:
                    sqft = float(r.get("SQUARE FEET", 0))
                except (ValueError, TypeError):
                    pass
                hoa = 0
                try:
                    hoa = float(r.get("HOA/MONTH", 0))
                except (ValueError, TypeError):
                    pass
                ppsf = 0
                try:
                    ppsf = float(r.get("$/SQUARE FEET", 0))
                except (ValueError, TypeError):
                    pass
                yr_built = 0
                try:
                    yr_built = int(float(r.get("YEAR BUILT", 0)))
                except (ValueError, TypeError):
                    pass

                zc = r.get("ZIP OR POSTAL CODE", "").strip()
                state = r.get("STATE OR PROVINCE", "").strip()
                city = r.get("CITY", "").strip()
                ptype = r.get("PROPERTY TYPE", "")

                prop_tax_rate = get_prop_tax_rate(city, state)
                est_tax_annual = price * prop_tax_rate
                est_rent = estimate_rent(fmr, zc, beds, ptype)

                lat = lon = None
                try:
                    lat = float(r.get("LATITUDE", ""))
                    lon = float(r.get("LONGITUDE", ""))
                except (ValueError, TypeError):
                    pass

                records.append({
                    "area": area_name, "address": r.get("ADDRESS", ""),
                    "city": city, "state": state, "zip": zc,
                    "price": price, "beds": beds, "baths": baths,
                    "sqft": sqft, "hoa": hoa, "ppsf": ppsf,
                    "yr_built": yr_built, "ptype": ptype,
                    "prop_tax_rate": prop_tax_rate,
                    "est_tax_annual": est_tax_annual,
                    "est_rent": est_rent,
                    "lat": lat, "lon": lon,
                    "url": r.get("URL (SEE https://www.redfin.com/buy-a-home/comparative-market-analysis FOR INFO ON PRICING)", ""),
                })
    return pd.DataFrame(records)


listings = load_listings()

if listings.empty:
    st.warning("No listings data found.")
    st.stop()


def calc_one_pct_rule(price, est_rent):
    if price <= 0 or est_rent is None or est_rent <= 0:
        return None
    return est_rent / price * 100


def calc_gross_yield(price, est_rent):
    if price <= 0 or est_rent is None or est_rent <= 0:
        return None
    return est_rent * 12 / price * 100


def calc_net_yield(price, est_rent, hoa, est_tax_annual, mgmt_pct, maint_pct):
    if price <= 0 or est_rent is None or est_rent <= 0:
        return None
    annual_rent = est_rent * 12
    annual_hoa = hoa * 12
    annual_mgmt = annual_rent * mgmt_pct
    annual_maint = price * maint_pct
    noi = annual_rent - annual_hoa - est_tax_annual - annual_mgmt - annual_maint
    return noi / price * 100


def calc_full_model(price, est_rent, hoa, est_tax_annual, prop_tax_rate,
                    mgmt_pct, maint_pct, fed_tax_rate,
                    down_pct, mortgage_rate, loan_term_yrs, appreciation_rate,
                    hold_years):
    if price <= 0 or est_rent is None or est_rent <= 0:
        return None

    down_payment = price * down_pct
    loan = price - down_payment
    closing_costs = price * 0.03
    total_cash_in = down_payment + closing_costs

    mr = mortgage_rate / 12
    n = loan_term_yrs * 12
    if mr > 0 and loan > 0:
        monthly_pmt = loan * (mr * (1 + mr) ** n) / ((1 + mr) ** n - 1)
    elif loan > 0:
        monthly_pmt = loan / n
    else:
        monthly_pmt = 0

    annual_rent = est_rent * 12
    annual_hoa = hoa * 12
    annual_mgmt = annual_rent * mgmt_pct
    annual_maint = price * maint_pct
    annual_mortgage = monthly_pmt * 12

    annual_interest_yr1 = loan * mortgage_rate if loan > 0 else 0

    total_opex = annual_hoa + est_tax_annual + annual_mgmt + annual_maint
    noi = annual_rent - total_opex

    building_value = price * 0.80
    annual_depreciation = building_value / 27.5

    taxable_income = annual_rent - total_opex - annual_interest_yr1 - annual_depreciation
    fed_tax = max(0, taxable_income * fed_tax_rate)

    annual_cf_after_tax = noi - annual_mortgage - fed_tax
    monthly_cf_after_tax = annual_cf_after_tax / 12

    coc = annual_cf_after_tax / total_cash_in * 100 if total_cash_in > 0 else 0

    balance = loan
    total_principal_paid = 0
    for m in range(1, hold_years * 12 + 1):
        interest = balance * mr if mr > 0 else 0
        principal = monthly_pmt - interest
        principal = min(principal, balance)
        balance -= principal
        balance = max(balance, 0)
        total_principal_paid += principal

    future_value = price * (1 + appreciation_rate) ** hold_years
    appreciation_gain = future_value - price

    total_cf = annual_cf_after_tax * hold_years
    total_return = total_cf + total_principal_paid + appreciation_gain
    total_return_pct = total_return / total_cash_in * 100 if total_cash_in > 0 else 0
    annualized_return = (1 + total_return / total_cash_in) ** (1 / hold_years) - 1 if total_cash_in > 0 else 0

    return {
        "monthly_cf": monthly_cf_after_tax,
        "annual_cf": annual_cf_after_tax,
        "coc_return": coc,
        "noi": noi,
        "fed_tax": fed_tax,
        "depreciation": annual_depreciation,
        "total_return": total_return,
        "total_return_pct": total_return_pct,
        "annualized_return": annualized_return * 100,
        "equity_buildup": total_principal_paid,
        "appreciation_gain": appreciation_gain,
        "total_cash_in": total_cash_in,
    }


with st.sidebar:
    st.header("Filters")
    sel_areas = st.multiselect("Area", sorted(listings["area"].unique().tolist()),
                               default=sorted(listings["area"].unique().tolist()))
    all_ptypes = sorted(listings["ptype"].unique().tolist())
    sel_ptypes = st.multiselect("Property Type", all_ptypes,
                                default=[p for p in all_ptypes if "Condo" in p or "Townhouse" in p] or all_ptypes[:2])
    price_min, price_max = st.slider(
        "Price Range ($)", 0, int(listings["price"].max()),
        (0, int(listings["price"].quantile(0.95))), 10_000, format="$%d"
    )
    bed_opts = sorted(listings["beds"].unique().tolist())
    sel_beds = st.multiselect("Bedrooms", bed_opts, default=bed_opts)
    max_hoa = st.slider("Max HOA ($/mo)", 0, int(listings["hoa"].max()) + 100,
                         int(listings["hoa"].max()) + 100, 50)

    st.divider()
    st.header("Financial Model Inputs")
    fm_mgmt_pct = st.slider("Management Fee (%)", 0, 20, 10, help="% of gross rent") / 100
    fm_maint_pct = st.slider("Maintenance (% of price/yr)", 0.0, 3.0, 1.0, 0.1) / 100
    fm_fed_tax = st.slider("Federal Tax on Rental Income (%)", 0, 37, 12) / 100
    fm_no_mortgage = st.checkbox("No Mortgage (100% cash)", value=True)
    if fm_no_mortgage:
        fm_down_pct = 1.0
        fm_mortgage_rate = 0.0
        fm_loan_term = 30
        st.caption("All-cash purchase — no financing costs.")
    else:
        fm_down_pct = st.slider("Down Payment (%)", 3, 50, 20) / 100
        fm_mortgage_rate = st.number_input("Mortgage Rate (%)", 0.5, 15.0, 6.75, 0.05) / 100
        fm_loan_term = st.selectbox("Loan Term (years)", [15, 20, 30], index=2)
    fm_appreciation = st.slider("Annual Appreciation (%)", 0.0, 8.0, 3.5, 0.1) / 100
    fm_hold_years = st.slider("Hold Period (years)", 1, 30, 10)

df = listings[
    (listings["area"].isin(sel_areas))
    & (listings["ptype"].isin(sel_ptypes))
    & (listings["price"] >= price_min)
    & (listings["price"] <= price_max)
    & (listings["beds"].isin(sel_beds))
    & (listings["hoa"] <= max_hoa)
].copy()

if df.empty:
    st.warning("No listings match current filters.")
    st.stop()

df["one_pct_ratio"] = df.apply(lambda r: calc_one_pct_rule(r["price"], r["est_rent"]), axis=1)
df["gross_yield"] = df.apply(lambda r: calc_gross_yield(r["price"], r["est_rent"]), axis=1)
df["net_yield"] = df.apply(
    lambda r: calc_net_yield(r["price"], r["est_rent"], r["hoa"], r["est_tax_annual"],
                             fm_mgmt_pct, fm_maint_pct), axis=1)

fm_results = df.apply(
    lambda r: calc_full_model(
        r["price"], r["est_rent"], r["hoa"], r["est_tax_annual"], r["prop_tax_rate"],
        fm_mgmt_pct, fm_maint_pct, fm_fed_tax,
        fm_down_pct, fm_mortgage_rate, fm_loan_term, fm_appreciation, fm_hold_years
    ), axis=1
)
fm_df = fm_results.apply(pd.Series)
for col in fm_df.columns:
    df[f"fm_{col}"] = fm_df[col]

st.markdown(f"**{len(df)}** listings matched")

mc = st.columns(5)
mc[0].metric("Median Price", f"${df['price'].median():,.0f}")
mc[1].metric("Median $/sqft", f"${df.loc[df['ppsf']>0, 'ppsf'].median():,.0f}" if (df["ppsf"] > 0).any() else "N/A")
mc[2].metric("Median HOA", f"${df.loc[df['hoa']>0, 'hoa'].median():,.0f}" if (df["hoa"] > 0).any() else "N/A")
avg_gross = df["gross_yield"].dropna().mean()
mc[3].metric("Avg Gross Yield", f"{avg_gross:.1f}%" if pd.notna(avg_gross) else "N/A")
avg_coc = df["fm_coc_return"].dropna().mean()
mc[4].metric("Avg Cash-on-Cash", f"{avg_coc:.1f}%" if pd.notna(avg_coc) else "N/A")

with st.expander("Yield Calculation Methods"):
    st.markdown("""
| Method | Formula | Use Case |
|---|---|---|
| **1% Rule** | Monthly rent / price. Target: >= 1.0% | Fastest screen. If rent is >= 1% of price, worth a deeper look. |
| **Gross Yield** | Annual rent / price | Quick comparison across listings. Ignores all expenses. |
| **Net Yield** | (Rent - HOA - Property Tax - Mgmt Fee - Maintenance) / price | More realistic. Includes actual HOA from listing, local property tax rate, management fee (default 10%), and maintenance (default 1%/yr). |
| **Full Financial Model** | After-tax cash-on-cash + equity + appreciation | Complete picture. Adds: mortgage debt service, depreciation write-off (27.5yr straight-line, 80% building), federal income tax on net rental income, equity build-up from principal paydown, and price appreciation over hold period. |
""")

st.divider()

st.subheader("Listings Map")
map_data = df.dropna(subset=["lat", "lon"]).copy()
if not map_data.empty:
    map_color = st.radio("Color by", ["Area", "Net Yield", "Cash-on-Cash", "Price"],
                         horizontal=True, key="map_color")

    color_col = {"Area": "area", "Net Yield": "net_yield",
                 "Cash-on-Cash": "fm_coc_return", "Price": "price"}[map_color]

    if map_color == "Area":
        fig_map = px.scatter_map(
            map_data, lat="lat", lon="lon", color="area",
            color_discrete_map=AREA_COLORS,
            hover_name="address",
            hover_data={"lat": False, "lon": False, "price": ":$,.0f",
                        "beds": True, "ptype": True, "net_yield": ":.1f%"},
            zoom=10, height=500,
        )
    else:
        plot_data = map_data.dropna(subset=[color_col])
        cscale = "RdYlGn" if "yield" in map_color.lower() or "cash" in map_color.lower() else "Blues"
        fig_map = px.scatter_map(
            plot_data, lat="lat", lon="lon", color=color_col,
            color_continuous_scale=cscale,
            hover_name="address",
            hover_data={"lat": False, "lon": False, "price": ":$,.0f",
                        "beds": True, "net_yield": ":.1f%"},
            zoom=10, height=500,
        )
    fig_map.update_layout(margin=dict(l=0, r=0, t=0, b=0))
    st.plotly_chart(fig_map, use_container_width=True)

st.subheader("Price Distributions")
c1, c2 = st.columns(2)

with c1:
    fig_box = px.box(df, x="area", y="price", color="area",
                     color_discrete_map=AREA_COLORS,
                     labels={"price": "Price ($)", "area": ""},
                     height=400)
    fig_box.update_layout(showlegend=False, title="Price by Area")
    st.plotly_chart(fig_box, use_container_width=True)

with c2:
    df_ppsf = df[df["ppsf"] > 0]
    if not df_ppsf.empty:
        fig_ppsf = px.box(df_ppsf, x="area", y="ppsf", color="area",
                          color_discrete_map=AREA_COLORS,
                          labels={"ppsf": "$/sqft", "area": ""},
                          height=400)
        fig_ppsf.update_layout(showlegend=False, title="$/sqft by Area")
        st.plotly_chart(fig_ppsf, use_container_width=True)

c3, c4 = st.columns(2)
with c3:
    df_hoa = df[df["hoa"] > 0]
    if not df_hoa.empty:
        fig_hoa = px.box(df_hoa, x="area", y="hoa", color="area",
                         color_discrete_map=AREA_COLORS,
                         labels={"hoa": "HOA $/mo", "area": ""},
                         height=400)
        fig_hoa.update_layout(showlegend=False, title="HOA by Area")
        st.plotly_chart(fig_hoa, use_container_width=True)

with c4:
    df_yield = df.dropna(subset=["net_yield"])
    if not df_yield.empty:
        fig_yield = px.box(df_yield, x="area", y="net_yield", color="area",
                           color_discrete_map=AREA_COLORS,
                           labels={"net_yield": "Net Yield (%)", "area": ""},
                           height=400)
        fig_yield.add_hline(y=0, line_color="grey", line_width=0.5)
        fig_yield.update_layout(showlegend=False, title="Net Yield by Area")
        st.plotly_chart(fig_yield, use_container_width=True)

st.subheader("Price vs Yield")
yield_choice = st.radio("Yield metric", ["Gross Yield", "Net Yield", "Cash-on-Cash Return", "Annualized Total Return"],
                        horizontal=True, key="yield_scatter")
yield_col_map = {
    "Gross Yield": "gross_yield",
    "Net Yield": "net_yield",
    "Cash-on-Cash Return": "fm_coc_return",
    "Annualized Total Return": "fm_annualized_return",
}
y_col = yield_col_map[yield_choice]

scatter_data = df.dropna(subset=[y_col, "price"])
if not scatter_data.empty:
    fig_sc = px.scatter(
        scatter_data, x="price", y=y_col, color="area",
        color_discrete_map=AREA_COLORS,
        hover_name="address",
        hover_data={"price": ":$,.0f", "beds": True, "hoa": ":$,.0f",
                    y_col: ":.1f%"},
        labels={"price": "Price ($)", y_col: f"{yield_choice} (%)"},
        height=450,
    )
    fig_sc.add_hline(y=0, line_color="grey", line_width=0.5)
    st.plotly_chart(fig_sc, use_container_width=True)

st.divider()
st.subheader("Listing Detail Table")

sort_options = {
    "fm_annualized_return": "Annualized Return (desc)",
    "fm_coc_return": "Cash-on-Cash (desc)",
    "net_yield": "Net Yield (desc)",
    "gross_yield": "Gross Yield (desc)",
    "one_pct_ratio": "1% Rule (desc)",
    "price": "Price (asc)",
    "ppsf": "$/sqft (asc)",
    "hoa": "HOA (asc)",
}
sort_col = st.selectbox("Sort by", list(sort_options.keys()),
                         format_func=lambda x: sort_options[x])
ascending = sort_col in ("price", "ppsf", "hoa")

show_cols = ["area", "address", "city", "zip", "ptype", "beds", "baths",
             "sqft", "price", "ppsf", "hoa", "est_rent",
             "one_pct_ratio", "gross_yield", "net_yield",
             "fm_coc_return", "fm_annualized_return", "fm_monthly_cf"]
show_cols = [c for c in show_cols if c in df.columns]
tbl = df[show_cols].sort_values(sort_col, ascending=ascending, na_position="last").copy()

tbl_fmt = tbl.copy()
fmt_map = {
    "price": "${:,.0f}", "ppsf": "${:,.0f}", "hoa": "${:,.0f}",
    "est_rent": "${:,.0f}", "sqft": "{:,.0f}",
    "one_pct_ratio": "{:.2f}%", "gross_yield": "{:.1f}%",
    "net_yield": "{:.1f}%", "fm_coc_return": "{:.1f}%",
    "fm_annualized_return": "{:.1f}%", "fm_monthly_cf": "${:,.0f}",
}
for col, f in fmt_map.items():
    if col in tbl_fmt.columns:
        tbl_fmt[col] = tbl_fmt[col].map(
            lambda x, _f=f: _f.format(x) if pd.notna(x) and x != 0 else "N/A")

tbl_fmt = tbl_fmt.rename(columns={
    "area": "Area", "address": "Address", "city": "City", "zip": "Zip",
    "ptype": "Type", "beds": "Beds", "baths": "Baths", "sqft": "Sqft",
    "price": "Price", "ppsf": "$/sqft", "hoa": "HOA/mo",
    "est_rent": "Est Rent", "one_pct_ratio": "1% Rule",
    "gross_yield": "Gross Yld", "net_yield": "Net Yld",
    "fm_coc_return": "Cash/Cash", "fm_annualized_return": "Ann. Return",
    "fm_monthly_cf": "Monthly CF",
})


def _row_color(row):
    try:
        v = float(str(df.loc[row.name, "fm_coc_return"]))
    except Exception:
        return [""] * len(row)
    color = "#d4edda" if v >= 5 else "#fff3cd" if v >= 0 else "#f8d7da"
    return [f"background-color: {color}"] * len(row)


st.caption("Row colors: green >= 5% CoC · yellow 0-5% · red < 0% (negative cash flow)")
st.dataframe(tbl_fmt.style.apply(_row_color, axis=1), use_container_width=True, height=600)

st.divider()
st.subheader("Single Listing Financial Breakdown")

addresses = df.dropna(subset=["est_rent"]).sort_values("fm_coc_return", ascending=False)["address"].tolist()
if addresses:
    sel_addr = st.selectbox("Select a listing", addresses)
    row = df[df["address"] == sel_addr].iloc[0]

    fm = calc_full_model(
        row["price"], row["est_rent"], row["hoa"], row["est_tax_annual"], row["prop_tax_rate"],
        fm_mgmt_pct, fm_maint_pct, fm_fed_tax,
        fm_down_pct, fm_mortgage_rate, fm_loan_term, fm_appreciation, fm_hold_years
    )

    if fm:
        st.markdown(f"**{sel_addr}** — {row['ptype']} · {row['beds']}BR/{row['baths']}BA · "
                    f"{row['sqft']:,.0f} sqft · **${row['price']:,.0f}**")

        km = st.columns(6)
        km[0].metric("1% Rule", f"{row['one_pct_ratio']:.2f}%",
                     delta="Pass" if row["one_pct_ratio"] and row["one_pct_ratio"] >= 1.0 else "Fail")
        km[1].metric("Gross Yield", f"{row['gross_yield']:.1f}%" if pd.notna(row["gross_yield"]) else "N/A")
        km[2].metric("Net Yield", f"{row['net_yield']:.1f}%" if pd.notna(row["net_yield"]) else "N/A")
        km[3].metric("Cash-on-Cash", f"{fm['coc_return']:.1f}%")
        km[4].metric("Monthly CF (after tax)", f"${fm['monthly_cf']:,.0f}")
        km[5].metric(f"Ann. Return ({fm_hold_years}yr)", f"{fm['annualized_return']:.1f}%")

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Annual Income & Expenses**")
            annual_rent = row["est_rent"] * 12
            items = {
                "Gross Rent": annual_rent,
                "- HOA": -(row["hoa"] * 12),
                "- Property Tax": -row["est_tax_annual"],
                f"- Management ({fm_mgmt_pct*100:.0f}%)": -(annual_rent * fm_mgmt_pct),
                f"- Maintenance ({fm_maint_pct*100:.0f}%)": -(row["price"] * fm_maint_pct),
                "= NOI": fm["noi"],
                "- Mortgage Payment": -(row["price"] * (1 - fm_down_pct) * fm_mortgage_rate * 12 /
                                        (1 - (1 + fm_mortgage_rate / 12) ** -(fm_loan_term * 12))
                                        if fm_mortgage_rate > 0 and fm_down_pct < 1 else 0),
                "- Depreciation write-off": -fm["depreciation"],
                f"- Federal Tax ({fm_fed_tax*100:.0f}%)": -fm["fed_tax"],
                "= After-Tax Cash Flow": fm["annual_cf"],
            }
            breakdown = pd.DataFrame({"Item": items.keys(), "Annual ($)": items.values()})
            breakdown["Annual ($)"] = breakdown["Annual ($)"].map(
                lambda x: f"${x:,.0f}" if x >= 0 else f"-${abs(x):,.0f}")
            st.dataframe(breakdown, use_container_width=True, hide_index=True)

        with c2:
            st.markdown(f"**{fm_hold_years}-Year Total Return**")
            return_items = {
                "Cash Invested (down + closing)": fm["total_cash_in"],
                f"Cumulative Cash Flow ({fm_hold_years}yr)": fm["annual_cf"] * fm_hold_years,
                "Equity Built (principal paydown)": fm["equity_buildup"],
                f"Appreciation ({fm_appreciation*100:.1f}%/yr)": fm["appreciation_gain"],
                "Total Return ($)": fm["total_return"],
                "Total Return (%)": None,
                "Annualized Return (%)": None,
            }
            ret_df = pd.DataFrame({"Item": return_items.keys(), "Value": return_items.values()})
            ret_df.loc[ret_df["Item"] == "Total Return (%)", "Value"] = fm["total_return_pct"]
            ret_df.loc[ret_df["Item"] == "Annualized Return (%)", "Value"] = fm["annualized_return"]

            def fmt_return(row):
                if "(%)" in row["Item"]:
                    return f"{row['Value']:.1f}%"
                v = row["Value"]
                if pd.isna(v):
                    return "N/A"
                return f"${v:,.0f}" if v >= 0 else f"-${abs(v):,.0f}"

            ret_df["Value"] = ret_df.apply(fmt_return, axis=1)
            st.dataframe(ret_df, use_container_width=True, hide_index=True)

        wf_items = ["Gross Rent", "HOA", "Prop Tax", "Mgmt Fee", "Maint", "Mortgage", "Fed Tax", "Cash Flow"]
        wf_vals = [
            annual_rent,
            -(row["hoa"] * 12),
            -row["est_tax_annual"],
            -(annual_rent * fm_mgmt_pct),
            -(row["price"] * fm_maint_pct),
            -(row["price"] * (1 - fm_down_pct) * fm_mortgage_rate * 12 /
              (1 - (1 + fm_mortgage_rate / 12) ** -(fm_loan_term * 12))
              if fm_mortgage_rate > 0 and fm_down_pct < 1 else 0),
            -fm["fed_tax"],
            fm["annual_cf"],
        ]
        wf_measures = ["absolute"] + ["relative"] * 6 + ["total"]

        fig_wf = go.Figure(go.Waterfall(
            x=wf_items, y=wf_vals, measure=wf_measures,
            connector=dict(line=dict(color="#888")),
            increasing=dict(marker=dict(color="#4CAF50")),
            decreasing=dict(marker=dict(color="#F44336")),
            totals=dict(marker=dict(color="#2196F3" if fm["annual_cf"] >= 0 else "#F44336")),
            text=[f"${abs(v):,.0f}" for v in wf_vals],
            textposition="outside",
        ))
        fig_wf.update_layout(
            title="Annual Cash Flow Waterfall",
            yaxis_title="$", height=420,
            showlegend=False,
        )
        st.plotly_chart(fig_wf, use_container_width=True)
