import streamlit as st
import sys
import os
import pandas as pd
import plotly.express as px

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database import (
    init_db, get_dashboard_data, get_vendor_dashboard_data, get_site_analysis,
    get_users, get_stores, get_brands, get_states
)

init_db()

user = st.session_state.get('user', {})
if not user:
    st.warning("Please login first.")
    st.stop()

role = user.get('role', 'Vendor')

st.title("📊 Dashboard")
st.markdown("---")

# ══════════════════════════════════════════════════════════════════════════════
# VENDOR DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
if role == 'Vendor':
    data = get_vendor_dashboard_data(user['id'])

    if not data:
        st.info("No data available. Submit a PMS entry to see your stats.")
        st.stop()

    st.markdown(f"### 👋 Welcome, {data.get('tech_name', user['name'])}")

    # ── Today's KPIs ──────────────────────────────────────────────────────────
    st.markdown("#### Today")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Stores Done",    data.get('stores_done', 0))
    k2.metric("Stores Pending", data.get('stores_pending', 0))
    k3.metric("ACs Checked",    data.get('ac_done', 0))
    k4.metric("ACs Pending",    data.get('ac_pending', 0))

    # ── This Month ────────────────────────────────────────────────────────────
    st.markdown("#### This Month")
    m1, m2 = st.columns(2)
    m1.metric("Sessions Completed", data.get('month_sessions', 0))
    m2.metric("ACs Serviced",       data.get('month_ac', 0))

    st.markdown("---")

    # ── Store Status Table ────────────────────────────────────────────────────
    st.markdown("#### Store Status")
    store_status = data.get('store_status', [])
    if store_status:
        rows = []
        for s in store_status:
            rows.append({
                "Store":       s['store_name'],
                "State":       s['state'],
                "Total AC":    s['total_ac'],
                "AC Done":     s['ac_done'],
                "AC Pending":  s['ac_pending'],
                "Status":      "✅ Done" if s['done_today'] else "⏳ Pending",
            })
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No stores assigned.")

    if st.button("🔄 Refresh"):
        st.rerun()

    st.stop()


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN / VIEWER DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
tab_overview, tab_site = st.tabs(["🏢 Central Overview", "🔍 Site Analysis"])

