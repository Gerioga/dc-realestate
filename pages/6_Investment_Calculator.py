import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from pathlib import Path

st.title("Investment Calculator")
st.caption("Mortgage amortization, equity build-up, true cost of ownership, and the 1% rule")

st.info(
    "**Data & Methodology:** User-defined inputs for purchase price, financing, and costs. "
    "Mortgage amortization uses standard fixed-rate formulas. Equity projections combine principal "
    "paydown with neighborhood-specific appreciation from ZHVI data. All projections shown in real (inflation-adjusted) terms. "
    "Tax on rental income uses 12% flat rate with net election (deducting expenses before tax)."
)

DATA = st.session_state.get("DATA", Path(__file__).resolve().parent.parent / "data")

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


@st.cache_data
def load_zhvi():
    df = pd.read_csv(DATA / "zhvi_condo.csv", dtype={"zip": str})
    return df


@st.cache_data
def compute_neighborhood_appreciation(zhvi_df):
    """Compute 5-year and 10-year CAGR for each neighborhood from ZHVI data."""
    year_cols = sorted([c for c in zhvi_df.columns if c.startswith("zhvi_")])
    records = []
    for _, row in zhvi_df.iterrows():
        nh = row["neighborhood"]
        zc = row["zip"]
        vals = {int(c.replace("zhvi_", "")): row[c] for c in year_cols if pd.notna(row[c]) and row[c] > 0}
        if len(vals) < 2:
            continue
        years_sorted = sorted(vals.keys())
        latest_yr = years_sorted[-1]
        latest_val = vals[latest_yr]

        cagr_5 = cagr_10 = cagr_all = None
        for window, label in [(5, "cagr_5"), (10, "cagr_10")]:
            target_yr = latest_yr - window
            if target_yr in vals and vals[target_yr] > 0:
                c = (latest_val / vals[target_yr]) ** (1 / window) - 1
                if label == "cagr_5":
                    cagr_5 = c
                else:
                    cagr_10 = c

        first_yr = years_sorted[0]
        n = latest_yr - first_yr
        if n > 0 and vals[first_yr] > 0:
            cagr_all = (latest_val / vals[first_yr]) ** (1 / n) - 1

        records.append({
            "zip": zc, "neighborhood": nh,
            "cagr_5yr": cagr_5, "cagr_10yr": cagr_10, "cagr_all": cagr_all,
            "latest_value": latest_val,
        })
    return pd.DataFrame(records)


zhvi_df = load_zhvi()
appreciation_df = compute_neighborhood_appreciation(zhvi_df)


def calculate_amortization(principal, annual_rate, term_years):
    monthly_rate = annual_rate / 100 / 12
    n_payments = term_years * 12
    if monthly_rate == 0:
        monthly_payment = principal / n_payments
    else:
        monthly_payment = principal * (monthly_rate * (1 + monthly_rate) ** n_payments) / (
            (1 + monthly_rate) ** n_payments - 1)

    records = []
    balance = principal
    for month in range(1, n_payments + 1):
        interest = balance * monthly_rate
        principal_paid = monthly_payment - interest
        balance -= principal_paid
        balance = max(balance, 0.0)
        records.append({
            "month": month, "year": (month - 1) // 12 + 1,
            "payment": monthly_payment, "principal": principal_paid,
            "interest": interest, "balance": balance,
        })
    return pd.DataFrame(records)


def calculate_home_value(purchase_price, appreciation_rate, years):
    return purchase_price * (1 + appreciation_rate / 100) ** np.arange(years + 1)


def adjust_for_inflation(values, inflation_rate):
    deflator = (1 + inflation_rate / 100) ** np.arange(len(values))
    return values / deflator


