import aiosqlite
from datetime import datetime, timedelta

DB_NAME = "bookings.db"


async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, username TEXT, service TEXT, master TEXT,
            date TEXT, time TEXT, duration INTEGER DEFAULT 30,
            name TEXT, phone TEXT, lang TEXT DEFAULT 'ru',
            status TEXT DEFAULT 'new', created_at TEXT
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE, name_ru TEXT NOT NULL, name_uz TEXT NOT NULL,
            price TEXT NOT NULL, duration INTEGER NOT NULL DEFAULT 30,
            active INTEGER NOT NULL DEFAULT 1
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS master_schedule (master_key TEXT, weekday INTEGER, start_time TEXT, end_time TEXT, UNIQUE(master_key,weekday))""")
        await db.execute("""CREATE TABLE IF NOT EXISTS masters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE, name_ru TEXT NOT NULL, name_uz TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS service_masters (
            service_key TEXT NOT NULL, master_key TEXT NOT NULL,
            PRIMARY KEY(service_key, master_key)
        )""")
        await db.commit()


async def seed_catalog():
    from salon_config import SALON
    async with aiosqlite.connect(DB_NAME) as db:
        for key, s in SALON["services"].items():
            await db.execute(
                "INSERT OR IGNORE INTO services (key,name_ru,name_uz,price,duration) VALUES (?,?,?,?,?)",
                (key, s["ru"], s["uz"], s["price"], s.get("duration", 30))
            )
        for key, m in SALON["masters"].items():
            await db.execute(
                "INSERT OR IGNORE INTO masters (key,name_ru,name_uz) VALUES (?,?,?)",
                (key, m["ru"], m["uz"])
            )
        for service_key in SALON["services"]:
            for master_key in SALON["masters"]:
                await db.execute(
                    "INSERT OR IGNORE INTO service_masters(service_key,master_key) VALUES(?,?)",
                    (service_key, master_key)
                )
        await db.commit()


async def add_booking(user_id: int, username: str, service: str, master: str, date: str, time: str, name: str, phone: str, lang: str = "ru", duration: int = 30) -> bool:
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("BEGIN IMMEDIATE")
        start = datetime.strptime(time, "%H:%M")
        end = start + timedelta(minutes=duration)
        cursor = await db.execute(
            "SELECT time, COALESCE(duration,30) FROM bookings WHERE date=? AND master=? AND status!='cancelled'",
            (date, master)
        )
        for existing_time, existing_duration in await cursor.fetchall():
            existing_start = datetime.strptime(existing_time, "%H:%M")
            existing_end = existing_start + timedelta(minutes=existing_duration or 30)
            if start < existing_end and existing_start < end:
                await db.rollback()
                return False
        await db.execute(
            """INSERT INTO bookings
            (user_id,username,service,master,date,time,duration,name,phone,lang,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (user_id, username, service, master, date, time, duration, name, phone, lang, datetime.now().isoformat())
        )
        await db.commit()
        return True



async def update_booking_status(booking_id: int, status: str):
    allowed = {"new", "confirmed", "cancelled"}
    if status not in allowed:
        return False
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("UPDATE bookings SET status=? WHERE id=?", (status, booking_id))
        await db.commit()
        return cursor.rowcount > 0
