import streamlit as st
import sys
import os
import json
import pandas as pd
import zipfile
import io
import qrcode
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database import (
    init_db, get_stores, add_store, update_store, delete_store,
    get_ac_types, add_ac_type, delete_ac_type,
    get_brands, add_brand, delete_brand,
    get_email_config, update_email_config, send_invite_email,
    authenticate, change_password, DB_PATH, UPLOAD_DIR
)

init_db()

user = st.session_state.get('user', {})
role = user.get('role', 'Viewer')

st.title("⚙️ Settings")
st.markdown("---")

# ── Shared helpers ─────────────────────────────────────────────────────────────
def _change_password_section(key_prefix=""):
    current = st.text_input("Current Password", type="password", key=f"{key_prefix}cur")
    new_pwd = st.text_input("New Password", type="password", key=f"{key_prefix}new",
                            placeholder="Min 6 characters")
    confirm = st.text_input("Confirm New Password", type="password", key=f"{key_prefix}cfm")
    if st.button("Update Password", type="primary", key=f"{key_prefix}btn"):
        if not current or not new_pwd or not confirm:
            st.error("All fields are required.")
        elif len(new_pwd) < 6:
            st.error("New password must be at least 6 characters.")
        elif new_pwd != confirm:
            st.error("New passwords do not match.")
        else:
            identifier = user.get('email') or user.get('mobile', '')
            if not authenticate(identifier, current):
                st.error("Current password is incorrect.")
            else:
                change_password(user['id'], new_pwd)
                st.success("Password updated successfully!")


def _build_zip():
    app_dir  = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(app_dir)
    buf = io.BytesIO()
    skip_dirs = {'data', 'uploads', '__pycache__', '.git', '.streamlit'}
    skip_exts = {'.db', '.pyc', '.log'}
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for dp, dns, fns in os.walk(root_dir):
            dns[:] = [d for d in dns if d not in skip_dirs]
            for fn in fns:
                if any(fn.endswith(e) for e in skip_exts): continue
                fp = os.path.join(dp, fn)
                zf.write(fp, os.path.relpath(fp, os.path.dirname(root_dir)))
        cfg_path = os.path.join(root_dir, '.streamlit', 'config.toml')
        if os.path.exists(cfg_path):
            zf.write(cfg_path, os.path.join('pms_app', '.streamlit', 'config.toml'))
    buf.seek(0)
    return buf.getvalue()


def _gdrive_to_direct(url):
    """Convert Google Drive share link to direct download link."""
    import re
    if not url:
        return url
    m = re.search(r'/d/([a-zA-Z0-9_-]+)', url)
    if m:
        return f"https://drive.google.com/uc?export=download&id={m.group(1)}"
    return url


