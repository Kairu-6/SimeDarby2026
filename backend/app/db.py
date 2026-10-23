import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from hashlib import scrypt
from secrets import token_hex

from .config import settings


def now() -> str:
    return datetime.now(UTC).isoformat()


def password_hash(password: str, salt: str) -> str:
    return scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()


@contextmanager
def connect():
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(settings.db_path, timeout=20)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
 role TEXT NOT NULL, township TEXT NOT NULL, points INTEGER NOT NULL DEFAULT 0 CHECK(points>=0),
 lifetime_points INTEGER NOT NULL DEFAULT 0, salt TEXT NOT NULL, password_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tokens (token TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id), expires_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS bins (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, township TEXT NOT NULL, address TEXT NOT NULL,
 latitude REAL NOT NULL, longitude REAL NOT NULL, food_fill REAL NOT NULL DEFAULT 0,
 recycle_fill REAL NOT NULL DEFAULT 0, online INTEGER NOT NULL DEFAULT 1, last_seen TEXT NOT NULL,
 device_id TEXT UNIQUE NOT NULL, empty_distance_cm REAL NOT NULL DEFAULT 60,
 full_distance_cm REAL NOT NULL DEFAULT 8
);
CREATE TABLE IF NOT EXISTS deposits (
 id TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id), bin_id TEXT REFERENCES bins(id),
 status TEXT NOT NULL, category TEXT, material TEXT, confidence REAL, model TEXT,
 weight_kg REAL, points INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
 expires_at TEXT NOT NULL, completed_at TEXT, event_id TEXT UNIQUE
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_bin_session ON deposits(bin_id) WHERE status IN ('pending','classified');
CREATE TABLE IF NOT EXISTS vouchers (
 id TEXT PRIMARY KEY, merchant TEXT NOT NULL, title TEXT NOT NULL, description TEXT NOT NULL,
 location TEXT NOT NULL, cost INTEGER NOT NULL CHECK(cost>0), category TEXT NOT NULL,
 color TEXT NOT NULL, stock INTEGER NOT NULL CHECK(stock>=0), valid_days INTEGER NOT NULL DEFAULT 30
);
CREATE TABLE IF NOT EXISTS redemptions (
 id TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id), voucher_id TEXT REFERENCES vouchers(id),
 code TEXT UNIQUE NOT NULL, cost INTEGER NOT NULL, status TEXT NOT NULL,
 created_at TEXT NOT NULL, expires_at TEXT NOT NULL, request_id TEXT NOT NULL,
 UNIQUE(user_id, request_id)
);
CREATE TABLE IF NOT EXISTS ledger (
 id TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id), type TEXT NOT NULL,
 title TEXT NOT NULL, subtitle TEXT NOT NULL, points INTEGER NOT NULL, weight_kg REAL DEFAULT 0,
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alerts (
 id TEXT PRIMARY KEY, bin_id TEXT REFERENCES bins(id), compartment TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'open', created_at TEXT NOT NULL, acknowledged_by TEXT REFERENCES users(id), resolved_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS one_open_alert ON alerts(bin_id,compartment) WHERE status != 'resolved';
CREATE TABLE IF NOT EXISTS sensor_events (event_id TEXT PRIMARY KEY, bin_id TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS notifications (
 id TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id), title TEXT NOT NULL,
 body TEXT NOT NULL, kind TEXT NOT NULL, is_read INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS push_tokens (
 token TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id), updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS push_outbox (
 id TEXT PRIMARY KEY, token TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
 next_attempt TEXT NOT NULL, last_error TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS compartment_config (
 bin_id TEXT REFERENCES bins(id), category TEXT NOT NULL,
 empty_cm REAL NOT NULL, full_cm REAL NOT NULL, threshold REAL NOT NULL DEFAULT 90,
 distance_cm REAL, valid INTEGER NOT NULL DEFAULT 0, sampled_at TEXT,
 PRIMARY KEY(bin_id,category), CHECK(empty_cm>full_cm), CHECK(threshold>0 AND threshold<=100)
);
CREATE TABLE IF NOT EXISTS device_state (
 bin_id TEXT PRIMARY KEY REFERENCES bins(id), boot_id TEXT NOT NULL, sequence_no INTEGER NOT NULL,
 received_at TEXT NOT NULL, event_id TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS device_packets (
 event_id TEXT PRIMARY KEY, bin_id TEXT NOT NULL, payload TEXT NOT NULL, received_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS device_cycles (
 id TEXT PRIMARY KEY, session_id TEXT UNIQUE REFERENCES deposits(id), device_id TEXT NOT NULL,
 request_id TEXT UNIQUE NOT NULL, route TEXT NOT NULL, weight_kg REAL NOT NULL,
 state TEXT NOT NULL DEFAULT 'armed', created_at TEXT NOT NULL, execute_before TEXT NOT NULL,
 completion_event_id TEXT, fault TEXT
);
CREATE TABLE IF NOT EXISTS kiosk_offers (
 id TEXT PRIMARY KEY, bin_id TEXT NOT NULL REFERENCES bins(id), category TEXT NOT NULL,
 key_hash TEXT UNIQUE NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'waiting', user_id TEXT REFERENCES users(id),
 deposit_id TEXT UNIQUE REFERENCES deposits(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS one_waiting_kiosk_offer ON kiosk_offers(bin_id) WHERE state='waiting';
CREATE TABLE IF NOT EXISTS smartbin_captures (
 capture_id TEXT PRIMARY KEY, device_id TEXT NOT NULL, session_id TEXT NOT NULL,
 digest TEXT NOT NULL, response TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sorting_events (
 event_id TEXT PRIMARY KEY, command_id TEXT NOT NULL REFERENCES device_cycles(id),
 status TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL
);
"""


def migrate(db):
    """Additive migration: keep existing residents, wallets and bin readings intact."""
    for table, column, declaration in [
        ("bins", "reject_fill", "REAL NOT NULL DEFAULT 0"),
        ("deposits", "classified_at", "TEXT"),
        ("deposits", "selected_category", "TEXT"),
        ("deposits", "capture_requested", "INTEGER NOT NULL DEFAULT 0"),
        ("deposits", "verification_message", "TEXT"),
    ]:
        if column not in {row[1] for row in db.execute(f"PRAGMA table_info({table})")}:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")
    for row in db.execute("SELECT * FROM bins").fetchall():
        for category in ("food", "recyclable", "reject"):
            db.execute(
                "INSERT OR IGNORE INTO compartment_config (bin_id,category,empty_cm,full_cm) VALUES (?,?,?,?)",
                (row["id"], category, row["empty_distance_cm"], row["full_distance_cm"]),
            )


def seed():
    with connect() as db:
        db.executescript(SCHEMA)
        migrate(db)
        if db.execute("SELECT count(*) FROM users").fetchone()[0]:
            return
        residents = [
            (
                "resident-1",
                "Aina Rahman",
                "resident@simeloop.demo",
                "resident",
                "City of Elmina",
                1240,
                1240,
            ),
            (
                "cleaner-1",
                "Ravi Kumar",
                "cleaner@simeloop.demo",
                "cleaner",
                "City of Elmina",
                0,
                0,
            ),
            (
                "resident-2",
                "Sarah Tan",
                "sarah@simeloop.demo",
                "resident",
                "City of Elmina",
                1680,
                1680,
            ),
            (
                "resident-3",
                "Daniel Lim",
                "daniel@simeloop.demo",
                "resident",
                "Ara Damansara",
                1540,
                1540,
            ),
            (
                "resident-4",
                "Amir Hakim",
                "amir@simeloop.demo",
                "resident",
                "Subang Jaya",
                980,
                980,
            ),
            (
                "resident-5",
                "Mei Ling",
                "mei@simeloop.demo",
                "resident",
                "Bandar Bukit Raja",
                720,
                720,
            ),
        ]
        for row in residents:
            salt = token_hex(16)
            db.execute(
                "INSERT INTO users VALUES (?,?,?,?,?,?,?,?,?)",
                (*row, salt, password_hash("Loop123!", salt)),
            )
        stamp = now()
        bins = [
            (
                "ELM-01",
                "Elmina Lakeside",
                "City of Elmina",
                "Lakeside promenade, Elmina Central Park",
                3.1768,
                101.5120,
                24,
                42,
            ),
            (
                "ELM-02",
                "Elmina Green",
                "City of Elmina",
                "Mawar Residences, Block B",
                3.1950,
                101.5170,
                38,
                94,
            ),
            (
                "ARA-01",
                "Oasis Square",
                "Ara Damansara",
                "Oasis Square, north entrance",
                3.1148,
                101.5777,
                16,
                31,
            ),
            (
                "SJ-01",
                "Subang Avenue",
                "Subang Jaya",
                "Community plaza, main entrance",
                3.0763,
                101.5880,
                91,
                67,
            ),
            (
                "BBR-01",
                "Raja Uda Park",
                "Bandar Bukit Raja",
                "Community park, Persiaran Setia",
                3.1000,
                101.4395,
                29,
                18,
            ),
            (
                "KL-01",
                "KL East Mall",
                "KL East",
                "Ground floor, community entrance",
                3.2345,
                101.7308,
                35,
                52,
            ),
            (
                "NS-01",
                "Seremban Central",
                "Seremban",
                "Township community centre",
                2.7258,
                101.9424,
                14,
                26,
            ),
        ]
        for row in bins:
            db.execute(
                "INSERT INTO bins (id,name,township,address,latitude,longitude,food_fill,recycle_fill,last_seen,device_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (*row, stamp, row[0]),
            )
        migrate(db)
        vouchers = [
            (
                "v1",
                "The Coffee House",
                "RM 5 off your next coffee",
                "A little pick-me-up, on your good habits. Minimum spend RM 12.",
                "Elmina Lakeside Mall",
                300,
                "Food & drinks",
                "#EEE1D0",
                80,
            ),
            (
                "v2",
                "FamilyMart",
                "RM 5 off a fresh favourite",
                "Your next snack stop just got more rewarding. Minimum spend RM 15.",
                "KL East Mall",
                350,
                "Food & drinks",
                "#E1EEDD",
                60,
            ),
            (
                "v3",
                "Nando’s",
                "RM 10 off your meal",
                "A feel-good meal for a feel-good choice. Minimum spend RM 35.",
                "Subang shopping precinct",
                600,
                "Food & drinks",
                "#F7E5DC",
                45,
            ),
            (
                "v4",
                "Village Grocer",
                "RM 10 off your groceries",
                "Make your next basket a little greener. Minimum spend RM 60.",
                "Elmina Lakeside Mall",
                700,
                "Shopping",
                "#E7E5F0",
                50,
            ),
            (
                "v5",
                "The Book Nook",
                "15% off your next read",
                "Find your next great story. Up to RM 15 off selected books.",
                "KL East Mall",
                450,
                "Lifestyle",
                "#F7EDC9",
                30,
            ),
            (
                "v6",
                "Weekend Treats",
                "RM 15 off a sweet escape",
                "Share something sweet. Minimum spend RM 45.",
                "Ara Damansara",
                1500,
                "Food & drinks",
                "#F2DFE5",
                25,
            ),
        ]
        db.executemany(
            "INSERT INTO vouchers (id,merchant,title,description,location,cost,category,color,stock) VALUES (?,?,?,?,?,?,?,?,?)",
            vouchers,
        )
        current = datetime.now(UTC)
        for i, (title, weight, points, days) in enumerate(
            [
                ("Recyclables sorted", 1.2, 120, 0),
                ("Food waste diverted", 0.8, 40, 1),
                ("Recyclables sorted", 2.1, 210, 3),
                ("Food waste diverted", 1.4, 70, 5),
                ("Recyclables sorted", 1.6, 160, 8),
                ("Recyclables sorted", 2.4, 240, 12),
                ("Food waste diverted", 2.0, 100, 18),
                ("Recyclables sorted", 3.0, 300, 35),
            ]
        ):
            db.execute(
                "INSERT INTO ledger VALUES (?,?,?,?,?,?,?,?)",
                (
                    f"seed-{i}",
                    "resident-1",
                    "earned",
                    title,
                    "Elmina Lakeside · City of Elmina",
                    points,
                    weight,
                    (current - timedelta(days=days)).isoformat(),
                ),
            )
        db.execute(
            "INSERT INTO notifications VALUES (?,?,?,?,?,?,?)",
            (
                token_hex(12),
                "resident-1",
                "Welcome to your greener everyday",
                "Your demo account is ready. Sort, drop and earn at a station near you.",
                "welcome",
                0,
                stamp,
            ),
        )
        for bin_id, compartment in [("ELM-02", "recyclable"), ("SJ-01", "food")]:
            db.execute(
                "INSERT INTO alerts (id,bin_id,compartment,created_at) VALUES (?,?,?,?)",
                (token_hex(12), bin_id, compartment, stamp),
            )
