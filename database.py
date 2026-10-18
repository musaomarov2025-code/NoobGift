import sqlite3
from config import DB, TASK_REWARD, REF_BONUS

def get_conn():
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                balance REAL DEFAULT 0.0,
                total_earned REAL DEFAULT 0.0,
                total_refs INTEGER DEFAULT 0,
                confirmed_refs INTEGER DEFAULT 0,
                tasks_completed INTEGER DEFAULT 0,
                referrer_id INTEGER,
                ref_bonus_paid INTEGER DEFAULT 0,
                ad_code TEXT DEFAULT NULL,
                reg_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                service TEXT,
                task_id TEXT,
                link TEXT,
                reward REAL,
                status TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action_type TEXT,
                amount REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS withdrawals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sponsors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_name TEXT,
                channel_link TEXT,
                channel_id TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE,
                owner TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

# === ПОЛЬЗОВАТЕЛИ ===
def get_user(user_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()

def create_user(user_id, username, first_name, referrer_id=None, ad_code=None):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO users (user_id, username, first_name, referrer_id, ad_code) VALUES (?, ?, ?, ?, ?)",
            (user_id, username, first_name, referrer_id, ad_code)
        )
        conn.commit()

def update_user_username(user_id, username, first_name):
    with get_conn() as conn:
        conn.execute("UPDATE users SET username = ?, first_name = ? WHERE user_id = ?", (username, first_name, user_id))
        conn.commit()

def add_balance(user_id, amount, action_type="task"):
    with get_conn() as conn:
        conn.execute("UPDATE users SET balance = balance + ?, total_earned = total_earned + ? WHERE user_id = ?", (amount, amount, user_id))
        conn.execute("INSERT INTO history (user_id, action_type, amount) VALUES (?, ?, ?)", (user_id, action_type, amount))
        conn.commit()

def remove_balance(user_id, amount):
    with get_conn() as conn:
        conn.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
        conn.commit()

def add_ref(user_id):
    with get_conn() as conn:
        conn.execute("UPDATE users SET total_refs = total_refs + 1 WHERE user_id = ?", (user_id,))
        conn.commit()

def confirm_ref(user_id, bonus, tasks_done_by_ref):
    with get_conn() as conn:
        conn.execute("UPDATE users SET confirmed_refs = confirmed_refs + 1, balance = balance + ?, total_earned = total_earned + ?, ref_bonus_paid = 1 WHERE user_id = ?", (bonus, bonus, user_id))
        conn.execute("INSERT INTO history (user_id, action_type, amount) VALUES (?, 'ref_bonus', ?)", (user_id, bonus))
        conn.commit()

def mark_task_completed(user_id):
    with get_conn() as conn:
        conn.execute("UPDATE users SET tasks_completed = tasks_completed + 1 WHERE user_id = ?", (user_id,))
        conn.commit()

# === ЗАДАНИЯ ===
def save_task(user_id, service, task_id, link, reward):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO tasks (user_id, service, task_id, link, reward, status) VALUES (?, ?, ?, ?, ?, 'pending')",
            (user_id, service, task_id, link, reward)
        )
        conn.commit()

