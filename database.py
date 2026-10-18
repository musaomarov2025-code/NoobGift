import sqlite3
import datetime
import time
from config import DB, TASK_REWARD, REF_BONUS, REF_TASKS_REQUIRED, WITHDRAW_FRIENDS_REQUIRED

def get_conn():
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_conn() as conn:
        cur = conn.cursor()
        
        # 1. Таблица пользователей
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
                welcome_bonus_paid INTEGER DEFAULT 0,
                reg_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 2. Таблица заданий (объединяем все сервисы)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                service TEXT,          -- piarflow, tgrass, trafsly
                task_id TEXT,          -- внутренний ID задания (ссылка или ads_id)
                link TEXT,             -- ссылка на задание
                reward REAL,           -- награда
                status TEXT,           -- pending, skipped, done
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 3. История действий (для топов за сегодня/неделю)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action_type TEXT,      -- task, ref_bonus, withdraw
                amount REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 4. Заявки на вывод
        cur.execute("""
            CREATE TABLE IF NOT EXISTS withdrawals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                status TEXT DEFAULT 'pending', -- pending, paid, rejected
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 5. Спонсоры (Личная ОП)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sponsors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_name TEXT,
                channel_link TEXT,
                channel_id TEXT
            )
        """)
        
        # 6. Настройки (для динамических текстов и т.д.)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.commit()

# ==========================================
# ФУНКЦИИ ДЛЯ ПОЛЬЗОВАТЕЛЕЙ
# ==========================================
def get_user(user_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()

def create_user(user_id, username, first_name, referrer_id=None):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO users (user_id, username, first_name, referrer_id) VALUES (?, ?, ?, ?)",
            (user_id, username, first_name, referrer_id)
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
    # Вызывается, когда реферал выполнил нужное кол-во заданий
    with get_conn() as conn:
        # Начисляем рефереру
        conn.execute("UPDATE users SET confirmed_refs = confirmed_refs + 1, balance = balance + ?, total_earned = total_earned + ?, ref_bonus_paid = 1 WHERE user_id = ?", (bonus, bonus, user_id))
        conn.execute("INSERT INTO history (user_id, action_type, amount) VALUES (?, 'ref_bonus', ?)", (user_id, bonus))
        conn.commit()

def mark_task_completed(user_id):
    with get_conn() as conn:
        conn.execute("UPDATE users SET tasks_completed = tasks_completed + 1 WHERE user_id = ?", (user_id,))
        conn.commit()

# ==========================================
# ФУНКЦИИ ДЛЯ ЗАДАНИЙ
# ==========================================
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

def mark_task_status(task_id, status):
    with get_conn() as conn:
        conn.execute("UPDATE tasks SET status = ? WHERE id = ?", (status, task_id))
        conn.commit()

def restore_skipped_tasks(user_id):
    # Возвращает скипнутые задания (если нужно)
    with get_conn() as conn:
        conn.execute("UPDATE tasks SET status = 'pending' WHERE user_id = ? AND status = 'skipped'", (user_id,))
        conn.commit()

# ==========================================
# ФУНКЦИИ ДЛЯ ВЫВОДА
# ==========================================
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

# ==========================================
# ФУНКЦИИ ДЛЯ СПОНСОРОВ (ОП)
# ==========================================
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

# ==========================================
# ФУНКЦИИ ДЛЯ СТАТИСТИКИ (ТОПЫ)
# ==========================================
def get_total_users():
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

def get_total_withdrawn():
    with get_conn() as conn:
        return conn.execute("SELECT SUM(amount) FROM withdrawals WHERE status = 'paid'").fetchone()[0] or 0.0

def get_top_balance(limit=10):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users ORDER BY balance DESC LIMIT ?", (limit,)).fetchall()

def get_user_place_by_balance(user_id):
    with get_conn() as conn:
        user_balance = conn.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)).fetchone()['balance']
        place = conn.execute("SELECT COUNT(*) FROM users WHERE balance > ?", (user_balance,)).fetchone()[0] + 1
        return place, user_balance

def get_top_refs(limit=10, period=None):
    with get_conn() as conn:
        if period == 'today':
            # Считаем по истории (нужно добавить запись в history при реферале)
            # Пока для простоты сортируем по total_refs
            return conn.execute("SELECT * FROM users ORDER BY total_refs DESC LIMIT ?", (limit,)).fetchall()
        elif period == 'week':
            return conn.execute("SELECT * FROM users ORDER BY total_refs DESC LIMIT ?", (limit,)).fetchall()
        else:
            return conn.execute("SELECT * FROM users ORDER BY total_refs DESC LIMIT ?", (limit,)).fetchall()

def get_top_earned(limit=10, period=None):
    with get_conn() as conn:
        if period == 'today':
            # Сложный запрос по истории
            pass
        return conn.execute("SELECT * FROM users ORDER BY total_earned DESC LIMIT ?", (limit,)).fetchall()
