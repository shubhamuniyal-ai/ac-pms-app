import streamlit as st
import sys
import os
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database import (
    init_db, authenticate, verify_token, activate_account,
    create_session_token, verify_session_token
)

st.set_page_config(
    page_title="AC PMS System",
    page_icon="❄️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<link rel="manifest" href="/_stcore/static/manifest.json">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="AC PMS">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="theme-color" content="#1E3A5F">
""", unsafe_allow_html=True)

init_db()

st.markdown("""
<style>
    .main-header {
        font-size: 2rem; font-weight: 800; color: #1E3A5F;
        text-align: center; padding: 1rem 0 0.3rem; letter-spacing: 1px;
    }
    .sub-header { text-align:center; color:#666; margin-bottom:1.5rem; font-size:.95rem; }
    .role-badge {
        display:inline-block; padding:3px 10px; border-radius:20px;
        font-size:.78rem; font-weight:600;
    }
    .badge-admin   { background:#fde8e8; color:#b91c1c; }
    .badge-vendor  { background:#d1fae5; color:#065f46; }
    .badge-viewer  { background:#dbeafe; color:#1e40af; }
</style>
""", unsafe_allow_html=True)

# ── Session state init ─────────────────────────────────────────────────────────
if 'logged_in' not in st.session_state:
    st.session_state.logged_in    = False
    st.session_state.user         = None
    st.session_state.login_date   = None
    st.session_state.session_token = None

# ── Auto-login via session token (URL or session_state) ───────────────────────
if not st.session_state.logged_in:
    # Check URL param first, then fall back to nothing (session_state already cleared)
    s_token = st.query_params.get('s', '') or st.session_state.get('session_token', '')
    if s_token:
        restored = verify_session_token(s_token)
        if restored:
            st.session_state.logged_in     = True
            st.session_state.user          = restored
            st.session_state.login_date    = date.today().isoformat()
            st.session_state.session_token = s_token

# ── Always keep token in URL so page refresh works ────────────────────────────
if st.session_state.logged_in and st.session_state.get('session_token'):
    tok = st.session_state.session_token
    try:
        if st.query_params.get('s', '') != tok:
            st.query_params['s'] = tok
    except Exception:
        pass

# ── End-of-day logout (11 PM) — does not fire during normal working hours ─────
if st.session_state.logged_in:
    from datetime import datetime as _dt
    now = _dt.now()
    # Logout only between 11 PM and 6 AM (outside normal working hours)
    if now.hour >= 23 or now.hour < 6:
        login_date = st.session_state.get('login_date')
        if login_date and login_date != date.today().isoformat():
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            try:
                st.query_params.clear()
            except Exception:
                pass
            st.rerun()


# ── Password setup flow (via invite link) ──────────────────────────────────────
def password_setup_view():
    token = st.query_params.get('setup_token', '')
    user  = verify_token(token) if token else None

    st.markdown('<div class="main-header">❄️ AC PMS System</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Account Setup</div>', unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        if not user:
            st.error("This setup link is invalid or has expired (links expire after 48 hours).")
            st.info("Ask your Admin to resend the invitation.")
            st.stop()

        st.success(f"Hello **{user['name']}** — set your password to activate your account.")
        st.markdown(f"Role: **{user['role']}**")
        st.markdown("---")

        pwd  = st.text_input("New Password", type="password", placeholder="Min 6 characters")
        pwd2 = st.text_input("Confirm Password", type="password")

        if st.button("Activate Account & Set Password", type="primary", use_container_width=True):
            if len(pwd) < 6:
                st.error("Password must be at least 6 characters.")
            elif pwd != pwd2:
                st.error("Passwords do not match.")
            else:
                activate_account(token, pwd)
                st.success("Account activated! You can now login.")
                st.balloons()
                st.query_params.clear()
                st.rerun()


# ── Login view ─────────────────────────────────────────────────────────────────
def login_view():
    st.markdown('<div class="main-header">❄️ AC PMS System</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Preventive Maintenance Service — Track, Manage & Report</div>',
                unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("#### Login")
        identifier = st.text_input("Email / Mobile", placeholder="Enter your email or mobile number")
        password   = st.text_input("Password", type="password", placeholder="Enter your password")

        if st.button("Login", type="primary", use_container_width=True):
            if identifier and password:
                user = authenticate(identifier, password)
                if user:
                    token = create_session_token(user['id'])
                    st.session_state.logged_in     = True
                    st.session_state.user          = user
                    st.session_state.login_date    = date.today().isoformat()
                    st.session_state.session_token = token
                    try:
                        st.query_params['s'] = token
                    except Exception:
                        pass
                    st.rerun()
                else:
                    st.error("Invalid credentials or account inactive.")
            else:
                st.warning("Please enter your email/mobile and password.")

        st.caption("Contact your administrator if you need login access.")


# ── Route: setup token → login → app ──────────────────────────────────────────
if 'setup_token' in st.query_params:
    pg = st.navigation([st.Page(password_setup_view, title="Set Password", icon="🔑")])
    pg.run()
    st.stop()

if not st.session_state.logged_in:
    pg = st.navigation([st.Page(login_view, title="Login", icon="🔐")])
    pg.run()
    st.stop()

# ── Authenticated: build role-based navigation ─────────────────────────────────
user = st.session_state.user
role = user['role']

pms_page      = st.Page("pages/1_PMS_Entry.py",   title="PMS Entry",    icon="📋")
dash_page     = st.Page("pages/2_Dashboard.py",   title="Dashboard",    icon="📊")
report_page   = st.Page("pages/3_Reports.py",     title="Reports",      icon="📑")
users_page    = st.Page("pages/4_Create_User.py", title="Manage Users", icon="👤")
settings_page = st.Page("pages/5_Settings.py",    title="Settings",     icon="⚙️")
history_page  = st.Page("pages/6_My_History.py",  title="My History",   icon="🕐")

if role == 'Admin':
    nav = {
        "Work":      [pms_page, history_page],
        "Analytics": [dash_page, report_page],
        "Admin":     [users_page, settings_page],
    }
elif role == 'Vendor':
    nav = {
        "Work":    [pms_page, history_page],
        "View":    [dash_page],
        "Account": [settings_page],
    }
else:  # Viewer
    nav = {
        "Analytics": [dash_page, report_page],
        "Account":   [settings_page],
    }

badge_class = {'Admin': 'badge-admin', 'Vendor': 'badge-vendor', 'Viewer': 'badge-viewer'}.get(role, '')
with st.sidebar:
    st.markdown(f"**{user['name']}**")
    st.markdown(
        f'<span class="role-badge {badge_class}">{role}</span>',
        unsafe_allow_html=True
    )
    st.caption(user.get('email') or user.get('mobile') or '')
    st.markdown("---")
    if st.button("Logout", use_container_width=True):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        try:
            st.query_params.clear()
        except Exception:
            pass
        st.rerun()
    st.markdown("---")

pg = st.navigation(nav)
pg.run()