# ── Tab 1: Central Overview ───────────────────────────────────────────────────
with tab_overview:
    data = get_dashboard_data()

    # KPIs
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Stores Covered Today",  data.get('stores_today', 0))
    k2.metric("ACs Checked Today",     data.get('ac_today', 0))
    k3.metric("Stores This Month",     data.get('stores_done_month', 0))
    k4.metric("ACs This Month",        data.get('ac_done_month', 0))
    k5.metric("Pending Stores",        data.get('stores_pending', 0))

    st.markdown("---")

    # Charts row 1: Brand distribution + Technician performance
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Brand Distribution")
        bd = data.get('brand_dist', [])
        if bd:
            df = pd.DataFrame(bd)
            fig = px.pie(df, values='cnt', names='brand',
                         color_discrete_sequence=px.colors.qualitative.Set2, hole=0.35)
            fig.update_layout(margin=dict(t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No brand data yet.")

    with c2:
        st.subheader("Technician Performance (This Month)")
        tp = data.get('tech_perf', [])
        if tp:
            df = pd.DataFrame(tp)
            fig = px.bar(df, x='name', y='ac_count',
                         color='ac_count', color_continuous_scale='Blues',
                         labels={'name': 'Technician', 'ac_count': 'AC Count'})
            fig.update_layout(showlegend=False, margin=dict(t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No technician data yet.")

    # Charts row 2: State-wise + AC type
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("State-wise Summary")
        ss = data.get('state_summary', [])
        if ss:
            df = pd.DataFrame(ss)
            fig = px.bar(df, x='state', y='ac_count',
                         color='ac_count', color_continuous_scale='Oranges',
                         labels={'state': 'State', 'ac_count': 'AC Count'})
            fig.update_layout(showlegend=False, margin=dict(t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No state data yet.")

    with c2:
        st.subheader("AC Type Distribution")
        at = data.get('ac_type_dist', [])
        if at:
            df = pd.DataFrame(at)
            fig = px.pie(df, values='cnt', names='ac_type',
                         color_discrete_sequence=px.colors.sequential.Blues_r, hole=0.4)
            fig.update_layout(margin=dict(t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No AC type data yet.")

    # Daily trend
    dt = data.get('daily_trend', [])
    if dt:
        st.subheader("Daily AC Check Trend (Last 30 Days)")
        df = pd.DataFrame(dt).sort_values('entry_date')
        fig = px.line(df, x='entry_date', y='ac_count', markers=True,
                      labels={'entry_date': 'Date', 'ac_count': 'AC Count'}, line_shape='spline')
        fig.update_traces(line_color='#1E3A5F', marker_color='#2D6A9F')
        fig.update_layout(margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # Pending stores
    pending = data.get('pending_stores', [])
    st.subheader(f"Pending Stores — Not Serviced This Month ({len(pending)})")
    if pending:
        df = pd.DataFrame(pending)[['store_name', 'state', 'total_ac']]
        df.columns = ['Store', 'State', 'Total AC']
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.success("All stores serviced this month! 🎉")

    if st.button("🔄 Refresh", key="ref_overview"):
        st.rerun()


# ── Tab 2: Site Analysis ──────────────────────────────────────────────────────
with tab_site:
    st.markdown("#### Filters")

    all_brands  = ["All"] + get_brands()
    all_states  = ["All"] + get_states()
    all_techs   = [{"id": None, "name": "All"}] + get_users(role="Vendor")
    all_stores  = [{"id": None, "store_name": "All"}] + get_stores()

    f1, f2, f3, f4, f5 = st.columns(5)
    with f1:
        sel_brand  = st.selectbox("Brand",      all_brands)
    with f2:
        sel_state  = st.selectbox("State",      all_states)
    with f3:
        tech_names = [t['name'] for t in all_techs]
        sel_tech_n = st.selectbox("Technician", tech_names)
    with f4:
        store_names = [s['store_name'] for s in all_stores]
        sel_store_n = st.selectbox("Store",     store_names)
    with f5:
        period = st.selectbox("Period", [7, 14, 30, 60, 90],
                              format_func=lambda x: f"Last {x} days", index=2)

    # Resolve selections to IDs/values
    brand_val  = None if sel_brand  == "All" else sel_brand
    state_val  = None if sel_state  == "All" else sel_state
    tech_obj   = next((t for t in all_techs  if t['name']       == sel_tech_n),  None)
    store_obj  = next((s for s in all_stores if s['store_name'] == sel_store_n), None)
    tech_id    = tech_obj['id']   if tech_obj  else None
    store_id   = store_obj['id']  if store_obj else None

    sa = get_site_analysis(
        brand=brand_val, tech_id=tech_id,
        store_id=store_id, state=state_val, period_days=period
    )

    st.markdown("---")

    # KPIs
    k1, k2 = st.columns(2)
    k1.metric("AC Entries in Period",   sa.get('ac_count', 0))
    k2.metric("PMS Sessions in Period", sa.get('sessions', 0))

    # Charts
    c1, c2 = st.columns(2)
    with c1:
        bs = sa.get('by_store', [])
        if bs:
            st.subheader("ACs by Store")
            df = pd.DataFrame(bs)
            fig = px.bar(df, x='store_name', y='ac_count',
                         color='ac_count', color_continuous_scale='Blues',
                         labels={'store_name': 'Store', 'ac_count': 'AC Count'})
            fig.update_layout(showlegend=False, margin=dict(t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)

    with c2:
        bt = sa.get('by_tech', [])
        if bt:
            st.subheader("ACs by Technician")
            df = pd.DataFrame(bt)
            fig = px.bar(df, x='name', y='ac_count',
                         color='ac_count', color_continuous_scale='Greens',
                         labels={'name': 'Technician', 'ac_count': 'AC Count'})
            fig.update_layout(showlegend=False, margin=dict(t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)

    # Date trend
    bd = sa.get('by_date', [])
    if bd:
        st.subheader("Daily Trend in Period")
        df = pd.DataFrame(bd).sort_values('entry_date')
        fig = px.line(df, x='entry_date', y='ac_count', markers=True,
                      labels={'entry_date': 'Date', 'ac_count': 'AC Count'}, line_shape='spline')
        fig.update_traces(line_color='#1E3A5F', marker_color='#2D6A9F')
        fig.update_layout(margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)

    # Store completion table
    sc = sa.get('store_completion', [])
    if sc:
        st.subheader("Store Completion Details")
        df = pd.DataFrame(sc)
        df.columns = ['Store', 'Total AC', 'AC Done', 'Last PMS']
        st.dataframe(df, use_container_width=True, hide_index=True)

    if st.button("🔄 Refresh", key="ref_site"):
        st.rerun()
