# app.py
# AMFI Mutual Fund Dashboard (2020–2025)
# FIXED:
# 1) Removes the pandas "Length of values (...) does not match length of index (...)" by NOT using as_index=False
#    (uses .groupby(...).agg(...).reset_index()).
# 2) Prevents KPI overlap/cut by using 3 KPIs per row + CSS no-wrap controls.
# 3) Prevents Market Share text overlap by:
#    - putting titles smaller,
#    - using horizontal legend at bottom,
#    - keeping only percent labels (2 decimals),
#    - enlarging donut and tightening margins.

import os
import re
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px

# -------------------- PAGE CONFIG --------------------
st.set_page_config(page_title="AMFI Mutual Fund Dashboard (2020–2025)", layout="wide")

# -------------------- CONFIG --------------------
DATA_FILE_PATH = "AMFI_Clean_data_final.xlsx"  # keep next to app.py OR update path
SHEET_NAME = "detail_rows"                     # you said you will use detail_rows only

MONTH_ORDER = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTH_MAP = {m: i + 1 for i, m in enumerate(MONTH_ORDER)}

# -------------------- STYLES (avoid overlaps) --------------------
st.markdown(
    """
    <style>
      /* KPI cards: keep clean, prevent clipping/overlap */
      .kpi-card{
        padding: 6px 8px;
        border-radius: 12px;
        background: rgba(0,0,0,0.02);
        min-height: 120px;
      }
      .kpi-label{
        font-size: 14px;
        color: #6b7280;
        margin-bottom: 10px;
      }
      .kpi-value{
        font-size: 34px;
        font-weight: 780;
        line-height: 1.05;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      /* Small screens: slightly smaller values to avoid overlap */
      @media (max-width: 1200px){
        .kpi-value{ font-size: 30px; }
      }
    </style>
    """,
    unsafe_allow_html=True
)

# -------------------- HELPERS --------------------
def coerce_numeric(x):
    """Robust numeric coercion for values like '1,234.56', '(123)', '-', '—'."""
    if pd.isna(x):
        return np.nan
    s = str(x).strip()
    if s in ("", "-", "—"):
        return np.nan
    s = s.replace(",", "")
    # (123.45) -> -123.45
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    # keep only valid numeric chars
    s = re.sub(r"[^0-9eE\.\-\+]", "", s)
    try:
        return float(s)
    except Exception:
        return np.nan

def lakh_cr(num_cr):
    """Convert ₹ Cr to ₹ Lakh Cr (1 Lakh Cr = 100,000 Cr)."""
    if pd.isna(num_cr):
        return np.nan
    return num_cr / 1e5

def fmt_lakh_cr(num_cr, decimals=2):
    """Format ₹ Cr into ₹ Lakh Cr string."""
    if pd.isna(num_cr):
        return "—"
    return f"₹ {num_cr/1e5:,.{decimals}f}"

