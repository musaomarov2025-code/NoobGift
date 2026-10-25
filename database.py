import sqlite3
from datetime import datetime
from config import DB, DEFAULTS

def get_conn():
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DROP TABLE IF EXISTS sponsors")
        cur.execute("DROP TABLE IF EXISTS user_sponsors")
        cur.execute("DROP TABLE IF EXISTS integrations")

        cur.execute("""CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, balance REAL DEFAULT 0.0, debt REAL DEFAULT 0.0, ref_earnings REAL DEFAULT 0.0, total_earned REAL DEFAULT 0.0, total_withdrawn REAL DEFAULT 0.0, tasks_completed INTEGER DEFAULT 0, referrer_id INTEGER, registered_at TEXT, is_banned INTEGER DEFAULT 0)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS sponsors (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, url TEXT, chat_id TEXT)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS custom_tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, url TEXT, chat_id TEXT, reward REAL)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS user_channels (user_id INTEGER, chat_id TEXT, type TEXT, PRIMARY KEY (user_id, chat_id))""")
        cur.execute("""CREATE TABLE IF NOT EXISTS withdrawals (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL, status TEXT DEFAULT 'pending', created_at TEXT)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, service TEXT, task_id TEXT, link TEXT, reward REAL, status TEXT DEFAULT 'pending')""")
        cur.execute("""CREATE TABLE IF NOT EXISTS notifies (id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT, media TEXT, mtype TEXT, btns TEXT, interval_h REAL, last_sent TEXT)""")

        cols = {r[1] for r in cur.execute("PRAGMA table_info(users)").fetchall()}
        if "debt" not in cols: cur.execute("ALTER TABLE users ADD COLUMN debt REAL DEFAULT 0.0")
        if "ref_earnings" not in cols: cur.execute("ALTER TABLE users ADD COLUMN ref_earnings REAL DEFAULT 0.0")
        if "total_withdrawn" not in cols: cur.execute("ALTER TABLE users ADD COLUMN total_withdrawn REAL DEFAULT 0.0")

        for k, v in DEFAULTS.items():
            cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, str(v)))
        conn.commit()

def get_setting(k):
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (k,)).fetchone()
        return row['value'] if row else DEFAULTS.get(k, "")
def set_setting(k, v):
    with get_conn() as conn: conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (k, str(v))); conn.commit()

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
        conn.execute("UPDATE users SET balance = balance + ?, total_earned = total_earned + ? WHERE user_id = ?", (round(amount, 2), round(amount, 2), uid)); conn.commit()
def add_ref_earning(ref_id, amount):
    with get_conn() as conn: conn.execute("UPDATE users SET balance = balance + ?, ref_earnings = ref_earnings + ?, total_earned = total_earned + ? WHERE user_id = ?", (round(amount, 2), round(amount, 2), round(amount, 2), ref_id)); conn.commit()

def add_sponsor(name, url, chat_id):
    with get_conn() as conn: conn.execute("INSERT INTO sponsors (name, url, chat_id) VALUES (?, ?, ?)", (name, url, chat_id)); conn.commit()
def get_sponsors():
    with get_conn() as conn: return conn.execute("SELECT * FROM sponsors").fetchall()
def del_sponsor(sid):
    with get_conn() as conn: conn.execute("DELETE FROM sponsors WHERE id=?", (sid,)); conn.commit()

def add_custom_task(name, url, chat_id, reward):
    with get_conn() as conn: conn.execute("INSERT INTO custom_tasks (name, url, chat_id, reward) VALUES (?, ?, ?, ?)", (name, url, chat_id, reward)); conn.commit()
def get_custom_tasks():
    with get_conn() as conn: return conn.execute("SELECT * FROM custom_tasks").fetchall()
def del_custom_task(tid):
    with get_conn() as conn: conn.execute("DELETE FROM custom_tasks WHERE id=?", (tid,)); conn.commit()

def mark_user_channel(uid, chat_id, ctype):
    with get_conn() as conn: conn.execute("INSERT OR IGNORE INTO user_channels (user_id, chat_id, type) VALUES (?, ?, ?)", (uid, str(chat_id), ctype)); conn.commit()
