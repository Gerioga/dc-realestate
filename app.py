import streamlit as st
from pathlib import Path

st.set_page_config(
    page_title="DC Real Estate Investment Dashboard",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Password gate ──
def check_password():
    if st.session_state.get("authenticated"):
        return True
    st.markdown(
        '<div style="text-align:center; padding: 60px 20px 20px;">'
        '<h1 style="color:#002245;">DC Metro Real Estate Dashboard</h1>'
        '</div>',
        unsafe_allow_html=True,
    )
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        pwd = st.text_input("Password", type="password", key="pwd_input")
        if st.button("Enter", use_container_width=True):
            if pwd == st.secrets.get("password", "Ordway"):
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("Incorrect password.")
    return False


if not check_password():
    st.stop()

# ── Data directory ──
DATA = Path(__file__).resolve().parent / "data"

# Store in session for pages
st.session_state["DATA"] = DATA

JURIS_COLORS = {
    "Washington DC": "#002245",
    "Arlington": "#0071BC",
    "Alexandria": "#EC553A",
    "Richmond": "#795548",
}
PTYPE_COLORS = {
    "Condo/Co-op": "#0071BC",
    "Townhouse": "#EC553A",
    "Single Family Residential": "#4CBB88",
    "Multi-Family (2-4 Unit)": "#862C8E",
}

st.session_state["JURIS_COLORS"] = JURIS_COLORS
st.session_state["PTYPE_COLORS"] = PTYPE_COLORS

# ── Landing page ──
st.markdown(
    """
    <div style="text-align:center; padding: 40px 20px;">
        <h1 style="color:#002245; font-size:2.6rem;">DC Metro Real Estate Investment Dashboard</h1>
        <p style="font-size:1.2rem; color:#555;">
            Washington DC &middot; Arlington &middot; Alexandria &middot; Richmond
        </p>
        <hr style="width:60%; margin:20px auto; border-color:#0071BC;">
    </div>
    """,
    unsafe_allow_html=True,
)

col1, col2, col3 = st.columns(3)
with col1:
    st.markdown("### Aggregated Analysis")
    st.markdown(
        "- **Market Overview** — headline metrics & choropleth map\n"
        "- **Price Trends** — time-series by area & property type\n"
        "- **Appreciation** — Zillow ZHVI historical trends\n"
        "- **Yield Analysis** — investment yield rankings"
    )
with col2:
    st.markdown("### Listing Data")
    st.markdown(
        "- **Listing Explorer** — browse individual Redfin listings\n"
        "- Filter by area, type, beds, price range\n"
        "- Interactive map & detail table"
    )
with col3:
    st.markdown("### Investment Tools")
    st.markdown(
        "- **Investment Calculator** — mortgage, equity & true cost\n"
        "- Break-even analysis vs renting\n"
        "- Nominal vs inflation-adjusted projections"
    )

st.markdown("---")

st.markdown("## Data Sources")
st.markdown(
    """
| Database | Description |
|---|---|
| **Redfin Market Tracker** | Quarterly zip-level aggregates: median sale price, $/sqft, days on market, sale-to-list ratio, homes sold, YoY changes. Covers DC, Arlington & Alexandria zip codes (2012-present). |
| **Zillow ZHVI** | Zillow Home Value Index for condos by zip code and neighborhood. Annual values 2000-2026. |
| **HUD Fair Market Rents** | FY 2025 Fair Market Rents by zip code and bedroom count (0BR-4BR). |
| **Redfin Listings** | Individual active listings from Redfin for DC, Arlington, Alexandria & Richmond. |
"""
)

st.markdown("---")

st.markdown("## Glossary")
st.markdown(
    """
| Term | Definition |
|---|---|
| **Median Sale Price** | The middle value of all closed sale prices in a zip code for a given period. |
| **$/sqft (PPSF)** | Price per square foot. |
| **Days on Market (DOM)** | Days from listing to accepted offer. Lower = hotter market. |
| **Sale-to-List Ratio** | Sale price / list price. >1.0 means homes sell above asking. |
| **ZHVI** | Zillow Home Value Index — smoothed, seasonally adjusted typical home value estimate. |
| **HUD FMR** | Fair Market Rent — HUD's 40th-percentile rent estimate including utilities. |
| **Gross Yield** | Annual rent / purchase price. |
| **Net Yield** | (Annual rent - HOA - tax - maintenance) / purchase price. |
| **Cash-on-Cash** | After-tax annual cash flow / cash invested. |
"""
)

st.caption("Use the sidebar to navigate between pages.")
