import streamlit as st
import sys
import os
import pandas as pd
import plotly.express as px

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database import init_db, get_dashboard_data

init_db()

st.title("📊 Dashboard")
st.markdown("---")

data = get_dashboard_data()

# ── KPI cards ──────────────────────────────────────────────────────────────────
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Stores Covered Today",  data['stores_today'])
c2.metric("AC Checked Today",      data['ac_today'])
c3.metric("Total AC (All Time)",   data['ac_total'])
c4.metric("Total PMS Sessions",    data['sessions_total'])
c5.metric("Pending Stores Today",  data['pending'])

st.markdown("---")

col1, col2 = st.columns(2)
with col1:
    st.subheader("Top Stores by AC Count")
    if data['store_ac']:
        df = pd.DataFrame(data['store_ac'])
        fig = px.bar(df, x='store_name', y='ac_count',
                     color='ac_count', color_continuous_scale='Blues',
                     labels={'store_name': 'Store', 'ac_count': 'AC Count'})
        fig.update_layout(showlegend=False, margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No data yet.")

with col2:
    st.subheader("AC Type Distribution")
    if data['ac_type_dist']:
        df = pd.DataFrame(data['ac_type_dist'])
        fig = px.pie(df, values='cnt', names='ac_type',
                     color_discrete_sequence=px.colors.sequential.Blues_r, hole=0.4)
        fig.update_layout(margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No data yet.")

col1, col2 = st.columns(2)
with col1:
    st.subheader("Technician Performance")
    if data['tech_perf']:
        df = pd.DataFrame(data['tech_perf'])
        fig = px.bar(df, x='name', y='ac_count',
                     color='ac_count', color_continuous_scale='Greens',
                     labels={'name': 'Technician', 'ac_count': 'AC Count'})
        fig.update_layout(showlegend=False, margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No data yet.")

with col2:
    st.subheader("State-wise Summary")
    if data['state_summary']:
        df = pd.DataFrame(data['state_summary'])
        fig = px.bar(df, x='state', y='ac_count',
                     color='ac_count', color_continuous_scale='Oranges',
                     labels={'state': 'State', 'ac_count': 'AC Count'})
        fig.update_layout(showlegend=False, margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No data yet.")

if data['daily_trend']:
    st.subheader("Daily AC Check Trend (Last 30 Days)")
    df = pd.DataFrame(data['daily_trend']).sort_values('entry_date')
    fig = px.line(df, x='entry_date', y='ac_count', markers=True,
                  labels={'entry_date': 'Date', 'ac_count': 'AC Count'}, line_shape='spline')
    fig.update_traces(line_color='#1E3A5F', marker_color='#2D6A9F')
    fig.update_layout(margin=dict(t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)

st.markdown("---")
if st.button("🔄 Refresh"):
    st.rerun()