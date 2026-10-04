"""SQLite connection, schema and demo data."""
import os
import random
import sqlite3
from datetime import date, datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "database.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS students(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  class TEXT NOT NULL,
  pin_hash TEXT
);
CREATE TABLE IF NOT EXISTS attendance(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id TEXT NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
  date TEXT NOT NULL,
  time TEXT NOT NULL,
  subject TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('Present','Absent','Late')),
  UNIQUE(student_id, date, subject)
);
CREATE TABLE IF NOT EXISTS qr_sessions(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  token TEXT NOT NULL UNIQUE,
  subject TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS activity(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  message TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'info',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS teachers(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS devices(
  student_id TEXT PRIMARY KEY REFERENCES students(student_id) ON DELETE CASCADE,
  device_id TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scan_fails(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id TEXT NOT NULL,
  ip TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_att_date ON attendance(date);
CREATE INDEX IF NOT EXISTS idx_att_student ON attendance(student_id);
CREATE INDEX IF NOT EXISTS idx_fail_time ON scan_fails(created_at);
"""

NAMES = ["Rahul Sharma", "Priya Verma", "Aman Gupta", "Sneha Patil", "Rohan Mehta", "Ananya Singh",
         "Karan Joshi", "Neha Kulkarni", "Vikram Rao", "Pooja Nair", "Arjun Reddy", "Isha Kapoor",
         "Dev Malhotra", "Riya Jain", "Siddharth Iyer", "Meera Desai", "Harsh Agarwal", "Kavya Menon",
         "Yash Thakur", "Divya Chauhan", "Nikhil Bansal", "Tanvi Shah", "Aditya Pandey", "Simran Kaur"]
CLASSES = ["CSE-A", "CSE-B", "IT-A"]
SUBJECTS = ["Java", "Python", "DBMS", "DSA"]
DEFAULT_SETTINGS = {"late_after": "10", "low_threshold": "75", "default_minutes": "5"}


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init():
    conn = connect()
    conn.executescript(SCHEMA)
    if "pin_hash" not in [r[1] for r in conn.execute("PRAGMA table_info(students)")]:  # upgrade older databases
        conn.execute("ALTER TABLE students ADD COLUMN pin_hash TEXT")
    for k, v in DEFAULT_SETTINGS.items():
        conn.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))
    if conn.execute("SELECT COUNT(*) FROM students").fetchone()[0] == 0:
        seed(conn)
    conn.commit()
    conn.close()


def seed(conn):
    rnd = random.Random(7)
    people = []
    for i, name in enumerate(NAMES):
        sid = f"CS24{i + 1:03d}"
        conn.execute("INSERT INTO students(student_id,name,class) VALUES(?,?,?)", (sid, name, CLASSES[i % 3]))
        people.append((sid, rnd.uniform(0.55, 0.98)))
    today = date.today()
    for back in range(30, -1, -1):
        d = today - timedelta(days=back)
        if d.weekday() >= 5 and back:
            continue
        subject = SUBJECTS[d.toordinal() % 4]
        for sid, p in people:
            if back == 0:
                if rnd.random() > 0.6:
                    continue
                status = "Late" if rnd.random() < 0.1 else "Present"
            else:
                r = rnd.random()
                status = "Present" if r < p * 0.92 else "Late" if r < p else "Absent"
            tm = "—" if status == "Absent" else f"09:{rnd.randint(0, 14):02d}:{rnd.randint(0, 59):02d}"
            conn.execute("INSERT INTO attendance(student_id,date,time,subject,status) VALUES(?,?,?,?,?)",
                         (sid, d.isoformat(), tm, subject, status))
    base = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
    for mins, msg, kind in [(0, "Welcome to AttendIQ. Demo data has been loaded.", "system"),
                            (2, "QR generated for Java class", "qr"),
                            (4, "Rahul Sharma marked attendance", "success"),
                            (5, "Priya Verma marked attendance", "success")]:
        conn.execute("INSERT INTO activity(message,kind,created_at) VALUES(?,?,?)",
                     (msg, kind, (base + timedelta(minutes=mins)).strftime("%Y-%m-%d %H:%M:%S")))
