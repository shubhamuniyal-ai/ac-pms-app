import streamlit as st
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database import (
    init_db, add_user, update_user, get_all_users, get_stores, get_states,
    update_user_status, generate_invite_token, send_invite_email,
    get_email_config, add_store, add_ac_type, get_ac_types
)

init_db()

st.title("👤 Manage Users")
st.markdown("---")

# ── Inline quick-add helpers (edit dropdown lists without leaving the page) ────
with st.expander("⚡ Quick-Add to Dropdown Lists", expanded=False):
    st.caption("Add stores or AC types instantly — they'll appear in all dropdowns.")
    c1, c2, c3 = st.columns(3)
    with c1:
        qs_name  = st.text_input("New Store Name", key="qs_name")
        qs_state = st.text_input("State", key="qs_state")
        qs_ac    = st.number_input("Total AC", min_value=0, key="qs_ac", value=0)
        if st.button("Add Store", key="qs_add_store"):
            if qs_name and qs_state:
                ok, msg = add_store(qs_name.strip(), qs_state.strip(), qs_ac)
                st.success(msg) if ok else st.error(msg)
                st.rerun()
    with c2:
        qa_type = st.text_input("New AC Type", key="qa_type")
        if st.button("Add AC Type", key="qa_add_type"):
            if qa_type:
                ok, msg = add_ac_type(qa_type.strip())
                st.success(msg) if ok else st.error(msg)
                st.rerun()
    with c3:
        email_cfg = get_email_config()
        smtp_ok = bool(email_cfg.get('smtp_user') and email_cfg.get('smtp_password'))
        if smtp_ok:
            st.success("✅ Email (SMTP) configured")
        else:
            st.warning("⚠️ SMTP not set — invites won't send.\nConfigure in **Settings → Email Config**.")

st.markdown("---")
tab1, tab2 = st.tabs(["➕ Create User", "👥 View / Manage Users"])

# ── Tab 1: Create ──────────────────────────────────────────────────────────────
with tab1:
    st.subheader("Create New User")

    col1, col2 = st.columns(2)
    with col1:
        name   = st.text_input("Full Name *")
        email  = st.text_input("Email Address *", placeholder="user@example.com")
        mobile = st.text_input("Mobile Number", placeholder="10 digits (optional)")
        role   = st.selectbox("Role *", ["Vendor", "Viewer", "Admin"],
                              help="Vendor: PMS entry + history | Viewer: dashboard + reports | Admin: full access")

    stores      = get_stores()
    store_names = [s['store_name'] for s in stores]
    states      = get_states()

    with col2:
        st.markdown("**Access Control**")
        st.caption("Leave blank to grant access to ALL stores/states.")

        assigned_stores = st.multiselect(
            "Assigned Stores (leave empty = all stores)",
            store_names,
            help="Vendor will only see these stores in PMS entry"
        )
        assigned_states = st.multiselect(
            "Assigned States (leave empty = all states)",
            states
        )

        st.markdown("&nbsp;")
        st.info(
            "📧 An invitation email with a **password setup link** will be sent automatically.\n\n"
            "If email fails, you'll see the setup link here to share manually."
        )

    if st.button("Create User & Send Invite", type="primary"):
        errors = []
        if not name.strip():
            errors.append("Full Name is required")
        if not email.strip() or '@' not in email:
            errors.append("Valid email address is required")
        if mobile and (len(mobile.strip()) != 10 or not mobile.strip().isdigit()):
            errors.append("Mobile must be exactly 10 digits if provided")

        if errors:
            for e in errors:
                st.error(e)
        else:
            ok, user_id, msg = add_user(
                name.strip(), mobile.strip() if mobile else None,
                email.strip(), role, assigned_states, assigned_stores
            )
            if not ok:
                st.error(msg)
            else:
                token = generate_invite_token(user_id)
                cfg   = get_email_config()
                app_url = cfg.get('app_url', 'http://localhost:8501')
                setup_link = f"{app_url}/?setup_token={token}"

                email_ok, email_msg = send_invite_email(email.strip(), name.strip(), role, token)

                st.success(f"✅ User **{name}** created as **{role}**.")

                if email_ok:
                    st.success(f"📧 {email_msg}")
                else:
                    st.warning(f"⚠️ {email_msg}")
                    st.markdown("**Share this setup link manually:**")
                    st.code(setup_link, language=None)
                    st.caption("This link expires in 48 hours.")


