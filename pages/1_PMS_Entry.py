import streamlit as st
import sys
import os
import json
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database import (
    init_db, get_accessible_stores, get_store_by_name, get_users,
    get_ac_types, get_brands, create_pms_session, create_ac_entry,
    UPLOAD_DIR, TONNAGE_OPTIONS
)
from sheets import append_pms_data as _sheets_append, is_configured as _sheets_ok

init_db()

user = st.session_state.get('user', {})
if not user:
    st.warning("Please login first.")
    st.stop()

st.title("📋 PMS Entry")

# ── Google Sheets required check ───────────────────────────────────────────────
if not _sheets_ok():
    st.error(
        "⚠️ **Google Sheets not configured.**  "
        "All PMS data is stored in Google Sheets. You must complete the setup before submitting entries."
    )
    st.markdown("""
**Quick setup (5 minutes):**
1. Go to **Settings → Google Sheets** tab
2. Follow the steps to create a Service Account and download the JSON credentials file
3. Upload the JSON file in Settings
4. Share the Google Sheet with the service account email shown
5. Come back here to submit PMS entries

Your Google Sheet: [Open Sheet](https://docs.google.com/spreadsheets/d/1HIFQU7keY70wWiwlo7R_wT8nAB3UdOQM-tLPEQqowJE)
    """)
    st.stop()
st.markdown("---")

stores = get_accessible_stores(user['id'])
store_names = [s['store_name'] for s in stores]

if user['role'] == 'Vendor':
    tech_pool = [user]
else:
    tech_pool = get_users()

tech_names = [t['name'] for t in tech_pool]
ac_types   = get_ac_types()
brands     = get_brands()

if not store_names:
    st.warning("No stores assigned to your account. Ask Admin to assign stores.")
    st.stop()
if not ac_types:
    st.warning("No AC types configured. Ask Admin to add AC types in Settings.")
    st.stop()

# ── Session Details ────────────────────────────────────────────────────────────
st.markdown("#### Session Details")
col1, col2, col3 = st.columns(3)
with col1:
    selected_store = st.selectbox("Store Name *", store_names)
with col2:
    ac_type = st.selectbox("AC Type *", ac_types)
with col3:
    entry_date = st.date_input("Date *", value=date.today())

store_info = get_store_by_name(selected_store)
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.text_input("State", value=store_info['state'] if store_info else "", disabled=True)
with col2:
    st.number_input("Total AC", value=store_info['total_ac'] if store_info else 0,
                    disabled=True, min_value=0)
with col3:
    brand_opts = [""] + brands
    selected_brand = st.selectbox("AC Brand *", brand_opts,
                                  format_func=lambda x: "— Select Brand —" if x == "" else x)
with col4:
    if user['role'] == 'Vendor':
        st.text_input("Technician", value=user['name'], disabled=True)
        selected_tech = user['name']
    else:
        selected_tech = st.selectbox("Technician *", tech_names)

st.markdown("---")

# ── AC count helpers ───────────────────────────────────────────────────────────
if 'ac_count' not in st.session_state:
    st.session_state.ac_count = 1


def _add_ac():
    st.session_state.ac_count += 1


def _remove_ac():
    if st.session_state.ac_count > 1:
        idx = st.session_state.ac_count - 1
        keys = ['ac_num', 'serial', 'cap', 'img_ac', 'img_serial', 'img_remote',
                'idu_filter', 'idu_drain', 'idu_pipe', 'idu_coil', 'idu_blower', 'idu_casing',
                'odu_condenser', 'odu_fan', 'odu_comp', 'odu_casing', 'odu_pipes',
                'elec_voltage', 'elec_current', 'elec_cap',
                'gas_check', 'gas_topup', 'gas_qty',
                'perf_inlet', 'perf_outlet',
                'issue_obs', 'issue_action', 'issue_parts',
                'rem_condition', 'rem_notes']
        for k in keys:
            st.session_state.pop(f"{k}_{idx}", None)
        st.session_state.ac_count -= 1


def save_image(file_obj, store, d, label, suffix):
    if file_obj is None:
        return None
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    ext  = file_obj.name.rsplit('.', 1)[-1] if '.' in file_obj.name else 'jpg'
    safe = store.replace(' ', '_').replace('/', '_')
    slbl = label.replace(' ', '_').replace('/', '_')
    path = os.path.join(UPLOAD_DIR, f"{safe}_{d}_{slbl}_{suffix}.{ext}")
    with open(path, 'wb') as f:
        f.write(file_obj.getbuffer())
    return path


