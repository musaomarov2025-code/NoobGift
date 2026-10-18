import sqlite3
from config import DB

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
        # Таблица промокодов (чеков)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS promo_codes (
                code TEXT PRIMARY KEY,
                amount_min REAL,
                amount_max REAL,
                max_activations INTEGER,
                current_activations INTEGER DEFAULT 0,
                is_task BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Таблица активаций (чтобы один юзер не активировал дважды)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS promo_activations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT,
                user_id INTEGER,
                activated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(code, user_id)
            )
        """)
        
        # Дефолтные настройки
        defaults = [
            ("task_reward", "0.45"),
            ("ref_bonus", "11.0"),
            ("ref_tasks_required", "5"),
            ("withdraw_friends", "3"),
            ("menu_avatar", "")
        ]
        for k, v in defaults:
            cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
            
        conn.commit()

# === ПОЛЬЗОВАТЕЛИ ===
def get_user(user_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()

def create_user(user_id, username, first_name, referrer_id=None, ad_code=None):
    with get_conn() as conn:
        conn.execute("INSERT INTO users (user_id, username, first_name, referrer_id, ad_code) VALUES (?, ?, ?, ?, ?)", (user_id, username, first_name, referrer_id, ad_code))
        conn.commit()

def update_user_username(user_id, username, first_name):
    with get_conn() as conn:
        conn.execute("UPDATE users SET username = ?, first_name = ? WHERE user_id = ?", (username, first_name, user_id))
        conn.commit()

def add_balance(user_id, amount, action_type="task"):
    with get_conn() as conn:
        conn.execute("UPDATE users SET balance = balance + ?, total_earned = total_earned + ? WHERE user_id = ?", (amount, amount, user_id))
        conn.commit()

def remove_balance(user_id, amount):
    with get_conn() as conn:
        conn.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
        conn.commit()

# === ЗАДАНИЯ ===
def save_task(user_id, service, task_id, link, reward):
    with get_conn() as conn:
        conn.execute("INSERT INTO tasks (user_id, service, task_id, link, reward, status) VALUES (?, ?, ?, ?, ?, 'pending')", (user_id, service, task_id, link, reward))
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

def mark_task_completed(user_id):
    with get_conn() as conn:
        conn.execute("UPDATE users SET tasks_completed = tasks_completed + 1 WHERE user_id = ?", (user_id,))
        conn.commit()

# === НАСТРОЙКИ ===
def get_setting(key):
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row['value'] if row else None

def set_setting(key, value):
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        conn.commit()

# === ПРОМОКОДЫ ===
def create_promo(code, amin, amax, max_act, is_task):
    with get_conn() as conn:
        conn.execute("INSERT INTO promo_codes (code, amount_min, amount_max, max_activations, is_task) VALUES (?, ?, ?, ?, ?)", (code, amin, amax, max_act, is_task))
        conn.commit()

def get_promo(code):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM promo_codes WHERE code = ?", (code,)).fetchone()

def check_promo_activation(code, user_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM promo_activations WHERE code = ? AND user_id = ?", (code, user_id)).fetchone()

def activate_promo(code, user_id, amount):
    with get_conn() as conn:
        conn.execute("INSERT INTO promo_activations (code, user_id) VALUES (?, ?)", (code, user_id))
        conn.execute("UPDATE promo_codes SET current_activations = current_activations + 1 WHERE code = ?", (code,))
        conn.execute("UPDATE users SET balance = balance + ?, total_earned = total_earned + ? WHERE user_id = ?", (amount, amount, user_id))
        conn.commit()

# === СТАТИСТИКА ===
def get_total_users():
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

def get_new_users_today():
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM users WHERE date(reg_date) = date('now')").fetchone()[0]

def get_total_balance():
    with get_conn() as conn:
        return conn.execute("SELECT SUM(balance) FROM users").fetchone()[0] or 0.0

def get_total_withdrawn():
    with get_conn() as conn:
        return conn.execute("SELECT SUM(amount) FROM withdrawals WHERE status = 'paid'").fetchone()[0] or 0.0

def get_total_tasks_done():
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'done'").fetchone()[0]

def get_user_referrals(user_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE referrer_id = ?", (user_id,)).fetchall()

def get_user_withdraws(user_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM withdrawals WHERE user_id = ? ORDER BY id DESC", (user_id,)).fetchall()

def get_db_path():
    return DB