# ── Tab 2: View / Manage ────────────────────────────────────────────────────────
with tab2:
    st.subheader("All Users")

    all_users  = get_all_users()
    role_filter = st.selectbox("Filter by Role", ["All", "Admin", "Vendor", "Viewer"], key="role_f")
    if role_filter != "All":
        all_users = [u for u in all_users if u['role'] == role_filter]

    if not all_users:
        st.info("No users found.")
    else:
        for u in all_users:
            badge = {"Admin": "🔴", "Vendor": "🟢", "Viewer": "🔵"}.get(u['role'], "⚪")
            status_icon = "✅" if u['is_active'] else "❌"
            has_pwd = bool(u.get('password'))

            with st.expander(f"{badge} {u['name']}  ·  {u.get('email') or u.get('mobile','—')}  {status_icon}", expanded=False):
                c1, c2, c3 = st.columns([3, 2, 2])
                with c1:
                    st.write(f"**Role:** {u['role']}")
                    st.write(f"**Email:** {u.get('email','—')}")
                    st.write(f"**Mobile:** {u.get('mobile','—')}")
                    st.write(f"**Status:** {'Active' if u['is_active'] else 'Inactive'}")
                    st.write(f"**Password set:** {'Yes' if has_pwd else 'Pending setup'}")
                    st.write(f"**Joined:** {u['created_at']}")

                with c2:
                    stores_all  = get_stores()
                    states_all  = get_states()
                    store_names = [s['store_name'] for s in stores_all]

                    import json
                    cur_stores = json.loads(u.get('assigned_stores') or '[]')
                    cur_states = json.loads(u.get('assigned_states') or '[]')

                    new_stores = st.multiselect(
                        "Assigned Stores", store_names,
                        default=[x for x in cur_stores if x in store_names],
                        key=f"ed_stores_{u['id']}"
                    )
                    new_states = st.multiselect(
                        "Assigned States", states_all,
                        default=[x for x in cur_states if x in states_all],
                        key=f"ed_states_{u['id']}"
                    )

                with c3:
                    new_name   = st.text_input("Name",   value=u['name'],                   key=f"ed_name_{u['id']}")
                    new_email  = st.text_input("Email",  value=u.get('email',''),            key=f"ed_email_{u['id']}")
                    new_mobile = st.text_input("Mobile", value=u.get('mobile','') or '',     key=f"ed_mob_{u['id']}")
                    new_role   = st.selectbox("Role", ["Vendor","Viewer","Admin"],
                                             index=["Vendor","Viewer","Admin"].index(u['role']) if u['role'] in ["Vendor","Viewer","Admin"] else 0,
                                             key=f"ed_role_{u['id']}")

                    if st.button("💾 Save Changes", key=f"save_{u['id']}"):
                        ok2, msg2 = update_user(
                            u['id'], new_name, new_mobile or None,
                            new_email, new_role, new_states, new_stores
                        )
                        st.success(msg2) if ok2 else st.error(msg2)
                        st.rerun()

                st.markdown("---")
                col_a, col_b, col_c = st.columns(3)

                with col_a:
                    is_default_admin = (u.get('mobile') == '9999999999' and u['role'] == 'Admin')
                    if not is_default_admin:
                        label = "Deactivate" if u['is_active'] else "Activate"
                        if st.button(label, key=f"tog_{u['id']}"):
                            update_user_status(u['id'], 0 if u['is_active'] else 1)
                            st.rerun()

                with col_b:
                    if st.button("🔗 Resend Invite", key=f"inv_{u['id']}",
                                 help="Generate a new setup link and email it"):
                        tok = generate_invite_token(u['id'])
                        cfg = get_email_config()
                        app_url = cfg.get('app_url', 'http://localhost:8501')
                        link = f"{app_url}/?setup_token={tok}"

                        email_ok, email_msg = send_invite_email(
                            u.get('email',''), u['name'], u['role'], tok
                        )
                        if email_ok:
                            st.success(f"📧 Invite sent to {u.get('email')}")
                        else:
                            st.warning(f"⚠️ {email_msg}")
                            st.code(link, language=None)