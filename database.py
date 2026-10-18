import sqlite3
import random
from datetime import datetime, timedelta, date
from config import DB, DEFAULTS, REFERRAL_DAYS

def get_conn():
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, balance REAL DEFAULT 0.0, total_earned REAL DEFAULT 0.0, last_bonus TEXT, referrer_id INTEGER, registered_at TEXT, ref_bonus_paid INTEGER DEFAULT 0, welcome_bonus_paid INTEGER DEFAULT 0, passed_op INTEGER DEFAULT 0)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS referrals (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, referrer_id INTEGER, created_at TEXT, status TEXT DEFAULT 'pending')""")
        cur.execute("""CREATE TABLE IF NOT EXISTS withdrawals (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL, status TEXT DEFAULT 'pending', created_at TEXT)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS promos (code TEXT PRIMARY KEY, amount REAL, max_uses INTEGER, used INTEGER DEFAULT 0, active INTEGER DEFAULT 1)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS promo_uses (code TEXT, user_id INTEGER, used_at TEXT, PRIMARY KEY (code, user_id))""")
        
        # Таблицы для задач
        cur.execute("""CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, service TEXT, task_id TEXT, link TEXT, status TEXT DEFAULT 'pending', created_at TEXT)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS task_completed (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, service TEXT, task_id TEXT, reward REAL, done_at TEXT)""")
        
        # Таблицы для рекламных меток
        cur.execute("""CREATE TABLE IF NOT EXISTS ad_sources (code TEXT PRIMARY KEY, owner_id INTEGER, created_at TEXT, clicks INTEGER DEFAULT 0)""")
        
        # Дефолтные настройки
        for k, v in DEFAULTS.items():
            cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, str(v)))
            
        conn.commit()

# ================== SETTINGS ==================
def get_setting(key):
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row['value'] if row else DEFAULTS.get(key, "")

def set_setting(key, value):
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
        conn.commit()

# ================== USERS ==================
def get_user(user_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()

def add_user(user_id, username, referrer_id=None):
    if get_user(user_id):
        return False
    with get_conn() as conn:
        conn.execute("INSERT INTO users (user_id, username, referrer_id, registered_at) VALUES (?, ?, ?, ?)",
                     (user_id, username, referrer_id, datetime.now().isoformat()))
        conn.commit()
    return True

def update_username(user_id, username):
    with get_conn() as conn:
        conn.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
        conn.commit()

def add_balance(user_id, amount):
    with get_conn() as conn:
        conn.execute("UPDATE users SET balance = balance + ?, total_earned = total_earned + ? WHERE user_id = ?", (amount, amount, user_id))
        conn.commit()

def remove_balance(user_id, amount):
    with get_conn() as conn:
        conn.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
        conn.commit()

def get_balance(user_id):
    with get_conn() as conn:
        row = conn.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return row['balance'] if row else 0.0

def set_op_passed(user_id):
    with get_conn() as conn:
        conn.execute("UPDATE users SET passed_op = 1 WHERE user_id = ?", (user_id,))
        conn.commit()

# ================== REFERRALS ==================
def create_pending_referral(user_id, referrer_id):
    with get_conn() as conn:
        conn.execute("INSERT INTO referrals (user_id, referrer_id, created_at, status) VALUES (?, ?, ?, 'pending')",
                     (user_id, referrer_id, datetime.now().isoformat()))
        conn.commit()

def confirm_referral(user_id):
    # Вызывается, когда друг прошел ОП
    with get_conn() as conn:
        row = conn.execute("SELECT id, referrer_id FROM referrals WHERE user_id = ? AND status = 'pending' ORDER BY id LIMIT 1", (user_id,)).fetchone()
        if not row:
            return None
        conn.execute("UPDATE referrals SET status = 'confirmed' WHERE id = ?", (row['id'],))
        conn.commit()
        return row['referrer_id']

def get_confirmed_refs_count(referrer_id):
    with get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) as cnt FROM referrals WHERE referrer_id = ? AND status = 'confirmed'", (referrer_id,)).fetchone()
        return row['cnt'] if row else 0

def get_pending_refs_count(referrer_id):
    with get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) as cnt FROM referrals WHERE referrer_id = ? AND status = 'pending'", (referrer_id,)).fetchone()
        return row['cnt'] if row else 0

def get_user_referrals(referrer_id):
    with get_conn() as conn:
        return conn.execute("SELECT r.user_id, u.username, r.created_at, r.status FROM referrals r LEFT JOIN users u ON u.user_id = r.user_id WHERE r.referrer_id = ? ORDER BY r.created_at DESC", (referrer_id,)).fetchall()

# ================== WITHDRAWALS ==================
def create_withdrawal(user_id, amount):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO withdrawals (user_id, amount, created_at) VALUES (?, ?, ?)",
                    (user_id, amount, datetime.now().isoformat()))
        wid = cur.lastrowid
        conn.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
        conn.commit()
        return wid

def get_withdrawal(wid):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM withdrawals WHERE id = ?", (wid,)).fetchone()

def get_pending_withdrawals():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM withdrawals WHERE status = 'pending' ORDER BY id").fetchall()

def set_withdrawal_status(wid, status):
    with get_conn() as conn:
        conn.execute("UPDATE withdrawals SET status = ? WHERE id = ?", (status, wid))
        conn.commit()

# ================== TASKS ==================
def save_task(user_id, service, task_id, link):
    with get_conn() as conn:
        conn.execute("INSERT INTO tasks (user_id, service, task_id, link, status, created_at) VALUES (?, ?, ?, ?, 'pending', ?)",
                     (user_id, service, task_id, link, datetime.now().isoformat()))
        conn.commit()

def get_pending_task(user_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM tasks WHERE user_id = ? AND status = 'pending' ORDER BY id ASC LIMIT 1", (user_id,)).fetchone()

def mark_task_status(task_id, status):
    with get_conn() as conn:
        conn.execute("UPDATE tasks SET status = ? WHERE id = ?", (status, task_id))
        conn.commit()

def was_task_completed(user_id, task_id):
    with get_conn() as conn:
        row = conn.execute("SELECT 1 FROM task_completed WHERE user_id = ? AND task_id = ?", (user_id, task_id)).fetchone()
        return row is not None

def mark_task_completed(user_id, service, task_id, reward):
    with get_conn() as conn:
        conn.execute("INSERT INTO task_completed (user_id, service, task_id, reward, done_at) VALUES (?, ?, ?, ?, ?)",
                     (user_id, service, task_id, reward, datetime.now().isoformat()))
        conn.commit()

def get_task_stats(period=None):
    with get_conn() as conn:
        where, params = "", []
        if period == "today":
            where = "WHERE done_at LIKE ?"
            params = [datetime.now().strftime("%Y-%m-%d") + "%"]
        elif period == "week":
            where = "WHERE done_at >= ?"
            params = [(datetime.now() - timedelta(days=7)).isoformat()]
            
        row = conn.execute(f"SELECT COUNT(*), COUNT(DISTINCT user_id), COALESCE(SUM(reward),0) FROM task_completed {where}", params).fetchone()
        return {"count": row[0] or 0, "unique_users": row[1] or 0, "stars": row[2] or 0}

def get_top_balance(limit=10):
    with get_conn() as conn:
        return conn.execute("SELECT user_id, username, balance FROM users ORDER BY balance DESC LIMIT ?", (limit,)).fetchall()

def get_top_refs(limit=10):
    with get_conn() as conn:
        return conn.execute("""SELECT u.user_id, u.username, COUNT(r.id) as refs FROM users u LEFT JOIN referrals r ON r.referrer_id = u.user_id AND r.status = 'confirmed' GROUP BY u.user_id HAVING refs > 0 ORDER BY refs DESC LIMIT ?""", (limit,)).fetchall()

# ================== STATS ==================
def get_stats():
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        today = conn.execute("SELECT COUNT(*) FROM users WHERE registered_at LIKE ?", (str(date.today()) + "%",)).fetchone()[0]
        total_balance = conn.execute("SELECT COALESCE(SUM(balance),0) FROM users").fetchone()[0]
        pending = conn.execute("SELECT COUNT(*) FROM withdrawals WHERE status = 'pending'").fetchone()[0]
        done = conn.execute("SELECT COUNT(*) FROM withdrawals WHERE status = 'completed'").fetchone()[0]
        total_stars = conn.execute("SELECT COALESCE(SUM(amount),0) FROM withdrawals WHERE status = 'completed'").fetchone()[0]
        return {"total": total, "today": today, "total_balance": total_balance, "pending": pending, "done": done, "total_stars": total_stars}

# ================== PROMOS ==================
def create_promo(code, amount, max_uses):
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO promos (code, amount, max_uses, used, active) VALUES (?, ?, ?, 0, 1)", (code.upper(), amount, max_uses))
        conn.commit()

def get_promo(code):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM promos WHERE code = ?", (code.upper(),)).fetchone()

def activate_promo(code, user_id):
    code = code.upper()
    promo = get_promo(code)
    if not promo: return False, "❌ Такого промокода нет."
    if not promo['active']: return False, "❌ Промокод деактивирован."
    if promo['used'] >= promo['max_uses']: return False, "❌ Лимит активаций исчерпан."
    
    with get_conn() as conn:
        if conn.execute("SELECT 1 FROM promo_uses WHERE code = ? AND user_id = ?", (code, user_id)).fetchone():
            return False, "❌ Вы уже активировали этот код."
            
        conn.execute("INSERT INTO promo_uses (code, user_id, used_at) VALUES (?, ?, ?)", (code, user_id, datetime.now().isoformat()))
        conn.execute("UPDATE promos SET used = used + 1 WHERE code = ?", (code,))
        conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (promo['amount'], user_id))
        conn.commit()
    return True, f"✅ Промокод активирован! +{promo['amount']} ⭐"

# ================== ADS ==================
def add_ad_source(code, owner_id):
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO ad_sources (code, owner_id, created_at) VALUES (?, ?, ?)", (code.lower(), owner_id, datetime.now().isoformat()))
        conn.commit()

def get_ad_source(code):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM ad_sources WHERE code = ?", (code.lower(),)).fetchone()

def increment_ad_click(code):
    with get_conn() as conn:
        conn.execute("UPDATE ad_sources SET clicks = clicks + 1 WHERE code = ?", (code.lower(),))
        conn.commit()

def get_ad_stats(code):
    with get_conn() as conn:
        src = get_ad_source(code)
        if not src: return None
        users = conn.execute("SELECT COUNT(*) FROM users WHERE referrer_id IS NULL").fetchone()[0] # заглушка, нужна будет связка
        return {"clicks": src['clicks']}
