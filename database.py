import aiosqlite
import json
from main import DB_PATH

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY, username TEXT, balance REAL DEFAULT 0.0,
                total_earned REAL DEFAULT 0.0, ref_by INTEGER DEFAULT 0, ref_count INTEGER DEFAULT 0,
                ref_earned REAL DEFAULT 0.0, ref_rewarded INTEGER DEFAULT 0, tasks_done INTEGER DEFAULT 0,
                banned INTEGER DEFAULT 0, traffic_name TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS services (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, api_key TEXT DEFAULT '',
                is_active INTEGER DEFAULT 1, priority INTEGER DEFAULT 1
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS withdrawals (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL,
                status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS task_completions (
                user_id INTEGER, service TEXT, task_id TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, service, task_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS traffic_ads (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, trafer TEXT, owner TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS promos (
                id INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT, text TEXT,
                media_type TEXT, media_id TEXT, buttons TEXT
            )
        """)
        
        defaults = [('task_reward', '0.65'), ('ref_reward', '15.0'), ('ref_tasks_needed', '5'), ('show_index', '1')]
        for k, v in defaults:
            await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
            
        default_services = [("BotoHub", 1), ("Traffy", 2), ("SubGram", 3), ("PiarFlow", 4), ("Flyer", 5), ("Tgrass", 6)]
        for srv_name, priority in default_services:
            await db.execute("INSERT OR IGNORE INTO services (name, priority) VALUES (?, ?)", (srv_name, priority))
            
        await db.commit()

async def get_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cursor:
            return await cursor.fetchone()

async def add_user(user_id: int, username: str, ref_by: int = 0):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO users (id, username, ref_by) VALUES (?, ?, ?)", (user_id, username, ref_by))
        if ref_by:
            await db.execute("UPDATE users SET ref_count = ref_count + 1 WHERE id = ?", (ref_by,))
        await db.commit()

async def update_balance(user_id: int, amount: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET balance = balance + ?, total_earned = total_earned + ? WHERE id = ?", (amount, amount, user_id))
        await db.commit()

async def deduct_balance(user_id: int, amount: float) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("UPDATE users SET balance = balance - ? WHERE id = ? AND balance >= ?", (amount, user_id, amount))
        await db.commit()
        return cursor.rowcount > 0

async def set_user_banned(user_id: int, banned: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET banned = ? WHERE id = ?", (banned, user_id))
        await db.commit()

async def set_ref_rewarded(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET ref_rewarded = 1 WHERE id = ?", (user_id,))
        await db.commit()

async def create_withdrawal(user_id: int, amount: float):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("INSERT INTO withdrawals (user_id, amount) VALUES (?, ?)", (user_id, amount))
        wd_id = cursor.lastrowid
        await db.commit()
        return wd_id

async def get_withdrawal(wd_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM withdrawals WHERE id = ?", (wd_id,)) as cursor:
            return await cursor.fetchone()

async def process_withdrawal(wd_id: int, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE withdrawals SET status = ? WHERE id = ?", (status, wd_id))
        if status == 'rejected':
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT user_id, amount FROM withdrawals WHERE id = ?", (wd_id,)) as cursor:
                wd = await cursor.fetchone()
                if wd:
                    await db.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (wd['amount'], wd['user_id']))
        await db.commit()

async def get_services():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM services ORDER BY priority ASC") as cursor:
            return await cursor.fetchall()

async def update_service_key(service_id: int, api_key: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE services SET api_key = ? WHERE id = ?", (api_key, service_id))
        await db.commit()

async def toggle_service(service_id: int, is_active: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE services SET is_active = ? WHERE id = ?", (is_active, service_id))
        await db.commit()

async def swap_service_priority(id1: int, id2: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT priority FROM services WHERE id = ?", (id1,)) as c1:
            p1 = (await c1.fetchone())['priority']
        async with db.execute("SELECT priority FROM services WHERE id = ?", (id2,)) as c2:
            p2 = (await c2.fetchone())['priority']
        await db.execute("UPDATE services SET priority = ? WHERE id = ?", (p2, id1))
        await db.execute("UPDATE services SET priority = ? WHERE id = ?", (p1, id2))
        await db.commit()

async def get_setting(key: str) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def set_setting(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        await db.commit()

async def is_task_completed(user_id: int, service: str, task_id: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT 1 FROM task_completions WHERE user_id = ? AND service = ? AND task_id = ?", (user_id, service, task_id)) as cursor:
            return await cursor.fetchone() is not None

async def add_task_completion(user_id: int, service: str, task_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO task_completions (user_id, service, task_id) VALUES (?, ?, ?)", (user_id, service, task_id))
        await db.execute("UPDATE users SET tasks_done = tasks_done + 1 WHERE id = ?", (user_id,))
        await db.commit()

async def check_ref_reward(user_id: int):
    needed = int(await get_setting('ref_tasks_needed') or 5)
    reward = float(await get_setting('ref_reward') or 15.0)
    
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT ref_by, tasks_done, ref_rewarded, username FROM users WHERE id = ?", (user_id,)) as cursor:
            user = await cursor.fetchone()
            
        if user and user['ref_by'] != 0 and user['tasks_done'] >= needed and user['ref_rewarded'] == 0:
            await db.execute("UPDATE users SET balance = balance + ?, ref_earned = ref_earned + ? WHERE id = ?", (reward, reward, user['ref_by']))
            await db.execute("UPDATE users SET ref_rewarded = 1 WHERE id = ?", (user_id,))
            await db.commit()
            return user['ref_by'], reward, user['username']
    return None, None, None

async def add_traffic_ad(name: str, trafer: str, owner: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO traffic_ads (name, trafer, owner) VALUES (?, ?, ?)", (name, trafer, owner))
        await db.commit()

async def get_traffic_ad(name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM traffic_ads WHERE name = ?", (name,)) as cursor:
            return await cursor.fetchone()

async def get_traffic_stats(name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users WHERE traffic_name = ?", (name,)) as c1:
            total = (await c1.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM users WHERE traffic_name = ? AND date(created_at) = date('now')", (name,)) as c2:
            today = (await c2.fetchone())[0]
        return total, today

async def add_promo(promo_type: str, text: str, media_type: str, media_id: str, buttons: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO promos (type, text, media_type, media_id, buttons) VALUES (?, ?, ?, ?, ?)", (promo_type, text, media_type, media_id, buttons))
        await db.commit()

async def get_welcome_promo():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM promos WHERE type = 'welcome' ORDER BY id DESC LIMIT 1") as cursor:
            return await cursor.fetchone()

async def get_all_shows():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM promos WHERE type = 'show' ORDER BY id ASC") as cursor:
            return await cursor.fetchall()

async def get_next_show():
    shows = await get_all_shows()
    if not shows: 
        return None
    index = int(await get_setting('show_index') or 0)
    if index >= len(shows): 
        index = 0
    promo = shows[index]
    next_idx = index + 1
    if next_idx >= len(shows): 
        next_idx = 0
    await set_setting('show_index', str(next_idx))
    return promo

async def delete_promo(promo_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM promos WHERE id = ?", (promo_id,))
        await db.commit()