# ── AC Entry Forms ─────────────────────────────────────────────────────────────
st.markdown(f"#### AC Entries — {st.session_state.ac_count} AC(s)")

CONDITION_OPTIONS = ["Good", "Average", "Needs Repair", "Non-Functional"]

for i in range(st.session_state.ac_count):
    with st.expander(f"AC #{i + 1}", expanded=True):

        # Basic Info
        col1, col2, col3 = st.columns(3)
        with col1:
            st.text_input("AC Number *", key=f"ac_num_{i}", placeholder="e.g. AC-001")
        with col2:
            st.text_input("Brand Serial Number *", key=f"serial_{i}", placeholder="e.g. SN123456")
        with col3:
            st.selectbox("Capacity (Ton) *", TONNAGE_OPTIONS, key=f"cap_{i}")

        # Photos
        st.markdown("**Photos**")
        pc1, pc2, pc3 = st.columns(3)
        with pc1:
            st.file_uploader("AC Number Photo", type=['jpg','jpeg','png','webp'],
                             key=f"img_ac_{i}", help="Tap to use camera on mobile")
            if st.session_state.get(f"img_ac_{i}"):
                st.image(st.session_state[f"img_ac_{i}"], width=160)
        with pc2:
            st.file_uploader("Serial Number Photo", type=['jpg','jpeg','png','webp'],
                             key=f"img_serial_{i}")
            if st.session_state.get(f"img_serial_{i}"):
                st.image(st.session_state[f"img_serial_{i}"], width=160)
        with pc3:
            st.file_uploader("Remote Display Photo", type=['jpg','jpeg','png','webp'],
                             key=f"img_remote_{i}")
            if st.session_state.get(f"img_remote_{i}"):
                st.image(st.session_state[f"img_remote_{i}"], width=160)

        st.markdown("---")

        # IDU Checks
        st.markdown("**🌀 IDU (Indoor Unit) Checks**")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.checkbox("Air filter cleaned",    key=f"idu_filter_{i}")
            st.checkbox("Drain tray cleaned",    key=f"idu_drain_{i}")
        with c2:
            st.checkbox("Drain pipe flushed",    key=f"idu_pipe_{i}")
            st.checkbox("Evaporator coil cleaned", key=f"idu_coil_{i}")
        with c3:
            st.checkbox("Blower/fan cleaned",    key=f"idu_blower_{i}")
            st.checkbox("Indoor casing wiped",   key=f"idu_casing_{i}")

        st.markdown("---")

        # ODU Checks
        st.markdown("**🔧 ODU (Outdoor Unit) Checks**")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.checkbox("Condenser coil cleaned", key=f"odu_condenser_{i}")
            st.checkbox("Fan motor OK",           key=f"odu_fan_{i}")
        with c2:
            st.checkbox("Compressor OK",          key=f"odu_comp_{i}")
            st.checkbox("ODU casing cleaned",     key=f"odu_casing_{i}")
        with c3:
            st.checkbox("Refrigerant pipes OK",   key=f"odu_pipes_{i}")

        st.markdown("---")

        # Electrical
        st.markdown("**⚡ Electrical Measurements**")
        e1, e2, e3 = st.columns(3)
        with e1:
            st.number_input("Supply Voltage (V)", min_value=0.0, max_value=500.0,
                            step=0.1, key=f"elec_voltage_{i}")
        with e2:
            st.number_input("Running Current (A)", min_value=0.0, max_value=100.0,
                            step=0.1, key=f"elec_current_{i}")
        with e3:
            st.checkbox("Capacitor OK", key=f"elec_cap_{i}")

        st.markdown("---")

        # Gas / Cooling
        st.markdown("**🌡️ Gas / Cooling Check**")
        g1, g2, g3 = st.columns(3)
        with g1:
            st.checkbox("Gas leak checked", key=f"gas_check_{i}")
        with g2:
            st.checkbox("Gas topped up",    key=f"gas_topup_{i}")
        with g3:
            st.number_input("Gas quantity (grams)", min_value=0, max_value=5000,
                            step=50, key=f"gas_qty_{i}")

        st.markdown("---")

        # Performance
        st.markdown("**📊 Performance**")
        p1, p2 = st.columns(2)
        with p1:
            st.number_input("Inlet Air Temp (°C)", min_value=0.0, max_value=60.0,
                            step=0.1, key=f"perf_inlet_{i}")
        with p2:
            st.number_input("Outlet Air Temp (°C)", min_value=0.0, max_value=60.0,
                            step=0.1, key=f"perf_outlet_{i}")

        st.markdown("---")

        # Issues & Action
        st.markdown("**🔴 Issues & Action Taken**")
        st.text_area("Issue Observed", key=f"issue_obs_{i}",    placeholder="Describe any problem found")
        st.text_area("Action Taken",   key=f"issue_action_{i}", placeholder="What was done to fix it")
        st.text_input("Spare Parts Used", key=f"issue_parts_{i}", placeholder="e.g. Capacitor 35µF")

        st.markdown("---")

        # Final Remarks
        st.markdown("**✅ Final Remarks**")
        r1, r2 = st.columns([1, 2])
        with r1:
            st.selectbox("Overall AC Condition", CONDITION_OPTIONS, key=f"rem_condition_{i}")
        with r2:
            st.text_area("Additional Notes", key=f"rem_notes_{i}", height=80,
                         placeholder="Any other observations")