def get_pending_task(user_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM tasks WHERE user_id = ? AND status = 'pending' ORDER BY id ASC LIMIT 1", (user_id,)).fetchone()

def get_task_by_link(user_id, link):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM tasks WHERE user_id = ? AND link = ?", (user_id, link)).fetchone()

def mark_task_status(task_id, status):
    with get_conn() as conn:
        conn.execute("UPDATE tasks SET status = ? WHERE id = ?", (status, task_id))
        conn.commit()

# === ВЫВОД ===
def create_withdraw(user_id, amount):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO withdrawals (user_id, amount) VALUES (?, ?)", (user_id, amount))
        conn.commit()
        return cur.lastrowid

def get_withdraw(withdraw_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM withdrawals WHERE id = ?", (withdraw_id,)).fetchone()

def update_withdraw_status(withdraw_id, status):
    with get_conn() as conn:
        conn.execute("UPDATE withdrawals SET status = ? WHERE id = ?", (status, withdraw_id))
        conn.commit()

# === СПОНСОРЫ ===
def get_sponsors():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM sponsors").fetchall()

def add_sponsor(name, link, channel_id):
    with get_conn() as conn:
        conn.execute("INSERT INTO sponsors (channel_name, channel_link, channel_id) VALUES (?, ?, ?)", (name, link, channel_id))
        conn.commit()

def delete_sponsor(sponsor_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM sponsors WHERE id = ?", (sponsor_id,))
        conn.commit()

# === СТАТИСТИКА (ОБЩАЯ) ===
def get_total_users():
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

def get_total_withdrawn():
    with get_conn() as conn:
        return conn.execute("SELECT SUM(amount) FROM withdrawals WHERE status = 'paid'").fetchone()[0] or 0.0

def get_all_users():
    with get_conn() as conn:
        return conn.execute("SELECT user_id FROM users").fetchall()

# === ТОПЫ ===
def get_top_balance(limit=10):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users ORDER BY balance DESC LIMIT ?", (limit,)).fetchall()

def get_user_place_by_balance(user_id):
    with get_conn() as conn:
        user_balance = conn.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)).fetchone()['balance']
        place = conn.execute("SELECT COUNT(*) FROM users WHERE balance > ?", (user_balance,)).fetchone()[0] + 1
        return place, user_balance

def get_top_refs(limit=10, period="all"):
    with get_conn() as conn:
        if period == "all":
            return conn.execute("SELECT * FROM users ORDER BY total_refs DESC LIMIT ?", (limit,)).fetchall()
        # Для сегодня/недели нужен подсчет по дате регистрации рефералов
        # Упрощенно: если reg_date подходит
        query = "SELECT referrer_id, COUNT(*) as cnt FROM users WHERE referrer_id IS NOT NULL"
        if period == "today":
            query += " AND date(reg_date) = date('now')"
        elif period == "week":
            query += " AND reg_date >= date('now', '-7 days')"
        query += " GROUP BY referrer_id ORDER BY cnt DESC LIMIT ?"
        
        # Возвращаем как объекты юзеров с фиктивным total_refs
        rows = conn.execute(query, (limit,)).fetchall()
        res = []
        for r in rows:
            u = conn.execute("SELECT * FROM users WHERE user_id = ?", (r['referrer_id'],)).fetchone()
            if u:
                u_dict = dict(u)
                u_dict['total_refs'] = r['cnt']
                res.append(u_dict)
        return res

def get_top_earned(limit=10, period="all"):
    with get_conn() as conn:
        if period == "all":
            return conn.execute("SELECT * FROM users ORDER BY total_earned DESC LIMIT ?", (limit,)).fetchall()
        
        query = "SELECT user_id, SUM(amount) as total FROM history WHERE action_type IN ('task', 'ref_bonus')"
        if period == "today":
            query += " AND date(created_at) = date('now')"
        elif period == "week":
            query += " AND created_at >= date('now', '-7 days')"
        query += " GROUP BY user_id ORDER BY total DESC LIMIT ?"
        
        rows = conn.execute(query, (limit,)).fetchall()
        res = []
        for r in rows:
            u = conn.execute("SELECT * FROM users WHERE user_id = ?", (r['user_id'],)).fetchone()
            if u:
                u_dict = dict(u)
                u_dict['total_earned'] = r['total']
                res.append(u_dict)
        return res

# === РЕКЛАМА ===
def add_ad(code, owner):
    with get_conn() as conn:
        conn.execute("INSERT INTO ads (code, owner) VALUES (?, ?)", (code, owner))
        conn.commit()

def get_ad_stats(code):
    with get_conn() as conn:
        # Всего юзеров по метке
        total = conn.execute("SELECT COUNT(*) FROM users WHERE ad_code = ?", (code,)).fetchone()[0]
        # За сегодня
        today = conn.execute("SELECT COUNT(*) FROM users WHERE ad_code = ? AND date(reg_date) = date('now')", (code,)).fetchone()[0]
        # Выполнено заданий (всего) этими юзерами
        tasks = conn.execute("""
            SELECT COUNT(*) FROM tasks t 
            JOIN users u ON t.user_id = u.user_id 
            WHERE u.ad_code = ? AND t.status = 'done'
        """, (code,)).fetchone()[0]
        # Заданий за сегодня
        tasks_today = conn.execute("""
            SELECT COUNT(*) FROM tasks t 
            JOIN users u ON t.user_id = u.user_id 
            WHERE u.ad_code = ? AND t.status = 'done' AND date(t.added_at) = date('now')
        """, (code,)).fetchone()[0]
        
        return {"total": total, "today": today, "tasks": tasks, "tasks_today": tasks_today}

# === БЭКАП (ЗАГЛУШКА) ===
def get_db_path():
    return DB
