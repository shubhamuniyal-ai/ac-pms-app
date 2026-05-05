"""
Google Sheets — primary data store for ALL PMS app data.

Sheet tabs used:
  PMS_Log   — one row per AC entry (sessions + checklist)
  Stores    — store master
  Brands    — brand list
  AC_Types  — AC type list

Credentials priority:
  1. st.secrets["gcp_service_account"]  (Streamlit Cloud)
  2. data/sheets_creds.json             (uploaded via Settings)
"""
import json, os
import streamlit as st

_BASE       = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR   = os.path.join(_BASE, "data")
_CREDS_FILE = os.path.join(_DATA_DIR, "sheets_creds.json")
_CFG_FILE   = os.path.join(_DATA_DIR, "sheets_config.json")

# ── Default sheet from the user's URL ─────────────────────────────────────────
DEFAULT_SHEET_ID = "1HIFQU7keY70wWiwlo7R_wT8nAB3UdOQM-tLPEQqowJE"

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# ── Column headers for each tab ───────────────────────────────────────────────
PMS_HEADERS = [
    "Date", "Store Name", "State", "Technician", "Brand", "AC Type",
    "AC Number", "Serial Number", "Capacity (Ton)",
    "Air Filter Cleaned", "Drain Tray Cleaned", "Drain Pipe Flushed",
    "Evaporator Coil Cleaned", "Blower Cleaned", "Indoor Casing Wiped",
    "Condenser Coil Cleaned", "Fan Motor OK", "Compressor OK",
    "ODU Casing Cleaned", "Refrigerant Pipes OK",
    "Supply Voltage (V)", "Running Current (A)", "Capacitor OK",
    "Gas Leak Checked", "Gas Topped Up", "Gas Qty (grams)",
    "Inlet Temp (°C)", "Outlet Temp (°C)",
    "Issue Observed", "Action Taken", "Parts Replaced",
    "Overall Condition", "AC Notes",
    "Technician Remarks", "Customer Signature", "Customer Emp Code",
    "Feedback", "Complaint / Pending Work",
]

STORE_HEADERS  = ["Store Name", "State", "Total AC"]
BRAND_HEADERS  = ["Brand Name"]
ACTYPE_HEADERS = ["AC Type"]


# ── Config helpers ─────────────────────────────────────────────────────────────

def get_config():
    try:
        with open(_CFG_FILE) as f:
            return json.load(f)
    except Exception:
        return {"sheet_id": DEFAULT_SHEET_ID}


def save_config(sheet_id):
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_CFG_FILE, "w") as f:
        json.dump({"sheet_id": sheet_id}, f)


def save_credentials(creds_dict):
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_CREDS_FILE, "w") as f:
        json.dump(creds_dict, f)


def _load_creds_info():
    try:
        info = dict(st.secrets["gcp_service_account"])
        if info:
            return info
    except Exception:
        pass
    if os.path.exists(_CREDS_FILE):
        with open(_CREDS_FILE) as f:
            return json.load(f)
    return None


def is_configured():
    cfg = get_config()
    return bool(cfg.get("sheet_id")) and (_load_creds_info() is not None)


# ── Connection helpers ─────────────────────────────────────────────────────────

def _open_spreadsheet(sheet_id):
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        return None, "gspread not installed. Run: pip install gspread google-auth"

    creds_info = _load_creds_info()
    if not creds_info:
        return None, (
            "Google credentials not uploaded yet.\n"
            "Go to Settings → Google Sheets → upload your service_account.json file."
        )
    try:
        creds  = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
        client = gspread.authorize(creds)
        sh     = client.open_by_key(sheet_id)
        return sh, None
    except Exception as e:
        return None, f"Cannot open sheet: {e}"


def _get_or_create_ws(sh, title, headers):
    """Return worksheet with given title, creating it with headers if needed."""
    try:
        ws = sh.worksheet(title)
    except Exception:
        ws = sh.add_worksheet(title=title, rows=1000, cols=len(headers))
    if not ws.row_values(1):
        ws.append_row(headers, value_input_option="USER_ENTERED")
    return ws


def test_connection(sheet_id=None):
    sheet_id = sheet_id or get_config().get("sheet_id", DEFAULT_SHEET_ID)
    sh, err = _open_spreadsheet(sheet_id)
    if err:
        return False, err
    try:
        return True, f'Connected ✅  Sheet: "{sh.title}"'
    except Exception as e:
        return False, str(e)


# ── PMS Data ───────────────────────────────────────────────────────────────────

