import os, json, secrets, smtplib
from datetime import date, datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

DATABASE_URL = os.environ.get("DATABASE_URL", "")
_BASE        = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR    = os.environ.get("DATA_DIR", os.path.join(_BASE, "data"))
DB_PATH      = os.path.join(_DATA_DIR, "pms.db")
UPLOAD_DIR   = os.path.join(_DATA_DIR, "uploads")
IS_PG        = bool(DATABASE_URL)

TONNAGE_OPTIONS = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.5, 7.5, 8.5, 11.0, 16.0]

if IS_PG:
    import psycopg2, psycopg2.extras


class _Conn:
    def __init__(self):
        if IS_PG:
            self._c = psycopg2.connect(DATABASE_URL)
            self._c.autocommit = False
        else:
            import sqlite3
            os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
            self._c = sqlite3.connect(DB_PATH)
            self._c.row_factory = sqlite3.Row
            self._c.execute("PRAGMA foreign_keys = ON")

    def _cur(self):
        if IS_PG:
            return self._c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        return self._c.cursor()

    @staticmethod
    def _sql(sql):
        return sql.replace("?", "%s") if IS_PG else sql

    def execute(self, sql, params=()):
        cur = self._cur()
        cur.execute(self._sql(sql), params)
        return cur

    def executescript(self, script):
        if IS_PG:
            cur = self._c.cursor()
            for stmt in script.split(";"):
                s = stmt.strip()
                if s:
                    try: cur.execute(s)
                    except Exception:
                        self._c.rollback(); raise
        else:
            self._c.executescript(script)

    def commit(self):   self._c.commit()
    def close(self):    self._c.close()
    def cursor(self):   return self._cur()

    def insert_returning_id(self, sql, params=()):
        if IS_PG:
            cur = self._cur()
            cur.execute(self._sql(sql) + " RETURNING id", params)
            return cur.fetchone()["id"]
        cur = self._c.execute(sql, params)
        return cur.lastrowid


def get_conn(): return _Conn()

def _S():  return "SERIAL PRIMARY KEY" if IS_PG else "INTEGER PRIMARY KEY AUTOINCREMENT"
def _ND(): return "CURRENT_DATE"       if IS_PG else "date('now')"
def _NT(): return "CURRENT_TIMESTAMP"  if IS_PG else "datetime('now','localtime')"
def _II(): return "ON CONFLICT DO NOTHING" if IS_PG else "OR IGNORE"


# ── Init & Migrate ─────────────────────────────────────────────────────────────

def init_db():
    conn = get_conn()
    conn.executescript(f"""
        CREATE TABLE IF NOT EXISTS stores (
            id {_S()}, store_name TEXT NOT NULL UNIQUE,
            state TEXT NOT NULL, total_ac INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS brands (
            id {_S()}, brand_name TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS users (
            id {_S()}, name TEXT NOT NULL, mobile TEXT, email TEXT,
            role TEXT NOT NULL, assigned_states TEXT DEFAULT '[]',
            assigned_stores TEXT DEFAULT '[]', password TEXT NOT NULL DEFAULT '',
            reset_token TEXT, token_expiry TEXT,
            session_token TEXT, session_expiry TEXT,
            is_active INTEGER DEFAULT 1, created_at TEXT DEFAULT ({_ND()})
        );
        CREATE TABLE IF NOT EXISTS ac_types (
            id {_S()}, type_name TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS pms_sessions (
            id {_S()}, store_id INTEGER NOT NULL, technician_id INTEGER NOT NULL,
            ac_type TEXT NOT NULL, brand TEXT DEFAULT '',
            entry_date TEXT NOT NULL, status TEXT DEFAULT 'Completed',
            img_air_filter TEXT, img_drain_tray TEXT,
            img_grill_temp TEXT, img_fsr_report TEXT,
            created_at TEXT DEFAULT ({_NT()})
        );
        CREATE TABLE IF NOT EXISTS ac_entries (
            id {_S()}, session_id INTEGER NOT NULL,
            ac_number TEXT NOT NULL, serial_number TEXT NOT NULL,
            capacity REAL NOT NULL,
            ac_number_image TEXT, serial_number_image TEXT,
            img_remote_display TEXT,
            checklist_data TEXT DEFAULT '{{}}',
            created_at TEXT DEFAULT ({_NT()})
        );
        CREATE TABLE IF NOT EXISTS email_config (
            id INTEGER PRIMARY KEY, smtp_host TEXT DEFAULT 'smtp.gmail.com',
            smtp_port INTEGER DEFAULT 587, smtp_user TEXT DEFAULT '',
            smtp_password TEXT DEFAULT '', sender_name TEXT DEFAULT 'AC PMS System',
            app_url TEXT DEFAULT 'http://localhost:8501', apk_url TEXT DEFAULT ''
        )
    """)
    conn.commit()
    _migrate(conn)

    def _count(tbl):
        row = conn.execute(f"SELECT COUNT(*) as n FROM {tbl}").fetchone()
        return dict(row)["n"]

    if _count("users") == 0:
        conn.execute("INSERT INTO users(name,mobile,email,role,password) VALUES(?,?,?,?,?)",
                     ("Admin","9999999999","admin@pms.local","Admin","admin123"))
    if _count("ac_types") == 0:
        for t in ["Split","Cassette","Ductable"]:
            conn.execute(f"INSERT {_II()} INTO ac_types(type_name) VALUES(?)", (t,))
    if _count("brands") == 0:
        for b in ["Blue Star","Daikin","Voltas","Hitachi","LG","Samsung","Carrier","Godrej"]:
            conn.execute(f"INSERT {_II()} INTO brands(brand_name) VALUES(?)", (b,))
    if _count("email_config") == 0:
        conn.execute("INSERT INTO email_config(id) VALUES(1)")
    conn.commit()
    conn.close()


