import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from pathlib import Path

st.title("Investment Calculator")
st.caption("Mortgage amortization, equity build-up, and true cost of ownership")

st.info(
    "**Data & Methodology:** User-defined inputs for purchase price, financing, and costs. "
    "Mortgage amortization uses standard fixed-rate formulas. Equity projections combine principal "
    "paydown with user-specified appreciation. True cost includes HOA, tax, and maintenance."
)


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


with st.sidebar:
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

    st.header("Rates & Assumptions")
    appreciation_rate = st.slider("Annual Appreciation (%)", 0.0, 10.0, 3.5, 0.1)
    inflation_rate = st.slider("Annual Inflation (%)", 0.0, 8.0, 3.0, 0.1)
    maintenance_rate = st.slider("Annual Maintenance (% of value)", 0.0, 3.0, 1.0, 0.1)
    opportunity_rate = st.slider("Opportunity Cost / S&P (%)", 0.0, 15.0, 7.0, 0.1)
    rent_estimate = st.number_input("Equivalent Monthly Rent ($)", 500, 10_000, 2_800, 50)

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

yearly_data = []
for yr in range(analysis_years + 1):
    cum_amort = amort_df[amort_df["year"] <= yr]
    balance = amort_df[amort_df["year"] == yr]["balance"].iloc[-1] if yr > 0 else loan_principal
    cum_interest = cum_amort["interest"].sum()
    cum_principal = cum_amort["principal"].sum()
    maintenance_cost = home_values[yr] * maintenance_rate / 100
    yearly_data.append({
        "year": yr, "calendar_year": purchase_year + yr,
        "home_value": home_values[yr],
        "remaining_balance": balance if yr > 0 else loan_principal,
        "equity": home_values[yr] - (balance if yr > 0 else loan_principal),
        "cum_interest": cum_interest, "cum_principal": cum_principal,
        "cum_hoa": hoa_monthly * 12 * yr,
        "cum_tax": property_tax_annual * yr,
        "cum_maintenance": maintenance_cost * yr,
        "opportunity_cost": opp_cost[yr],
    })

yearly_df = pd.DataFrame(yearly_data)
yearly_df["cum_total_paid"] = (
    yearly_df["cum_interest"] + yearly_df["cum_principal"]
    + yearly_df["cum_hoa"] + yearly_df["cum_tax"] + yearly_df["cum_maintenance"]
)
yearly_df["net_cost"] = yearly_df["cum_total_paid"] - yearly_df["equity"]
yearly_df["cum_rent"] = rent_estimate * 12 * yearly_df["year"]
yearly_df["home_value_real"] = adjust_for_inflation(home_values, inflation_rate)
yearly_df["equity_real"] = adjust_for_inflation(yearly_df["equity"].values, inflation_rate)

tab1, tab2, tab3 = st.tabs(["Monthly Costs", "Equity & Net Worth", "True Cost of Ownership"])

