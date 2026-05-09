"""
Google Sheets integration via Apps Script Web App.
No API keys. No service account. Completely free.

Setup (one time, 3 minutes):
  1. Open the Google Sheet → Extensions → Apps Script
  2. Paste the APPS_SCRIPT_CODE below into the editor → Save
  3. Deploy → New deployment → Type: Web app
     Execute as: Me  |  Who has access: Anyone
  4. Copy the Web App URL → paste in Settings → Google Sheets
"""
import json, os, requests as _requests

DEFAULT_SHEET_ID = "1HIFQU7keY70wWiwlo7R_wT8nAB3UdOQM-tLPEQqowJE"

# ── Apps Script to paste into the Google Sheet ─────────────────────────────────
APPS_SCRIPT_CODE = """\
function doPost(e) {
  try {
    var ss   = SpreadsheetApp.getActiveSpreadsheet();
    var data = JSON.parse(e.postData.contents);
    var tab  = data.tab || "PMS_Log";
    var ws   = ss.getSheetByName(tab);
    if (!ws) ws = ss.insertSheet(tab);
    if (data.headers && ws.getLastRow() === 0)
      ws.appendRow(data.headers);
    (data.rows || []).forEach(function(r){ ws.appendRow(r); });
    return ContentService
      .createTextOutput(JSON.stringify({status:"ok", count:(data.rows||[]).length}))
      .setMimeType(ContentService.MimeType.JSON);
  } catch(err) {
    return ContentService
      .createTextOutput(JSON.stringify({status:"error", message:err.toString()}))
      .setMimeType(ContentService.MimeType.JSON);
  }
}
function doGet(e) {
  return ContentService.createTextOutput("AC PMS Web App is running ✅");
}
"""

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


# ── Config helpers — stored in database so data survives redeployments ─────────

def get_config():
    try:
        from database import get_sheets_config
        cfg = get_sheets_config()
        return cfg if cfg else {"sheet_id": DEFAULT_SHEET_ID, "webapp_url": ""}
    except Exception:
        return {"sheet_id": DEFAULT_SHEET_ID, "webapp_url": ""}


def save_config(webapp_url, sheet_id=None):
    try:
        from database import save_sheets_config
        save_sheets_config(webapp_url.strip())
    except Exception:
        pass


def is_configured():
    return bool(get_config().get("webapp_url", ""))


# ── Core POST helper ──────────────────────────────────────────────────────────

def _post(tab, headers, rows):
    url = get_config().get("webapp_url", "")
    if not url:
        return False, "Web App URL not set. Go to Settings → Google Sheets."
    try:
        resp = _requests.post(
            url,
            data=json.dumps({"tab": tab, "headers": headers, "rows": rows}),
            headers={"Content-Type": "application/json"},
            timeout=30,
            allow_redirects=True
        )
        result = resp.json()
        if result.get("status") == "ok":
            return True, f"{result.get('count', len(rows))} row(s) saved."
        return False, result.get("message", "Unknown error from Apps Script.")
    except Exception as ex:
        return False, f"Connection error: {ex}"


def test_connection():
    url = get_config().get("webapp_url", "")
    if not url:
        return False, "No Web App URL saved yet."
    try:
        resp = _requests.get(url, timeout=15, allow_redirects=True)
        if resp.status_code == 200:
            return True, f"Connected ✅  Response: {resp.text[:80]}"
        return False, f"HTTP {resp.status_code}"
    except Exception as ex:
        return False, f"Connection error: {ex}"


# ── PMS data ───────────────────────────────────────────────────────────────────

def append_pms_data(session_info, entries, final_remarks):
    fr   = final_remarks or {}
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
        yn   = lambda v: "Yes" if v else "No"
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
    return _post("PMS_Log", PMS_HEADERS, rows)


# ── Stores & Brands sync ───────────────────────────────────────────────────────

def sync_stores(stores):
    rows = [[s.get("store_name",""), s.get("state",""), s.get("total_ac",0)] for s in stores]
    return _post("Stores", STORE_HEADERS, rows)


def sync_brands(brands):
    rows = [[b] for b in brands]
    return _post("Brands", BRAND_HEADERS, rows)


def sync_all(stores, brands):
    return [sync_stores(stores), sync_brands(brands)]
