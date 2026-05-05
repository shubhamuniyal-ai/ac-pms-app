"""
Google Sheets integration — writes PMS data on each submission.

Credentials priority:
  1. st.secrets["gcp_service_account"]   (Streamlit Cloud)
  2. data/sheets_creds.json              (uploaded via Settings)
"""
import json, os
import streamlit as st

_BASE       = os.path.dirname(os.path.abspath(__file__))
_CREDS_FILE = os.path.join(_BASE, "data", "sheets_creds.json")
_CFG_FILE   = os.path.join(_BASE, "data", "sheets_config.json")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

HEADERS = [
    "Date", "Store Name", "State", "Technician", "Brand", "AC Type",
    "AC Number", "Serial Number", "Capacity (Ton)",
    # IDU
    "Air Filter Cleaned", "Drain Tray Cleaned", "Drain Pipe Flushed",
    "Evaporator Coil Cleaned", "Blower Cleaned", "Indoor Casing Wiped",
    # ODU
    "Condenser Coil Cleaned", "Fan Motor OK", "Compressor OK",
    "ODU Casing Cleaned", "Refrigerant Pipes OK",
    # Electrical
    "Supply Voltage (V)", "Running Current (A)", "Capacitor OK",
    # Gas
    "Gas Leak Checked", "Gas Topped Up", "Gas Qty (grams)",
    # Performance
    "Inlet Temp (°C)", "Outlet Temp (°C)",
    # Issues
    "Issue Observed", "Action Taken", "Parts Replaced",
    # Remarks
    "Overall Condition", "AC Notes",
    # Final
    "Technician Remarks", "Customer Signature", "Customer Emp Code",
    "Feedback", "Complaint / Pending Work",
]


def get_config():
    try:
        with open(_CFG_FILE) as f:
            return json.load(f)
    except Exception:
        return {"sheet_id": ""}


def save_config(sheet_id):
    os.makedirs(os.path.dirname(_CFG_FILE), exist_ok=True)
    with open(_CFG_FILE, "w") as f:
        json.dump({"sheet_id": sheet_id}, f)


def save_credentials(creds_dict):
    os.makedirs(os.path.dirname(_CREDS_FILE), exist_ok=True)
    with open(_CREDS_FILE, "w") as f:
        json.dump(creds_dict, f)


def _load_creds_info():
    """Returns credentials dict or None."""
    # 1. Streamlit Cloud secrets
    try:
        info = dict(st.secrets["gcp_service_account"])
        if info:
            return info
    except Exception:
        pass
    # 2. Uploaded credentials file
    if os.path.exists(_CREDS_FILE):
        with open(_CREDS_FILE) as f:
            return json.load(f)
    return None


def _get_worksheet(sheet_id):
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        return None, "gspread not installed. Run: pip install gspread google-auth"

    creds_info = _load_creds_info()
    if not creds_info:
        return None, "Google credentials not configured. Upload service_account.json in Settings → Google Sheets."

    try:
        creds  = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
        client = gspread.authorize(creds)
        sh     = client.open_by_key(sheet_id)
        return sh.sheet1, None
    except Exception as e:
        return None, f"Could not open sheet: {e}"


def test_connection(sheet_id):
    """Returns (success, message)."""
    ws, err = _get_worksheet(sheet_id)
    if err:
        return False, err
    try:
        title = ws.spreadsheet.title
        return True, f"Connected ✅  Sheet: \"{title}\""
    except Exception as e:
        return False, str(e)


def is_configured():
    cfg = get_config()
    return bool(cfg.get("sheet_id")) and (_load_creds_info() is not None)


def append_pms_data(session_info, entries, final_remarks):
    """
    Write one row per AC entry to the Google Sheet.
    session_info: dict — date, store_name, state, tech_name, brand, ac_type
    entries:      list of dicts — ac_number, serial_number, capacity, checklist
    final_remarks: dict
    Returns (success, message)
    """
    cfg = get_config()
    sheet_id = cfg.get("sheet_id", "")
    if not sheet_id:
        return False, "Sheet ID not configured."

    ws, err = _get_worksheet(sheet_id)
    if err:
        return False, err

    try:
        # Add headers if sheet is empty
        if not ws.row_values(1):
            ws.append_row(HEADERS, value_input_option="USER_ENTERED")

        fr = final_remarks or {}
        rows = []
        for e in entries:
            cl    = e.get("checklist", {})
            idu   = cl.get("idu",         {})
            odu   = cl.get("odu",         {})
            elec  = cl.get("electrical",  {})
            gas   = cl.get("gas_cooling", {})
            perf  = cl.get("performance", {})
            iss   = cl.get("issues",      {})
            rem   = cl.get("remarks",     {})

            def yn(v): return "Yes" if v else "No"

            row = [
                session_info["date"],
                session_info["store_name"],
                session_info["state"],
                session_info["tech_name"],
                session_info["brand"],
                session_info["ac_type"],
                e["ac_number"],
                e["serial_number"],
                e["capacity"],
                # IDU
                yn(idu.get("air_filter_cleaned")),
                yn(idu.get("drain_tray_cleaned")),
                yn(idu.get("drain_pipe_flushed")),
                yn(idu.get("evaporator_coil_cleaned")),
                yn(idu.get("blower_cleaned")),
                yn(idu.get("casing_wiped")),
                # ODU
                yn(odu.get("condenser_coil_cleaned")),
                yn(odu.get("fan_motor_ok")),
                yn(odu.get("compressor_ok")),
                yn(odu.get("casing_cleaned")),
                yn(odu.get("pipes_ok")),
                # Electrical
                elec.get("supply_voltage",  0),
                elec.get("running_current", 0),
                yn(elec.get("capacitor_ok")),
                # Gas
                yn(gas.get("gas_leak_checked")),
                yn(gas.get("gas_topped_up")),
                gas.get("gas_qty_grams", 0),
                # Performance
                perf.get("inlet_temp",  0),
                perf.get("outlet_temp", 0),
                # Issues
                iss.get("issue_observed", ""),
                iss.get("action_taken",   ""),
                iss.get("parts_replaced", ""),
                # Remarks
                rem.get("overall_condition", ""),
                rem.get("notes", ""),
                # Final
                fr.get("technician_remarks",  ""),
                fr.get("customer_signature",  ""),
                fr.get("customer_emp_code",   ""),
                fr.get("feedback",            ""),
                fr.get("complaint_pending",   ""),
            ]
            rows.append(row)

        for row in rows:
            ws.append_row(row, value_input_option="USER_ENTERED")

        return True, f"{len(rows)} row(s) written to Google Sheet."

    except Exception as ex:
        return False, f"Sheet write error: {ex}"
