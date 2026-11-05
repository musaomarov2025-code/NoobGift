import os
import aiosqlite
from config import DB_PATH, DEFAULTS

SPONSORS = ["tgrass", "piarflow", "flyer", "trafsly", "traffy"]


async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            balance REAL DEFAULT 0,
            referrer_id INTEGER,
            tasks_done INTEGER DEFAULT 0,
            ref_paid INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS settings(
            key TEXT PRIMARY KEY, value TEXT
        );
        CREATE TABLE IF NOT EXISTS sponsors(
            name TEXT PRIMARY KEY,
            api_key TEXT DEFAULT '',
            enabled INTEGER DEFAULT 1,
            priority INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS done_tasks(
            user_id INTEGER,
            task_id TEXT,
            PRIMARY KEY(user_id, task_id)
        );
        CREATE TABLE IF NOT EXISTS withdrawals(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            status TEXT DEFAULT 'new'
        );
        """)
        for k, v in DEFAULTS.items():
            await db.execute(
                "INSERT OR IGNORE INTO settings VALUES(?,?)", (k, v))
        for i, n in enumerate(SPONSORS):
            await db.execute(
                "INSERT OR IGNORE INTO sponsors(name, priority) "
                "VALUES(?,?)", (n, i + 1))
        await db.commit()


# ---------- настройки ----------

async def get_setting(key):
    async with aiosqlite.connect(DB_PATH) as db:
        c = await db.execute(
            "SELECT value FROM settings WHERE key=?", (key,))
        r = await c.fetchone()
        return r[0] if r else DEFAULTS.get(key)


async def set_setting(key, value):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO settings VALUES(?,?)",
            (key, str(value)))
        await db.commit()


# ---------- пользователи ----------

async def get_user(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        c = await db.execute(
            "SELECT * FROM users WHERE user_id=?", (user_id,))
        return await c.fetchone()


async def add_user(user_id, username, referrer_id=None):
    if await get_user(user_id):
        return False
    if referrer_id == user_id or not await get_user(referrer_id or 0):
        referrer_id = None
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO users(user_id, username, referrer_id) "
            "VALUES(?,?,?)", (user_id, username, referrer_id))
        await db.commit()
    return True


async def add_balance(user_id, amount):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET balance=balance+? WHERE user_id=?",
            (amount, user_id))
        await db.commit()


async def count_refs(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        c = await db.execute(
            "SELECT COUNT(*) FROM users WHERE referrer_id=?", (user_id,))
        return (await c.fetchone())[0]


# ---------- задания ----------

async def is_task_done(user_id, task_id):
    async with aiosqlite.connect(DB_PATH) as db:
        c = await db.execute(
            "SELECT 1 FROM done_tasks WHERE user_id=? AND task_id=?",
            (user_id, task_id))
        return await c.fetchone() is not None


async def finish_task(user_id, task_id, reward):
    """Засчитать задание. False, если уже было засчитано."""
    async with aiosqlite.connect(DB_PATH) as db:
        c = await db.execute(
            "INSERT OR IGNORE INTO done_tasks VALUES(?,?)",
            (user_id, task_id))
        if c.rowcount == 0:
            return False
        await db.execute(
            "UPDATE users SET balance=balance+?, "
            "tasks_done=tasks_done+1 WHERE user_id=?",
            (reward, user_id))
        await db.commit()
        return True


async def check_ref_reward(user_id):
    """Если друг выполнил нужное число заданий, платим пригласившему.
    Возвращает (referrer_id, reward) или None."""
    u = await get_user(user_id)
    if not u or not u["referrer_id"] or u["ref_paid"]:
        return None
    need = int(await get_setting("ref_tasks_needed"))
    if u["tasks_done"] < need:
        return None
    reward = float(await get_setting("ref_reward"))
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET ref_paid=1 WHERE user_id=?", (user_id,))
        await db.execute(
            "UPDATE users SET balance=balance+? WHERE user_id=?",
            (reward, u["referrer_id"]))
        await db.commit()
    return u["referrer_id"], reward


# ---------- спонсоры ----------

async def get_sponsors(only_active=False):
    sql = "SELECT * FROM sponsors"
    if only_active:
        sql += " WHERE enabled=1 AND api_key!=''"
    sql += " ORDER BY priority"
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        c = await db.execute(sql)
        return await c.fetchall()


async def get_sponsor(name):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        c = await db.execute(
            "SELECT * FROM sponsors WHERE name=?", (name,))
        return await c.fetchone()


async def set_sponsor_key(name, key):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE sponsors SET api_key=? WHERE name=?", (key, name))
        await db.commit()


async def toggle_sponsor(name):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE sponsors SET enabled=1-enabled WHERE name=?", (name,))
        await db.commit()


async def move_sponsor(name, up=True):
    names = [s["name"] for s in await get_sponsors()]
    i = names.index(name)
    j = i - 1 if up else i + 1
    if j < 0 or j >= len(names):
        return
    names[i], names[j] = names[j], names[i]
    async with aiosqlite.connect(DB_PATH) as db:
        for p, n in enumerate(names, 1):
            await db.execute(
                "UPDATE sponsors SET priority=? WHERE name=?", (p, n))
        await db.commit()


# ---------- вывод и статистика ----------

async def create_withdrawal(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        c = await db.execute(
            "SELECT balance FROM users WHERE user_id=?", (user_id,))
        row = await c.fetchone()
        if not row or row[0] <= 0:
            return None
        amount = row[0]
        await db.execute(
            "UPDATE users SET balance=0 WHERE user_id=?", (user_id,))
        c = await db.execute(
            "INSERT INTO withdrawals(user_id, amount) VALUES(?,?)",
            (user_id, amount))
        await db.commit()
        return c.lastrowid, amount


async def get_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        c = await db.execute(
            "SELECT COUNT(*), COALESCE(SUM(balance),0), "
            "COALESCE(SUM(tasks_done),0) FROM users")
        return await c.fetchone()
