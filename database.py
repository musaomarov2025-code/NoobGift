import sqlite3
import random
from datetime import datetime, timedelta, date
from config import DB, DEFAULTS, REFERRAL_DAYS, JOIN_REQUEST_HOURS, ADMIN_ID

def get_conn():
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_conn() as conn:
        cur = conn.cursor()
        
        cur.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, balance REAL DEFAULT 0.0, 
            total_earned REAL DEFAULT 0.0, tasks_completed INTEGER DEFAULT 0,
            last_bonus TEXT, referrer_id INTEGER, registered_at TEXT, 
            passed_op INTEGER DEFAULT 0, welcome_bonus_paid INTEGER DEFAULT 0,
            ad_code TEXT DEFAULT NULL, is_banned INTEGER DEFAULT 0
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS referrals (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, referrer_id INTEGER, created_at TEXT, reminded INTEGER DEFAULT 0, status TEXT DEFAULT 'pending')""")
        cur.execute("""CREATE TABLE IF NOT EXISTS withdrawals (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL, status TEXT DEFAULT 'pending', created_at TEXT)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS promos (code TEXT PRIMARY KEY, amount REAL, max_uses INTEGER, used INTEGER DEFAULT 0, active INTEGER DEFAULT 1, is_op INTEGER DEFAULT 0, op_service TEXT, op_count INTEGER DEFAULT 0)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS promo_uses (code TEXT, user_id INTEGER, used_at TEXT, PRIMARY KEY (code, user_id))""")
        cur.execute("""CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, service TEXT, task_id TEXT, link TEXT, status TEXT DEFAULT 'pending', created_at TEXT)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS task_completed (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, service TEXT, task_id TEXT, reward REAL, done_at TEXT)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS ad_sources (code TEXT PRIMARY KEY, owner_id INTEGER, created_at TEXT, clicks INTEGER DEFAULT 0, price REAL DEFAULT 0)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS integrations (name TEXT PRIMARY KEY, api_key TEXT DEFAULT '', status TEXT DEFAULT 'off', role TEXT DEFAULT 'tasks')""")
        cur.execute("""CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY, added_by INTEGER, added_at TEXT)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS banners (id INTEGER PRIMARY KEY AUTOINCREMENT, caption TEXT DEFAULT '', text TEXT, url TEXT, color TEXT DEFAULT 'None')""")

        services = [('botohub', 'op'), ('piarflow', 'tasks'), ('tgrass', 'tasks'), ('trafsly', 'tasks'), ('subgram', 'tasks'), ('flyer', 'tasks')]
        for name, role in services:
            cur.execute("INSERT OR IGNORE INTO integrations (name, role) VALUES (?, ?)", (name, role))

        cur.execute("PRAGMA table_info(users)")
        cols = {r[1] for r in cur.fetchall()}
        if "total_earned" not in cols: cur.execute("ALTER TABLE users ADD COLUMN total_earned REAL DEFAULT 0.0")
        if "tasks_completed" not in cols: cur.execute("ALTER TABLE users ADD COLUMN tasks_completed INTEGER DEFAULT 0")
        if "passed_op" not in cols: cur.execute("ALTER TABLE users ADD COLUMN passed_op INTEGER DEFAULT 0")
        if "welcome_bonus_paid" not in cols: cur.execute("ALTER TABLE users ADD COLUMN welcome_bonus_paid INTEGER DEFAULT 0")
        if "registered_at" not in cols: cur.execute("ALTER TABLE users ADD COLUMN registered_at TEXT")
        if "ad_code" not in cols: cur.execute("ALTER TABLE users ADD COLUMN ad_code TEXT DEFAULT NULL")
        if "is_banned" not in cols: cur.execute("ALTER TABLE users ADD COLUMN is_banned INTEGER DEFAULT 0")

        cur.execute("PRAGMA table_info(ad_sources)")
        cols_ads = {r[1] for r in cur.fetchall()}
        if "price" not in cols_ads: cur.execute("ALTER TABLE ad_sources ADD COLUMN price REAL DEFAULT 0")

        cur.execute("PRAGMA table_info(promos)")
        cols_promo = {r[1] for r in cur.fetchall()}
        if "is_op" not in cols_promo: cur.execute("ALTER TABLE promos ADD COLUMN is_op INTEGER DEFAULT 0")
        if "op_service" not in cols_promo: cur.execute("ALTER TABLE promos ADD COLUMN op_service TEXT")
        if "op_count" not in cols_promo: cur.execute("ALTER TABLE promos ADD COLUMN op_count INTEGER DEFAULT 0")

        cur.execute("PRAGMA table_info(tasks)")
        cols_tasks = {r[1] for r in cur.fetchall()}
        if "created_at" not in cols_tasks: cur.execute("ALTER TABLE tasks ADD COLUMN created_at TEXT")

        cur.execute("PRAGMA table_info(banners)")
        cols_banners = {r[1] for r in cur.fetchall()}
        if cols_banners and "caption" not in cols_banners: cur.execute("ALTER TABLE banners ADD COLUMN caption TEXT DEFAULT ''")

        for k, v in DEFAULTS.items():
            cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, str(v)))
        cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('banner_index', '0')")
        conn.commit()

def get_setting(key):
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row['value'] if row else DEFAULTS.get(key, "")

def set_setting(key, value):
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
        conn.commit()

def add_banner(caption, text, url, color="None"):
    with get_conn() as conn:
        conn.execute("INSERT INTO banners (caption, text, url, color) VALUES (?, ?, ?, ?)", (caption, text, url, color))
        conn.commit()

def get_all_banners():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM banners ORDER BY id").fetchall()

def delete_banner(bid):
    with get_conn() as conn:
        conn.execute("DELETE FROM banners WHERE id = ?", (bid,))
        conn.commit()

def get_next_banner():
    with get_conn() as conn:
        banners = conn.execute("SELECT * FROM banners ORDER BY id").fetchall()
        if not banners: return None
        try: current_idx = int(get_setting("banner_index"))
        except: current_idx = 0
        if current_idx >= len(banners): current_idx = 0
        banner = banners[current_idx]
        next_idx = (current_idx + 1) % len(banners)
        set_setting("banner_index", str(next_idx))
        return banner

def is_main_admin(user_id): return user_id == ADMIN_ID
def is_admin(user_id):
    if is_main_admin(user_id): return True
    with get_conn() as conn:
        row = conn.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,)).fetchone()
        return row is not None
def add_admin(user_id, added_by):
    with get_conn() as conn:
        if conn.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,)).fetchone(): return False
        conn.execute("INSERT INTO admins (user_id, added_by, added_at) VALUES (?, ?, ?)", (user_id, added_by, datetime.now().isoformat()))
        conn.commit()
        return True
def remove_admin(user_id):
    if is_main_admin(user_id): return False
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
        conn.commit()
        return cur.rowcount > 0
def get_admins():
    result = []
    main_user = get_user(ADMIN_ID)
    result.append({"user_id": ADMIN_ID, "username": main_user['username'] if main_user else None, "is_main": True})
    with get_conn() as conn:
        rows = conn.execute("SELECT user_id FROM admins ORDER BY added_at").fetchall()
        for r in rows:
            u = conn.execute("SELECT username FROM users WHERE user_id = ?", (r['user_id'],)).fetchone()
            result.append({"user_id": r['user_id'], "username": u['username'] if u else None, "is_main": False})
    return result

def get_user(user_id):
    with get_conn() as conn: return conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
def get_user_by_username(username):
    with get_conn() as conn: return conn.execute("SELECT * FROM users WHERE username = ?", (username.replace('@', ''),)).fetchone()
def add_user(user_id, username, referrer_id=None):
    if get_user(user_id): return False
    with get_conn() as conn:
        conn.execute("INSERT INTO users (user_id, username, referrer_id, registered_at) VALUES (?, ?, ?, ?)", (user_id, username, referrer_id, datetime.now().isoformat()))
        conn.commit()
    return True
def update_username(user_id, username):
    with get_conn() as conn: conn.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id)); conn.commit()
def toggle_ban(user_id, ban_status):
    with get_conn() as conn: conn.execute("UPDATE users SET is_banned = ? WHERE user_id = ?", (ban_status, user_id)); conn.commit()
def add_balance(user_id, amount):
    with get_conn() as conn: conn.execute("UPDATE users SET balance = balance + ?, total_earned = total_earned + ? WHERE user_id = ?", (amount, amount, user_id)); conn.commit()
def set_op_passed(user_id):
    with get_conn() as conn: conn.execute("UPDATE users SET passed_op = 1 WHERE user_id = ?", (user_id,)); conn.commit()
def set_user_ad_code(user_id, code):
    with get_conn() as conn: conn.execute("UPDATE users SET ad_code = ? WHERE user_id = ?", (code, user_id)); conn.commit()

def create_pending_referral(user_id, referrer_id):
    with get_conn() as conn: conn.execute("INSERT INTO referrals (user_id, referrer_id, created_at, status) VALUES (?, ?, ?, 'pending')", (user_id, referrer_id, datetime.now().isoformat())); conn.commit()
def confirm_referral(user_id):
    with get_conn() as conn:
        row = conn.execute("SELECT id, referrer_id FROM referrals WHERE user_id = ? AND status = 'pending' ORDER BY id LIMIT 1", (user_id,)).fetchone()
        if not row: return None
        conn.execute("UPDATE referrals SET status = 'confirmed' WHERE id = ?", (row['id'],)); conn.commit()
        return row['referrer_id']
def get_confirmed_refs_count(referrer_id):
    with get_conn() as conn: return conn.execute("SELECT COUNT(*) as cnt FROM referrals WHERE referrer_id = ? AND status = 'confirmed'", (referrer_id,)).fetchone()['cnt']
def get_pending_refs_count(referrer_id):
    with get_conn() as conn: return conn.execute("SELECT COUNT(*) as cnt FROM referrals WHERE referrer_id = ? AND status = 'pending'", (referrer_id,)).fetchone()['cnt']
def get_user_referrals(referrer_id):
    with get_conn() as conn: return conn.execute("SELECT r.user_id, u.username, r.created_at, r.status FROM referrals r LEFT JOIN users u ON u.user_id = r.user_id WHERE r.referrer_id = ? ORDER BY r.created_at DESC", (referrer_id,)).fetchall()

def create_withdrawal(user_id, amount):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO withdrawals (user_id, amount, created_at) VALUES (?, ?, ?)", (user_id, amount, datetime.now().isoformat()))
        wid = cur.lastrowid
        conn.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id)); conn.commit()
        return wid
def get_withdrawal(wid):
    with get_conn() as conn: return conn.execute("SELECT * FROM withdrawals WHERE id = ?", (wid,)).fetchone()
def get_pending_withdrawals():
    with get_conn() as conn: return conn.execute("SELECT * FROM withdrawals WHERE status = 'pending' ORDER BY id").fetchall()
def set_withdrawal_status(wid, status):
    with get_conn() as conn: conn.execute("UPDATE withdrawals SET status = ? WHERE id = ?", (status, wid)); conn.commit()

def save_task(user_id, service, task_id, link):
    with get_conn() as conn: conn.execute("INSERT INTO tasks (user_id, service, task_id, link, status, created_at) VALUES (?, ?, ?, ?, 'pending', ?)", (user_id, service, task_id, link, datetime.now().isoformat())); conn.commit()
def get_pending_task(user_id):
    with get_conn() as conn: return conn.execute("SELECT * FROM tasks WHERE user_id = ? AND status = 'pending' ORDER BY id ASC LIMIT 1", (user_id,)).fetchone()
def mark_task_status(task_id, status):
    with get_conn() as conn: conn.execute("UPDATE tasks SET status = ? WHERE id = ?", (status, task_id)); conn.commit()
def mark_task_completed(user_id, service, task_id, reward):
    with get_conn() as conn:
        conn.execute("INSERT INTO task_completed (user_id, service, task_id, reward, done_at) VALUES (?, ?, ?, ?, ?)", (user_id, service, task_id, reward, datetime.now().isoformat()))
        conn.execute("UPDATE users SET tasks_completed = tasks_completed + 1 WHERE user_id = ?", (user_id,)); conn.commit()

def get_stats():
    with get_conn() as conn:
        return {
            "total": conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
            "today": conn.execute("SELECT COUNT(*) FROM users WHERE registered_at LIKE ?", (str(date.today()) + "%",)).fetchone()[0],
            "total_balance": conn.execute("SELECT COALESCE(SUM(balance),0) FROM users").fetchone()[0],
            "pending": conn.execute("SELECT COUNT(*) FROM withdrawals WHERE status = 'pending'").fetchone()[0],
            "done": conn.execute("SELECT COUNT(*) FROM withdrawals WHERE status = 'completed'").fetchone()[0],
            "total_stars": conn.execute("SELECT COALESCE(SUM(amount),0) FROM withdrawals WHERE status = 'completed'").fetchone()[0]
        }
def get_top_balance(limit=10):
    with get_conn() as conn: return conn.execute("SELECT user_id, username, balance FROM users ORDER BY balance DESC LIMIT ?", (limit,)).fetchall()
def get_top_refs(limit=10):
    with get_conn() as conn: return conn.execute("SELECT u.user_id, u.username, COUNT(r.id) as refs FROM users u LEFT JOIN referrals r ON r.referrer_id = u.user_id AND r.status = 'confirmed' GROUP BY u.user_id HAVING refs > 0 ORDER BY refs DESC LIMIT ?", (limit,)).fetchall()

def create_promo(code, amount, max_uses, is_op=0, op_service=None, op_count=0):
    with get_conn() as conn: conn.execute("INSERT OR REPLACE INTO promos (code, amount, max_uses, used, active, is_op, op_service, op_count) VALUES (?, ?, ?, 0, 1, ?, ?, ?)", (code.upper(), amount, max_uses, is_op, op_service, op_count)); conn.commit()
def get_promo(code):
    with get_conn() as conn: return conn.execute("SELECT * FROM promos WHERE code = ?", (code.upper(),)).fetchone()
def activate_promo(code, user_id):
    code = code.upper(); promo = get_promo(code)
    if not promo: return False, "❌ Такого промокода нет."
    if not promo['active']: return False, "❌ Промокод деактивирован."
    if promo['used'] >= promo['max_uses']: return False, "❌ Лимит активаций исчерпан."
    with get_conn() as conn:
        if conn.execute("SELECT 1 FROM promo_uses WHERE code = ? AND user_id = ?", (code, user_id)).fetchone(): return False, "❌ Вы уже активировали этот код."
        conn.execute("INSERT INTO promo_uses (code, user_id, used_at) VALUES (?, ?, ?)", (code, user_id, datetime.now().isoformat()))
        conn.execute("UPDATE promos SET used = used + 1 WHERE code = ?", (code,))
        conn.execute("UPDATE users SET balance = balance + ?, total_earned = total_earned + ? WHERE user_id = ?", (promo['amount'], promo['amount'], user_id))
        conn.commit()
    return True, f"✅ Промокод активирован! +{promo['amount']} ⭐"
def get_all_promos():
    with get_conn() as conn: return conn.execute("SELECT * FROM promos ORDER BY used DESC").fetchall()

def add_ad_source(code, owner_id, price=0):
    with get_conn() as conn: conn.execute("INSERT OR REPLACE INTO ad_sources (code, owner_id, created_at, price) VALUES (?, ?, ?, ?)", (code.lower(), owner_id, datetime.now().isoformat(), price)); conn.commit()
def get_ad_source(code):
    with get_conn() as conn: return conn.execute("SELECT * FROM ad_sources WHERE code = ?", (code.lower(),)).fetchone()
def track_ad_click(code):
    with get_conn() as conn: conn.execute("UPDATE ad_sources SET clicks = clicks + 1 WHERE code = ?", (code.lower(),)); conn.commit()
def get_all_ads():
    with get_conn() as conn: return conn.execute("SELECT * FROM ad_sources ORDER BY clicks DESC").fetchall()

def get_integration(name):
    with get_conn() as conn: return conn.execute("SELECT * FROM integrations WHERE name = ?", (name,)).fetchone()
def get_all_integrations():
    with get_conn() as conn: return conn.execute("SELECT * FROM integrations").fetchall()
def toggle_integration(name, status):
    with get_conn() as conn: conn.execute("UPDATE integrations SET status = ? WHERE name = ?", (status, name)); conn.commit()
def set_integration_role(name, role):
    with get_conn() as conn: conn.execute("UPDATE integrations SET role = ? WHERE name = ?", (role, name)); conn.commit()
def update_integration_key(name, key):
    with get_conn() as conn: conn.execute("UPDATE integrations SET api_key = ? WHERE name = ?", (key, name)); conn.commit()