def check_user_channel(uid, chat_id):
    with get_conn() as conn: return conn.execute("SELECT 1 FROM user_channels WHERE user_id=? AND chat_id=?", (uid, str(chat_id))).fetchone() is not None

def get_refs_count(uid):
    with get_conn() as conn: return conn.execute("SELECT COUNT(*) as cnt FROM users WHERE referrer_id=?", (uid,)).fetchone()['cnt']

def create_withdrawal(uid, amount):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO withdrawals (user_id, amount, created_at) VALUES (?, ?, ?)", (uid, amount, datetime.now().isoformat()))
        conn.execute("UPDATE users SET balance = balance - ?, total_withdrawn = total_withdrawn + ? WHERE user_id = ?", (amount, amount, uid)); conn.commit()
        return cur.lastrowid
def set_withdrawal_status(wid, status):
    with get_conn() as conn: conn.execute("UPDATE withdrawals SET status=? WHERE id=?", (status, wid)); conn.commit()
def get_pending_withdrawals():
    with get_conn() as conn: return conn.execute("SELECT * FROM withdrawals WHERE status='pending'").fetchall()
def get_withdrawal(wid):
    with get_conn() as conn: return conn.execute("SELECT * FROM withdrawals WHERE id=?", (wid,)).fetchone()

def save_task(uid, srv, tid, link, reward):
    with get_conn() as conn: conn.execute("INSERT INTO tasks (user_id, service, task_id, link, reward) VALUES (?, ?, ?, ?, ?)", (uid, srv, tid, link, reward)); conn.commit()
def get_pending_task(uid):
    with get_conn() as conn: return conn.execute("SELECT * FROM tasks WHERE user_id=? AND status='pending' LIMIT 1", (uid,)).fetchone()
def get_manual_tasks():
    with get_conn() as conn: return conn.execute("SELECT * FROM tasks WHERE status='manual'").fetchall()
def mark_task_status(tid, status):
    with get_conn() as conn: conn.execute("UPDATE tasks SET status=? WHERE id=?", (status, tid)); conn.commit()
def add_task_completed(uid):
    with get_conn() as conn: conn.execute("UPDATE users SET tasks_completed = tasks_completed + 1 WHERE user_id=?", (uid,)); conn.commit()

def get_stats():
    with get_conn() as conn:
        return {"total": conn.execute("SELECT COUNT(*) FROM users").fetchone()[0], "today": conn.execute("SELECT COUNT(*) FROM users WHERE registered_at LIKE ?", (str(datetime.now().date()) + "%",)).fetchone()[0], "total_bal": conn.execute("SELECT SUM(balance) FROM users").fetchone()[0] or 0, "pending_wd": conn.execute("SELECT SUM(amount) FROM withdrawals WHERE status='pending'").fetchone()[0] or 0}
def get_top_balance():
    with get_conn() as conn: return conn.execute("SELECT username, balance FROM users ORDER BY balance DESC LIMIT 10").fetchall()
def get_top_refs():
    with get_conn() as conn: return conn.execute("SELECT u.username, COUNT(r.user_id) as cnt FROM users u JOIN users r ON u.user_id = r.referrer_id GROUP BY u.user_id ORDER BY cnt DESC LIMIT 10").fetchall()
def get_top_earn():
    with get_conn() as conn: return conn.execute("SELECT username, total_earned FROM users ORDER BY total_earned DESC LIMIT 10").fetchall()

def get_notifies():
    with get_conn() as conn: return conn.execute("SELECT * FROM notifies").fetchall()
def add_notify(text, media, mtype, btns, int_h):
    with get_conn() as conn: conn.execute("INSERT INTO notifies (text, media, mtype, btns, interval_h) VALUES (?, ?, ?, ?, ?)", (text, media, mtype, btns, int_h)); conn.commit()
def del_notify(nid):
    with get_conn() as conn: conn.execute("DELETE FROM notifies WHERE id=?", (nid,)); conn.commit()
def update_notify_time(nid, t):
    with get_conn() as conn: conn.execute("UPDATE notifies SET last_sent=? WHERE id=?", (t, nid)); conn.commit()
