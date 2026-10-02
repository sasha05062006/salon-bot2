import aiosqlite
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

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
        await db.execute("""CREATE TABLE IF NOT EXISTS master_schedule (master_key TEXT, weekday INTEGER, start_time TEXT, end_time TEXT, lunch_start TEXT, lunch_end TEXT, UNIQUE(master_key,weekday))""")
        await db.execute("""CREATE TABLE IF NOT EXISTS masters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE, name_ru TEXT NOT NULL, name_uz TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS service_masters (
            service_key TEXT NOT NULL, master_key TEXT NOT NULL,
            PRIMARY KEY(service_key, master_key)
        )""")
        cols = [r[1] for r in await (await db.execute("PRAGMA table_info(master_schedule)")).fetchall()]
        master_cols = [r[1] for r in await (await db.execute("PRAGMA table_info(masters)")).fetchall()]
        if "telegram_id" not in master_cols:
            await db.execute("ALTER TABLE masters ADD COLUMN telegram_id INTEGER")
        if "lunch_start" not in cols:
            await db.execute("ALTER TABLE master_schedule ADD COLUMN lunch_start TEXT")
        if "lunch_end" not in cols:
            await db.execute("ALTER TABLE master_schedule ADD COLUMN lunch_end TEXT")
        bcols = [r[1] for r in await (await db.execute("PRAGMA table_info(bookings)")).fetchall()]
        if "master_comment" not in bcols: await db.execute("ALTER TABLE bookings ADD COLUMN master_comment TEXT")
        if "reminder_24_sent" not in bcols: await db.execute("ALTER TABLE bookings ADD COLUMN reminder_24_sent INTEGER NOT NULL DEFAULT 0")
        if "reminder_2_sent" not in bcols: await db.execute("ALTER TABLE bookings ADD COLUMN reminder_2_sent INTEGER NOT NULL DEFAULT 0")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_bookings_date_master ON bookings(date, master, status)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_bookings_user ON bookings(user_id, id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_bookings_status ON bookings(status, date)")
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
        existing_links = await (await db.execute("SELECT COUNT(*) FROM service_masters")).fetchone()
        if not existing_links[0]:
            for service_key in SALON["services"]:
                for master_key in SALON["masters"]:
                    await db.execute(
                        "INSERT OR IGNORE INTO service_masters(service_key,master_key) VALUES(?,?)",
                        (service_key, master_key)
                    )

        # Import the default schedule into the DB only when a day has no saved schedule.
        # This keeps admin-edited schedules intact on subsequent restarts.
        for master_key, weekly in SALON.get("master_schedule", {}).items():
            for weekday, ranges in weekly.items():
                count = await (await db.execute(
                    "SELECT COUNT(*) FROM master_schedule WHERE master_key=? AND weekday=?",
                    (master_key, int(weekday))
                )).fetchone()
                if not count[0] and ranges:
                    start_time, end_time = ranges[0]
                    await db.execute(
                        "INSERT OR IGNORE INTO master_schedule(master_key,weekday,start_time,end_time,lunch_start,lunch_end) VALUES(?,?,?,?,NULL,NULL)",
                        (master_key, int(weekday), start_time, end_time)
                    )
        await db.commit()


async def add_booking(user_id: int, username: str, service: str, master: str, date: str, time: str, name: str, phone: str, lang: str = "ru", duration: int = 30) -> int | None:
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("PRAGMA busy_timeout=5000")
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
                return None
        insert_cursor = await db.execute(
            """INSERT INTO bookings
            (user_id,username,service,master,date,time,duration,name,phone,lang,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (user_id, username, service, master, date, time, duration, name, phone, lang, datetime.now(ZoneInfo('Asia/Tashkent')).isoformat())
        )
        await db.commit()
        return insert_cursor.lastrowid


async def update_booking_status(booking_id: int, status: str):
    if status not in {"new", "confirmed", "cancelled", "in_progress", "completed", "no_show"}:
        return None
    async with aiosqlite.connect(DB_NAME) as db:
        row = await (await db.execute("SELECT status FROM bookings WHERE id=?", (booking_id,))).fetchone()
        if not row:
            return None
        old_status = row[0]
        if old_status == status:
            return None
        cursor = await db.execute("UPDATE bookings SET status=? WHERE id=?", (status, booking_id))
        await db.commit()
        return old_status if cursor.rowcount else None


async def get_booking(booking_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute("SELECT * FROM bookings WHERE id=?", (booking_id,))).fetchone()
        return dict(row) if row else None


async def get_all_bookings():
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute("SELECT * FROM bookings ORDER BY id DESC")).fetchall()
        return [dict(r) for r in rows]


async def is_slot_available(date: str, start_time: str, duration_minutes: int, master: str) -> bool:
    start = datetime.strptime(start_time, "%H:%M")
    end = start + timedelta(minutes=duration_minutes)
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT time,COALESCE(duration,30) FROM bookings WHERE date=? AND master=? AND status!='cancelled'",
            (date, master)
        )
        for existing_time, existing_duration in await cursor.fetchall():
            existing_start = datetime.strptime(existing_time, "%H:%M")
            existing_end = existing_start + timedelta(minutes=existing_duration or 30)
            if start < existing_end and existing_start < end:
                return False
    return True


async def is_slot_booked(date: str, time: str, master: str) -> bool:
    return not await is_slot_available(date, time, 30, master)


async def get_salon_settings():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS salon_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        rows=await (await db.execute("SELECT key,value FROM salon_settings")).fetchall()
        return dict(rows)

async def set_salon_setting(key, value):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS salon_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        await db.execute("INSERT INTO salon_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(key,str(value)))
        await db.commit()

async def get_services():
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute("SELECT * FROM services WHERE active=1 ORDER BY id")).fetchall()
        return [dict(r) for r in rows]


async def get_masters():
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute("SELECT * FROM masters WHERE active=1 ORDER BY id")).fetchall()
        return [dict(r) for r in rows]


async def add_service(key, name_ru, name_uz, price, duration):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO services(key,name_ru,name_uz,price,duration) VALUES(?,?,?,?,?)", (key,name_ru,name_uz,price,duration))
        await db.commit()

async def deactivate_service(key):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE services SET active=0 WHERE key=?", (key,))
        await db.commit()

async def add_master(key, name_ru, name_uz):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO masters(key,name_ru,name_uz) VALUES(?,?,?)", (key,name_ru,name_uz))
        await db.commit()

async def deactivate_master(key):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE masters SET active=0 WHERE key=?", (key,))
        await db.commit()


async def set_master_day(master_key, weekday, start_time, end_time, lunch_start=None, lunch_end=None):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM master_schedule WHERE master_key=? AND weekday=?", (master_key, weekday))
        if start_time and end_time:
            await db.execute(
                "INSERT INTO master_schedule(master_key,weekday,start_time,end_time,lunch_start,lunch_end) VALUES(?,?,?,?,?,?)",
                (master_key, weekday, start_time, end_time, lunch_start, lunch_end)
            )
        await db.commit()


async def get_master_schedule(master_key):
    async with aiosqlite.connect(DB_NAME) as db:
        rows = await (await db.execute(
            "SELECT weekday,start_time,end_time,lunch_start,lunch_end FROM master_schedule WHERE master_key=? ORDER BY weekday",
            (master_key,)
        )).fetchall()
        return rows

async def get_service(key):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute("SELECT * FROM services WHERE key=? AND active=1", (key,))).fetchone()
        return dict(row) if row else None

async def get_master(key):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute("SELECT * FROM masters WHERE key=? AND active=1", (key,))).fetchone()
        return dict(row) if row else None


async def update_service(key, name_ru, name_uz, price, duration):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE services SET name_ru=?, name_uz=?, price=?, duration=? WHERE key=?", (name_ru, name_uz, price, duration, key))
        await db.commit()


async def get_masters_for_service(service_key):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            """SELECT m.* FROM masters m
               JOIN service_masters sm ON sm.master_key=m.key
               WHERE sm.service_key=? AND m.active=1 ORDER BY m.id""",
            (service_key,)
        )).fetchall()
        return [dict(r) for r in rows]


async def get_services_for_master(master_key):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            """SELECT s.* FROM services s
               JOIN service_masters sm ON sm.service_key=s.key
               WHERE sm.master_key=? AND s.active=1 ORDER BY s.id""",
            (master_key,)
        )).fetchall()
        return [dict(r) for r in rows]


async def set_master_service(service_key, master_key, enabled):
    async with aiosqlite.connect(DB_NAME) as db:
        if enabled:
            await db.execute(
                "INSERT OR IGNORE INTO service_masters(service_key,master_key) VALUES(?,?)",
                (service_key, master_key)
            )
        else:
            await db.execute(
                "DELETE FROM service_masters WHERE service_key=? AND master_key=?",
                (service_key, master_key)
            )
        await db.commit()


async def get_bookings_for_user(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            "SELECT * FROM bookings WHERE user_id=? ORDER BY id DESC LIMIT 50", (user_id,)
        )).fetchall()
        return [dict(r) for r in rows]


async def update_booking_details(booking_id: int, date: str, time: str, master: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("PRAGMA busy_timeout=5000")
        await db.execute("BEGIN IMMEDIATE")
        db.row_factory = aiosqlite.Row
        row = await (await db.execute("SELECT service,duration,status FROM bookings WHERE id=?", (booking_id,))).fetchone()
        if not row or row["status"] == "cancelled":
            return False
        duration = int(row["duration"] or 30)
        service_row = await (await db.execute("SELECT key FROM services WHERE name_ru=? OR name_uz=? LIMIT 1", (row["service"], row["service"]))).fetchone()
        if not service_row:
            return False
        allowed = await (await db.execute("SELECT 1 FROM service_masters WHERE service_key=? AND master_key=? LIMIT 1", (service_row["key"], master))).fetchone()
        if not allowed:
            return False
        parsed = datetime.strptime(date, "%d.%m")
        start_dt = datetime.strptime(time, "%H:%M")
        end_dt = start_dt + timedelta(minutes=duration)
        now_tz = datetime.now(ZoneInfo("Asia/Tashkent"))
        year = now_tz.year
        if parsed.month < now_tz.month and (now_tz.month - parsed.month) >= 6:
            year += 1
        selected = parsed.replace(year=year)
        if selected.date() < now_tz.date():
            return False
        weekday = selected.weekday()
        sched = await (await db.execute("SELECT start_time,end_time,lunch_start,lunch_end FROM master_schedule WHERE master_key=? AND weekday=?", (master,weekday))).fetchone()
        if not sched:
            return False
        work_start = datetime.strptime(sched["start_time"], "%H:%M")
        work_end = datetime.strptime(sched["end_time"], "%H:%M")
        lunch_start = datetime.strptime(sched["lunch_start"], "%H:%M") if sched["lunch_start"] else None
        lunch_end = datetime.strptime(sched["lunch_end"], "%H:%M") if sched["lunch_end"] else None
        if start_dt < work_start or end_dt > work_end or (lunch_start and lunch_end and start_dt < lunch_end and end_dt > lunch_start):
            return False
        cursor = await db.execute("SELECT time,COALESCE(duration,30) FROM bookings WHERE date=? AND master=? AND status!='cancelled' AND id!=?", (date, master, booking_id))
        for existing_time, existing_duration in await cursor.fetchall():
            es = datetime.strptime(existing_time, "%H:%M")
            ee = es + timedelta(minutes=int(existing_duration or 30))
            if start_dt < ee and es < end_dt:
                return False
        await db.execute("UPDATE bookings SET date=?,time=?,master=? WHERE id=?", (date,time,master,booking_id))
        await db.commit()
        return True


async def get_bookings_filtered(date=None, master=None, status=None, q=None):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        sql = "SELECT * FROM bookings WHERE 1=1"
        args = []
        if date:
            sql += " AND date=?"; args.append(date)
        if master:
            sql += " AND master=?"; args.append(master)
        if status:
            sql += " AND status=?"; args.append(status)
        if q:
            sql += " AND (name LIKE ? OR phone LIKE ? OR username LIKE ?)"
            like = "%" + q + "%"; args.extend([like, like, like])
        sql += " ORDER BY date ASC, time ASC, id ASC"
        rows = await (await db.execute(sql, args)).fetchall()
        return [dict(r) for r in rows]

async def get_booking_stats():
    async with aiosqlite.connect(DB_NAME) as db:
        rows = await (await db.execute("SELECT status, COUNT(*) FROM bookings GROUP BY status")).fetchall()
        return {str(status): int(count) for status, count in rows}


async def get_admin_catalog():
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        services = [dict(x) for x in await (await db.execute("SELECT * FROM services ORDER BY id")).fetchall()]
        masters = [dict(x) for x in await (await db.execute("SELECT * FROM masters ORDER BY id")).fetchall()]
        links = [dict(x) for x in await (await db.execute("SELECT service_key,master_key FROM service_masters")).fetchall()]
        return {"services": services, "masters": masters, "links": links}


async def set_master_telegram_id(master_key, telegram_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE masters SET telegram_id=? WHERE key=?", (telegram_id, master_key))
        await db.commit()

async def get_master_by_telegram_id(telegram_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute("SELECT * FROM masters WHERE active=1 AND telegram_id=? LIMIT 1", (telegram_id,))).fetchone()
        return dict(row) if row else None

async def get_bookings_for_master(master_name):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute("SELECT * FROM bookings WHERE master=? AND status!='cancelled' ORDER BY date ASC,time ASC,id ASC", (master_name,))).fetchall()
        return [dict(r) for r in rows]

async def get_confirmed_bookings_for_reminders():
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute("SELECT * FROM bookings WHERE status='confirmed' AND user_id IS NOT NULL AND (reminder_24_sent=0 OR reminder_2_sent=0)")).fetchall()
        return [dict(r) for r in rows]

async def mark_reminder(booking_id, kind):
    col = "reminder_24_sent" if kind == "24h" else "reminder_2_sent"
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(f"UPDATE bookings SET {col}=1 WHERE id=?", (booking_id,))
        await db.commit()


async def get_master_by_name(name):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute("SELECT * FROM masters WHERE active=1 AND (name_ru=? OR name_uz=?) LIMIT 1", (name, name))).fetchone()
        return dict(row) if row else None


async def update_booking_master_result(booking_id, status, comment=None):
    allowed = {"completed", "no_show", "in_progress"}
    if status not in allowed:
        return False
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE bookings SET status=?, master_comment=? WHERE id=?", (status, comment, booking_id))
        await db.commit()
        return True