def _migrate(conn):
    """Add missing columns to existing tables (works for both SQLite and PG)."""
    ps_new = [("brand","TEXT DEFAULT ''"),("img_air_filter","TEXT"),
              ("img_drain_tray","TEXT"),("img_grill_temp","TEXT"),("img_fsr_report","TEXT")]
    ae_new = [("img_remote_display","TEXT"),("checklist_data","TEXT DEFAULT '{}'")]
    us_new = [("session_token","TEXT"),("session_expiry","TEXT")]

    if IS_PG:
        for col, dtype in ps_new:
            try: conn.execute(f"ALTER TABLE pms_sessions ADD COLUMN IF NOT EXISTS {col} {dtype}")
            except: pass
        for col, dtype in ae_new:
            try: conn.execute(f"ALTER TABLE ac_entries ADD COLUMN IF NOT EXISTS {col} {dtype}")
            except: pass
        for col, dtype in us_new:
            try: conn.execute(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} {dtype}")
            except: pass
        try: conn.execute("CREATE TABLE IF NOT EXISTS brands (id SERIAL PRIMARY KEY, brand_name TEXT NOT NULL UNIQUE)")
        except: pass
        conn.commit()
    else:
        def _add_cols(table, cols):
            existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            for col, dtype in cols:
                if col not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {dtype}")

        _add_cols("pms_sessions", ps_new)
        _add_cols("ac_entries", ae_new)
        _add_cols("users", us_new)

        # Old schema rebuild (Technician → Vendor)
        r = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
        if r:
            sql_txt = r[0] if isinstance(r, (list,tuple)) else r["sql"]
            if "Technician" in sql_txt:
                existing = conn.execute("SELECT * FROM users").fetchall()
                cols_list = [d[0] for d in conn.cursor()._c.execute("SELECT * FROM users LIMIT 0").description] if False else []
                # simpler: just fix roles
                conn.execute("UPDATE users SET role='Vendor' WHERE role='Technician'")

        conn.execute("UPDATE users SET email='admin@pms.local' WHERE email IS NULL AND mobile='9999999999'")
        # Update localhost default URL to Streamlit Cloud URL
        conn.execute(
            "UPDATE email_config SET app_url=? WHERE app_url='http://localhost:8501'",
            ("https://ac-pms-app-pcgm2gtvkyh2zjwlgeyxxx.streamlit.app",)
        )

        ecols = {r[1] for r in conn.execute("PRAGMA table_info(email_config)").fetchall()}
        if "apk_url" not in ecols:
            conn.execute("ALTER TABLE email_config ADD COLUMN apk_url TEXT DEFAULT ''")
        conn.commit()


# ── Session tokens (for persistent login) ─────────────────────────────────────

def create_session_token(user_id):
    """Create a session token valid until midnight."""
    token  = secrets.token_urlsafe(32)
    midnight = datetime.now().replace(hour=23, minute=59, second=59)
    conn = get_conn()
    conn.execute("UPDATE users SET session_token=?, session_expiry=? WHERE id=?",
                 (token, midnight.isoformat(), user_id))
    conn.commit(); conn.close()
    return token