def _mobile_install_section():
    cfg     = get_email_config()
    app_url = cfg.get('app_url', 'http://localhost:8501').rstrip('/')
    apk_url = _gdrive_to_direct(cfg.get('apk_url', '').strip())

    # ── APK download button (prominent, top) ──────────────────────────────────
    if apk_url:
        st.markdown(
            f"""
            <div style="background:#1E3A5F;padding:18px 24px;border-radius:12px;
                        text-align:center;margin-bottom:20px">
              <a href="{apk_url}"
                 style="color:#fff;font-size:1.2rem;font-weight:700;text-decoration:none">
                 📲 Download Android APK
              </a>
              <p style="color:#aac4e0;margin:6px 0 0;font-size:.85rem">
                Tap → Download → Install → Use as native app
              </p>
            </div>
            """,
            unsafe_allow_html=True
        )
        with st.expander("How to install the APK on Android"):
            st.markdown("""
1. Tap **Download Android APK** above
2. Open **Files / Downloads** on your phone
3. Tap the downloaded `.apk` file
4. If asked, tap **Install anyway** (allow unknown sources once)
5. App installs — open it from home screen ✅

> **If blocked:** Go to **Settings → Security → Install unknown apps** → allow your browser
            """)
    else:
        st.info("💡 Admin can add an APK download link in **Settings → Email Config → APK Download URL**")

    st.markdown("---")
    st.markdown(f"**App URL:** `{app_url}`")
    col1, col2 = st.columns([1, 1.8])
    with col1:
        qr = qrcode.QRCode(box_size=6, border=2)
        qr.add_data(app_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#1E3A5F", back_color="white")
        st.image(img.get_image(), caption="Scan to open in browser", width=210)
    with col2:
        st.markdown("#### 🤖 Android — Install as App (Chrome)")
        st.markdown("""
1. Scan QR code → opens in Chrome
2. Tap **⋮** menu (top-right)
3. Tap **"Add to Home screen"**
4. Tap **Add** — icon appears on home screen ✅
        """)
        st.markdown("#### 🍎 iPhone / iPad (Safari)")
        st.markdown("""
1. Scan QR → open in **Safari**
2. Tap **Share ↑** (bottom bar)
3. Tap **"Add to Home Screen"** → Add ✅
        """)
        st.caption("Runs full screen with camera access — same as a native app.")


# ── Non-admin: password + mobile install + download ────────────────────────────
if role != 'Admin':
    tab_pwd, tab_mob, tab_dl = st.tabs(["🔑 Change Password", "📱 Install on Mobile", "📦 Download App"])

    with tab_pwd:
        st.subheader("Change Your Password")
        _change_password_section("usr_")

    with tab_mob:
        st.subheader("Install App on Your Phone")
        _mobile_install_section()

    with tab_dl:
        st.subheader("Download App Source")
        st.markdown("Download and run on another Windows machine:\n```\npip install -r requirements.txt\nstreamlit run app.py\n```")
        if st.button("📦 Generate ZIP"):
            with st.spinner("Packaging..."):
                data = _build_zip()
            st.download_button("⬇️ Download pms_app.zip", data=data,
                               file_name="pms_app.zip", mime="application/zip")
    st.stop()

# ── Admin only below this line ─────────────────────────────────────────────────
tab_sheets, tab0, tab1, tab2, tab_brands, tab3, tab4, tab5 = st.tabs([
    "📊 Google Sheets", "🔑 Change Password", "🏪 Store Master", "❄️ AC Types",
    "🏷️ AC Brands", "📧 Email Config", "📱 Install on Mobile", "📦 App Download"
])

with tab0:
    st.subheader("Change Your Password")
    _change_password_section("adm_")

# ── Tab 1: Store Master ────────────────────────────────────────────────────────
with tab1:
    subtab_add, subtab_bulk, subtab_list, subtab_del = st.tabs(["Add Store", "Bulk Upload", "Store List", "🗑️ Delete All"])

    with subtab_add:
        col1, col2 = st.columns(2)
        with col1:
            sname  = st.text_input("Store Name *")
            sstate = st.text_input("State *")
            stac   = st.number_input("Total AC Count *", min_value=0, value=0)
            if st.button("Add Store", type="primary"):
                if sname.strip() and sstate.strip():
                    ok, msg = add_store(sname.strip(), sstate.strip(), stac)
                    st.success(msg) if ok else st.error(msg)
                    if ok:
                        st.rerun()
                else:
                    st.warning("Store Name and State are required.")

    with subtab_bulk:
        st.markdown("Upload Excel/CSV with columns: **Store Name**, **State**, **Total AC**")
        tmpl = pd.DataFrame(columns=['Store Name', 'State', 'Total AC'])
        st.download_button("📥 Download Template", tmpl.to_csv(index=False),
                           "store_template.csv", "text/csv")
        up = st.file_uploader("Upload File", type=['xlsx', 'xls', 'csv'])
        if up:
            try:
                if up.name.endswith('.csv'):
                    raw = up.read()
                    for enc in ('utf-8', 'cp1252', 'latin-1', 'utf-8-sig'):
                        try:
                            df = pd.read_csv(__import__('io').BytesIO(raw), encoding=enc)
                            break
                        except (UnicodeDecodeError, Exception):
                            continue
                    else:
                        st.error("Could not read CSV. Try saving the file as UTF-8 CSV from Excel.")
                        st.stop()
                else:
                    df = pd.read_excel(up)
                df.columns = df.columns.str.strip()
                required = {'Store Name', 'State', 'Total AC'}
                if not required.issubset(set(df.columns)):
                    st.error(f"Missing columns: {required - set(df.columns)}")
                else:
                    df = df.dropna(subset=['Store Name', 'State'])
                    df['Total AC'] = pd.to_numeric(df['Total AC'], errors='coerce').fillna(0).astype(int)
                    st.dataframe(df.head(20), use_container_width=True)
                    if st.button("Import Stores", type="primary"):
                        added = skipped = 0
                        for _, row in df.iterrows():
                            ok, _ = add_store(str(row['Store Name']).strip(),
                                              str(row['State']).strip(), int(row['Total AC']))
                            if ok: added += 1
                            else:  skipped += 1
                        st.success(f"Imported: **{added}** stores | Skipped (duplicates): **{skipped}**")
                        st.rerun()
            except Exception as e:
                st.error(f"Error reading file: {e}")

    with subtab_list:
        stores = get_stores()
        if not stores:
            st.info("No stores added yet.")
        else:
            st.write(f"**{len(stores)} stores in master**")
            for s in stores:
                with st.expander(f"🏪 {s['store_name']} — {s['state']} ({s['total_ac']} ACs)"):
                    c1, c2 = st.columns([3, 1])
                    with c1:
                        n_name  = st.text_input("Store Name", value=s['store_name'], key=f"sn_{s['id']}")
                        n_state = st.text_input("State",      value=s['state'],      key=f"ss_{s['id']}")
                        n_tac   = st.number_input("Total AC", value=s['total_ac'],   key=f"st_{s['id']}",
                                                  min_value=0)
                    with c2:
                        st.write("")
                        st.write("")
                        if st.button("💾 Save", key=f"sv_{s['id']}"):
                            ok, msg = update_store(s['id'], n_name, n_state, n_tac)
                            st.success(msg) if ok else st.error(msg)
                            if ok: st.rerun()
                        if st.button("🗑️ Delete", key=f"dl_{s['id']}"):
                            delete_store(s['id'])
                            st.success(f"Deleted '{s['store_name']}'")
                            st.rerun()


    with subtab_del:
        st.subheader("Delete All Stores")
        stores_all = get_stores()
        if not stores_all:
            st.info("No stores in the database.")
        else:
            st.warning(f"This will permanently delete all **{len(stores_all)} stores**. This cannot be undone.")
            confirm_del = st.text_input("Type **DELETE ALL** to confirm", placeholder="DELETE ALL")
            if st.button("🗑️ Delete All Stores", type="primary",
                         disabled=(confirm_del != "DELETE ALL")):
                for s in stores_all:
                    delete_store(s['id'])
                st.success(f"All {len(stores_all)} stores deleted.")
                st.rerun()


# ── Tab 2: AC Types ────────────────────────────────────────────────────────────
with tab2:
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Add AC Type")
        new_type = st.text_input("AC Type Name", placeholder="e.g. VRF")
        if st.button("Add AC Type", type="primary"):
            if new_type.strip():
                ok, msg = add_ac_type(new_type.strip())
                st.success(msg) if ok else st.error(msg)
                if ok: st.rerun()
            else:
                st.warning("AC Type name required.")

    with col2:
        st.subheader("Current AC Types")
        types = get_ac_types()
        if types:
            for t in types:
                ca, cb = st.columns([5, 1])
                with ca: st.write(f"❄️  {t}")
                with cb:
                    if st.button("Delete", key=f"dt_{t}"):
                        delete_ac_type(t)
                        st.rerun()
        else:
            st.info("No AC types defined.")


# ── Tab Brands ────────────────────────────────────────────────────────────────
with tab_brands:
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Add Brand")
        new_brand = st.text_input("Brand Name", placeholder="e.g. O General")
        if st.button("Add Brand", type="primary"):
            if new_brand.strip():
                ok, msg = add_brand(new_brand.strip())
                st.success(msg) if ok else st.error(msg)
                if ok: st.rerun()
            else:
                st.warning("Brand name is required.")

    with col2:
        st.subheader("Current Brands")
        brands = get_brands()
        if brands:
            for b in brands:
                ca, cb = st.columns([5, 1])
                with ca: st.write(f"🏷️  {b}")
                with cb:
                    if st.button("Delete", key=f"db_{b}"):
                        delete_brand(b)
                        st.rerun()
        else:
            st.info("No brands defined yet.")


# ── Tab Google Sheets ─────────────────────────────────────────────────────────
with tab_sheets:
    import sys as _sys
    _sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from sheets import (
        get_config as _sh_get_cfg, save_config as _sh_save_cfg,
        test_connection as _sh_test, is_configured as _sh_ok,
        sync_all as _sh_sync_all, APPS_SCRIPT_CODE,
        DEFAULT_SHEET_ID as _DEFAULT_SID
    )

    _sh_cfg    = _sh_get_cfg()
    _sh_active = _sh_ok()

    if _sh_active:
        st.success("✅ Google Sheets active — all PMS entries save directly to your sheet. Free.")
    else:
        st.error("⚠️ Not configured yet. Follow the 3 steps below (takes ~3 minutes, completely free).")

    st.markdown(
        f"📄 **Your Sheet:** [Open Google Sheet]"
        f"(https://docs.google.com/spreadsheets/d/{_sh_cfg.get('sheet_id', _DEFAULT_SID)})"
    )
    st.markdown("---")

    # ── Step 1 ─────────────────────────────────────────────────────────────────
    st.markdown("### Step 1 — Add the script to your Google Sheet")
    st.markdown(
        "Open your **[Google Sheet](https://docs.google.com/spreadsheets/d/"
        f"{_sh_cfg.get('sheet_id', _DEFAULT_SID)})** → "
        "click **Extensions → Apps Script** → delete all existing code → paste this:"
    )
    st.code(APPS_SCRIPT_CODE, language="javascript")
    st.caption("Click 💾 Save in Apps Script after pasting.")

    st.markdown("---")

    # ── Step 2 ─────────────────────────────────────────────────────────────────
    st.markdown("### Step 2 — Deploy as Web App")
    st.markdown("""
1. In Apps Script → click **Deploy → New deployment**
2. Click ⚙️ gear icon next to "Select type" → choose **Web app**
3. Set:
   - **Execute as:** Me
   - **Who has access:** Anyone
4. Click **Deploy** → **Authorize access** → Allow
5. Copy the **Web app URL** that appears (looks like `https://script.google.com/macros/s/...`)
""")

    st.markdown("---")

    # ── Step 3 ─────────────────────────────────────────────────────────────────
    st.markdown("### Step 3 — Paste the Web App URL here")
    current_url = _sh_cfg.get("webapp_url", "")
    new_url = st.text_input(
        "Web App URL",
        value=current_url,
        placeholder="https://script.google.com/macros/s/AKfy.../exec"
    )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("💾 Save & Activate", type="primary", disabled=not new_url.strip()):
            _sh_save_cfg(new_url.strip())
            st.success("✅ Saved! Google Sheets is now active.")
            st.rerun()
    with c2:
        if st.button("🔗 Test Connection"):
            if not new_url.strip():
                st.warning("Paste the Web App URL first.")
            else:
                _sh_save_cfg(new_url.strip())
                with st.spinner("Testing..."):
                    ok, msg = _sh_test()
                st.success(msg) if ok else st.error(msg)

    st.markdown("---")

    if _sh_active:
        if st.button("🔄 Sync Stores & Brands to Sheet"):
            from database import get_stores as _gst, get_brands as _gbr
            with st.spinner("Syncing..."):
                results = _sh_sync_all(_gst(), _gbr())
            for ok, msg in results:
                st.success(msg) if ok else st.error(msg)


# ── Tab 3: Email Config + APK URL ─────────────────────────────────────────────
with tab3:
    cfg = get_email_config()

    st.subheader("📧 Email / SMTP")
    st.caption("Needed to auto-send invitation emails when you create new users.")
    col1, col2 = st.columns(2)
    with col1:
        smtp_host   = st.text_input("SMTP Host",   value=cfg.get('smtp_host','smtp.gmail.com'))
        smtp_port   = st.number_input("SMTP Port", value=int(cfg.get('smtp_port',587)), min_value=1, max_value=65535)
        sender_name = st.text_input("Sender Name", value=cfg.get('sender_name','AC PMS System'))
    with col2:
        smtp_user  = st.text_input("Email / Username", value=cfg.get('smtp_user',''))
        smtp_pass  = st.text_input("App Password", value=cfg.get('smtp_password',''), type="password",
                                   help="Use Gmail App Password, not your regular Gmail password")
        app_url    = st.text_input("App URL", value=cfg.get('app_url','http://localhost:8501'),
                                   help="Network URL of this app — used in invite email links")

    st.markdown("---")
    st.subheader("📲 Android APK Download Link")
    st.markdown("""
    Paste a link here → a **Download APK** button appears on the **Install on Mobile** page for all users.

    **How to get the APK (free, 5 minutes):**
    1. Go to **[MIT App Inventor](https://appinventor.mit.edu)** → Sign in with Google
    2. Click **Start new project** → name it `PMS App`
    3. Drag a **WebViewer** component onto the screen
    4. Set **HomeUrl** = your App URL above (e.g. `http://10.90.97.34:8501`)
    5. Click **Build → App (provide QR code for .apk)** or **Build → App (save .apk)**
    6. Download the `.apk` file
    7. Upload it to **Google Drive** → right-click → **Share → Copy link**
    8. Paste the Google Drive link below 👇
    """)
    apk_url = st.text_input(
        "APK Download Link (Google Drive / Dropbox / any direct link)",
        value=cfg.get('apk_url',''),
        placeholder="https://drive.google.com/file/d/XXXXX/view?usp=sharing"
    )
    if apk_url.strip():
        direct = _gdrive_to_direct(apk_url.strip())
        st.success(f"✅ APK link set — users will see a Download button")
        st.caption(f"Direct link: `{direct}`")

    st.markdown("---")
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("💾 Save All Config", type="primary"):
            update_email_config(smtp_host, smtp_port, smtp_user, smtp_pass,
                                sender_name, app_url, apk_url)
            st.success("Configuration saved!")
    with col_b:
        test_addr = st.text_input("Test email address", placeholder="your@email.com")
        if st.button("📧 Send Test Email"):
            if test_addr and '@' in test_addr:
                update_email_config(smtp_host, smtp_port, smtp_user, smtp_pass,
                                    sender_name, app_url, apk_url)
                ok, msg = send_invite_email(test_addr, "Test User", "Vendor", "TEST_TOKEN_NOT_VALID")
                st.success(msg) if ok else st.error(msg)
            else:
                st.warning("Enter a valid email address.")

    st.markdown("---")
    c1, c2 = st.columns(2)
    c1.success("✅ SMTP configured") if cfg.get('smtp_user') and cfg.get('smtp_password') else c1.warning("⚠️ SMTP not configured")
    c2.success("✅ APK link set") if cfg.get('apk_url') else c2.warning("⚠️ No APK link yet")


# ── Tab 4: Mobile Install ──────────────────────────────────────────────────────
with tab4:
    st.subheader("Install App on Mobile")
    _mobile_install_section()


# ── Tab 5: App Download ────────────────────────────────────────────────────────
with tab5:
    st.subheader("Download App Source")
    st.markdown("""
    Download as ZIP and run on another Windows machine:
    ```
    pip install -r requirements.txt
    streamlit run app.py
    ```
    """)
    if st.button("📦 Generate App ZIP"):
        with st.spinner("Packaging app..."):
            zip_bytes = _build_zip()
        st.download_button("⬇️ Download pms_app.zip", data=zip_bytes,
                           file_name="pms_app.zip", mime="application/zip")
        st.success(f"ZIP ready — {len(zip_bytes)//1024} KB")

    st.markdown("---")
    st.subheader("Image Storage")
    if os.path.exists(UPLOAD_DIR):
        imgs = [f for f in os.listdir(UPLOAD_DIR)
                if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]
        st.metric("Total AC Images Stored", len(imgs))
        st.info(f"Storage path: `{UPLOAD_DIR}`")
    else:
        st.info("No images stored yet.")