col1, col2 = st.columns(2)
with col1:
    st.button("➕ Add Another AC", on_click=_add_ac, use_container_width=True)
with col2:
    if st.session_state.ac_count > 1:
        st.button("➖ Remove Last AC", on_click=_remove_ac, use_container_width=True)

st.markdown("---")

# ── Session-Level Photos ───────────────────────────────────────────────────────
st.markdown("#### 📸 Session Photos  *(one photo covers all ACs)*")
st.caption("Upload one photo/video per category — applies to the whole visit.")

sp1, sp2 = st.columns(2)
with sp1:
    st.file_uploader("Air Filter Cleaned — Photo",
                     type=['jpg','jpeg','png','webp'], key="sess_air_filter",
                     help="One photo showing cleaned air filter(s)")
    if st.session_state.get("sess_air_filter"):
        st.image(st.session_state["sess_air_filter"], width=200)

    st.file_uploader("Drain Tray Cleaned — Photo",
                     type=['jpg','jpeg','png','webp'], key="sess_drain_tray")
    if st.session_state.get("sess_drain_tray"):
        st.image(st.session_state["sess_drain_tray"], width=200)

with sp2:
    st.file_uploader("Grill Temp — Photo / Video",
                     type=['jpg','jpeg','png','webp','mp4','mov'], key="sess_grill_temp",
                     help="Temperature gun reading or thermal image")
    if st.session_state.get("sess_grill_temp"):
        f = st.session_state["sess_grill_temp"]
        if f.type.startswith("image"):
            st.image(f, width=200)

st.markdown("---")

# ── Final Remarks (mandatory — filled last) ────────────────────────────────────
st.markdown("#### 🔹 Final Remarks")
st.info("⚠️ All fields below are mandatory. Fill these after completing all AC entries and photos above.")

fr1, fr2 = st.columns(2)
with fr1:
    st.text_area("Technician Remarks *", key="fr_tech_remarks",
                 placeholder="Write your observations / service summary")
    st.text_input("Customer Signature (Name) *", key="fr_cust_signature",
                  placeholder="Customer representative name")
with fr2:
    st.text_input("Customer Emp Code *", key="fr_cust_empcode",
                  placeholder="Employee / staff code of the customer")
    st.text_area("Feedback *", key="fr_feedback",
                 placeholder="Customer feedback about this service visit")

st.text_area("Customer Complaint after Service & Pending Work *",
             key="fr_complaint",
             placeholder="List any complaints raised after service OR pending work to be done",
             height=100)

st.file_uploader("FSR Report — Upload Photo / PDF *",
                 type=['jpg','jpeg','png','webp','pdf'], key="sess_fsr_report",
                 help="Field Service Report document or photo")
if st.session_state.get("sess_fsr_report"):
    f = st.session_state["sess_fsr_report"]
    if f.type.startswith("image"):
        st.image(f, width=250)
    else:
        st.success(f"📄 {f.name} uploaded")

st.markdown("---")