def verify_session_token(token):
    """Verify a session token is still valid."""
    if not token:
        return None
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM users WHERE session_token=? AND session_expiry > ? AND is_active=1",
        (token, datetime.now().isoformat())
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# ── Auth ───────────────────────────────────────────────────────────────────────

def authenticate(identifier, password):
    conn = get_conn()
    row = conn.execute(
        """SELECT * FROM users WHERE (email=? OR mobile=?) AND password=?
           AND password IS NOT NULL AND password != '' AND is_active=1""",
        (identifier, identifier, password)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def generate_invite_token(user_id):
    token  = secrets.token_urlsafe(32)
    expiry = (datetime.now() + timedelta(hours=48)).isoformat()
    conn = get_conn()
    conn.execute("UPDATE users SET reset_token=?, token_expiry=? WHERE id=?",
                 (token, expiry, user_id))
    conn.commit(); conn.close()
    return token


def verify_token(token):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM users WHERE reset_token=? AND token_expiry > ?",
        (token, datetime.now().isoformat())
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def activate_account(token, new_password):
    conn = get_conn()
    conn.execute("UPDATE users SET password=?, reset_token=NULL, token_expiry=NULL WHERE reset_token=?",
                 (new_password, token))
    conn.commit(); conn.close()


def change_password(user_id, new_password):
    conn = get_conn()
    conn.execute("UPDATE users SET password=? WHERE id=?", (new_password, user_id))
    conn.commit(); conn.close()


# ── Brands ─────────────────────────────────────────────────────────────────────

def get_brands():
    conn = get_conn()
    rows = conn.execute("SELECT brand_name FROM brands ORDER BY brand_name").fetchall()
    conn.close()
    return [dict(r)["brand_name"] for r in rows]


def add_brand(brand_name):
    conn = get_conn()
    try:
        conn.execute(f"INSERT {_II()} INTO brands(brand_name) VALUES(?)", (brand_name,))
        conn.commit()
        return True, "Brand added"
    except Exception:
        return False, "Brand already exists"
    finally:
        conn.close()


def delete_brand(brand_name):
    conn = get_conn()
    conn.execute("DELETE FROM brands WHERE brand_name=?", (brand_name,))
    conn.commit(); conn.close()


# ── Stores ─────────────────────────────────────────────────────────────────────

def get_stores():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM stores ORDER BY store_name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_accessible_stores(user_id):
    conn = get_conn()
    row = conn.execute("SELECT assigned_stores FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    if row:
        assigned = json.loads(dict(row).get("assigned_stores") or "[]")
        if assigned:
            return [s for s in get_stores() if s["store_name"] in assigned]
    return get_stores()


def get_store_by_name(name):
    conn = get_conn()
    row = conn.execute("SELECT * FROM stores WHERE store_name=?", (name,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_states():
    conn = get_conn()
    rows = conn.execute("SELECT DISTINCT state FROM stores ORDER BY state").fetchall()
    conn.close()
    return [dict(r)["state"] for r in rows]


def add_store(store_name, state, total_ac):
    conn = get_conn()
    try:
        conn.execute("INSERT INTO stores(store_name,state,total_ac) VALUES(?,?,?)",
                     (store_name, state, int(total_ac)))
        conn.commit()
        return True, "Store added successfully"
    except Exception:
        return False, "Store name already exists"
    finally:
        conn.close()


def update_store(store_id, store_name, state, total_ac):
    conn = get_conn()
    try:
        conn.execute("UPDATE stores SET store_name=?, state=?, total_ac=? WHERE id=?",
                     (store_name, state, int(total_ac), store_id))
        conn.commit()
        return True, "Store updated"
    except Exception:
        return False, "Store name already exists"
    finally:
        conn.close()


def delete_store(store_id):
    conn = get_conn()
    conn.execute("DELETE FROM stores WHERE id=?", (store_id,))
    conn.commit(); conn.close()


# ── Users ──────────────────────────────────────────────────────────────────────

def get_users(role=None):
    conn = get_conn()
    if role:
        rows = conn.execute(
            "SELECT * FROM users WHERE role=? AND is_active=1 ORDER BY name", (role,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM users WHERE is_active=1 ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_users():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM users ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_user(name, mobile, email, role, assigned_states, assigned_stores):
    conn = get_conn()
    try:
        uid = conn.insert_returning_id(
            "INSERT INTO users(name,mobile,email,role,assigned_states,assigned_stores,password)"
            " VALUES(?,?,?,?,?,?,?)",
            (name, mobile or None, email.strip().lower(), role,
             json.dumps(assigned_states), json.dumps(assigned_stores), "")
        )
        conn.commit()
        return True, uid, "User created"
    except Exception as e:
        msg = str(e).lower()
        return False, None, "Email already registered" if "email" in msg else "Mobile already registered"
    finally:
        conn.close()


def update_user_status(user_id, is_active):
    conn = get_conn()
    conn.execute("UPDATE users SET is_active=? WHERE id=?", (is_active, user_id))
    conn.commit(); conn.close()


def update_user(user_id, name, mobile, email, role, assigned_states, assigned_stores):
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE users SET name=?,mobile=?,email=?,role=?,assigned_states=?,assigned_stores=? WHERE id=?",
            (name, mobile, email.strip().lower(), role,
             json.dumps(assigned_states), json.dumps(assigned_stores), user_id))
        conn.commit()
        return True, "User updated"
    except Exception:
        return False, "Email or mobile already in use"
    finally:
        conn.close()


# ── AC Types ───────────────────────────────────────────────────────────────────

def get_ac_types():
    conn = get_conn()
    rows = conn.execute("SELECT type_name FROM ac_types ORDER BY type_name").fetchall()
    conn.close()
    return [dict(r)["type_name"] for r in rows]


def add_ac_type(type_name):
    conn = get_conn()
    try:
        conn.execute(f"INSERT {_II()} INTO ac_types(type_name) VALUES(?)", (type_name,))
        conn.commit()
        return True, "AC type added"
    except Exception:
        return False, "AC type already exists"
    finally:
        conn.close()


def delete_ac_type(type_name):
    conn = get_conn()
    conn.execute("DELETE FROM ac_types WHERE type_name=?", (type_name,))
    conn.commit(); conn.close()


# ── PMS Sessions ───────────────────────────────────────────────────────────────

def create_pms_session(store_id, tech_id, ac_type, entry_date,
                        brand="",
                        img_air_filter=None, img_drain_tray=None,
                        img_grill_temp=None, img_fsr_report=None):
    conn = get_conn()
    sid = conn.insert_returning_id(
        "INSERT INTO pms_sessions(store_id,technician_id,ac_type,brand,entry_date,"
        "img_air_filter,img_drain_tray,img_grill_temp,img_fsr_report) VALUES(?,?,?,?,?,?,?,?,?)",
        (store_id, tech_id, ac_type, brand, entry_date,
         img_air_filter, img_drain_tray, img_grill_temp, img_fsr_report)
    )
    conn.commit(); conn.close()
    return sid


def create_ac_entry(session_id, ac_number, serial_number, capacity,
                     ac_img, serial_img, checklist_data=None, img_remote_display=None):
    conn = get_conn()
    conn.execute(
        "INSERT INTO ac_entries(session_id,ac_number,serial_number,capacity,"
        "ac_number_image,serial_number_image,checklist_data,img_remote_display) VALUES(?,?,?,?,?,?,?,?)",
        (session_id, ac_number, serial_number, capacity, ac_img, serial_img,
         json.dumps(checklist_data or {}), img_remote_display))
    conn.commit(); conn.close()


def get_vendor_history(user_id):
    conn = get_conn()
    rows = conn.execute("""
        SELECT ps.id as session_id, s.store_name, s.state, ps.entry_date,
               ps.ac_type, ps.brand, ps.status, ps.created_at,
               COUNT(ae.id) as ac_count
        FROM pms_sessions ps
        JOIN stores s ON ps.store_id=s.id
        LEFT JOIN ac_entries ae ON ae.session_id=ps.id
        WHERE ps.technician_id=?
        GROUP BY ps.id, s.store_name, s.state, ps.entry_date,
                 ps.ac_type, ps.brand, ps.status, ps.created_at
        ORDER BY ps.entry_date DESC, ps.created_at DESC
    """, (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_session_ac_entries(session_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM ac_entries WHERE session_id=? ORDER BY id", (session_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Dashboard ──────────────────────────────────────────────────────────────────

def get_vendor_dashboard_data(user_id):
    """Dashboard data for a specific Vendor/Technician."""
    conn = get_conn()
    row = conn.execute("SELECT assigned_stores, name FROM users WHERE id=?", (user_id,)).fetchone()
    if not row:
        conn.close()
        return {}
    row = dict(row)
    tech_name = row["name"]
    assigned  = json.loads(row.get("assigned_stores") or "[]")

    today     = date.today().isoformat()
    month_start = date.today().replace(day=1).isoformat()

    # Get all assigned stores with today's PMS status
    stores = get_accessible_stores(user_id)
    store_names = [s["store_name"] for s in stores]

    store_status = []
    for s in stores:
        done_today = dict(conn.execute(
            "SELECT COUNT(*) as n FROM pms_sessions WHERE store_id=? AND entry_date=? AND technician_id=?",
            (s["id"], today, user_id)
        ).fetchone())["n"]
        ac_done = dict(conn.execute(
            """SELECT COUNT(ae.id) as n FROM ac_entries ae
               JOIN pms_sessions ps ON ae.session_id=ps.id
               WHERE ps.store_id=? AND ps.entry_date=? AND ps.technician_id=?""",
            (s["id"], today, user_id)
        ).fetchone())["n"]
        store_status.append({
            "store_name": s["store_name"], "state": s["state"],
            "total_ac": s["total_ac"], "done_today": done_today > 0,
            "ac_done": ac_done, "ac_pending": max(0, s["total_ac"] - ac_done)
        })

    total_stores   = len(stores)
    stores_done    = sum(1 for s in store_status if s["done_today"])
    stores_pending = total_stores - stores_done
    total_ac       = sum(s["total_ac"] for s in store_status)
    ac_done_total  = sum(s["ac_done"] for s in store_status)

    # Monthly stats
    month_sessions = dict(conn.execute(
        "SELECT COUNT(*) as n FROM pms_sessions WHERE technician_id=? AND entry_date>=?",
        (user_id, month_start)
    ).fetchone())["n"]
    month_ac = dict(conn.execute(
        """SELECT COUNT(ae.id) as n FROM ac_entries ae
           JOIN pms_sessions ps ON ae.session_id=ps.id
           WHERE ps.technician_id=? AND ps.entry_date>=?""",
        (user_id, month_start)
    ).fetchone())["n"]

    conn.close()
    return {
        "tech_name": tech_name,
        "total_stores": total_stores,
        "stores_done": stores_done,
        "stores_pending": stores_pending,
        "total_ac": total_ac,
        "ac_done": ac_done_total,
        "ac_pending": max(0, total_ac - ac_done_total),
        "store_status": store_status,
        "month_sessions": month_sessions,
        "month_ac": month_ac,
    }


def get_dashboard_data():
    """Full admin dashboard data."""
    conn = get_conn()
    today = date.today().isoformat()
    month_start = date.today().replace(day=1).isoformat()
    d = {}

    def _n(sql, params=()):
        return dict(conn.execute(sql, params).fetchone())["n"]

    d["stores_today"]    = _n("SELECT COUNT(DISTINCT store_id) as n FROM pms_sessions WHERE entry_date=?", (today,))
    d["ac_today"]        = _n("SELECT COUNT(*) as n FROM ac_entries ae JOIN pms_sessions ps ON ae.session_id=ps.id WHERE ps.entry_date=?", (today,))
    d["ac_total"]        = _n("SELECT COUNT(*) as n FROM ac_entries")
    d["sessions_total"]  = _n("SELECT COUNT(*) as n FROM pms_sessions")
    d["total_stores"]    = _n("SELECT COUNT(*) as n FROM stores")
    d["stores_pending"]  = max(0, d["total_stores"] - d["stores_today"])

    # Month stats
    d["stores_done_month"] = _n("SELECT COUNT(DISTINCT store_id) as n FROM pms_sessions WHERE entry_date>=?", (month_start,))
    d["ac_done_month"]     = _n("SELECT COUNT(*) as n FROM ac_entries ae JOIN pms_sessions ps ON ae.session_id=ps.id WHERE ps.entry_date>=?", (month_start,))

    def _rows(sql, params=()):
        return [dict(r) for r in conn.execute(sql, params).fetchall()]

    d["store_ac"]      = _rows("""SELECT s.store_name, COUNT(ae.id) as ac_count,
        MAX(ps.entry_date) as last_pms
        FROM stores s LEFT JOIN pms_sessions ps ON ps.store_id=s.id
        LEFT JOIN ac_entries ae ON ae.session_id=ps.id
        GROUP BY s.store_name ORDER BY ac_count DESC LIMIT 15""")

    d["ac_type_dist"]  = _rows("SELECT ac_type, COUNT(*) as cnt FROM pms_sessions GROUP BY ac_type")
    d["brand_dist"]    = _rows("SELECT brand, COUNT(*) as cnt FROM pms_sessions WHERE brand!='' GROUP BY brand ORDER BY cnt DESC")

    d["tech_perf"]     = _rows("""SELECT u.name, COUNT(DISTINCT ps.id) as sessions,
        COUNT(ae.id) as ac_count
        FROM users u LEFT JOIN pms_sessions ps ON ps.technician_id=u.id AND ps.entry_date>=?
        LEFT JOIN ac_entries ae ON ae.session_id=ps.id
        WHERE u.role='Vendor' AND u.is_active=1
        GROUP BY u.name ORDER BY ac_count DESC""", (month_start,))

    d["state_summary"] = _rows("""SELECT s.state, COUNT(ae.id) as ac_count,
        COUNT(DISTINCT s.id) as store_count
        FROM pms_sessions ps JOIN stores s ON ps.store_id=s.id
        JOIN ac_entries ae ON ae.session_id=ps.id
        GROUP BY s.state ORDER BY ac_count DESC""")

    d["daily_trend"]   = _rows("""SELECT ps.entry_date, COUNT(ae.id) as ac_count
        FROM pms_sessions ps JOIN ac_entries ae ON ae.session_id=ps.id
        GROUP BY ps.entry_date ORDER BY ps.entry_date DESC LIMIT 30""")

    # Store done vs pending this month
    done_stores = {dict(r)["store_id"] for r in conn.execute(
        "SELECT DISTINCT store_id FROM pms_sessions WHERE entry_date>=?", (month_start,)
    ).fetchall()}
    all_stores_list = _rows("SELECT id, store_name, state, total_ac FROM stores")
    d["pending_stores"] = [s for s in all_stores_list if s["id"] not in done_stores]

    # Brand-wise store completion
    d["brand_store_pending"] = _rows("""
        SELECT ps.brand, COUNT(DISTINCT ps.store_id) as done_count
        FROM pms_sessions ps WHERE ps.entry_date>=? AND ps.brand!=''
        GROUP BY ps.brand ORDER BY done_count DESC""", (month_start,))

    conn.close()
    return d


def get_site_analysis(brand=None, tech_id=None, store_id=None, state=None, period_days=30):
    """Filtered dashboard data for Site Analysis tab."""
    conn = get_conn()
    since = (date.today() - timedelta(days=period_days)).isoformat()
    params = [since]
    where  = "WHERE ps.entry_date>=?"

    if brand:   where += " AND ps.brand=?";             params.append(brand)
    if tech_id: where += " AND ps.technician_id=?";     params.append(tech_id)
    if store_id:where += " AND ps.store_id=?";          params.append(store_id)
    if state:   where += " AND s.state=?";              params.append(state)

    def _rows(sql, p=()):
        return [dict(r) for r in conn.execute(sql, p).fetchall()]

    base = f"""FROM pms_sessions ps
               JOIN stores s ON ps.store_id=s.id
               JOIN users u ON ps.technician_id=u.id
               LEFT JOIN ac_entries ae ON ae.session_id=ps.id
               {where}"""

    result = {
        "ac_count":    dict(conn.execute(f"SELECT COUNT(ae.id) as n {base}", params).fetchone())["n"],
        "sessions":    dict(conn.execute(f"SELECT COUNT(DISTINCT ps.id) as n {base}", params).fetchone())["n"],
        "by_store":    _rows(f"SELECT s.store_name, COUNT(ae.id) as ac_count {base} GROUP BY s.store_name ORDER BY ac_count DESC", params),
        "by_tech":     _rows(f"SELECT u.name, COUNT(ae.id) as ac_count {base} GROUP BY u.name ORDER BY ac_count DESC", params),
        "by_brand":    _rows(f"SELECT ps.brand, COUNT(ae.id) as ac_count {base} AND ps.brand!='' GROUP BY ps.brand ORDER BY ac_count DESC", params),
        "by_state":    _rows(f"SELECT s.state, COUNT(ae.id) as ac_count {base} GROUP BY s.state ORDER BY ac_count DESC", params),
        "by_date":     _rows(f"SELECT ps.entry_date, COUNT(ae.id) as ac_count {base} GROUP BY ps.entry_date ORDER BY ps.entry_date", params),
        "store_completion": _rows(f"""
            SELECT s.store_name, s.total_ac,
                   COUNT(ae.id) as ac_done,
                   MAX(ps.entry_date) as last_pms
            {base} GROUP BY s.store_name, s.total_ac ORDER BY ac_done DESC""", params),
    }
    conn.close()
    return result


# ── Reports ────────────────────────────────────────────────────────────────────

def get_report_data(start_date=None, end_date=None, store_id=None, state=None, tech_id=None):
    conn = get_conn()
    query = """SELECT s.store_name, s.state, ps.entry_date, u.name as technician,
               ps.brand, ps.ac_type, ae.ac_number, ae.serial_number, ae.capacity,
               ae.ac_number_image, ae.serial_number_image, ae.checklist_data, ps.status
        FROM ac_entries ae
        JOIN pms_sessions ps ON ae.session_id=ps.id
        JOIN stores s ON ps.store_id=s.id
        JOIN users u ON ps.technician_id=u.id WHERE 1=1"""
    params = []
    if start_date: query += " AND ps.entry_date>=?"; params.append(start_date)
    if end_date:   query += " AND ps.entry_date<=?"; params.append(end_date)
    if store_id:   query += " AND ps.store_id=?";   params.append(store_id)
    if state:      query += " AND s.state=?";        params.append(state)
    if tech_id:    query += " AND ps.technician_id=?"; params.append(tech_id)
    query += " ORDER BY ps.entry_date DESC, s.store_name"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Email Config ───────────────────────────────────────────────────────────────

def get_email_config():
    conn = get_conn()
    row = conn.execute("SELECT * FROM email_config WHERE id=1").fetchone()
    conn.close()
    return dict(row) if row else {}


def update_email_config(smtp_host, smtp_port, smtp_user, smtp_password, sender_name, app_url, apk_url=""):
    conn = get_conn()
    conn.execute("""UPDATE email_config SET smtp_host=?,smtp_port=?,smtp_user=?,
        smtp_password=?,sender_name=?,app_url=?,apk_url=? WHERE id=1""",
        (smtp_host, int(smtp_port), smtp_user, smtp_password, sender_name,
         app_url.rstrip("/"), apk_url.strip()))
    conn.commit(); conn.close()


def send_invite_email(to_email, user_name, role, token):
    cfg = get_email_config()
    if not cfg.get("smtp_user") or not cfg.get("smtp_password"):
        return False, "SMTP not configured. Go to Settings → Email Config."
    app_url    = cfg.get("app_url", "http://localhost:8501")
    setup_link = f"{app_url}/?setup_token={token}"
    html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"></head>
    <body style="font-family:Arial,sans-serif;background:#f4f6f8;padding:30px">
      <div style="max-width:520px;margin:auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.1)">
        <div style="background:#1E3A5F;padding:28px;text-align:center">
          <h1 style="color:#fff;margin:0">❄️ AC PMS System</h1>
        </div>
        <div style="padding:32px">
          <h2 style="color:#1E3A5F">Welcome, {user_name}!</h2>
          <p>Your account is created with role <strong>{role}</strong>.<br>
             Click below to set your password.</p>
          <div style="text-align:center;margin:28px 0">
            <a href="{setup_link}" style="background:#1E3A5F;color:#fff;padding:14px 32px;
               border-radius:8px;text-decoration:none;font-weight:bold">
              Set Password &amp; Login
            </a>
          </div>
          <p style="color:#888;font-size:.85rem">Link expires in 48 hours.</p>
          <p><strong>App URL:</strong> <a href="{app_url}">{app_url}</a></p>
        </div>
      </div>
    </body></html>"""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Welcome to AC PMS System — Set Your Password"
    msg["From"]    = f"{cfg['sender_name']} <{cfg['smtp_user']}>"
    msg["To"]      = to_email
    msg.attach(MIMEText(html, "html"))
    try:
        with smtplib.SMTP(cfg["smtp_host"], int(cfg["smtp_port"]), timeout=15) as srv:
            srv.ehlo(); srv.starttls()
            srv.login(cfg["smtp_user"], cfg["smtp_password"])
            srv.send_message(msg)
        return True, "Invitation email sent successfully"
    except Exception as e:
        return False, f"Email failed: {e}"
