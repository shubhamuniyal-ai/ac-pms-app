import sqlite3
import os
import json
import secrets
import smtplib
from datetime import date, datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

_BASE = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = os.environ.get("DATA_DIR", os.path.join(_BASE, "data"))
DB_PATH   = os.path.join(_DATA_DIR, "pms.db")
UPLOAD_DIR = os.path.join(_DATA_DIR, "uploads")


def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS stores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            store_name TEXT NOT NULL UNIQUE,
            state TEXT NOT NULL,
            total_ac INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            mobile TEXT,
            email TEXT,
            role TEXT NOT NULL CHECK(role IN ('Admin','Vendor','Viewer')),
            assigned_states TEXT DEFAULT '[]',
            assigned_stores TEXT DEFAULT '[]',
            password TEXT,
            reset_token TEXT,
            token_expiry TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (date('now'))
        );
        CREATE TABLE IF NOT EXISTS ac_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type_name TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS pms_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            store_id INTEGER NOT NULL REFERENCES stores(id),
            technician_id INTEGER NOT NULL REFERENCES users(id),
            ac_type TEXT NOT NULL,
            entry_date TEXT NOT NULL,
            status TEXT DEFAULT 'Completed',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS ac_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL REFERENCES pms_sessions(id),
            ac_number TEXT NOT NULL,
            serial_number TEXT NOT NULL,
            capacity REAL NOT NULL,
            ac_number_image TEXT,
            serial_number_image TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS email_config (
            id INTEGER PRIMARY KEY,
            smtp_host TEXT DEFAULT 'smtp.gmail.com',
            smtp_port INTEGER DEFAULT 587,
            smtp_user TEXT DEFAULT '',
            smtp_password TEXT DEFAULT '',
            sender_name TEXT DEFAULT 'AC PMS System',
            app_url TEXT DEFAULT 'http://localhost:8501',
            apk_url TEXT DEFAULT ''
        );
    """)

    _migrate(conn)

    c = conn.cursor()
    # Seed default admin
    if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        c.execute("""
            INSERT INTO users(name, mobile, email, role, password)
            VALUES('Admin','9999999999','admin@pms.local','Admin','admin123')
        """)
    # Seed AC types
    if c.execute("SELECT COUNT(*) FROM ac_types").fetchone()[0] == 0:
        for t in ['Split', 'Cassette', 'Ductable']:
            c.execute("INSERT OR IGNORE INTO ac_types(type_name) VALUES(?)", (t,))
    # Seed email config row
    if c.execute("SELECT COUNT(*) FROM email_config").fetchone()[0] == 0:
        c.execute("INSERT INTO email_config(id) VALUES(1)")

    conn.commit()
    conn.close()


def _migrate(conn):
    c = conn.cursor()

    # Check if users table needs schema upgrade (old CHECK uses 'Technician' not 'Vendor')
    create_sql = c.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='users'"
    ).fetchone()
    needs_rebuild = create_sql and ('Technician' in create_sql[0] or 'Viewer' not in create_sql[0])

    if needs_rebuild:
        # Save existing data
        existing_users = c.execute("SELECT * FROM users").fetchall()
        col_names = [d[0] for d in c.description]

        # Drop and recreate with correct schema
        c.execute("DROP TABLE IF EXISTS users_old")
        c.execute("ALTER TABLE users RENAME TO users_old")
        c.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                mobile TEXT,
                email TEXT,
                role TEXT NOT NULL CHECK(role IN ('Admin','Vendor','Viewer')),
                assigned_states TEXT DEFAULT '[]',
                assigned_stores TEXT DEFAULT '[]',
                password TEXT NOT NULL DEFAULT '',
                reset_token TEXT,
                token_expiry TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (date('now'))
            )
        """)
        # Re-insert existing users, mapping Technician → Vendor
        for row in existing_users:
            row_dict = dict(zip(col_names, row))
            role = row_dict.get('role', 'Vendor')
            if role == 'Technician':
                role = 'Vendor'
            c.execute("""
                INSERT INTO users(id,name,mobile,email,role,assigned_states,
                                  assigned_stores,password,reset_token,token_expiry,
                                  is_active,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                row_dict.get('id'),
                row_dict.get('name'),
                row_dict.get('mobile'),
                row_dict.get('email'),
                role,
                row_dict.get('assigned_states', '[]'),
                row_dict.get('assigned_stores', '[]'),
                row_dict.get('password', ''),
                row_dict.get('reset_token'),
                row_dict.get('token_expiry'),
                row_dict.get('is_active', 1),
                row_dict.get('created_at'),
            ))
        c.execute("DROP TABLE users_old")
    else:
        # Just add missing columns if any
        existing_cols = {row[1] for row in c.execute("PRAGMA table_info(users)")}
        for col, dtype in [('email','TEXT'), ('reset_token','TEXT'), ('token_expiry','TEXT')]:
            if col not in existing_cols:
                c.execute(f"ALTER TABLE users ADD COLUMN {col} {dtype}")

    # Set default email for the seeded admin if still missing
    c.execute("""
        UPDATE users SET email='admin@pms.local'
        WHERE email IS NULL AND mobile='9999999999' AND role='Admin'
    """)

    # Ensure email_config table exists
    c.execute("""
        CREATE TABLE IF NOT EXISTS email_config (
            id INTEGER PRIMARY KEY,
            smtp_host TEXT DEFAULT 'smtp.gmail.com',
            smtp_port INTEGER DEFAULT 587,
            smtp_user TEXT DEFAULT '',
            smtp_password TEXT DEFAULT '',
            sender_name TEXT DEFAULT 'AC PMS System',
            app_url TEXT DEFAULT 'http://localhost:8501',
            apk_url TEXT DEFAULT ''
        )
    """)
    # Add apk_url column to existing DBs that don't have it
    ecols = {row[1] for row in c.execute("PRAGMA table_info(email_config)")}
    if 'apk_url' not in ecols:
        c.execute("ALTER TABLE email_config ADD COLUMN apk_url TEXT DEFAULT ''")
    conn.commit()


# ── Auth ───────────────────────────────────────────────────────────────────────

def authenticate(identifier, password):
    """Login with email or mobile. Blocks accounts with empty/unset password."""
    conn = get_conn()
    row = conn.execute(
        """SELECT * FROM users
           WHERE (email=? OR mobile=?) AND password=?
           AND password IS NOT NULL AND password != ''
           AND is_active=1""",
        (identifier, identifier, password)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def generate_invite_token(user_id):
    token = secrets.token_urlsafe(32)
    expiry = (datetime.now() + timedelta(hours=48)).isoformat()
    conn = get_conn()
    conn.execute(
        "UPDATE users SET reset_token=?, token_expiry=? WHERE id=?",
        (token, expiry, user_id)
    )
    conn.commit()
    conn.close()
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
    conn.execute(
        "UPDATE users SET password=?, reset_token=NULL, token_expiry=NULL WHERE reset_token=?",
        (new_password, token)
    )
    conn.commit()
    conn.close()


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
        assigned = json.loads(row['assigned_stores'] or '[]')
        if assigned:
            all_stores = get_stores()
            return [s for s in all_stores if s['store_name'] in assigned]
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
    return [r[0] for r in rows]


def add_store(store_name, state, total_ac):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO stores(store_name,state,total_ac) VALUES(?,?,?)",
            (store_name, state, int(total_ac))
        )
        conn.commit()
        return True, "Store added successfully"
    except sqlite3.IntegrityError:
        return False, "Store name already exists"
    finally:
        conn.close()


def update_store(store_id, store_name, state, total_ac):
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE stores SET store_name=?, state=?, total_ac=? WHERE id=?",
            (store_name, state, int(total_ac), store_id)
        )
        conn.commit()
        return True, "Store updated"
    except sqlite3.IntegrityError:
        return False, "Store name already exists"
    finally:
        conn.close()


def delete_store(store_id):
    conn = get_conn()
    conn.execute("DELETE FROM stores WHERE id=?", (store_id,))
    conn.commit()
    conn.close()


# ── Users ──────────────────────────────────────────────────────────────────────

def get_users(role=None):
    conn = get_conn()
    if role:
        rows = conn.execute(
            "SELECT * FROM users WHERE role=? AND is_active=1 ORDER BY name", (role,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM users WHERE is_active=1 ORDER BY name"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_users():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM users ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_user(name, mobile, email, role, assigned_states, assigned_stores):
    """Create user without password — they set it via invite link."""
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute(
            """INSERT INTO users(name,mobile,email,role,assigned_states,assigned_stores,password)
               VALUES(?,?,?,?,?,?,?)""",
            (name, mobile or None, email.strip().lower(), role,
             json.dumps(assigned_states), json.dumps(assigned_stores), '')
        )
        user_id = c.lastrowid
        conn.commit()
        return True, user_id, "User created"
    except sqlite3.IntegrityError as e:
        msg = str(e).lower()
        if 'email' in msg:
            return False, None, "Email already registered"
        return False, None, "Mobile number already registered"
    finally:
        conn.close()


def update_user_status(user_id, is_active):
    conn = get_conn()
    conn.execute("UPDATE users SET is_active=? WHERE id=?", (is_active, user_id))
    conn.commit()
    conn.close()


def update_user(user_id, name, mobile, email, role, assigned_states, assigned_stores):
    conn = get_conn()
    try:
        conn.execute(
            """UPDATE users SET name=?,mobile=?,email=?,role=?,
               assigned_states=?,assigned_stores=? WHERE id=?""",
            (name, mobile, email.strip().lower(), role,
             json.dumps(assigned_states), json.dumps(assigned_stores), user_id)
        )
        conn.commit()
        return True, "User updated"
    except sqlite3.IntegrityError:
        return False, "Email or mobile already in use"
    finally:
        conn.close()


# ── AC Types ───────────────────────────────────────────────────────────────────

def get_ac_types():
    conn = get_conn()
    rows = conn.execute("SELECT type_name FROM ac_types ORDER BY type_name").fetchall()
    conn.close()
    return [r[0] for r in rows]


def add_ac_type(type_name):
    conn = get_conn()
    try:
        conn.execute("INSERT INTO ac_types(type_name) VALUES(?)", (type_name,))
        conn.commit()
        return True, "AC type added"
    except sqlite3.IntegrityError:
        return False, "AC type already exists"
    finally:
        conn.close()


def delete_ac_type(type_name):
    conn = get_conn()
    conn.execute("DELETE FROM ac_types WHERE type_name=?", (type_name,))
    conn.commit()
    conn.close()


# ── PMS Sessions ───────────────────────────────────────────────────────────────

def create_pms_session(store_id, tech_id, ac_type, entry_date):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO pms_sessions(store_id,technician_id,ac_type,entry_date) VALUES(?,?,?,?)",
        (store_id, tech_id, ac_type, entry_date)
    )
    session_id = c.lastrowid
    conn.commit()
    conn.close()
    return session_id


def create_ac_entry(session_id, ac_number, serial_number, capacity, ac_img, serial_img):
    conn = get_conn()
    conn.execute(
        """INSERT INTO ac_entries(session_id,ac_number,serial_number,capacity,
           ac_number_image,serial_number_image) VALUES(?,?,?,?,?,?)""",
        (session_id, ac_number, serial_number, capacity, ac_img, serial_img)
    )
    conn.commit()
    conn.close()


def get_vendor_history(user_id):
    conn = get_conn()
    rows = conn.execute("""
        SELECT ps.id as session_id, s.store_name, s.state, ps.entry_date,
               ps.ac_type, ps.status, ps.created_at,
               COUNT(ae.id) as ac_count
        FROM pms_sessions ps
        JOIN stores s ON ps.store_id=s.id
        LEFT JOIN ac_entries ae ON ae.session_id=ps.id
        WHERE ps.technician_id=?
        GROUP BY ps.id
        ORDER BY ps.entry_date DESC, ps.created_at DESC
    """, (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_session_ac_entries(session_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM ac_entries WHERE session_id=? ORDER BY id",
        (session_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Dashboard & Reports ────────────────────────────────────────────────────────

def get_dashboard_data():
    conn = get_conn()
    today = date.today().isoformat()
    d = {}
    d['stores_today'] = conn.execute(
        "SELECT COUNT(DISTINCT store_id) FROM pms_sessions WHERE entry_date=?", (today,)
    ).fetchone()[0]
    d['ac_today'] = conn.execute(
        """SELECT COUNT(*) FROM ac_entries ae
           JOIN pms_sessions ps ON ae.session_id=ps.id WHERE ps.entry_date=?""", (today,)
    ).fetchone()[0]
    d['ac_total'] = conn.execute("SELECT COUNT(*) FROM ac_entries").fetchone()[0]
    d['sessions_total'] = conn.execute("SELECT COUNT(*) FROM pms_sessions").fetchone()[0]
    total_stores = conn.execute("SELECT COUNT(*) FROM stores").fetchone()[0]
    d['pending'] = max(0, total_stores - d['stores_today'])

    d['store_ac'] = [dict(r) for r in conn.execute("""
        SELECT s.store_name, COUNT(ae.id) as ac_count
        FROM pms_sessions ps JOIN stores s ON ps.store_id=s.id
        JOIN ac_entries ae ON ae.session_id=ps.id
        GROUP BY s.store_name ORDER BY ac_count DESC LIMIT 10
    """).fetchall()]
    d['ac_type_dist'] = [dict(r) for r in conn.execute("""
        SELECT ac_type, COUNT(*) as cnt FROM pms_sessions GROUP BY ac_type
    """).fetchall()]
    d['tech_perf'] = [dict(r) for r in conn.execute("""
        SELECT u.name, COUNT(ae.id) as ac_count
        FROM pms_sessions ps JOIN users u ON ps.technician_id=u.id
        JOIN ac_entries ae ON ae.session_id=ps.id
        GROUP BY u.name ORDER BY ac_count DESC
    """).fetchall()]
    d['state_summary'] = [dict(r) for r in conn.execute("""
        SELECT s.state, COUNT(ae.id) as ac_count
        FROM pms_sessions ps JOIN stores s ON ps.store_id=s.id
        JOIN ac_entries ae ON ae.session_id=ps.id
        GROUP BY s.state ORDER BY ac_count DESC
    """).fetchall()]
    d['daily_trend'] = [dict(r) for r in conn.execute("""
        SELECT ps.entry_date, COUNT(ae.id) as ac_count
        FROM pms_sessions ps JOIN ac_entries ae ON ae.session_id=ps.id
        GROUP BY ps.entry_date ORDER BY ps.entry_date DESC LIMIT 30
    """).fetchall()]
    conn.close()
    return d


def get_report_data(start_date=None, end_date=None, store_id=None, state=None, tech_id=None):
    conn = get_conn()
    query = """
        SELECT s.store_name, s.state, ps.entry_date, u.name as technician,
               ae.ac_number, ae.serial_number, ae.capacity, ps.ac_type,
               ae.ac_number_image, ae.serial_number_image, ps.status
        FROM ac_entries ae
        JOIN pms_sessions ps ON ae.session_id=ps.id
        JOIN stores s ON ps.store_id=s.id
        JOIN users u ON ps.technician_id=u.id
        WHERE 1=1
    """
    params = []
    if start_date:
        query += " AND ps.entry_date>=?"; params.append(start_date)
    if end_date:
        query += " AND ps.entry_date<=?"; params.append(end_date)
    if store_id:
        query += " AND ps.store_id=?"; params.append(store_id)
    if state:
        query += " AND s.state=?"; params.append(state)
    if tech_id:
        query += " AND ps.technician_id=?"; params.append(tech_id)
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


def update_email_config(smtp_host, smtp_port, smtp_user, smtp_password, sender_name, app_url, apk_url=''):
    conn = get_conn()
    conn.execute("""
        UPDATE email_config SET smtp_host=?,smtp_port=?,smtp_user=?,
        smtp_password=?,sender_name=?,app_url=?,apk_url=? WHERE id=1
    """, (smtp_host, int(smtp_port), smtp_user, smtp_password, sender_name,
          app_url.rstrip('/'), apk_url.strip()))
    conn.commit()
    conn.close()


def send_invite_email(to_email, user_name, role, token):
    cfg = get_email_config()
    if not cfg.get('smtp_user') or not cfg.get('smtp_password'):
        return False, "SMTP not configured. Go to Settings → Email Config."

    app_url = cfg.get('app_url', 'http://localhost:8501')
    setup_link = f"{app_url}/?setup_token={token}"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"></head>
    <body style="font-family:Arial,sans-serif;background:#f4f6f8;padding:30px;margin:0">
      <div style="max-width:520px;margin:auto;background:#fff;border-radius:12px;
                  box-shadow:0 2px 12px rgba(0,0,0,0.1);overflow:hidden">
        <div style="background:#1E3A5F;padding:28px 32px;text-align:center">
          <h1 style="color:#fff;margin:0;font-size:1.6rem">❄️ AC PMS System</h1>
          <p style="color:#aac4e0;margin:6px 0 0">Preventive Maintenance Service</p>
        </div>
        <div style="padding:32px">
          <h2 style="color:#1E3A5F;margin-top:0">Welcome, {user_name}!</h2>
          <p style="color:#444;line-height:1.6">
            Your account has been created with role <strong>{role}</strong>.<br>
            Click the button below to set your password and start using the app.
          </p>
          <div style="text-align:center;margin:28px 0">
            <a href="{setup_link}"
               style="background:#1E3A5F;color:#fff;padding:14px 32px;border-radius:8px;
                      text-decoration:none;font-size:1rem;font-weight:bold;display:inline-block">
              Set Password &amp; Login
            </a>
          </div>
          <p style="color:#888;font-size:0.85rem;line-height:1.5">
            This link expires in <strong>48 hours</strong>.<br>
            If you didn't expect this email, ignore it.
          </p>
          <hr style="border:none;border-top:1px solid #eee;margin:20px 0">
          <p style="color:#444;margin:0">
            <strong>App URL:</strong>
            <a href="{app_url}" style="color:#1E3A5F">{app_url}</a>
          </p>
          <p style="color:#444;margin-top:8px">
            <strong>Your Role:</strong> {role}
          </p>
          {'<p style="color:#444;margin-top:8px"><strong>Vendor Access:</strong> Fill PMS forms &amp; view your submission history</p>' if role == 'Vendor' else ''}
          {'<p style="color:#444;margin-top:8px"><strong>Viewer Access:</strong> Dashboard &amp; downloadable reports</p>' if role == 'Viewer' else ''}
          {'<p style="color:#444;margin-top:8px"><strong>Admin Access:</strong> Full access to all features</p>' if role == 'Admin' else ''}
        </div>
        <div style="background:#f4f6f8;padding:16px 32px;text-align:center">
          <p style="color:#aaa;font-size:0.8rem;margin:0">
            Sent by {cfg.get('sender_name','AC PMS System')} &nbsp;|&nbsp;
            <a href="{app_url}" style="color:#1E3A5F">Open App</a>
          </p>
        </div>
      </div>
    </body>
    </html>
    """

    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"Welcome to AC PMS System — Set Your Password"
    msg['From'] = f"{cfg['sender_name']} <{cfg['smtp_user']}>"
    msg['To'] = to_email
    msg.attach(MIMEText(html, 'html'))

    try:
        with smtplib.SMTP(cfg['smtp_host'], int(cfg['smtp_port']), timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(cfg['smtp_user'], cfg['smtp_password'])
            server.send_message(msg)
        return True, "Invitation email sent successfully"
    except Exception as e:
        return False, f"Email failed: {e}"