# ── Submit ─────────────────────────────────────────────────────────────────────
if st.button("✅ Submit PMS Entry", type="primary", use_container_width=True):
    errors  = []
    entries = []

    if not selected_brand:
        errors.append("Brand is required.")

    # Final Remarks — all mandatory
    fr_tech_remarks   = st.session_state.get("fr_tech_remarks",    "").strip()
    fr_cust_signature = st.session_state.get("fr_cust_signature",  "").strip()
    fr_cust_empcode   = st.session_state.get("fr_cust_empcode",    "").strip()
    fr_feedback       = st.session_state.get("fr_feedback",        "").strip()
    fr_complaint      = st.session_state.get("fr_complaint",       "").strip()
    fr_fsr_file       = st.session_state.get("sess_fsr_report")

    if not fr_tech_remarks:
        errors.append("Final Remarks: Technician Remarks is required.")
    if not fr_cust_signature:
        errors.append("Final Remarks: Customer Signature (Name) is required.")
    if not fr_cust_empcode:
        errors.append("Final Remarks: Customer Emp Code is required.")
    if not fr_feedback:
        errors.append("Final Remarks: Feedback is required.")
    if not fr_complaint:
        errors.append("Final Remarks: Customer Complaint / Pending Work is required.")
    if not fr_fsr_file:
        errors.append("Final Remarks: FSR Report upload is required.")

    for i in range(st.session_state.ac_count):
        ac_num = st.session_state.get(f"ac_num_{i}", "").strip()
        serial = st.session_state.get(f"serial_{i}", "").strip()
        cap    = st.session_state.get(f"cap_{i}", 1.0)
        if not ac_num:
            errors.append(f"AC #{i+1}: AC Number is required.")
        if not serial:
            errors.append(f"AC #{i+1}: Serial Number is required.")
        if ac_num and serial:
            checklist = {
                "idu": {
                    "air_filter_cleaned":      bool(st.session_state.get(f"idu_filter_{i}")),
                    "drain_tray_cleaned":      bool(st.session_state.get(f"idu_drain_{i}")),
                    "drain_pipe_flushed":      bool(st.session_state.get(f"idu_pipe_{i}")),
                    "evaporator_coil_cleaned": bool(st.session_state.get(f"idu_coil_{i}")),
                    "blower_cleaned":          bool(st.session_state.get(f"idu_blower_{i}")),
                    "casing_wiped":            bool(st.session_state.get(f"idu_casing_{i}")),
                },
                "odu": {
                    "condenser_coil_cleaned": bool(st.session_state.get(f"odu_condenser_{i}")),
                    "fan_motor_ok":           bool(st.session_state.get(f"odu_fan_{i}")),
                    "compressor_ok":          bool(st.session_state.get(f"odu_comp_{i}")),
                    "casing_cleaned":         bool(st.session_state.get(f"odu_casing_{i}")),
                    "pipes_ok":               bool(st.session_state.get(f"odu_pipes_{i}")),
                },
                "electrical": {
                    "supply_voltage":  float(st.session_state.get(f"elec_voltage_{i}") or 0),
                    "running_current": float(st.session_state.get(f"elec_current_{i}") or 0),
                    "capacitor_ok":    bool(st.session_state.get(f"elec_cap_{i}")),
                },
                "gas_cooling": {
                    "gas_leak_checked": bool(st.session_state.get(f"gas_check_{i}")),
                    "gas_topped_up":    bool(st.session_state.get(f"gas_topup_{i}")),
                    "gas_qty_grams":    int(st.session_state.get(f"gas_qty_{i}") or 0),
                },
                "performance": {
                    "inlet_temp":  float(st.session_state.get(f"perf_inlet_{i}") or 0),
                    "outlet_temp": float(st.session_state.get(f"perf_outlet_{i}") or 0),
                },
                "issues": {
                    "issue_observed": st.session_state.get(f"issue_obs_{i}", ""),
                    "action_taken":   st.session_state.get(f"issue_action_{i}", ""),
                    "parts_replaced": st.session_state.get(f"issue_parts_{i}", ""),
                },
                "remarks": {
                    "overall_condition": st.session_state.get(f"rem_condition_{i}", "Good"),
                    "notes":             st.session_state.get(f"rem_notes_{i}", ""),
                },
            }
            entries.append((ac_num, serial, cap,
                            st.session_state.get(f"img_ac_{i}"),
                            st.session_state.get(f"img_serial_{i}"),
                            st.session_state.get(f"img_remote_{i}"),
                            checklist))

    if errors:
        for e in errors:
            st.error(e)
    else:
        try:
            store_obj = get_store_by_name(selected_store)
            tech_obj  = next(t for t in tech_pool if t['name'] == selected_tech)
            d_str     = entry_date.isoformat()

            # Save session-level photos
            def _save_sess(file_obj, suffix):
                if file_obj is None:
                    return None
                os.makedirs(UPLOAD_DIR, exist_ok=True)
                ext  = file_obj.name.rsplit('.', 1)[-1] if '.' in file_obj.name else 'jpg'
                safe = selected_store.replace(' ', '_').replace('/', '_')
                path = os.path.join(UPLOAD_DIR, f"{safe}_{d_str}_sess_{suffix}.{ext}")
                with open(path, 'wb') as f:
                    f.write(file_obj.getbuffer())
                return path

            p_air    = _save_sess(st.session_state.get("sess_air_filter"),  "air_filter")
            p_drain  = _save_sess(st.session_state.get("sess_drain_tray"),  "drain_tray")
            p_grill  = _save_sess(st.session_state.get("sess_grill_temp"),  "grill_temp")
            p_fsr    = _save_sess(st.session_state.get("sess_fsr_report"),  "fsr_report")

            final_remarks_data = {
                "technician_remarks":   fr_tech_remarks,
                "customer_signature":   fr_cust_signature,
                "customer_emp_code":    fr_cust_empcode,
                "feedback":             fr_feedback,
                "complaint_pending":    fr_complaint,
            }

            session_id = create_pms_session(
                store_obj['id'], tech_obj['id'], ac_type, d_str,
                brand=selected_brand,
                img_air_filter=p_air, img_drain_tray=p_drain,
                img_grill_temp=p_grill, img_fsr_report=p_fsr,
                final_remarks=final_remarks_data
            )

            for ac_num, serial, cap, img_ac, img_sr, img_rd, checklist in entries:
                p_ac = save_image(img_ac, selected_store, d_str, ac_num, 'ac')
                p_sr = save_image(img_sr, selected_store, d_str, ac_num, 'serial')
                p_rd = save_image(img_rd, selected_store, d_str, ac_num, 'remote')
                create_ac_entry(session_id, ac_num, serial, cap, p_ac, p_sr,
                                checklist_data=checklist, img_remote_display=p_rd)

            st.success(
                f"✅ PMS Entry submitted! **{len(entries)} AC(s)** recorded for **{selected_store}**."
            )
            st.balloons()

            # Write to Google Sheet (primary data store)
            sess_info = {
                "date":       d_str,
                "store_name": selected_store,
                "state":      store_obj.get("state", ""),
                "tech_name":  tech_obj["name"],
                "brand":      selected_brand,
                "ac_type":    ac_type,
            }
            sheet_entries = [
                {"ac_number": ac_num, "serial_number": serial,
                 "capacity": cap, "checklist": cl}
                for ac_num, serial, cap, _, _, _, cl in entries
            ]
            with st.spinner("Saving to Google Sheet..."):
                sh_ok, sh_msg = _sheets_append(sess_info, sheet_entries, final_remarks_data)
            if sh_ok:
                st.info(f"📊 {sh_msg}")
            else:
                st.error(f"📊 Google Sheet save failed: {sh_msg}")

            # Reset form
            st.session_state.ac_count = 1
            for i in range(50):
                for k in ['ac_num', 'serial', 'cap', 'img_ac', 'img_serial', 'img_remote',
                          'idu_filter', 'idu_drain', 'idu_pipe', 'idu_coil', 'idu_blower', 'idu_casing',
                          'odu_condenser', 'odu_fan', 'odu_comp', 'odu_casing', 'odu_pipes',
                          'elec_voltage', 'elec_current', 'elec_cap',
                          'gas_check', 'gas_topup', 'gas_qty',
                          'perf_inlet', 'perf_outlet',
                          'issue_obs', 'issue_action', 'issue_parts',
                          'rem_condition', 'rem_notes']:
                    st.session_state.pop(f"{k}_{i}", None)
            for k in ['sess_air_filter', 'sess_drain_tray', 'sess_grill_temp', 'sess_fsr_report',
                      'fr_tech_remarks', 'fr_cust_signature', 'fr_cust_empcode',
                      'fr_feedback', 'fr_complaint']:
                st.session_state.pop(k, None)

        except Exception as e:
            st.error(f"Failed to save: {e}")
