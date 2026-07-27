"""
M-Pesa Intelligence System — Streamlit analytics companion.

A lightweight, read-only analytics view over the same Postgres 14 `transactions`
table used by the FastAPI backend. Useful for analysts who want fast ad-hoc
exploration (filtering, pivoting, exporting) without touching the main app.

Run:
    streamlit run app.py

Config: reads the same POSTGRES_* / DATABASE_URL env vars as the backend
(see backend/.env.example). Copy your .env next to this file, or export the
vars in your shell / deployment platform.
"""
import os
import datetime as dt

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Page config + theme
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="M-Pesa Intelligence — Analytics",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

PLOTLY_TEMPLATE = "plotly_dark"
COLOR_SEQ = ["#1fd18f", "#4c8be0", "#e8b84b", "#e2574c", "#a884e8", "#3ec6d6", "#f08a5d", "#6fcf97"]

CUSTOM_CSS = """
<style>
.stApp {
  background:
    radial-gradient(circle at 12% 8%, rgba(31,209,143,0.08), transparent 42%),
    radial-gradient(circle at 88% 18%, rgba(76,139,224,0.10), transparent 45%),
    linear-gradient(160deg, #060d16 0%, #0a1420 45%, #0d1b29 100%);
}
section[data-testid="stSidebar"] {
  background: linear-gradient(180deg, rgba(10,20,32,0.96), rgba(8,16,26,0.98));
  border-right: 1px solid rgba(255,255,255,0.08);
}
h1, h2, h3 { color: #eaf1f8 !important; }
[data-testid="stMetricValue"] { color: #1fd18f; font-weight: 800; }
[data-testid="stMetricLabel"] { color: #93a7bb; }
div[data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; }
.mp-badge {
  display:inline-block; padding:3px 10px; border-radius:999px; font-size:12px;
  font-weight:700; background:rgba(31,209,143,0.15); color:#1fd18f; margin-right:6px;
}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Auth (simple shared-password gate — swap for something stronger in prod)
# ---------------------------------------------------------------------------
def check_password() -> bool:
    app_password = os.getenv("STREAMLIT_APP_PASSWORD")
    if not app_password:
        return True  # no password configured -> open access (dev mode)

    if st.session_state.get("authed"):
        return True

    st.markdown("### 🔒 M-Pesa Intelligence — Analytics")
    pw = st.text_input("Enter access password", type="password")
    if st.button("Sign in"):
        if pw == app_password:
            st.session_state["authed"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    return False


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
@st.cache_resource
def get_engine():
    url = os.getenv("DATABASE_URL")
    if not url:
        host = os.getenv("POSTGRES_HOST", "localhost")
        port = os.getenv("POSTGRES_PORT", "5435")
        db = os.getenv("POSTGRES_DB", "mpesa")
        user = os.getenv("POSTGRES_USER", "postgres")
        pw = os.getenv("POSTGRES_PASSWORD", "Anngatz3112#")
        url = f"postgresql+psycopg2://{user}:{pw}@{host}:{port}/{db}"
    return create_engine(url, pool_pre_ping=True)


@st.cache_data(ttl=60)
def load_transactions(date_from=None, date_to=None) -> pd.DataFrame:
    engine = get_engine()
    query = "SELECT * FROM transactions WHERE 1=1"
    params = {}
    if date_from:
        query += " AND completion_time >= :date_from"
        params["date_from"] = date_from
    if date_to:
        query += " AND completion_time <= :date_to"
        params["date_to"] = date_to
    query += " ORDER BY completion_time DESC"
    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn, params=params)
    if "completion_time" in df.columns:
        df["completion_time"] = pd.to_datetime(df["completion_time"], errors="coerce")
    return df


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
def page_overview(df: pd.DataFrame):
    st.title("📊 Overview")
    st.caption("High-level snapshot of everything ingested so far.")

    if df.empty:
        st.info("No transactions found yet. Upload statements via the main app, or check your DB connection.")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total transactions", f"{len(df):,}")
    coverage = 100 * df["transaction_category"].notna().sum() / len(df)
    c2.metric("Classification coverage", f"{coverage:.1f}%")
    net_flow = df["paid_in"].sum() - df["withdrawn"].sum()
    c3.metric("Net flow (KES)", f"{net_flow:,.0f}")
    avg_conf = df["category_confidence"].mean()
    c4.metric("Avg. category confidence", f"{avg_conf*100:.1f}%" if pd.notna(avg_conf) else "—")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Category breakdown")
        cat_counts = df["transaction_category"].fillna("Unclassified").value_counts().reset_index()
        cat_counts.columns = ["category", "count"]
        fig = px.pie(cat_counts, names="category", values="count", hole=0.5,
                     color_discrete_sequence=COLOR_SEQ, template=PLOTLY_TEMPLATE)
        fig.update_layout(margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Monthly inflow vs outflow")
        m = df.dropna(subset=["completion_time"]).copy()
        m["month"] = m["completion_time"].dt.to_period("M").astype(str)
        monthly = m.groupby("month").agg(total_in=("paid_in", "sum"), total_out=("withdrawn", "sum")).reset_index()
        fig = go.Figure()
        fig.add_bar(x=monthly["month"], y=monthly["total_in"], name="Inflow", marker_color="#1fd18f")
        fig.add_bar(x=monthly["month"], y=monthly["total_out"], name="Outflow", marker_color="#e2574c")
        fig.update_layout(template=PLOTLY_TEMPLATE, barmode="group", margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(fig, use_container_width=True)


def page_explorer(df: pd.DataFrame):
    st.title("🔍 Transaction Explorer")
    st.caption("Filter, sort, and export the raw ledger.")

    if df.empty:
        st.info("No transactions to explore yet.")
        return

    with st.sidebar:
        st.markdown("#### Filters")
        labels = ["All"] + sorted(df["transaction_label"].dropna().unique().tolist())
        categories = ["All"] + sorted(df["transaction_category"].dropna().unique().tolist())
        sel_label = st.selectbox("Label", labels)
        sel_category = st.selectbox("Category", categories)
        search = st.text_input("Search details")

    filtered = df.copy()
    if sel_label != "All":
        filtered = filtered[filtered["transaction_label"] == sel_label]
    if sel_category != "All":
        filtered = filtered[filtered["transaction_category"] == sel_category]
    if search:
        filtered = filtered[filtered["details"].str.contains(search, case=False, na=False)]

    st.markdown(f"**{len(filtered):,}** matching transactions")
    show_cols = ["completion_time", "receipt_no", "details", "paid_in", "withdrawn",
                 "transaction_label", "transaction_classification", "transaction_category",
                 "category_confidence"]
    show_cols = [c for c in show_cols if c in filtered.columns]
    st.dataframe(filtered[show_cols].head(1000), use_container_width=True, height=520)

    csv = filtered[show_cols].to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Download filtered CSV", csv, "transactions_export.csv", "text/csv")


def page_trends(df: pd.DataFrame):
    st.title("📈 Trends & Behavioural Patterns")
    st.caption("Time of day, weekday vs weekend, and monthly week-by-week progression.")

    if df.empty:
        st.info("No transactions to analyze yet.")
        return

    d = df.dropna(subset=["completion_time"]).copy()
    d["hour"] = d["completion_time"].dt.hour
    d["dow"] = d["completion_time"].dt.dayofweek
    d["is_weekend"] = d["dow"].isin([5, 6])
    d["amount_abs"] = (d["paid_in"].fillna(0) - d["withdrawn"].fillna(0)).abs()

    st.subheader("Time of day")
    hourly = d.groupby("hour").size().reindex(range(24), fill_value=0).reset_index(name="count")
    hourly.columns = ["hour", "count"]
    hourly["is_rush"] = hourly["hour"].apply(lambda h: "Rush hour" if (6 <= h <= 9 or 17 <= h <= 21) else "Off-peak")
    fig = px.bar(hourly, x="hour", y="count", color="is_rush",
                 color_discrete_map={"Rush hour": "#e8b84b", "Off-peak": "#4c8be0"},
                 template=PLOTLY_TEMPLATE)
    fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), xaxis_title="Hour of day", yaxis_title="Transactions")
    st.plotly_chart(fig, use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Weekday vs weekend")
        wk = d.groupby("is_weekend").agg(count=("hour", "size"), avg_amount=("amount_abs", "mean")).reset_index()
        wk["bucket"] = wk["is_weekend"].map({True: "Weekend", False: "Weekday"})
        fig = px.bar(wk, x="bucket", y="count", color="bucket",
                     color_discrete_sequence=["#1fd18f", "#e8b84b"], template=PLOTLY_TEMPLATE)
        fig.update_layout(showlegend=False, margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Day-of-week pattern")
        names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        dow_counts = d.groupby("dow").size().reindex(range(7), fill_value=0).reset_index(name="count")
        dow_counts["day"] = dow_counts["dow"].apply(lambda i: names[i])
        fig = px.bar(dow_counts, x="day", y="count", color="day",
                     color_discrete_sequence=COLOR_SEQ, template=PLOTLY_TEMPLATE)
        fig.update_layout(showlegend=False, margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Monthly progression — first week to last week")
    c1, c2 = st.columns(2)
    year = c1.number_input("Year", min_value=2015, max_value=2035, value=dt.date.today().year)
    month = c2.number_input("Month", min_value=1, max_value=12, value=dt.date.today().month)

    month_df = d[(d["completion_time"].dt.year == year) & (d["completion_time"].dt.month == month)].copy()
    if month_df.empty:
        st.info("No transactions in the selected month.")
    else:
        month_df["week"] = ((month_df["completion_time"].dt.day - 1) // 7 + 1).clip(upper=5)
        weekly = month_df.groupby("week").agg(count=("hour", "size"), total_value=("amount_abs", "sum")).reindex(
            range(1, 6), fill_value=0
        ).reset_index()
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=weekly["week"], y=weekly["count"], name="Transaction count",
                                  line=dict(color="#1fd18f"), fill="tozeroy"))
        fig.add_trace(go.Scatter(x=weekly["week"], y=weekly["total_value"], name="Total value (KES)",
                                  line=dict(color="#e8b84b"), yaxis="y2"))
        fig.update_layout(
            template=PLOTLY_TEMPLATE, margin=dict(t=10, b=10, l=10, r=10),
            xaxis=dict(title="Week of month", tickmode="linear"),
            yaxis=dict(title="Count"), yaxis2=dict(title="KES", overlaying="y", side="right"),
        )
        st.plotly_chart(fig, use_container_width=True)


def page_monitoring(df: pd.DataFrame):
    st.title("🛰️ Monitoring")
    st.caption("Model coverage and confidence health, computed directly from the database.")

    if df.empty:
        st.info("No transactions yet.")
        return

    c1, c2, c3 = st.columns(3)
    unclassified = df["transaction_label"].isna().sum()
    c1.metric("Unclassified rows", f"{unclassified:,}")
    avg_conf = df["category_confidence"].mean()
    c2.metric("Avg. category confidence", f"{avg_conf*100:.1f}%" if pd.notna(avg_conf) else "—")
    low_conf_count = (df["category_confidence"] < 0.55).sum()
    c3.metric("Low-confidence rows (<55%)", f"{low_conf_count:,}")

    st.subheader("Confidence distribution")
    conf_df = df.dropna(subset=["category_confidence"])
    if not conf_df.empty:
        fig = px.histogram(conf_df, x="category_confidence", nbins=25,
                            color_discrete_sequence=["#4c8be0"], template=PLOTLY_TEMPLATE)
        fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), xaxis_title="Confidence", yaxis_title="Count")
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Transactions flagged for review")
    flagged = df[df["category_confidence"] < 0.55].sort_values("category_confidence").head(50)
    cols = [c for c in ["completion_time", "details", "transaction_category", "category_confidence"] if c in flagged.columns]
    st.dataframe(flagged[cols], use_container_width=True, height=400)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    if not check_password():
        return

    with st.sidebar:
        st.markdown("## 📊 M-Pesa Intel")
        st.caption("Analytics companion")
        page = st.radio("Navigate", ["Overview", "Explorer", "Trends", "Monitoring"], label_visibility="collapsed")
        st.divider()
        date_range = st.date_input(
            "Date range filter",
            value=(dt.date.today() - dt.timedelta(days=90), dt.date.today()),
        )
        st.divider()
        if st.button("🔄 Refresh data"):
            st.cache_data.clear()
            st.rerun()

    date_from = date_range[0] if isinstance(date_range, tuple) and len(date_range) > 0 else None
    date_to = date_range[1] if isinstance(date_range, tuple) and len(date_range) > 1 else None

    try:
        df = load_transactions(date_from, date_to)
    except Exception as e:
        st.error(f"Could not connect to the database: {e}")
        st.info("Check POSTGRES_* / DATABASE_URL env vars (see backend/.env.example).")
        return

    if page == "Overview":
        page_overview(df)
    elif page == "Explorer":
        page_explorer(df)
    elif page == "Trends":
        page_trends(df)
    elif page == "Monitoring":
        page_monitoring(df)


if __name__ == "__main__":
    main()