def append_pms_data(session_info, entries, final_remarks):
    """Write one row per AC entry to the PMS_Log tab."""
    cfg      = get_config()
    sheet_id = cfg.get("sheet_id", DEFAULT_SHEET_ID)
    sh, err  = _open_spreadsheet(sheet_id)
    if err:
        return False, err

    try:
        ws = _get_or_create_ws(sh, "PMS_Log", PMS_HEADERS)
        fr = final_remarks or {}
        rows = []
        for e in entries:
            cl   = e.get("checklist", {})
            idu  = cl.get("idu",         {})
            odu  = cl.get("odu",         {})
            elec = cl.get("electrical",  {})
            gas  = cl.get("gas_cooling", {})
            perf = cl.get("performance", {})
            iss  = cl.get("issues",      {})
            rem  = cl.get("remarks",     {})

            def yn(v): return "Yes" if v else "No"

            rows.append([
                session_info.get("date", ""),
                session_info.get("store_name", ""),
                session_info.get("state", ""),
                session_info.get("tech_name", ""),
                session_info.get("brand", ""),
                session_info.get("ac_type", ""),
                e.get("ac_number", ""),
                e.get("serial_number", ""),
                e.get("capacity", ""),
                yn(idu.get("air_filter_cleaned")),
                yn(idu.get("drain_tray_cleaned")),
                yn(idu.get("drain_pipe_flushed")),
                yn(idu.get("evaporator_coil_cleaned")),
                yn(idu.get("blower_cleaned")),
                yn(idu.get("casing_wiped")),
                yn(odu.get("condenser_coil_cleaned")),
                yn(odu.get("fan_motor_ok")),
                yn(odu.get("compressor_ok")),
                yn(odu.get("casing_cleaned")),
                yn(odu.get("pipes_ok")),
                elec.get("supply_voltage",  0),
                elec.get("running_current", 0),
                yn(elec.get("capacitor_ok")),
                yn(gas.get("gas_leak_checked")),
                yn(gas.get("gas_topped_up")),
                gas.get("gas_qty_grams", 0),
                perf.get("inlet_temp",  0),
                perf.get("outlet_temp", 0),
                iss.get("issue_observed", ""),
                iss.get("action_taken",   ""),
                iss.get("parts_replaced", ""),
                rem.get("overall_condition", ""),
                rem.get("notes", ""),
                fr.get("technician_remarks",  ""),
                fr.get("customer_signature",  ""),
                fr.get("customer_emp_code",   ""),
                fr.get("feedback",            ""),
                fr.get("complaint_pending",   ""),
            ])

        for row in rows:
            ws.append_row(row, value_input_option="USER_ENTERED")

        return True, f"{len(rows)} row(s) saved to Google Sheet (PMS_Log tab)."
    except Exception as ex:
        return False, f"Sheet write error: {ex}"


# ── Store sync ─────────────────────────────────────────────────────────────────

def sync_stores(stores):
    """Overwrite the Stores tab with current store list."""
    cfg      = get_config()
    sheet_id = cfg.get("sheet_id", DEFAULT_SHEET_ID)
    sh, err  = _open_spreadsheet(sheet_id)
    if err:
        return False, err
    try:
        ws = _get_or_create_ws(sh, "Stores", STORE_HEADERS)
        # Clear existing data (keep header)
        ws.clear()
        ws.append_row(STORE_HEADERS, value_input_option="USER_ENTERED")
        for s in stores:
            ws.append_row([s.get("store_name",""), s.get("state",""), s.get("total_ac",0)],
                          value_input_option="USER_ENTERED")
        return True, f"{len(stores)} stores synced to Google Sheet."
    except Exception as ex:
        return False, f"Store sync error: {ex}"


# ── Brand sync ─────────────────────────────────────────────────────────────────

def sync_brands(brands):
    """Overwrite the Brands tab with current brand list."""
    cfg      = get_config()
    sheet_id = cfg.get("sheet_id", DEFAULT_SHEET_ID)
    sh, err  = _open_spreadsheet(sheet_id)
    if err:
        return False, err
    try:
        ws = _get_or_create_ws(sh, "Brands", BRAND_HEADERS)
        ws.clear()
        ws.append_row(BRAND_HEADERS, value_input_option="USER_ENTERED")
        for b in brands:
            ws.append_row([b], value_input_option="USER_ENTERED")
        return True, f"{len(brands)} brands synced to Google Sheet."
    except Exception as ex:
        return False, f"Brand sync error: {ex}"


# ── Full sync ──────────────────────────────────────────────────────────────────

def sync_all(stores, brands):
    """Sync stores and brands tabs. Returns list of (ok, msg) tuples."""
    results = []
    results.append(sync_stores(stores))
    results.append(sync_brands(brands))
    return results