with tab1:
    st.subheader("Monthly Cost Breakdown")
    maintenance_monthly = purchase_price * maintenance_rate / 100 / 12
    cost_items = {
        "Mortgage P&I": monthly_payment,
        "HOA + Condo Fees": hoa_monthly,
        "Property Tax": property_tax_monthly,
        "Maintenance (est.)": maintenance_monthly,
    }
    total_monthly = sum(cost_items.values())

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Monthly Cost", f"${total_monthly:,.0f}")
    c2.metric("Equivalent Rent", f"${rent_estimate:,.0f}")
    delta = total_monthly - rent_estimate
    c3.metric("Own vs Rent Delta", f"${abs(delta):,.0f}",
              delta=f"{'more' if delta > 0 else 'less'} to own")

    fig_bar = go.Figure(go.Bar(
        x=list(cost_items.keys()), y=list(cost_items.values()),
        marker_color=["#2196F3", "#FF9800", "#4CAF50", "#9C27B0"],
        text=[f"${v:,.0f}" for v in cost_items.values()], textposition="outside",
    ))
    fig_bar.add_hline(y=rent_estimate, line_dash="dash", line_color="red",
                      annotation_text=f"Rent ${rent_estimate:,.0f}")
    fig_bar.update_layout(title="Monthly Cost Components", yaxis_title="$/month",
                          showlegend=False, height=400)
    st.plotly_chart(fig_bar, use_container_width=True)

    monthly_over_time = []
    for yr in range(1, analysis_years + 1):
        maint = home_values[yr] * maintenance_rate / 100 / 12
        monthly_over_time.append({
            "Year": purchase_year + yr,
            "Mortgage P&I": monthly_payment,
            "HOA + Fees": hoa_monthly,
            "Property Tax": property_tax_monthly,
            "Maintenance": maint,
        })
    mdf = pd.DataFrame(monthly_over_time)
    mdf["Total"] = mdf[["Mortgage P&I", "HOA + Fees", "Property Tax", "Maintenance"]].sum(axis=1)

    fig_line = go.Figure()
    fig_line.add_trace(go.Scatter(x=mdf["Year"], y=mdf["Total"],
                                  name="Total Monthly Cost", line=dict(color="#2196F3", width=2)))
    fig_line.add_trace(go.Scatter(
        x=mdf["Year"],
        y=[rent_estimate * (1 + inflation_rate / 100) ** i for i in range(analysis_years)],
        name="Rent (inflation-adjusted)", line=dict(color="red", dash="dash")))
    fig_line.update_layout(title="Monthly Cost vs Rent Over Time", yaxis_title="$/month", height=350)
    st.plotly_chart(fig_line, use_container_width=True)

with tab2:
    st.subheader("Equity & Net Worth Over Time")
    c1, c2, c3 = st.columns(3)
    c1.metric(f"Equity at Year {analysis_years}", f"${yearly_df['equity'].iloc[-1]:,.0f}")
    c2.metric("Opportunity Cost", f"${opp_cost[-1]:,.0f}")
    c3.metric("Appreciation Gain", f"${home_values[-1] - purchase_price:,.0f}")

    fig_eq = go.Figure()
    fig_eq.add_trace(go.Scatter(x=yearly_df["calendar_year"], y=yearly_df["home_value"],
                                name="Home Value", fill="tozeroy",
                                fillcolor="rgba(33,150,243,0.15)", line=dict(color="#2196F3")))
    fig_eq.add_trace(go.Scatter(x=yearly_df["calendar_year"], y=yearly_df["remaining_balance"],
                                name="Remaining Balance", fill="tozeroy",
                                fillcolor="rgba(244,67,54,0.15)", line=dict(color="#F44336")))
    fig_eq.add_trace(go.Scatter(x=yearly_df["calendar_year"], y=yearly_df["equity"],
                                name="Equity", line=dict(color="#4CAF50", width=2.5)))
    fig_eq.add_trace(go.Scatter(x=yearly_df["calendar_year"], y=yearly_df["opportunity_cost"],
                                name="Opp. Cost (invested)", line=dict(color="#FF9800", dash="dot", width=2)))
    fig_eq.update_layout(title="Home Value, Balance, Equity vs Opportunity Cost",
                         yaxis_title="$", height=450)
    st.plotly_chart(fig_eq, use_container_width=True)

    breakeven_year = None
    for _, row in yearly_df.iterrows():
        if row["equity"] >= row["opportunity_cost"]:
            breakeven_year = int(row["calendar_year"])
            break
    if breakeven_year:
        st.info(f"Break-even: equity exceeds opportunity cost around **{breakeven_year}** "
                f"(year {breakeven_year - purchase_year}).")
    else:
        st.warning("Equity never exceeds opportunity cost under these assumptions.")

    fig_amort = go.Figure()
    fig_amort.add_trace(go.Scatter(x=yearly_df["calendar_year"], y=yearly_df["cum_principal"],
                                   name="Cumulative Principal", fill="tozeroy",
                                   fillcolor="rgba(76,175,80,0.2)", line=dict(color="#4CAF50")))
    fig_amort.add_trace(go.Scatter(x=yearly_df["calendar_year"], y=yearly_df["cum_interest"],
                                   name="Cumulative Interest", fill="tozeroy",
                                   fillcolor="rgba(244,67,54,0.2)", line=dict(color="#F44336")))
    fig_amort.update_layout(title="Cumulative Principal vs Interest", yaxis_title="$", height=350)
    st.plotly_chart(fig_amort, use_container_width=True)

    with st.expander("Amortization Schedule"):
        disp = amort_df.copy()
        disp["calendar_year"] = purchase_year + (disp["month"] - 1) // 12
        for col in ["payment", "principal", "interest", "balance"]:
            disp[col] = disp[col].map("${:,.2f}".format)
        st.dataframe(disp, use_container_width=True)