def kpi(label, value):
    st.markdown(
        f"""
        <div class="kpi-card">
          <div class="kpi-label">{label}</div>
          <div class="kpi-value">{value}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

@st.cache_data(show_spinner=False)
def load_data(path: str, sheet: str):
    df = pd.read_excel(path, sheet_name=sheet)

    # Normalize known AMFI column names (tolerant)
    rename_map = {
        "Funds Mobilized (Rs. Cr.)": "Funds Mobilized",
        "Redemption (Rs. Cr.)": "Redemption",
        "Net Inflow (Rs. Cr.)": "Net Inflow",
        "Average AUM (Rs. Cr.)": "Average AUM",
        "Average AUM": "Average AUM",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    # remove duplicated columns if any
    df = df.loc[:, ~df.columns.duplicated()].copy()
    df = df.reset_index(drop=True)

    # required columns
    needed = ["Year", "Month", "Main Type", "Sub Type",
              "Average AUM", "Funds Mobilized", "Redemption", "Net Inflow"]
    missing = [c for c in needed if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns in sheet '{sheet}': {missing}")

    # clean text cols
    df["Year"] = pd.to_numeric(df["Year"], errors="coerce")
    df["Month"] = df["Month"].astype(str).str.strip().str[:3]
    df["Main Type"] = df["Main Type"].astype(str).str.strip()
    df["Sub Type"] = df["Sub Type"].astype(str).str.strip()

    # numeric cols
    for c in ["Average AUM", "Funds Mobilized", "Redemption", "Net Inflow"]:
        df[c] = df[c].map(coerce_numeric)

    df["MonthNum"] = df["Month"].map(MONTH_MAP)
    df["Date"] = pd.to_datetime(
        dict(year=df["Year"], month=df["MonthNum"], day=1),
        errors="coerce"
    )

    # keep only valid
    df = df.dropna(subset=["Year", "Month", "Date"])
    df["Year"] = df["Year"].astype(int)

    # restrict to 2020–2025
    df = df[(df["Year"] >= 2020) & (df["Year"] <= 2025)].copy()

    # categorical month ordering
    df["Month"] = pd.Categorical(df["Month"], categories=MONTH_ORDER, ordered=True)

    # ratios (% of AUM)
    denom = df["Average AUM"].replace(0, np.nan)
    df["Funds % of AUM"] = df["Funds Mobilized"] / denom
    df["Redemption % of AUM"] = df["Redemption"] / denom
    df["Net % of AUM"] = df["Net Inflow"] / denom

    return df

# -------------------- LOAD --------------------
st.title("AMFI Mutual Fund Dashboard (2020–2025)")
st.caption("Interactive dashboard built from AMFI monthly files.")

if not os.path.exists(DATA_FILE_PATH):
    st.error(f"❌ File not found: {DATA_FILE_PATH}\n\nKeep it next to app.py or update DATA_FILE_PATH.")
    st.stop()

try:
    df = load_data(DATA_FILE_PATH, SHEET_NAME)
except Exception as e:
    st.exception(e)
    st.stop()

if df.empty:
    st.warning("No rows available after cleaning.")
    st.stop()

# -------------------- SIDEBAR FILTERS --------------------
st.sidebar.header("Filters")

years = sorted(df["Year"].unique().tolist())
yr_range = st.sidebar.slider("Year range", min(years), max(years), (min(years), max(years)), step=1)

st.sidebar.subheader("Months")
selected_months = [m for m in MONTH_ORDER if st.sidebar.checkbox(m, value=True, key=f"m_{m}")]

st.sidebar.subheader("Main Type (checkboxes)")
main_types = sorted(df["Main Type"].unique().tolist())
selected_main = [mt for mt in main_types if st.sidebar.checkbox(mt, value=True, key=f"mt_{mt}")]

# Sub types depend on main selection
sub_pool = df[df["Main Type"].isin(selected_main)] if selected_main else df
sub_types = sorted(sub_pool["Sub Type"].unique().tolist())
selected_sub = st.sidebar.multiselect("Sub Type (optional)", sub_types, default=[])

top_n = st.sidebar.slider("Top-N Sub Types (Net Inflow)", 5, 40, 20, step=1)

# Filtered dataframe
f = df[(df["Year"] >= yr_range[0]) & (df["Year"] <= yr_range[1])].copy()
f = f[f["Month"].isin(selected_months)]
if selected_main:
    f = f[f["Main Type"].isin(selected_main)]
if selected_sub:
    f = f[f["Sub Type"].isin(selected_sub)]

# Safety: duplicate columns / index weirdness protection
f = f.loc[:, ~f.columns.duplicated()].copy()
f = f.reset_index(drop=True)

if f.empty:
    st.warning("No data for selected filters.")
    st.stop()

# -------------------- AGGREGATIONS (CRITICAL FIX) --------------------
# IMPORTANT: DO NOT use as_index=False. Use reset_index() after agg.

industry_month = (
    f.groupby(["Year", "Month", "Date"])
     .agg(AUM=("Average AUM", "sum"),
          Funds=("Funds Mobilized", "sum"),
          Redemption=("Redemption", "sum"),
          Net=("Net Inflow", "sum"))
     .reset_index()
     .sort_values(["Year", "Date"])
)

industry_year = (
    f.groupby(["Year"])
     .agg(AUM=("Average AUM", "sum"),
          Funds=("Funds Mobilized", "sum"),
          Redemption=("Redemption", "sum"),
          Net=("Net Inflow", "sum"))
     .reset_index()
     .sort_values("Year")
)

main_total = (
    f.groupby(["Main Type"])
     .agg(AUM=("Average AUM", "sum"),
          Funds=("Funds Mobilized", "sum"),
          Redemption=("Redemption", "sum"),
          Net=("Net Inflow", "sum"))
     .reset_index()
     .sort_values("AUM", ascending=False)
)

latest_date = f["Date"].max()
latest = f[f["Date"] == latest_date].copy()

latest_main = (
    latest.groupby(["Main Type"])
          .agg(AUM=("Average AUM", "sum"),
               Funds=("Funds Mobilized", "sum"),
               Redemption=("Redemption", "sum"),
               Net=("Net Inflow", "sum"))
          .reset_index()
          .sort_values("AUM", ascending=False)
)

latest_sub = (
    latest.groupby(["Main Type", "Sub Type"])
          .agg(AUM=("Average AUM", "sum"),
               Funds=("Funds Mobilized", "sum"),
               Redemption=("Redemption", "sum"),
               Net=("Net Inflow", "sum"))
          .reset_index()
)

# Convert to Lakh Cr numeric columns for charts
for dfx in [industry_month, industry_year, main_total, latest_main, latest_sub]:
    dfx["AUM_LCr"] = dfx["AUM"].map(lakh_cr)
    dfx["Funds_LCr"] = dfx["Funds"].map(lakh_cr)
    dfx["Redemption_LCr"] = dfx["Redemption"].map(lakh_cr)
    dfx["Net_LCr"] = dfx["Net"].map(lakh_cr)

# -------------------- KPI SUMMARY (3 + 3, no overlap) --------------------
k_aum = f["Average AUM"].sum()
k_funds = f["Funds Mobilized"].sum()
k_red = f["Redemption"].sum()
k_net = f["Net Inflow"].sum()

den = k_aum if (pd.notna(k_aum) and k_aum != 0) else np.nan
funds_pct = (k_funds / den) if pd.notna(den) else np.nan
red_pct = (k_red / den) if pd.notna(den) else np.nan

row1 = st.columns(3)
with row1[0]: kpi("AUM (₹ Lakh Cr)", fmt_lakh_cr(k_aum, 2))
with row1[1]: kpi("Funds (₹ Lakh Cr)", fmt_lakh_cr(k_funds, 2))
with row1[2]: kpi("Redemption (₹ Lakh Cr)", fmt_lakh_cr(k_red, 2))

row2 = st.columns(3)
with row2[0]: kpi("Net (₹ Lakh Cr)", fmt_lakh_cr(k_net, 2))
with row2[1]: kpi("Funds % of AUM", (f"{funds_pct:.2%}" if pd.notna(funds_pct) else "—"))
with row2[2]: kpi("Redemption % of AUM", (f"{red_pct:.2%}" if pd.notna(red_pct) else "—"))

st.markdown("---")

# -------------------- CHARTS --------------------
st.subheader("Monthly Flows by Year (Stacked) — ₹ Lakh Cr")
c1, c2 = st.columns(2)

with c1:
    fig_funds = px.bar(
        industry_month, x="Month", y="Funds_LCr", color="Year",
        barmode="stack", category_orders={"Month": MONTH_ORDER},
        title="Funds Mobilized by Month and Year",
        labels={"Funds_LCr": "Funds (₹ Lakh Cr)"}
    )
    fig_funds.update_layout(height=420, legend_title_text="Year", title_font_size=16)
    st.plotly_chart(fig_funds, use_container_width=True)

with c2:
    fig_red = px.bar(
        industry_month, x="Month", y="Redemption_LCr", color="Year",
        barmode="stack", category_orders={"Month": MONTH_ORDER},
        title="Redemption by Month and Year",
        labels={"Redemption_LCr": "Redemption (₹ Lakh Cr)"}
    )
    fig_red.update_layout(height=420, legend_title_text="Year", title_font_size=16)
    st.plotly_chart(fig_red, use_container_width=True)

st.subheader("Yearly Trends — ₹ Lakh Cr")
t1, t2 = st.columns(2)

with t1:
    fig_aum = px.line(
        industry_year, x="Year", y="AUM_LCr", markers=True,
        title="AUM by Year", labels={"AUM_LCr": "AUM (₹ Lakh Cr)"}
    )
    fig_aum.update_layout(height=420, title_font_size=16)
    st.plotly_chart(fig_aum, use_container_width=True)

with t2:
    fig_net = px.line(
        industry_year, x="Year", y="Net_LCr", markers=True,
        title="Net Inflow by Year", labels={"Net_LCr": "Net (₹ Lakh Cr)"}
    )
    fig_net.update_layout(height=420, title_font_size=16)
    st.plotly_chart(fig_net, use_container_width=True)

st.subheader("Contribution by Main Type — ₹ Lakh Cr")
b1, b2, b3, b4 = st.columns(4)

with b1:
    fig = px.bar(main_total, x="Main Type", y="AUM_LCr", title="AUM",
                 labels={"AUM_LCr": "AUM (₹ Lakh Cr)"})
    fig.update_layout(height=420, title_font_size=16)
    st.plotly_chart(fig, use_container_width=True)

with b2:
    fig = px.bar(main_total, x="Main Type", y="Funds_LCr", title="Funds",
                 labels={"Funds_LCr": "Funds (₹ Lakh Cr)"})
    fig.update_layout(height=420, title_font_size=16)
    st.plotly_chart(fig, use_container_width=True)

with b3:
    fig = px.bar(main_total, x="Main Type", y="Redemption_LCr", title="Redemption",
                 labels={"Redemption_LCr": "Redemption (₹ Lakh Cr)"})
    fig.update_layout(height=420, title_font_size=16)
    st.plotly_chart(fig, use_container_width=True)

with b4:
    fig = px.bar(main_total, x="Main Type", y="Net_LCr", title="Net",
                 labels={"Net_LCr": "Net (₹ Lakh Cr)"})
    fig.update_layout(height=420, title_font_size=16)
    st.plotly_chart(fig, use_container_width=True)

# -------------------- MARKET SHARE (NO OVERLAP) --------------------
st.subheader(f"Market Share by Main Type (Latest Month: {latest_date.strftime('%b %Y')})")

latest_main["Main Type Short"] = (
    latest_main["Main Type"].str.replace("SCHEMES", "", regex=False).str.strip()
)

def donut(df_in, value_col, title):
    fig = px.pie(
        df_in, names="Main Type Short", values=value_col, hole=0.62
    )
    fig.update_traces(
        textposition="inside",
        textinfo="percent",
        insidetextorientation="radial",
        texttemplate="%{percent:.2%}",  # 2 decimals
        hovertemplate="<b>%{label}</b><br>%{percent:.2%}<br>₹ %{value:,.2f} L Cr<extra></extra>",
        sort=False
    )
    # Key layout to avoid overlap:
    fig.update_layout(
        title=dict(text=title, font=dict(size=16)),
        height=440,
        margin=dict(t=70, b=90, l=10, r=10),
        legend=dict(
            orientation="h",   # horizontal legend at bottom
            yanchor="top", y=-0.08,
            xanchor="center", x=0.5,
            font=dict(size=11)
        ),
        uniformtext=dict(minsize=12, mode="hide")
    )
    return fig

ms1, ms2, ms3, ms4 = st.columns(4)

with ms1:
    st.plotly_chart(donut(latest_main, "AUM_LCr", "AUM Share"), use_container_width=True)
with ms2:
    st.plotly_chart(donut(latest_main, "Funds_LCr", "Funds Share"), use_container_width=True)
with ms3:
    st.plotly_chart(donut(latest_main, "Redemption_LCr", "Redemption Share"), use_container_width=True)

latest_main["AbsNet_LCr"] = latest_main["Net_LCr"].abs()
with ms4:
    st.plotly_chart(donut(latest_main, "AbsNet_LCr", "Net Share (ABS)"), use_container_width=True)

# Signed Net bar for latest month
fig_net_dir = px.bar(
    latest_main.sort_values("Net_LCr", ascending=False),
    x="Main Type Short", y="Net_LCr",
    title="Net Inflow by Main Type (Signed) — Latest Month",
    labels={"Net_LCr": "Net (₹ Lakh Cr)", "Main Type Short": "Main Type"}
)
fig_net_dir.update_layout(height=420, title_font_size=16)
st.plotly_chart(fig_net_dir, use_container_width=True)

# -------------------- TREEMAP (Latest Month AUM composition with values) --------------------
st.subheader(f"Latest Month Composition (AUM) — {latest_date.strftime('%b %Y')} (₹ Lakh Cr)")

latest_sub["AUM_LCr"] = latest_sub["AUM_LCr"].fillna(0)
latest_sub["Label"] = latest_sub["Sub Type"].astype(str) + "<br>₹ " + latest_sub["AUM_LCr"].round(2).astype(str)

fig_tree = px.treemap(
    latest_sub,
    path=["Main Type", "Sub Type"],
    values="AUM_LCr",
    hover_data={"AUM_LCr": ":,.2f", "Funds_LCr": ":,.2f", "Redemption_LCr": ":,.2f", "Net_LCr": ":,.2f"}
)
fig_tree.update_traces(
    text=latest_sub["Label"],
    textinfo="label+percent parent",
    textfont_size=14
)
fig_tree.update_layout(
    height=560,
    margin=dict(t=40, l=10, r=10, b=10),
    uniformtext=dict(minsize=10, mode="hide")
)
st.plotly_chart(fig_tree, use_container_width=True)

# -------------------- TOP-N SUB TYPES --------------------
st.subheader("Net Inflow by Sub Type (Top-N) — ₹ Lakh Cr")
sub_net = (
    f.groupby(["Sub Type"])["Net Inflow"].sum()
     .sort_values(ascending=False)
     .head(top_n)
     .reset_index()
)
sub_net["Net_LCr"] = sub_net["Net Inflow"].map(lakh_cr)

fig_sub = px.bar(
    sub_net, x="Sub Type", y="Net_LCr",
    title=f"Top {top_n} Sub Types by Net Inflow",
    labels={"Net_LCr": "Net (₹ Lakh Cr)", "Sub Type": "Sub Type"}
)
fig_sub.update_layout(height=520, xaxis_tickangle=-35, title_font_size=16)
st.plotly_chart(fig_sub, use_container_width=True)
