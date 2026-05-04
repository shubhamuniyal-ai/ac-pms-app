import streamlit as st
import sys
import os
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database import (
    init_db, get_accessible_stores, get_store_by_name, get_users,
    get_ac_types, create_pms_session, create_ac_entry, UPLOAD_DIR
)

init_db()

user = st.session_state.get('user', {})

st.title("📋 PMS Entry")
st.markdown("---")

stores = get_accessible_stores(user['id'])
store_names = [s['store_name'] for s in stores]

# Vendors submit their own entries; Admins can select any technician
if user['role'] == 'Vendor':
    tech_pool = [user]
else:
    tech_pool = get_users()  # all active users

tech_names = [t['name'] for t in tech_pool]
ac_types   = get_ac_types()

if not store_names:
    st.warning("No stores are assigned to your account. Ask your Admin to assign stores.")
    st.stop()
if not ac_types:
    st.warning("No AC types configured. Ask your Admin to add AC types in Settings.")
    st.stop()

# ── Header fields ──────────────────────────────────────────────────────────────
st.markdown("#### Session Details")
col1, col2, col3 = st.columns(3)
with col1:
    selected_store = st.selectbox("Store Name *", store_names)
with col2:
    ac_type = st.selectbox("AC Type *", ac_types)
with col3:
    entry_date = st.date_input("Date *", value=date.today())

store_info = get_store_by_name(selected_store)
col1, col2, col3 = st.columns(3)
with col1:
    st.text_input("State (Auto)", value=store_info['state'] if store_info else "", disabled=True)
with col2:
    st.number_input(
        "Total AC (from master)",
        value=store_info['total_ac'] if store_info else 0,
        disabled=True, min_value=0
    )
with col3:
    if user['role'] == 'Vendor':
        st.text_input("Technician", value=user['name'], disabled=True)
        selected_tech = user['name']
    else:
        default_idx = 0
        selected_tech = st.selectbox("Technician Name *", tech_names, index=default_idx)

st.markdown("---")

# ── AC count state ─────────────────────────────────────────────────────────────
if 'ac_count' not in st.session_state:
    st.session_state.ac_count = 1


def _add_ac():
    st.session_state.ac_count += 1


def _remove_ac():
    if st.session_state.ac_count > 1:
        idx = st.session_state.ac_count - 1
        for sfx in ('ac_num', 'serial', 'cap', 'img_ac', 'img_serial'):
            st.session_state.pop(f"{sfx}_{idx}", None)
        st.session_state.ac_count -= 1


def save_image(file_obj, store, d, ac_num, suffix):
    if file_obj is None:
        return None
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    ext  = file_obj.name.rsplit('.', 1)[-1] if '.' in file_obj.name else 'jpg'
    safe = store.replace(' ', '_').replace('/', '_')
    sac  = ac_num.replace(' ', '_').replace('/', '_')
    path = os.path.join(UPLOAD_DIR, f"{safe}_{d}_{sac}_{suffix}.{ext}")
    with open(path, 'wb') as f:
        f.write(file_obj.getbuffer())
    return path


# ── AC entry forms ─────────────────────────────────────────────────────────────
st.markdown(f"#### AC Entries  —  {st.session_state.ac_count} AC(s)")

for i in range(st.session_state.ac_count):
    with st.expander(f"AC #{i + 1}", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            st.text_input("AC Number *", key=f"ac_num_{i}", placeholder="e.g. AC-001")
            st.file_uploader(
                "AC Number Photo",
                type=['jpg', 'jpeg', 'png', 'webp'],
                key=f"img_ac_{i}",
                help="On mobile, tap to open camera"
            )
            if st.session_state.get(f"img_ac_{i}"):
                st.image(st.session_state[f"img_ac_{i}"], width=200)
        with col2:
            st.text_input("Brand Serial Number *", key=f"serial_{i}", placeholder="e.g. SN123456")
            st.file_uploader(
                "Serial Number Photo",
                type=['jpg', 'jpeg', 'png', 'webp'],
                key=f"img_serial_{i}",
                help="On mobile, tap to open camera"
            )
            if st.session_state.get(f"img_serial_{i}"):
                st.image(st.session_state[f"img_serial_{i}"], width=200)
        st.selectbox(
            "AC Capacity (Ton)",
            [0.75, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0],
            key=f"cap_{i}"
        )

col1, col2 = st.columns([1, 1])
with col1:
    st.button("➕ Add Another AC", on_click=_add_ac, use_container_width=True)
with col2:
    if st.session_state.ac_count > 1:
        st.button("➖ Remove Last AC", on_click=_remove_ac, use_container_width=True)

st.markdown("---")

# ── Submit ─────────────────────────────────────────────────────────────────────
if st.button("✅ Submit PMS Entry", type="primary"):
    errors  = []
    entries = []

    for i in range(st.session_state.ac_count):
        ac_num  = st.session_state.get(f"ac_num_{i}", "").strip()
        serial  = st.session_state.get(f"serial_{i}", "").strip()
        cap     = st.session_state.get(f"cap_{i}", 1.0)
        img_ac  = st.session_state.get(f"img_ac_{i}")
        img_sr  = st.session_state.get(f"img_serial_{i}")

        if not ac_num:
            errors.append(f"AC #{i+1}: AC Number is required")
        if not serial:
            errors.append(f"AC #{i+1}: Serial Number is required")
        if not img_ac and not img_sr:
            errors.append(f"AC #{i+1}: At least one photo is required")
        if ac_num and serial:
            entries.append((ac_num, serial, cap, img_ac, img_sr))

    if errors:
        for e in errors:
            st.error(e)
    else:
        try:
            store_obj = get_store_by_name(selected_store)
            tech_obj  = next(t for t in tech_pool if t['name'] == selected_tech)

            session_id = create_pms_session(
                store_obj['id'], tech_obj['id'], ac_type, entry_date.isoformat()
            )
            for ac_num, serial, cap, img_ac, img_sr in entries:
                path_ac = save_image(img_ac, selected_store, entry_date.isoformat(), ac_num, '1')
                path_sr = save_image(img_sr, selected_store, entry_date.isoformat(), ac_num, '2')
                create_ac_entry(session_id, ac_num, serial, cap, path_ac, path_sr)

            st.success(
                f"PMS Entry submitted! **{len(entries)} AC(s)** recorded for **{selected_store}**."
            )
            st.balloons()
            st.session_state.ac_count = 1
            for i in range(30):
                for sfx in ('ac_num', 'serial', 'cap', 'img_ac', 'img_serial'):
                    st.session_state.pop(f"{sfx}_{i}", None)
        except Exception as e:
            st.error(f"Failed to save: {e}")