with tab3:
    st.subheader("True Cost of Ownership")
    total_paid = yearly_df["cum_total_paid"].iloc[-1]
    total_equity = yearly_df["equity"].iloc[-1]
    net = yearly_df["net_cost"].iloc[-1]

    c1, c2, c3 = st.columns(3)
    c1.metric(f"Total Paid (yr {analysis_years})", f"${total_paid:,.0f}")
    c2.metric("Total Equity Gained", f"${total_equity:,.0f}")
    c3.metric("Net Cost (paid - equity)", f"${net:,.0f}")

    fig_area = go.Figure()
    for col, name, fillcolor in [
        ("cum_interest", "Interest", "rgba(244,67,54,0.6)"),
        ("cum_hoa", "HOA/Fees", "rgba(255,152,0,0.6)"),
        ("cum_tax", "Property Tax", "rgba(156,39,176,0.6)"),
        ("cum_maintenance", "Maintenance", "rgba(96,125,139,0.6)"),
    ]:
        fig_area.add_trace(go.Scatter(
            x=yearly_df["calendar_year"], y=yearly_df[col],
            name=name, stackgroup="costs",
            fillcolor=fillcolor, line=dict(color="rgba(0,0,0,0)"),
        ))
    fig_area.add_trace(go.Scatter(
        x=yearly_df["calendar_year"], y=yearly_df["equity"],
        name="Equity Gained", line=dict(color="#4CAF50", width=2.5),
    ))
    fig_area.add_trace(go.Scatter(
        x=yearly_df["calendar_year"], y=yearly_df["cum_rent"],
        name="Cumulative Rent (if renting)", line=dict(color="red", dash="dash"),
    ))
    fig_area.update_layout(title="Cumulative Costs vs Equity (Nominal)",
                           yaxis_title="$", height=450)
    st.plotly_chart(fig_area, use_container_width=True)

    fig_real = go.Figure()
    fig_real.add_trace(go.Scatter(x=yearly_df["calendar_year"], y=yearly_df["home_value"],
                                  name="Home Value (nominal)", line=dict(color="#2196F3")))
    fig_real.add_trace(go.Scatter(x=yearly_df["calendar_year"], y=yearly_df["home_value_real"],
                                  name="Home Value (real)", line=dict(color="#2196F3", dash="dot")))
    fig_real.add_trace(go.Scatter(x=yearly_df["calendar_year"], y=yearly_df["equity"],
                                  name="Equity (nominal)", line=dict(color="#4CAF50")))
    fig_real.add_trace(go.Scatter(x=yearly_df["calendar_year"], y=yearly_df["equity_real"],
                                  name="Equity (real)", line=dict(color="#4CAF50", dash="dot")))
    fig_real.update_layout(title="Nominal vs Inflation-Adjusted", yaxis_title="$", height=380)
    st.plotly_chart(fig_real, use_container_width=True)

    st.subheader("Yearly Summary")
    display_df = yearly_df[[
        "calendar_year", "home_value", "remaining_balance", "equity",
        "cum_total_paid", "net_cost", "home_value_real", "equity_real",
    ]].copy()
    display_df.columns = ["Year", "Home Value", "Loan Balance", "Equity",
                           "Total Paid", "Net Cost", "Home Value (Real)", "Equity (Real)"]
    for col in display_df.columns[1:]:
        display_df[col] = display_df[col].map("${:,.0f}".format)
    st.dataframe(display_df, use_container_width=True)
