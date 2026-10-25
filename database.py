import sqlite3
from datetime import datetime
from config import DB, DEFAULTS, ADMIN_ID

def get_conn():
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, balance REAL DEFAULT 0.0, debt REAL DEFAULT 0.0, ref_earnings REAL DEFAULT 0.0, total_earned REAL DEFAULT 0.0, total_withdrawn REAL DEFAULT 0.0, tasks_completed INTEGER DEFAULT 0, referrer_id INTEGER, registered_at TEXT, is_banned INTEGER DEFAULT 0)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS sponsors (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, url TEXT, chat_id TEXT)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS user_sponsors (user_id INTEGER, sponsor_id INTEGER, PRIMARY KEY (user_id, sponsor_id))""")
        cur.execute("""CREATE TABLE IF NOT EXISTS withdrawals (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL, status TEXT DEFAULT 'pending', created_at TEXT)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, service TEXT, task_id TEXT, link TEXT, status TEXT DEFAULT 'pending')""")
        
        # Миграции для старой базы
        cols = {r[1] for r in cur.execute("PRAGMA table_info(users)").fetchall()}
        if "debt" not in cols: cur.execute("ALTER TABLE users ADD COLUMN debt REAL DEFAULT 0.0")
        if "ref_earnings" not in cols: cur.execute("ALTER TABLE users ADD COLUMN ref_earnings REAL DEFAULT 0.0")
        if "total_withdrawn" not in cols: cur.execute("ALTER TABLE users ADD COLUMN total_withdrawn REAL DEFAULT 0.0")

        for k, v in DEFAULTS.items():
            cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, str(v)))
        conn.commit()

def get_setting(key):
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row['value'] if row else DEFAULTS.get(key, "")
def set_setting(key, value):
    with get_conn() as conn: conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value))); conn.commit()

# --- Юзеры ---
def get_user(uid):
    with get_conn() as conn: return conn.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
def get_user_by_username(uname):
    with get_conn() as conn: return conn.execute("SELECT * FROM users WHERE username=?", (uname.replace('@',''),)).fetchone()
def add_user(uid, uname, ref_id=None):
    with get_conn() as conn:
        if conn.execute("SELECT 1 FROM users WHERE user_id=?", (uid,)).fetchone(): return False
        conn.execute("INSERT INTO users (user_id, username, referrer_id, registered_at) VALUES (?, ?, ?, ?)", (uid, uname, ref_id, datetime.now().isoformat()))
        conn.commit(); return True
def update_username(uid, uname):
    with get_conn() as conn: conn.execute("UPDATE users SET username=? WHERE user_id=?", (uname, uid)); conn.commit()
def toggle_ban(uid, ban):
    with get_conn() as conn: conn.execute("UPDATE users SET is_banned=? WHERE user_id=?", (ban, uid)); conn.commit()
def add_balance(uid, amount):
    with get_conn() as conn:
        u = conn.execute("SELECT debt FROM users WHERE user_id=?", (uid,)).fetchone()
        debt = u['debt'] if u else 0
        if debt > 0 and amount > 0:
            if amount >= debt: amount -= debt; conn.execute("UPDATE users SET debt=0 WHERE user_id=?", (uid,))
            else: debt -= amount; amount = 0; conn.execute("UPDATE users SET debt=? WHERE user_id=?", (debt, uid))
        conn.execute("UPDATE users SET balance = balance + ?, total_earned = total_earned + ? WHERE user_id = ?", (amount, amount, uid)); conn.commit()
def add_ref_earning(ref_id, amount):
    with get_conn() as conn: conn.execute("UPDATE users SET balance = balance + ?, ref_earnings = ref_earnings + ?, total_earned = total_earned + ? WHERE user_id = ?", (amount, amount, amount, ref_id)); conn.commit()

# --- Спонсоры ---
def add_sponsor(name, url, chat_id):
    with get_conn() as conn: conn.execute("INSERT INTO sponsors (name, url, chat_id) VALUES (?, ?, ?)", (name, url, chat_id)); conn.commit()
def get_sponsors():
    with get_conn() as conn: return conn.execute("SELECT * FROM sponsors").fetchall()
def get_sponsor(sid):
    with get_conn() as conn: return conn.execute("SELECT * FROM sponsors WHERE id=?", (sid,)).fetchone()
def del_sponsor(sid):
    with get_conn() as conn: conn.execute("DELETE FROM sponsors WHERE id=?", (sid,)); conn.commit()
def save_user_sponsor(uid, sid):
    with get_conn() as conn: conn.execute("INSERT OR IGNORE INTO user_sponsors (user_id, sponsor_id) VALUES (?, ?)", (uid, sid)); conn.commit()

# --- Рефералы и Выводы ---
def get_refs_count(uid):
    with get_conn() as conn: return conn.execute("SELECT COUNT(*) as cnt FROM users WHERE referrer_id=?", (uid,)).fetchone()['cnt']
def create_withdrawal(uid, amount):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO withdrawals (user_id, amount, created_at) VALUES (?, ?, ?)", (uid, amount, datetime.now().isoformat()))
        wid = cur.lastrowid
        conn.execute("UPDATE users SET balance = balance - ?, total_withdrawn = total_withdrawn + ? WHERE user_id = ?", (amount, amount, uid)); conn.commit()
        return wid
def set_withdrawal_status(wid, status):
    with get_conn() as conn: conn.execute("UPDATE withdrawals SET status=? WHERE id=?", (status, wid)); conn.commit()
def get_pending_withdrawals():
    with get_conn() as conn: return conn.execute("SELECT * FROM withdrawals WHERE status='pending'").fetchall()
def get_withdrawal(wid):
    with get_conn() as conn: return conn.execute("SELECT * FROM withdrawals WHERE id=?", (wid,)).fetchone()

# --- Задания и Статистика ---
def save_task(uid, srv, tid, link):
    with get_conn() as conn: conn.execute("INSERT INTO tasks (user_id, service, task_id, link) VALUES (?, ?, ?, ?)", (uid, srv, tid, link)); conn.commit()
def get_pending_task(uid):
    with get_conn() as conn: return conn.execute("SELECT * FROM tasks WHERE user_id=? AND status='pending' LIMIT 1", (uid,)).fetchone()
def mark_task_status(tid, status):
    with get_conn() as conn: conn.execute("UPDATE tasks SET status=? WHERE id=?", (status, tid)); conn.commit()
def add_task_completed(uid):
    with get_conn() as conn: conn.execute("UPDATE users SET tasks_completed = tasks_completed + 1 WHERE user_id=?", (uid,)); conn.commit()

def get_stats():
    with get_conn() as conn:
        return {
            "total": conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
            "today": conn.execute("SELECT COUNT(*) FROM users WHERE registered_at LIKE ?", (str(datetime.now().date()) + "%",)).fetchone()[0],
            "total_bal": conn.execute("SELECT SUM(balance) FROM users").fetchone()[0] or 0,
            "pending_wd": conn.execute("SELECT SUM(amount) FROM withdrawals WHERE status='pending'").fetchone()[0] or 0
        }
def get_top_balance():
    with get_conn() as conn: return conn.execute("SELECT username, balance FROM users ORDER BY balance DESC LIMIT 10").fetchall()
def get_top_refs():
    with get_conn() as conn: return conn.execute("SELECT u.username, COUNT(r.user_id) as cnt FROM users u JOIN users r ON u.user_id = r.referrer_id GROUP BY u.user_id ORDER BY cnt DESC LIMIT 10").fetchall()
def get_top_earn():
    with get_conn() as conn: return conn.execute("SELECT username, total_earned FROM users ORDER BY total_earned DESC LIMIT 10").fetchall()