# ── Sidebar ──
with st.sidebar:
    st.header("Neighborhood")
    nh_options = sorted(appreciation_df["neighborhood"].unique().tolist())
    sel_nh = st.selectbox("Select Neighborhood", ["Manual entry"] + nh_options,
                          index=0, help="Pick a neighborhood to auto-fill appreciation from ZHVI data")

    if sel_nh != "Manual entry":
        nh_row = appreciation_df[appreciation_df["neighborhood"] == sel_nh].iloc[0]
        # Use 5yr CAGR if available, else 10yr, else all
        data_appreciation = nh_row["cagr_5yr"] if pd.notna(nh_row["cagr_5yr"]) else \
            nh_row["cagr_10yr"] if pd.notna(nh_row["cagr_10yr"]) else \
            nh_row["cagr_all"] if pd.notna(nh_row["cagr_all"]) else 0.03
        data_appreciation_pct = round(data_appreciation * 100, 1)
        cagr_info = []
        if pd.notna(nh_row["cagr_5yr"]):
            cagr_info.append(f"5yr: {nh_row['cagr_5yr']:.1%}")
        if pd.notna(nh_row["cagr_10yr"]):
            cagr_info.append(f"10yr: {nh_row['cagr_10yr']:.1%}")
        if pd.notna(nh_row["cagr_all"]):
            cagr_info.append(f"All: {nh_row['cagr_all']:.1%}")
        st.caption(f"ZHVI CAGR: {' · '.join(cagr_info)}")
    else:
        data_appreciation_pct = 3.5

    st.header("Property Details")
    purchase_price = st.number_input("Purchase Price ($)", 50_000, 5_000_000, 550_000, 5_000)
    purchase_year = st.number_input("Purchase Year", 2000, 2030, 2025)

    st.header("Mortgage")
    no_mortgage = st.checkbox("No Mortgage (100% cash)", value=True)
    if no_mortgage:
        down_payment_pct = 100
        mortgage_rate = 0.0
        loan_term = 30
        st.caption("All-cash purchase — no financing costs.")
    else:
        down_payment_pct = st.slider("Down Payment (%)", 3, 50, 20)
        mortgage_rate = st.number_input("Mortgage Rate (%)", 0.5, 15.0, 6.75, 0.05)
        loan_term = st.selectbox("Loan Term (years)", [15, 20, 30], index=2)
    down_payment = purchase_price * down_payment_pct / 100
    st.caption(f"Down payment: ${down_payment:,.0f}")

    st.header("Monthly Costs")
    hoa_monthly = st.number_input("HOA + Condo Fees ($/mo)", 0, 5_000, 500, 25)
    property_tax_annual = st.number_input("Annual Property Tax ($)", 0, 50_000, 5_500, 100)

    st.header("Rental Income")
    rent_estimate = st.number_input("Expected Monthly Rent ($)", 500, 10_000, 2_800, 50)
    rent_tax_rate = st.number_input("Tax Rate on Net Rental Income (%)", 0.0, 50.0, 12.0, 0.5,
                                     help="12% flat rate with net election: tax is applied to rent minus deductible expenses")

    st.header("Rates & Assumptions")
    appreciation_rate = st.slider("Annual Appreciation (%)", -5.0, 15.0, data_appreciation_pct, 0.1,
                                  help="Auto-filled from ZHVI 5yr CAGR if neighborhood selected")
    inflation_rate = st.slider("Annual Inflation (%)", 0.0, 8.0, 3.0, 0.1)
    maintenance_rate = st.slider("Annual Maintenance (% of value)", 0.0, 3.0, 1.0, 0.1)
    opportunity_rate = st.slider("Opportunity Cost / S&P (%)", 0.0, 15.0, 7.0, 0.1)

    st.header("Include in Calculations")
    include_maintenance = st.checkbox("Maintenance", value=True)
    include_hoa = st.checkbox("HOA + Condo Fees", value=True)
    include_property_tax = st.checkbox("Property Tax", value=True)
    include_rent_tax = st.checkbox("Tax on Rental Income", value=True)

# ── Core calculations ──
loan_principal = purchase_price - down_payment
if loan_principal > 0:
    amort_df = calculate_amortization(loan_principal, mortgage_rate, loan_term)
    monthly_payment = amort_df["payment"].iloc[0]
