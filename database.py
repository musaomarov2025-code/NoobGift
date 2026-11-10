import json
import time
from datetime import datetime, timedelta

import aiosqlite

from config import DB_PATH, DEFAULTS, MSK, WITHDRAW_OPTIONS

SPONSORS = ["tgrass", "piarflow", "flyer", "trafsly", "traffy",
            "flowly", "botohub", "darkboost", "subgram", "axionna"]
GROUPS = ("all", "new", "active", "inactive", "rich")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
    user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
    balance REAL DEFAULT 0, referrer_id INTEGER,
    tasks_done INTEGER DEFAULT 0, ref_paid INTEGER DEFAULT 0,
    created_at INTEGER DEFAULT 0, verified INTEGER DEFAULT 1,
    banned INTEGER DEFAULT 0, blocked INTEGER DEFAULT 0,
    ip_hash TEXT, fp TEXT, lang TEXT, premium INTEGER DEFAULT 0,
    source TEXT, bonus INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS sponsors(
    name TEXT PRIMARY KEY, api_key TEXT DEFAULT '',
    enabled INTEGER DEFAULT 1, priority INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS done_tasks(
    user_id INTEGER, task_id TEXT, ts INTEGER DEFAULT 0,
    reward REAL DEFAULT 0, url TEXT, checked INTEGER DEFAULT 0,
    unsub INTEGER DEFAULT 0, refunded INTEGER DEFAULT 0,
    PRIMARY KEY(user_id, task_id)
);
CREATE TABLE IF NOT EXISTS withdrawals(
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL,
    status TEXT DEFAULT 'new', created_at INTEGER DEFAULT 0,
    processed_at INTEGER DEFAULT 0, need_tasks INTEGER DEFAULT 0,
    base_tasks INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS ads(
    id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, file_id TEXT,
    text TEXT, entities TEXT, buttons TEXT, enabled INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS ad_shows(
    ad_id INTEGER, day TEXT, n INTEGER DEFAULT 0,
    PRIMARY KEY(ad_id, day)
);
CREATE TABLE IF NOT EXISTS sources(
    name TEXT PRIMARY KEY, owner TEXT, created_at INTEGER DEFAULT 0
);
"""

# Колонки, которые добавляются в старые базы
MIGRATE = {
    "users": {
        "first_name": "TEXT", "created_at": "INTEGER DEFAULT 0",
        "verified": "INTEGER DEFAULT 1", "banned": "INTEGER DEFAULT 0",
        "blocked": "INTEGER DEFAULT 0", "ip_hash": "TEXT", "fp": "TEXT",
        "lang": "TEXT", "premium": "INTEGER DEFAULT 0",
        "source": "TEXT", "bonus": "INTEGER DEFAULT 0",
    },
    "withdrawals": {
        "created_at": "INTEGER DEFAULT 0",
        "processed_at": "INTEGER DEFAULT 0",
        "need_tasks": "INTEGER DEFAULT 0",
        "base_tasks": "INTEGER DEFAULT 0",
    },
    "done_tasks": {
        "ts": "INTEGER DEFAULT 0", "reward": "REAL DEFAULT 0",
        "url": "TEXT", "checked": "INTEGER DEFAULT 0",
        "unsub": "INTEGER DEFAULT 0", "refunded": "INTEGER DEFAULT 0",
    },
}


def _now():
    return int(time.time())


def day_start(back=0):
    """Начало дня по Москве (unix), back дней назад."""
    d = datetime.now(MSK).replace(hour=0, minute=0, second=0, microsecond=0)
    return int(d.timestamp()) - back * 86400


def _day(back=0):
    return (datetime.now(MSK) - timedelta(days=back)).strftime("%Y-%m-%d")


# ---------- мелкие помощники ----------

async def _rows(sql, args=()):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        c = await db.execute(sql, args)
        return await c.fetchall()


async def _row(sql, args=()):
    rows = await _rows(sql, args)
    return rows[0] if rows else None


async def _val(sql, args=()):
    async with aiosqlite.connect(DB_PATH) as db:
        c = await db.execute(sql, args)
        r = await c.fetchone()
        return r[0] if r else None


async def _exec(sql, args=()):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(sql, args)
        await db.commit()


async def init_db():
    import os
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        for table, cols in MIGRATE.items():
            c = await db.execute(f"PRAGMA table_info({table})")
            have = {r[1] for r in await c.fetchall()}
            for name, typ in cols.items():
                if name not in have:
                    await db.execute(
                        f"ALTER TABLE {table} ADD COLUMN {name} {typ}")
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
    v = await _val("SELECT value FROM settings WHERE key=?", (key,))
    return v if v is not None else DEFAULTS.get(key)


async def set_setting(key, value):
    await _exec(
        "INSERT OR REPLACE INTO settings VALUES(?,?)", (key, str(value)))


# ---------- пользователи ----------

async def get_user(user_id):
    return await _row("SELECT * FROM users WHERE user_id=?", (user_id,))


async def get_user_by_username(name):
    return await _row(
        "SELECT * FROM users WHERE lower(username)=lower(?)", (name,))


async def add_user(user_id, username, first_name, lang, premium,
                   referrer_id=None, source=None):
    """Возвращает (создан_ли, id пригласившего или None)."""
    async with aiosqlite.connect(DB_PATH) as db:
        c = await db.execute(
            "SELECT 1 FROM users WHERE user_id=?", (user_id,))
        if await c.fetchone():
            await db.execute(
                "UPDATE users SET username=?, first_name=?, lang=?, "
                "premium=?, blocked=0 WHERE user_id=?",
                (username, first_name, lang, premium, user_id))
            await db.commit()
            return False, None
        ref = None
        if referrer_id and referrer_id != user_id:
            c = await db.execute(
                "SELECT 1 FROM users WHERE user_id=?", (referrer_id,))
            if await c.fetchone():
                ref = referrer_id
        await db.execute(
            "INSERT INTO users(user_id, username, first_name, lang, "
            "premium, referrer_id, created_at, verified, source) "
            "VALUES(?,?,?,?,?,?,?,1,?)",
            (user_id, username, first_name, lang, premium, ref, _now(),
             source))
        await db.commit()
        return True, ref


async def set_banned(user_id, flag):
    await _exec("UPDATE users SET banned=? WHERE user_id=?",
                (1 if flag else 0, user_id))


async def mark_blocked(user_id):
    await _exec("UPDATE users SET blocked=1 WHERE user_id=?", (user_id,))


async def add_balance(user_id, amount):
    """amount может быть отрицательным; баланс не уходит ниже нуля."""
    await _exec(
        "UPDATE users SET balance=MAX(0, balance+?) WHERE user_id=?",
        (amount, user_id))


async def count_refs(user_id):
    return await _val(
        "SELECT COUNT(*) FROM users WHERE referrer_id=?", (user_id,))


async def user_ids_by_group(group):
    """Кому отправлять рассылку: all, new, active, inactive, rich."""
    base = "SELECT user_id FROM users WHERE banned=0 AND blocked=0"
    now = _now()
    d3 = now - 3 * 86400
    exists = ("EXISTS(SELECT 1 FROM done_tasks d "
              "WHERE d.user_id=users.user_id AND d.ts>=?)")
    if group == "new":
        rows = await _rows(base + " AND created_at>=?", (now - 7 * 86400,))
    elif group == "active":
        rows = await _rows(base + " AND " + exists, (d3,))
    elif group == "inactive":
        rows = await _rows(
            base + " AND created_at<? AND NOT " + exists, (d3, d3))
    elif group == "rich":
        rows = await _rows(
            base + " AND balance>=?", (min(WITHDRAW_OPTIONS),))
    else:
        rows = await _rows(base)
    return [r["user_id"] for r in rows]


async def all_user_ids():
    return await user_ids_by_group("all")


async def get_user_card(user_id):
    u = await get_user(user_id)
    if not u:
        return None
    invited = await _rows(
        "SELECT user_id, username, first_name, tasks_done, created_at "
        "FROM users WHERE referrer_id=? ORDER BY created_at", (user_id,))
    return {"user": u, "invited": invited}


# ---------- задания и рефералы ----------

async def is_task_done(user_id, task_id):
    return await _val(
        "SELECT 1 FROM done_tasks WHERE user_id=? AND task_id=?",
        (user_id, task_id)) is not None


async def finish_task(user_id, task_id, reward, url=None):
    """Засчитать задание. False, если уже было засчитано."""
    async with aiosqlite.connect(DB_PATH) as db:
        c = await db.execute(
            "INSERT OR IGNORE INTO done_tasks(user_id, task_id, ts, reward, "
            "url) VALUES(?,?,?,?,?)", (user_id, task_id, _now(), reward, url))
        if c.rowcount == 0:
            return False
        await db.execute(
            "UPDATE users SET balance=balance+?, "
            "tasks_done=tasks_done+1 WHERE user_id=?", (reward, user_id))
        await db.commit()
        return True


async def check_ref_reward(user_id):
    """Если друг выполнил нужное число заданий, платим пригласившему.
    Возвращает (referrer_id, reward, need) или None."""
    u = await get_user(user_id)
    if not u or not u["referrer_id"] or u["ref_paid"]:
        return None
    need = int(float(await get_setting("ref_tasks_needed")))
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
    return u["referrer_id"], reward, need


# ---------- спонсоры ----------

async def get_sponsors(only_active=False):
    sql = "SELECT * FROM sponsors"
    if only_active:
        sql += " WHERE enabled=1 AND api_key!=''"
    return await _rows(sql + " ORDER BY priority")


async def get_sponsor(name):
    return await _row("SELECT * FROM sponsors WHERE name=?", (name,))


async def set_sponsor_key(name, key):
    await _exec("UPDATE sponsors SET api_key=? WHERE name=?", (key, name))


async def toggle_sponsor(name):
    await _exec(
        "UPDATE sponsors SET enabled=1-enabled WHERE name=?", (name,))


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


# ---------- заявки на вывод ----------
# статусы: wait (ждёт заданий), new (ждёт выплаты), paid, rejected, cancel

async def create_withdrawal(user_id, amount, need_tasks=0):
    """Резервирует amount. Возвращает (номер, статус) или None, если
    не хватает звёзд. Статус wait, если нужно выполнить задания."""
    async with aiosqlite.connect(DB_PATH) as db:
        c = await db.execute(
            "SELECT balance, tasks_done FROM users WHERE user_id=?",
            (user_id,))
        row = await c.fetchone()
        if not row or row[0] < amount:
            return None
        status = "wait" if need_tasks > 0 else "new"
        await db.execute(
            "UPDATE users SET balance=balance-? WHERE user_id=?",
            (amount, user_id))
        c = await db.execute(
            "INSERT INTO withdrawals(user_id, amount, status, created_at, "
            "need_tasks, base_tasks) VALUES(?,?,?,?,?,?)",
            (user_id, amount, status, _now(), need_tasks, row[1]))
        await db.commit()
        return c.lastrowid, status


async def wait_progress(user_id):
    """Вывод, который ждёт заданий: {'w', 'done', 'need'} или None."""
    w = await _row(
        "SELECT * FROM withdrawals WHERE user_id=? AND status='wait' "
        "ORDER BY id DESC LIMIT 1", (user_id,))
    if not w:
        return None
    tasks = await _val(
        "SELECT tasks_done FROM users WHERE user_id=?", (user_id,)) or 0
    return {"w": dict(w), "done": max(tasks - w["base_tasks"], 0),
            "need": w["need_tasks"]}


async def activate_withdrawal(wid):
    """wait -> new. True, если заявка только что создана."""
    async with aiosqlite.connect(DB_PATH) as db:
        c = await db.execute(
            "UPDATE withdrawals SET status='new', created_at=? "
            "WHERE id=? AND status='wait'", (_now(), wid))
        await db.commit()
        return c.rowcount > 0


async def cancel_wait(wid, user_id):
    """Отмена вывода, который ждёт заданий; звёзды возвращаются."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        c = await db.execute(
            "SELECT * FROM withdrawals WHERE id=? AND user_id=? "
            "AND status='wait'", (wid, user_id))
        w = await c.fetchone()
        if not w:
            return None
        await db.execute(
            "UPDATE withdrawals SET status='cancel', processed_at=? "
            "WHERE id=?", (_now(), wid))
        await db.execute(
            "UPDATE users SET balance=balance+? WHERE user_id=?",
            (w["amount"], user_id))
        await db.commit()
        return dict(w)


async def get_withdrawal(wid):
    return await _row(
        "SELECT w.*, u.username, u.first_name FROM withdrawals w "
        "LEFT JOIN users u ON u.user_id=w.user_id WHERE w.id=?", (wid,))


async def list_withdrawals(kind, limit=20):
    """kind: 'new' (ожидают выплаты) или 'done' (обработанные)."""
    cond = ("w.status='new'" if kind == "new"
            else "w.status NOT IN ('new','wait')")
    order = "ASC" if kind == "new" else "DESC"
    return await _rows(
        "SELECT w.*, u.username, u.first_name FROM withdrawals w "
        "LEFT JOIN users u ON u.user_id=w.user_id "
        f"WHERE {cond} ORDER BY w.id {order} LIMIT ?", (limit,))


async def set_withdrawal_status(wid, status):
    """paid или rejected (с возвратом звёзд). None, если уже обработана."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        c = await db.execute(
            "SELECT * FROM withdrawals WHERE id=? AND status='new'", (wid,))
        w = await c.fetchone()
        if not w:
            return None
        await db.execute(
            "UPDATE withdrawals SET status=?, processed_at=? WHERE id=?",
            (status, _now(), wid))
        if status == "rejected":
            await db.execute(
                "UPDATE users SET balance=balance+? WHERE user_id=?",
                (w["amount"], w["user_id"]))
        await db.commit()
        return dict(w)


# ---------- статистика ----------

async def get_stats():
    s = {}
    s["users"] = await _val("SELECT COUNT(*) FROM users")
    s["new_today"] = await _val(
        "SELECT COUNT(*) FROM users WHERE created_at>=?", (day_start(),))
    s["new_week"] = await _val(
        "SELECT COUNT(*) FROM users WHERE created_at>=?", (day_start(6),))
    s["balance"] = await _val(
        "SELECT COALESCE(SUM(balance),0) FROM users")
    s["tasks_total"] = await _val("SELECT COUNT(*) FROM done_tasks")
    s["tasks_today"] = await _val(
        "SELECT COUNT(*) FROM done_tasks WHERE ts>=?", (day_start(),))
    rows = await _rows(
        "SELECT substr(task_id,1,instr(task_id,':')-1) AS sp, COUNT(*) AS n "
        "FROM done_tasks GROUP BY sp ORDER BY n DESC")
    s["by_sponsor"] = [(r["sp"], r["n"]) for r in rows]
    s["unsub"] = await _val(
        "SELECT COUNT(*) FROM done_tasks WHERE unsub=1 AND refunded=0")
    s["paid_sum"] = await _val(
        "SELECT COALESCE(SUM(amount),0) FROM withdrawals "
        "WHERE status='paid'")
    s["paid_count"] = await _val(
        "SELECT COUNT(*) FROM withdrawals WHERE status='paid'")
    s["pending_sum"] = await _val(
        "SELECT COALESCE(SUM(amount),0) FROM withdrawals "
        "WHERE status='new'")
    s["pending_count"] = await _val(
        "SELECT COUNT(*) FROM withdrawals WHERE status='new'")
    return s


async def top_referrers(limit=10):
    return await _rows(
        "SELECT r.referrer_id AS uid, COUNT(*) AS n, u.username, "
        "u.first_name FROM users r LEFT JOIN users u "
        "ON u.user_id=r.referrer_id WHERE r.referrer_id IS NOT NULL "
        "GROUP BY r.referrer_id ORDER BY n DESC LIMIT ?", (limit,))


# ---------- показы ----------

async def add_ad(post):
    await _exec(
        "INSERT INTO ads(kind, file_id, text, entities, buttons) "
        "VALUES(?,?,?,?,?)",
        (post["kind"], post.get("file_id"), post.get("text") or "",
         json.dumps(post.get("entities") or [], ensure_ascii=False),
         json.dumps(post.get("buttons") or [], ensure_ascii=False)))


async def list_ads():
    return await _rows("SELECT * FROM ads ORDER BY id")


async def get_ad(ad_id):
    return await _row("SELECT * FROM ads WHERE id=?", (ad_id,))


async def update_ad(ad_id, **fields):
    allowed = {"kind", "file_id", "text", "entities", "buttons", "enabled"}
    keys = [k for k in fields if k in allowed]
    if not keys:
        return
    sql = ("UPDATE ads SET " + ",".join(f"{k}=?" for k in keys)
           + " WHERE id=?")
    await _exec(sql, [fields[k] for k in keys] + [ad_id])


async def delete_ad(ad_id):
    await _exec("DELETE FROM ads WHERE id=?", (ad_id,))
    await _exec("DELETE FROM ad_shows WHERE ad_id=?", (ad_id,))


async def toggle_ad(ad_id):
    await _exec("UPDATE ads SET enabled=1-enabled WHERE id=?", (ad_id,))


async def count_ad_show(ad_id):
    await _exec(
        "INSERT INTO ad_shows(ad_id, day, n) VALUES(?,?,1) "
        "ON CONFLICT(ad_id, day) DO UPDATE SET n=n+1", (ad_id, _day()))


async def ad_stats(ad_id):
    total = await _val(
        "SELECT COALESCE(SUM(n),0) FROM ad_shows WHERE ad_id=?", (ad_id,))
    today = await _val(
        "SELECT COALESCE(SUM(n),0) FROM ad_shows WHERE ad_id=? AND day=?",
        (ad_id, _day()))
    week = await _val(
        "SELECT COALESCE(SUM(n),0) FROM ad_shows WHERE ad_id=? AND day>=?",
        (ad_id, _day(6)))
    return {"total": total, "today": today, "week": week}


async def next_ad():
    """Следующий включённый показ по кругу: 1, 2, 3, снова 1."""
    ads = await _rows("SELECT * FROM ads WHERE enabled=1 ORDER BY id")
    if not ads:
        return None
    ptr = int(float(await get_setting("ads_pointer") or 0))
    nxt = next((a for a in ads if a["id"] > ptr), ads[0])
    await set_setting("ads_pointer", nxt["id"])
    return nxt


# ---------- бонус за старт, отписки, возвраты ----------

async def give_start_bonus(user_id, amount):
    """Один раз на пользователя. True, если бонус выдан сейчас."""
    async with aiosqlite.connect(DB_PATH) as db:
        c = await db.execute(
            "UPDATE users SET bonus=1, balance=balance+? "
            "WHERE user_id=? AND bonus=0", (amount, user_id))
        await db.commit()
        return c.rowcount > 0


async def due_rechecks(limit=30):
    """Задания, которым пора сделать проверку на отписку (через час)."""
    now = _now()
    return await _rows(
        "SELECT rowid AS rid, user_id, task_id, reward, url FROM done_tasks "
        "WHERE checked=0 AND reward>0 AND ts>=? AND ts<=? "
        "ORDER BY ts LIMIT ?", (now - 48 * 3600, now - 3600, limit))


async def mark_checked(user_id, task_id):
    await _exec(
        "UPDATE done_tasks SET checked=1 WHERE user_id=? AND task_id=?",
        (user_id, task_id))


async def apply_penalty(user_id, task_id):
    """Отписка: списываем награду. Возвращает (rid, reward) или None."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        c = await db.execute(
            "SELECT rowid AS rid, reward FROM done_tasks "
            "WHERE user_id=? AND task_id=? AND unsub=0", (user_id, task_id))
        row = await c.fetchone()
        if not row:
            return None
        await db.execute(
            "UPDATE done_tasks SET unsub=1, checked=1 "
            "WHERE user_id=? AND task_id=?", (user_id, task_id))
        await db.execute(
            "UPDATE users SET balance=MAX(0, balance-?) WHERE user_id=?",
            (row["reward"], user_id))
        await db.commit()
        return row["rid"], row["reward"]


async def get_done_by_rid(rid):
    return await _row(
        "SELECT rowid AS rid, * FROM done_tasks WHERE rowid=?", (rid,))


async def refund_task(rid, user_id):
    """Возврат награды за отписку (один раз). Возвращает сумму или None."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        c = await db.execute(
            "SELECT rowid AS rid, reward FROM done_tasks WHERE rowid=? "
            "AND user_id=? AND unsub=1 AND refunded=0", (rid, user_id))
        row = await c.fetchone()
        if not row:
            return None
        await db.execute(
            "UPDATE done_tasks SET refunded=1 WHERE rowid=?", (rid,))
        await db.execute(
            "UPDATE users SET balance=balance+? WHERE user_id=?",
            (row["reward"], user_id))
        await db.commit()
        return row["reward"]


# ---------- источники трафика (статистика для рекламодателей) ----------

async def create_source(name, owner):
    await _exec(
        "INSERT OR REPLACE INTO sources(name, owner, created_at) "
        "VALUES(?,?,?)", (name.lower(), owner.lstrip("@"), _now()))


async def get_source(name):
    return await _row("SELECT * FROM sources WHERE name=?", (name.lower(),))


async def list_sources():
    return await _rows(
        "SELECT s.name, s.owner, "
        "(SELECT COUNT(*) FROM users u WHERE u.source=s.name) AS users "
        "FROM sources s ORDER BY s.created_at")


async def delete_source(name):
    await _exec("DELETE FROM sources WHERE name=?", (name.lower(),))


async def source_stats(name):
    n = name.lower()
    s = {}
    s["users"] = await _val(
        "SELECT COUNT(*) FROM users WHERE source=?", (n,))
    s["new_today"] = await _val(
        "SELECT COUNT(*) FROM users WHERE source=? AND created_at>=?",
        (n, day_start()))
    s["new_week"] = await _val(
        "SELECT COUNT(*) FROM users WHERE source=? AND created_at>=?",
        (n, day_start(6)))
    base = ("SELECT COUNT(*) FROM done_tasks d JOIN users u "
            "ON u.user_id=d.user_id WHERE u.source=?")
    s["tasks_total"] = await _val(base, (n,))
    s["tasks_today"] = await _val(base + " AND d.ts>=?", (n, day_start()))
    s["unsub"] = await _val(
        base + " AND d.unsub=1 AND d.refunded=0", (n,))
    return s