else:
    amort_df = pd.DataFrame({
        "month": range(1, loan_term * 12 + 1),
        "year": [(m - 1) // 12 + 1 for m in range(1, loan_term * 12 + 1)],
        "payment": 0.0, "principal": 0.0, "interest": 0.0, "balance": 0.0,
    })
    monthly_payment = 0.0

property_tax_monthly = property_tax_annual / 12
analysis_years = loan_term
home_values = calculate_home_value(purchase_price, appreciation_rate, analysis_years)
opp_cost = down_payment * (1 + opportunity_rate / 100) ** np.arange(analysis_years + 1)

# Effective monthly costs based on toggles
eff_hoa = hoa_monthly if include_hoa else 0
eff_tax_annual = property_tax_annual if include_property_tax else 0
eff_tax_monthly = eff_tax_annual / 12
eff_maintenance_rate = maintenance_rate if include_maintenance else 0

yearly_data = []
for yr in range(analysis_years + 1):
    cum_amort = amort_df[amort_df["year"] <= yr]
    balance = amort_df[amort_df["year"] == yr]["balance"].iloc[-1] if yr > 0 else loan_principal
    cum_interest = cum_amort["interest"].sum()
    cum_principal = cum_amort["principal"].sum()
    maintenance_cost = home_values[yr] * eff_maintenance_rate / 100

    # Annual rental income and tax
    annual_rent = rent_estimate * 12
    annual_expenses = eff_hoa * 12 + eff_tax_annual + maintenance_cost + (cum_amort[cum_amort["year"] == yr]["interest"].sum() if yr > 0 else 0)
    net_rental_income = max(0, annual_rent - annual_expenses)
    rental_tax = net_rental_income * (rent_tax_rate / 100) if include_rent_tax else 0

    yearly_data.append({
        "year": yr, "calendar_year": purchase_year + yr,
        "home_value": home_values[yr],
        "remaining_balance": balance if yr > 0 else loan_principal,
        "equity": home_values[yr] - (balance if yr > 0 else loan_principal),
        "cum_interest": cum_interest, "cum_principal": cum_principal,
        "cum_hoa": eff_hoa * 12 * yr,
        "cum_tax": eff_tax_annual * yr,
        "cum_maintenance": sum(home_values[y] * eff_maintenance_rate / 100 for y in range(1, yr + 1)),
        "opportunity_cost": opp_cost[yr],
        "annual_rent": annual_rent if yr > 0 else 0,
        "annual_expenses": annual_expenses if yr > 0 else 0,
        "net_rental_income": net_rental_income if yr > 0 else 0,
        "rental_tax": rental_tax if yr > 0 else 0,
        "annual_cash_flow": (annual_rent - annual_expenses - rental_tax - (monthly_payment * 12)) if yr > 0 else 0,
    })

yearly_df = pd.DataFrame(yearly_data)
yearly_df["cum_total_paid"] = (
    yearly_df["cum_interest"] + yearly_df["cum_principal"]
    + yearly_df["cum_hoa"] + yearly_df["cum_tax"] + yearly_df["cum_maintenance"]
)
yearly_df["cum_rental_tax"] = yearly_df["rental_tax"].cumsum()
yearly_df["cum_total_paid"] = yearly_df["cum_total_paid"] + yearly_df["cum_rental_tax"]
yearly_df["net_cost"] = yearly_df["cum_total_paid"] - yearly_df["equity"]
yearly_df["cum_rent_if_renting"] = rent_estimate * 12 * yearly_df["year"]

# Inflation-adjusted columns
yearly_df["home_value_real"] = adjust_for_inflation(home_values, inflation_rate)
yearly_df["equity_real"] = adjust_for_inflation(yearly_df["equity"].values, inflation_rate)
yearly_df["cum_total_paid_real"] = adjust_for_inflation(yearly_df["cum_total_paid"].values, inflation_rate)
yearly_df["net_cost_real"] = adjust_for_inflation(yearly_df["net_cost"].values, inflation_rate)
yearly_df["annual_cash_flow_real"] = adjust_for_inflation(yearly_df["annual_cash_flow"].values, inflation_rate)
yearly_df["opportunity_cost_real"] = adjust_for_inflation(yearly_df["opportunity_cost"].values, inflation_rate)

# ── Tabs ──
tab1, tab2, tab3, tab4 = st.tabs(["1% Rule", "Monthly Costs", "Equity & Net Worth", "True Cost of Ownership"])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 1: 1% RULE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab1:
    st.subheader("The 1% Rule")
    st.caption("A property passes the 1% rule if monthly rent >= 1% of purchase price. "
               "It's a quick screening heuristic — not a full analysis.")

    one_pct_target = purchase_price * 0.01
    ratio_pct = (rent_estimate / purchase_price) * 100 if purchase_price > 0 else 0
    passes = rent_estimate >= one_pct_target

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Purchase Price", f"${purchase_price:,.0f}")
    c2.metric("Monthly Rent", f"${rent_estimate:,.0f}")
    c3.metric("1% Target", f"${one_pct_target:,.0f}/mo")
    c4.metric("Actual Ratio", f"{ratio_pct:.2f}%",
              delta="PASS" if passes else "FAIL",
              delta_color="normal" if passes else "inverse")

    if passes:
        st.success(f"This property **passes** the 1% rule. Rent (${rent_estimate:,.0f}) >= 1% of price (${one_pct_target:,.0f}).")
    else:
        gap = one_pct_target - rent_estimate
        st.warning(f"This property **fails** the 1% rule. You'd need **${gap:,.0f}/mo more** rent, "
                   f"or a price of **${rent_estimate * 100:,.0f}** or less at this rent level.")

    # Sensitivity table: what rent ratio at different prices
    st.subheader("Sensitivity: Rent Ratio at Different Prices & Rents")
    price_range = [int(purchase_price * m) for m in [0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3]]
    rent_range = [int(rent_estimate * m) for m in [0.8, 0.9, 1.0, 1.1, 1.2, 1.3]]
    sens_data = {}
    for r in rent_range:
        row = {}
        for p in price_range:
            pct = (r / p) * 100
            row[f"${p:,.0f}"] = f"{pct:.2f}%"
        sens_data[f"${r:,.0f}/mo"] = row
    sens_df = pd.DataFrame(sens_data).T
    sens_df.index.name = "Rent \\ Price"

    def _color_1pct(val):
        try:
            v = float(val.replace("%", ""))
            if v >= 1.0:
                return "background-color: #d4edda"
            elif v >= 0.8:
                return "background-color: #fff3cd"
            else:
                return "background-color: #f8d7da"
        except Exception:
            return ""

    st.dataframe(sens_df.style.map(_color_1pct), use_container_width=True)

    # Annual cash flow summary (real)
    st.subheader("Year 1 Cash Flow (Inflation-Adjusted)")

    maint_yr1 = home_values[1] * eff_maintenance_rate / 100 if analysis_years >= 1 else 0
    interest_yr1 = amort_df[amort_df["year"] == 1]["interest"].sum() if loan_principal > 0 else 0
    expenses_yr1 = eff_hoa * 12 + eff_tax_annual + maint_yr1 + interest_yr1
    net_income_yr1 = max(0, rent_estimate * 12 - expenses_yr1)
    tax_yr1 = net_income_yr1 * (rent_tax_rate / 100) if include_rent_tax else 0
    cash_flow_yr1 = rent_estimate * 12 - expenses_yr1 - tax_yr1 - monthly_payment * 12

    deflator_yr1 = 1 + inflation_rate / 100
    cash_flow_yr1_real = cash_flow_yr1 / deflator_yr1

    flow_items = {
        "Gross Rental Income": rent_estimate * 12,
        "(-) Mortgage P&I": -monthly_payment * 12,
    }
    if include_hoa:
        flow_items["(-) HOA + Fees"] = -eff_hoa * 12
    if include_property_tax:
        flow_items["(-) Property Tax"] = -eff_tax_annual
    if include_maintenance:
        flow_items["(-) Maintenance"] = -maint_yr1
    if include_rent_tax:
        flow_items[f"(-) Rental Income Tax ({rent_tax_rate:.0f}%)"] = -tax_yr1
    flow_items["= Net Cash Flow (nominal)"] = cash_flow_yr1
    flow_items["= Net Cash Flow (real)"] = cash_flow_yr1_real

    flow_df = pd.DataFrame({"Item": flow_items.keys(), "Amount": flow_items.values()})
    flow_df["Amount"] = flow_df["Amount"].map(lambda x: f"${x:,.0f}")
    st.dataframe(flow_df, use_container_width=True, hide_index=True)

    # Cash-on-cash return
    if down_payment > 0:
        coc_nominal = cash_flow_yr1 / down_payment * 100
        coc_real = cash_flow_yr1_real / down_payment * 100
        cc1, cc2 = st.columns(2)
        cc1.metric("Cash-on-Cash Return (nominal)", f"{coc_nominal:.1f}%")
        cc2.metric("Cash-on-Cash Return (real)", f"{coc_real:.1f}%")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 2: MONTHLY COSTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab2:
    st.subheader("Monthly Cost Breakdown")
    maintenance_monthly = purchase_price * eff_maintenance_rate / 100 / 12
    cost_items = {"Mortgage P&I": monthly_payment}
    if include_hoa:
        cost_items["HOA + Condo Fees"] = eff_hoa
    if include_property_tax:
        cost_items["Property Tax"] = eff_tax_monthly
    if include_maintenance:
        cost_items["Maintenance (est.)"] = maintenance_monthly

    total_monthly = sum(cost_items.values())
    cost_colors = ["#2196F3", "#FF9800", "#4CAF50", "#9C27B0"][:len(cost_items)]

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Monthly Cost", f"${total_monthly:,.0f}")
    c2.metric("Monthly Rent Income", f"${rent_estimate:,.0f}")
    delta = total_monthly - rent_estimate
    c3.metric("Cost vs Rent Delta", f"${abs(delta):,.0f}",
              delta=f"{'costs exceed rent' if delta > 0 else 'rent exceeds costs'}")

    fig_bar = go.Figure(go.Bar(
        x=list(cost_items.keys()), y=list(cost_items.values()),
        marker_color=cost_colors,
        text=[f"${v:,.0f}" for v in cost_items.values()], textposition="outside",
    ))
    fig_bar.add_hline(y=rent_estimate, line_dash="dash", line_color="red",
                      annotation_text=f"Rent ${rent_estimate:,.0f}")
    fig_bar.update_layout(title="Monthly Cost Components", yaxis_title="$/month",
                          showlegend=False, height=400)
    st.plotly_chart(fig_bar, use_container_width=True)

    # Monthly costs over time — all in real terms
    monthly_over_time = []
    for yr in range(1, analysis_years + 1):
        deflator = (1 + inflation_rate / 100) ** yr
        maint = home_values[yr] * eff_maintenance_rate / 100 / 12 / deflator
        monthly_over_time.append({
            "Year": purchase_year + yr,
            "Mortgage P&I": monthly_payment / deflator,
            "HOA + Fees": eff_hoa / deflator if include_hoa else 0,
            "Property Tax": eff_tax_monthly / deflator if include_property_tax else 0,
            "Maintenance": maint if include_maintenance else 0,
        })
    mdf = pd.DataFrame(monthly_over_time)
    active_cols = [c for c in ["Mortgage P&I", "HOA + Fees", "Property Tax", "Maintenance"]
                   if mdf[c].sum() > 0]
    mdf["Total"] = mdf[active_cols].sum(axis=1) if active_cols else 0

    fig_line = go.Figure()
    fig_line.add_trace(go.Scatter(x=mdf["Year"], y=mdf["Total"],
                                  name="Total Monthly Cost (real)", line=dict(color="#2196F3", width=2)))
    # Rent stays flat in real terms (assuming it grows with inflation)
    fig_line.add_trace(go.Scatter(
        x=mdf["Year"],
        y=[rent_estimate] * len(mdf),
        name="Rent (real, constant)", line=dict(color="red", dash="dash")))
    fig_line.update_layout(title="Monthly Cost vs Rent Over Time (Real $)", yaxis_title="$/month (real)", height=350)
    st.plotly_chart(fig_line, use_container_width=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 3: EQUITY & NET WORTH
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab3:
    st.subheader("Equity & Net Worth Over Time (Real $)")
    c1, c2, c3 = st.columns(3)
    c1.metric(f"Equity at Year {analysis_years} (real)", f"${yearly_df['equity_real'].iloc[-1]:,.0f}")
    c2.metric("Opportunity Cost (real)", f"${yearly_df['opportunity_cost_real'].iloc[-1]:,.0f}")
    c3.metric("Appreciation Gain (real)", f"${yearly_df['home_value_real'].iloc[-1] - purchase_price:,.0f}")

    fig_eq = go.Figure()
    fig_eq.add_trace(go.Scatter(x=yearly_df["calendar_year"], y=yearly_df["home_value_real"],
                                name="Home Value (real)", fill="tozeroy",
                                fillcolor="rgba(33,150,243,0.15)", line=dict(color="#2196F3")))
    fig_eq.add_trace(go.Scatter(x=yearly_df["calendar_year"], y=yearly_df["remaining_balance"],
                                name="Remaining Balance", fill="tozeroy",
                                fillcolor="rgba(244,67,54,0.15)", line=dict(color="#F44336")))
    fig_eq.add_trace(go.Scatter(x=yearly_df["calendar_year"], y=yearly_df["equity_real"],
                                name="Equity (real)", line=dict(color="#4CAF50", width=2.5)))
    fig_eq.add_trace(go.Scatter(x=yearly_df["calendar_year"], y=yearly_df["opportunity_cost_real"],
                                name="Opp. Cost (real)", line=dict(color="#FF9800", dash="dot", width=2)))
    fig_eq.update_layout(title="Home Value, Balance, Equity vs Opportunity Cost (Real $)",
                         yaxis_title="$ (real)", height=450)
    st.plotly_chart(fig_eq, use_container_width=True)

    breakeven_year = None
    for _, row in yearly_df.iterrows():
        if row["equity_real"] >= row["opportunity_cost_real"]:
            breakeven_year = int(row["calendar_year"])
            break
    if breakeven_year:
        st.info(f"Break-even (real): equity exceeds opportunity cost around **{breakeven_year}** "
                f"(year {breakeven_year - purchase_year}).")
    else:
        st.warning("Equity never exceeds opportunity cost under these assumptions (in real terms).")

    fig_amort = go.Figure()
    fig_amort.add_trace(go.Scatter(x=yearly_df["calendar_year"], y=yearly_df["cum_principal"],
                                   name="Cumulative Principal", fill="tozeroy",
                                   fillcolor="rgba(76,175,80,0.2)", line=dict(color="#4CAF50")))
    fig_amort.add_trace(go.Scatter(x=yearly_df["calendar_year"], y=yearly_df["cum_interest"],
                                   name="Cumulative Interest", fill="tozeroy",
                                   fillcolor="rgba(244,67,54,0.2)", line=dict(color="#F44336")))
    fig_amort.update_layout(title="Cumulative Principal vs Interest", yaxis_title="$", height=350)
    st.plotly_chart(fig_amort, use_container_width=True)

    # Cash flow over time
    st.subheader("Annual Cash Flow (Real $)")
    cf_df = yearly_df[yearly_df["year"] > 0].copy()
    fig_cf = go.Figure()
    fig_cf.add_trace(go.Bar(
        x=cf_df["calendar_year"], y=cf_df["annual_cash_flow_real"],
        marker_color=[("#4CAF50" if v >= 0 else "#F44336") for v in cf_df["annual_cash_flow_real"]],
        text=cf_df["annual_cash_flow_real"].map(lambda x: f"${x:,.0f}"), textposition="outside",
    ))
    fig_cf.add_hline(y=0, line_color="grey", line_width=1)
    fig_cf.update_layout(title="Annual Net Cash Flow After All Costs & Tax (Real $)",
                         yaxis_title="$ (real)", height=400, showlegend=False)
    st.plotly_chart(fig_cf, use_container_width=True)

    with st.expander("Amortization Schedule"):
        disp = amort_df.copy()
        disp["calendar_year"] = purchase_year + (disp["month"] - 1) // 12
        for col in ["payment", "principal", "interest", "balance"]:
            disp[col] = disp[col].map("${:,.2f}".format)
        st.dataframe(disp, use_container_width=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 4: TRUE COST OF OWNERSHIP
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab3:
    pass  # equity tab content above

with tab4:
    st.subheader("True Cost of Ownership (Real $)")
    total_paid_real = yearly_df["cum_total_paid_real"].iloc[-1]
    total_equity_real = yearly_df["equity_real"].iloc[-1]
    net_real = yearly_df["net_cost_real"].iloc[-1]

    c1, c2, c3 = st.columns(3)
    c1.metric(f"Total Paid (yr {analysis_years}, real)", f"${total_paid_real:,.0f}")
    c2.metric("Total Equity Gained (real)", f"${total_equity_real:,.0f}")
    c3.metric("Net Cost (real)", f"${net_real:,.0f}")

    fig_area = go.Figure()
    cost_traces = [
        ("cum_interest", "Interest", "rgba(244,67,54,0.6)"),
        ("cum_rental_tax", "Rental Income Tax", "rgba(255,87,34,0.6)"),
    ]
    if include_hoa:
        cost_traces.append(("cum_hoa", "HOA/Fees", "rgba(255,152,0,0.6)"))
    if include_property_tax:
        cost_traces.append(("cum_tax", "Property Tax", "rgba(156,39,176,0.6)"))
    if include_maintenance:
        cost_traces.append(("cum_maintenance", "Maintenance", "rgba(96,125,139,0.6)"))

    for col, name, fillcolor in cost_traces:
        fig_area.add_trace(go.Scatter(
            x=yearly_df["calendar_year"], y=yearly_df[col],
            name=name, stackgroup="costs",
            fillcolor=fillcolor, line=dict(color="rgba(0,0,0,0)"),
        ))
    fig_area.add_trace(go.Scatter(
        x=yearly_df["calendar_year"], y=yearly_df["equity_real"],
        name="Equity (real)", line=dict(color="#4CAF50", width=2.5),
    ))
    fig_area.add_trace(go.Scatter(
        x=yearly_df["calendar_year"], y=yearly_df["cum_rent_if_renting"],
        name="Cumulative Rent (if renting)", line=dict(color="red", dash="dash"),
    ))
    fig_area.update_layout(title="Cumulative Costs vs Equity",
                           yaxis_title="$", height=450)
    st.plotly_chart(fig_area, use_container_width=True)

    # Summary table — all real
    st.subheader("Yearly Summary (Real $)")
    display_df = yearly_df[[
        "calendar_year", "home_value_real", "remaining_balance", "equity_real",
        "cum_total_paid_real", "net_cost_real", "annual_cash_flow_real",
    ]].copy()
    display_df.columns = ["Year", "Home Value (Real)", "Loan Balance", "Equity (Real)",
                           "Total Paid (Real)", "Net Cost (Real)", "Cash Flow (Real)"]
    for col in display_df.columns[1:]:
        display_df[col] = display_df[col].map("${:,.0f}".format)
    st.dataframe(display_df, use_container_width=True)

    # Included/excluded summary
    st.caption("**Included in calculations:** " + ", ".join(
        [x for x, on in [("Maintenance", include_maintenance), ("HOA", include_hoa),
                          ("Property Tax", include_property_tax), ("Rental Tax", include_rent_tax)] if on]
    ) + " · **Excluded:** " + ", ".join(
        [x for x, on in [("Maintenance", include_maintenance), ("HOA", include_hoa),
                          ("Property Tax", include_property_tax), ("Rental Tax", include_rent_tax)] if not on]
    ))
