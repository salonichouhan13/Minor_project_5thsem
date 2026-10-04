"""AttendIQ - Smart Attendance System (Flask + SQLite)."""
import csv
import io
import os
import secrets
import sqlite3
import time
from datetime import date, datetime, timedelta

from flask import (Flask, Response, abort, g, jsonify, redirect, render_template, request, send_file,
                   session, url_for)
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

from utils.db import SUBJECTS, connect, init
from utils.helpers import base_url, make_qr_png

app = Flask(__name__)
ROOT = os.path.dirname(os.path.abspath(__file__))


def load_secret():
    """SECRET_KEY env var wins; otherwise a random key is created once and kept in secret.key."""
    if os.environ.get("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    path = os.path.join(ROOT, "secret.key")
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write(secrets.token_hex(32))
    with open(path) as f:
        return f.read().strip()


app.config.update(
    SECRET_KEY=load_secret(),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("SECURE_COOKIES") == "1",  # set to 1 when served over HTTPS
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

PAGES = {
    "dashboard": ("Dashboard", "Your classroom at a glance", "layout-dashboard"),
    "qr": ("Generate QR", "Start an attendance session", "qr-code"),
    "students": ("Students", "Manage your class list", "users"),
    "attendance": ("Attendance", "Every record in one place", "clipboard-check"),
    "analytics": ("Analytics", "Trends and patterns", "trending-up"),
    "reports": ("Reports", "Download and share", "file-text"),
    "settings": ("Settings", "Tune the rules", "settings"),
}


# ---------------------------------------------------------------- helpers
def db():
    if "db" not in g:
        g.db = connect()
    return g.db


@app.teardown_appcontext
def close_db(_):
    conn = g.pop("db", None)
    if conn:
        conn.close()


def rows(sql, args=()):
    return [dict(r) for r in db().execute(sql, args).fetchall()]


def one(sql, args=()):
    r = db().execute(sql, args).fetchone()
    return dict(r) if r else None


def ts(d=None):
    return (d or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")


def today():
    return date.today().isoformat()


def log(message, kind="info"):
    db().execute("INSERT INTO activity(message,kind,created_at) VALUES(?,?,?)", (message, kind, ts()))
    db().commit()


def setting(key):
    return int(one("SELECT value FROM settings WHERE key=?", (key,))["value"])


def new_pin():
    return str(secrets.randbelow(9000) + 1000)  # 4 digits, never starts with 0 (safe in Excel)


def err(message, code=400, kind="error"):
    return jsonify(ok=False, message=message, kind=kind), code


def student_rows(where="", params=()):
    sql = f"""SELECT s.student_id, s.name, s.class AS cls, COUNT(a.id) total,
        COALESCE(SUM(a.status IN ('Present','Late')),0) att,
        COALESCE(SUM(a.status='Present'),0) present, COALESCE(SUM(a.status='Late'),0) late,
        COALESCE(SUM(a.status='Absent'),0) absent,
        (SELECT status FROM attendance WHERE student_id=s.student_id AND date=? ORDER BY id DESC LIMIT 1) today,
        (s.pin_hash IS NOT NULL) has_pin,
        EXISTS(SELECT 1 FROM devices d WHERE d.student_id=s.student_id) device_linked
        FROM students s LEFT JOIN attendance a ON a.student_id=s.student_id {where}
        GROUP BY s.id ORDER BY s.name"""
    out = rows(sql, (today(), *params))
    for r in out:
        r["pct"] = round(r["att"] * 100 / r["total"]) if r["total"] else 100
        r["today"] = r["today"] or "Absent"
    return out


def trend_rows(days):
    total = one("SELECT COUNT(*) c FROM students")["c"] or 1
    since = (date.today() - timedelta(days=days - 1)).isoformat()
    rs = rows("""SELECT date, COUNT(DISTINCT CASE WHEN status IN ('Present','Late') THEN student_id END) p
                 FROM attendance WHERE date>=? GROUP BY date ORDER BY date""", (since,))
    return [{"date": r["date"], "present": r["p"], "pct": round(r["p"] * 100 / total)} for r in rs]


def qr_state():
    s = one("SELECT * FROM qr_sessions ORDER BY id DESC LIMIT 1")
    if not s:
        return {"state": "none"}
    exp = datetime.fromisoformat(s["expires_at"])
    rem = int((exp - datetime.now()).total_seconds())
    if rem <= 0 and s["active"]:
        db().execute("UPDATE qr_sessions SET active=0 WHERE id=?", (s["id"],))
        db().commit()
        log(f"Attendance session expired for {s['subject']}", "qr")
        s["active"] = 0
    state = "active" if rem > 0 and s["active"] else "expired"
    att = rows("""SELECT a.student_id, a.time, a.status, st.name FROM attendance a
                  JOIN students st ON st.student_id=a.student_id
                  WHERE a.date=? AND a.subject=? AND a.time!='—' ORDER BY a.time DESC""",
               (s["created_at"][:10], s["subject"]))
    return {"state": state, "token": s["token"], "subject": s["subject"], "remaining": max(rem, 0),
            "total": int((exp - datetime.fromisoformat(s["created_at"])).total_seconds()),
            "url": f"{base_url(request)}/scan/{s['token']}", "attendees": att}


# ---------------------------------------------------------------- auth
PUBLIC = {"login", "setup", "logout", "scan_page", "scan_info", "api_scan", "static"}
FAILS = {}  # ip -> (failed attempts, locked_until). In-memory: fine for a single-process app.


def teacher_count():
    return one("SELECT COUNT(*) c FROM teachers")["c"]


@app.before_request
def guard():
    ep = request.endpoint
    if ep is None or ep in PUBLIC or session.get("user"):
        return
    if request.path.startswith("/api/"):
        return err("Your session has ended. Please sign in again.", 401, "auth")
    if teacher_count() == 0:
        return redirect(url_for("setup"))
    return redirect(url_for("login", next=request.path))


def start_session(username):
    session.clear()
    session["user"] = username
    session.permanent = True


@app.route("/login", methods=["GET", "POST"])
def login():
    if teacher_count() == 0:
        return redirect(url_for("setup"))
    error, nxt = None, request.values.get("next", "")
    if request.method == "POST":
        ip = request.remote_addr or "?"
        n, until = FAILS.get(ip, (0, 0))
        if n >= 5 and until <= time.time():
            n = 0
        if until > time.time():
            error = f"Too many attempts. Try again in {int((until - time.time()) // 60) + 1} minute(s)."
        else:
            t = one("SELECT * FROM teachers WHERE username=?", (request.form.get("username", "").strip().lower(),))
            if t and check_password_hash(t["password_hash"], request.form.get("password", "")):
                FAILS.pop(ip, None)
                start_session(t["username"])
                safe = nxt.startswith("/") and not nxt.startswith("//")
                return redirect(nxt if safe else url_for("page"))
            n += 1
            FAILS[ip] = (n, time.time() + 300 if n >= 5 else 0)
            error = "Wrong username or password." if n < 5 else "Too many attempts. Try again in 5 minutes."
    return render_template("auth.html", mode="login", error=error, next=nxt), (401 if error else 200)


@app.route("/setup", methods=["GET", "POST"])
def setup():
    """Create the first teacher account. Disabled as soon as one exists."""
    if teacher_count() > 0:
        return redirect(url_for("login"))
    error = None
    if request.method == "POST":
        u = request.form.get("username", "").strip().lower()
        p, p2 = request.form.get("password", ""), request.form.get("confirm", "")
        if len(u) < 3:
            error = "Username must be at least 3 characters."
        elif len(p) < 8:
            error = "Password must be at least 8 characters."
        elif p != p2:
            error = "The two passwords do not match."
        else:
            db().execute("INSERT INTO teachers(username,password_hash) VALUES(?,?)", (u, generate_password_hash(p)))
            db().commit()
            start_session(u)
            return redirect(url_for("page"))
    return render_template("auth.html", mode="setup", error=error, next=""), (400 if error else 200)


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.post("/api/password")
def change_password():
    d = request.get_json(silent=True) or {}
    t = one("SELECT * FROM teachers WHERE username=?", (session["user"],))
    if not t or not check_password_hash(t["password_hash"], d.get("current", "")):
        return err("Your current password is incorrect.")
    if len(d.get("new", "")) < 8:
        return err("New password must be at least 8 characters.")
    db().execute("UPDATE teachers SET password_hash=? WHERE id=?", (generate_password_hash(d["new"]), t["id"]))
    db().commit()
    return jsonify(ok=True)


# ---------------------------------------------------------------- pages
@app.route("/")
@app.route("/<page>")
def page(page="dashboard"):
    if page not in PAGES:
        abort(404)
    t, sub, _ = PAGES[page]
    return render_template(f"{page}.html", page=page, title=t, sub=sub, user=session.get("user", "T"),
                           nav=[(k, v[0], v[2]) for k, v in PAGES.items()],
                           today=datetime.now().strftime("%a, %d %b %Y"))


@app.route("/scan/<token>")
def scan_page(token):
    return render_template("scan.html", token=token)


# ---------------------------------------------------------------- stats / analytics
@app.get("/api/stats")
def api_stats():
    studs = student_rows()
    total = len(studs)
    present = sum(1 for s in studs if s["today"] in ("Present", "Late"))
    late = sum(1 for s in studs if s["today"] == "Late")
    low = setting("low_threshold")
    return jsonify(total=total, present=present, late=late, absent=total - present,
                   pct=round(present * 100 / total) if total else 0,
                   absent_list=[{"student_id": s["student_id"], "name": s["name"], "cls": s["cls"]}
                                for s in studs if s["today"] == "Absent"],
                   low_count=sum(1 for s in studs if s["pct"] < low),
                   qr=qr_state(), trend=trend_rows(30))


@app.get("/api/analytics")
def api_analytics():
    tr = trend_rows(30)
    by = {}
    for r in tr:
        by.setdefault(datetime.fromisoformat(r["date"]).weekday(), []).append(r["pct"])
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    weekly = [{"day": names[k], "pct": round(sum(v) / len(v))} for k, v in sorted(by.items())]
    since = (date.today() - timedelta(days=29)).isoformat()
    status = {r["status"]: r["c"] for r in rows(
        "SELECT status, COUNT(*) c FROM attendance WHERE date>=? GROUP BY status", (since,))}
    subjects = rows("""SELECT subject, ROUND(100.0*SUM(status IN ('Present','Late'))/COUNT(*)) pct
                       FROM attendance GROUP BY subject ORDER BY subject""")
    return jsonify(trend=tr, weekly=weekly, status=status, subjects=subjects)


@app.get("/api/activity")
def api_activity():
    return jsonify(rows("SELECT * FROM activity ORDER BY id DESC LIMIT 10"))


@app.get("/api/notifications")
def api_notifications():
    low = setting("low_threshold")
    out = [{"type": "low", "title": "Low attendance", "text": f"{s['name']} is at {s['pct']}%",
            "time": ""} for s in sorted(student_rows(), key=lambda x: x["pct"]) if s["pct"] < low][:3]
    for a in rows("SELECT * FROM activity WHERE kind IN ('warn','qr','system') ORDER BY id DESC LIMIT 6"):
        out.append({"type": a["kind"], "title": {"warn": "Security alert", "qr": "QR session",
                                                  "system": "System"}[a["kind"]],
                    "text": a["message"], "time": a["created_at"]})
    return jsonify(out)


# ---------------------------------------------------------------- students
@app.get("/api/students")
def api_students():
    where, params = [], []
    if request.args.get("q"):
        where.append("(s.name LIKE ? OR s.student_id LIKE ?)")
        params += [f"%{request.args['q']}%"] * 2
    if request.args.get("cls"):
        where.append("s.class=?")
        params.append(request.args["cls"])
    return jsonify(student_rows("WHERE " + " AND ".join(where) if where else "", params))


@app.post("/api/students")
def add_student():
    d = request.get_json(silent=True) or {}
    sid, name, cls = (d.get(k, "").strip() for k in ("student_id", "name", "cls"))
    if not (sid and name and cls):
        return err("Please fill in ID, name and class.")
    pin = new_pin()
    try:
        db().execute("INSERT INTO students(student_id,name,class,pin_hash) VALUES(?,?,?,?)",
                     (sid.upper(), name, cls, generate_password_hash(pin)))
        db().commit()
    except sqlite3.IntegrityError:
        return err("A student with this ID already exists.", 409)
    log(f"{name} was added to {cls}", "system")
    return jsonify(ok=True, pin=pin)


@app.post("/api/students/<sid>/reset-pin")
def reset_pin(sid):
    """New PIN (shown once) and the old phone link is removed."""
    if not one("SELECT 1 FROM students WHERE student_id=?", (sid,)):
        return err("Student not found.", 404)
    pin = new_pin()
    db().execute("UPDATE students SET pin_hash=? WHERE student_id=?", (generate_password_hash(pin), sid))
    db().execute("DELETE FROM devices WHERE student_id=?", (sid,))
    db().execute("DELETE FROM scan_fails WHERE student_id=?", (sid,))
    db().commit()
    return jsonify(ok=True, pin=pin)


@app.post("/api/students/<sid>/unlink-device")
def unlink_device(sid):
    db().execute("DELETE FROM devices WHERE student_id=?", (sid,))
    db().commit()
    return jsonify(ok=True)


@app.post("/api/pins/generate")
def generate_pins():
    """Creates PINs only for students who have none yet. PINs are stored hashed, so this is the only time they are visible."""
    out = []
    for s in rows("SELECT student_id, name, class AS cls FROM students WHERE pin_hash IS NULL ORDER BY name"):
        pin = new_pin()
        db().execute("UPDATE students SET pin_hash=? WHERE student_id=?", (generate_password_hash(pin), s["student_id"]))
        out.append({**s, "pin": pin})
    db().commit()
    return jsonify(ok=True, pins=out)


@app.put("/api/students/<sid>")
def edit_student(sid):
    d = request.get_json(silent=True) or {}
    name, cls = d.get("name", "").strip(), d.get("cls", "").strip()
    if not (name and cls):
        return err("Name and class cannot be empty.")
    db().execute("UPDATE students SET name=?, class=? WHERE student_id=?", (name, cls, sid))
    db().commit()
    return jsonify(ok=True)


@app.delete("/api/students/<sid>")
def delete_student(sid):
    db().execute("DELETE FROM students WHERE student_id=?", (sid,))
    db().commit()
    return jsonify(ok=True)


@app.get("/api/students/<sid>")
def student_detail(sid):
    s = next((x for x in student_rows("WHERE s.student_id=?", (sid,))), None)
    if not s:
        return err("Student not found.", 404)
    hist = rows("SELECT date,time,subject,status FROM attendance WHERE student_id=? ORDER BY date,id", (sid,))
    run, att, trend = 0, 0, []
    for h in hist:
        run += 1
        att += h["status"] != "Absent"
        trend.append({"date": h["date"], "pct": round(att * 100 / run)})
    return jsonify(student=s, trend=trend[-20:], history=hist[::-1][:10])


# ---------------------------------------------------------------- attendance
def attendance_query():
    a = request.args
    sql = """SELECT a.date,a.time,a.subject,a.status,a.student_id,s.name,s.class AS cls
             FROM attendance a JOIN students s ON s.student_id=a.student_id WHERE 1=1"""
    p = []
    if a.get("q"):
        sql += " AND (s.name LIKE ? OR a.student_id LIKE ?)"
        p += [f"%{a['q']}%"] * 2
    for key, col in (("date", "a.date"), ("subject", "a.subject"), ("sid", "a.student_id"), ("status", "a.status")):
        if a.get(key):
            sql += f" AND {col}=?"
            p.append(a[key])
    return sql + " ORDER BY a.date DESC, a.time DESC", p


@app.get("/api/attendance")
def api_attendance():
    sql, p = attendance_query()
    return jsonify(rows(sql + " LIMIT 400", p))


@app.get("/api/attendance/export.csv")
def export_csv():
    sql, p = attendance_query()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Student ID", "Name", "Class", "Date", "Time", "Subject", "Status"])
    for r in rows(sql, p):
        w.writerow([r["student_id"], r["name"], r["cls"], r["date"], r["time"], r["subject"], r["status"]])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=attendance_{today()}.csv"})


# ---------------------------------------------------------------- QR sessions
@app.get("/api/qr/current")
def qr_current():
    return jsonify(qr_state())


@app.post("/api/qr/generate")
def qr_generate():
    d = request.get_json(silent=True) or {}
    subject = d.get("subject", "").strip()
    try:
        minutes = int(d.get("minutes", 5))
    except (TypeError, ValueError):
        return err("Duration must be a number.")
    if subject not in SUBJECTS or not 1 <= minutes <= 60:
        return err("Pick a subject and a duration between 1 and 60 minutes.")
    now = datetime.now()
    db().execute("UPDATE qr_sessions SET active=0 WHERE active=1")
    db().execute("INSERT INTO qr_sessions(token,subject,created_at,expires_at) VALUES(?,?,?,?)",
                 (secrets.token_urlsafe(9), subject, ts(now), ts(now + timedelta(minutes=minutes))))
    db().commit()
    log(f"QR generated for {subject} class", "qr")
    return jsonify(ok=True)


@app.post("/api/qr/stop")
def qr_stop():
    db().execute("UPDATE qr_sessions SET active=0, expires_at=? WHERE active=1", (ts(),))
    db().commit()
    log("Attendance session ended by teacher", "qr")
    return jsonify(ok=True)


@app.get("/api/qr/<token>/image.png")
def qr_image(token):
    if not one("SELECT 1 FROM qr_sessions WHERE token=?", (token,)):
        abort(404)
    return send_file(make_qr_png(f"{base_url(request)}/scan/{token}"), mimetype="image/png")


@app.get("/api/scan/<token>/info")
def scan_info(token):
    s = one("SELECT * FROM qr_sessions WHERE token=?", (token,))
    if not s:
        return err("This QR code is not valid.", 404, "invalid")
    rem = int((datetime.fromisoformat(s["expires_at"]) - datetime.now()).total_seconds())
    return jsonify(ok=True, subject=s["subject"], remaining=max(rem, 0), active=bool(s["active"]) and rem > 0)


LOCK_MIN, MAX_STUDENT_FAILS, MAX_IP_FAILS = 10, 5, 15


def lock_minutes(sid, ip):
    """Minutes left if this student ID or this IP made too many wrong attempts recently, else 0."""
    since = ts(datetime.now() - timedelta(minutes=LOCK_MIN))
    for col, val, limit in (("student_id", sid, MAX_STUDENT_FAILS), ("ip", ip, MAX_IP_FAILS)):
        r = one(f"SELECT COUNT(*) c, MIN(created_at) m FROM scan_fails WHERE {col}=? AND created_at>=?", (val, since))
        if r["c"] >= limit:
            end = datetime.fromisoformat(r["m"]) + timedelta(minutes=LOCK_MIN)
            return max(1, int((end - datetime.now()).total_seconds() // 60) + 1)
    return 0


def record_fail(sid, ip):
    db().execute("INSERT INTO scan_fails(student_id,ip,created_at) VALUES(?,?,?)", (sid[:40], ip, ts()))
    db().commit()


@app.post("/api/scan")
def api_scan():
    """Server-side checks, in order: QR valid, QR not expired, attempt limit, student ID + PIN,
    phone link, duplicate. Only then is attendance saved."""
    d = request.get_json(silent=True) or {}
    token, sid = str(d.get("token", "")).strip(), str(d.get("student_id", "")).strip().upper()
    pin, dev = str(d.get("pin", "")).strip(), str(d.get("device_id", "")).strip()
    ip = request.remote_addr or "?"
    s = one("SELECT * FROM qr_sessions WHERE token=?", (token,))
    if not s:
        return err("This QR code is not valid.", 404, "invalid")
    now = datetime.now()
    if not s["active"] or datetime.fromisoformat(s["expires_at"]) <= now:
        return err("This QR code has expired.", 410, "expired")
    if len(dev) < 16:
        return err("Your browser could not be identified. Reload this page and try again.", 400, "device")
    db().execute("DELETE FROM scan_fails WHERE created_at < ?", (ts(now - timedelta(days=1)),))
    wait = lock_minutes(sid, ip)
    if wait:
        return err(f"Too many wrong attempts. Try again in about {wait} minute(s).", 429, "locked")

    st = one("SELECT * FROM students WHERE student_id=?", (sid,))
    if not st:  # same message as a wrong PIN, so IDs cannot be tested one by one
        record_fail(sid, ip)
        return err("Student ID or PIN is incorrect.", 401, "auth")
    if not st["pin_hash"]:
        return err("Your PIN has not been created yet. Ask your teacher.", 403, "nopin")
    if not check_password_hash(st["pin_hash"], pin):
        record_fail(sid, ip)
        if lock_minutes(sid, ip):
            log(f"Too many wrong PIN attempts for {st['name']}", "warn")
            return err(f"Too many wrong attempts. Try again in about {LOCK_MIN} minutes.", 429, "locked")
        return err("Student ID or PIN is incorrect.", 401, "auth")

    bound = one("SELECT device_id FROM devices WHERE student_id=?", (sid,))
    if bound and bound["device_id"] != dev:
        log(f"Blocked: {st['name']}'s account was used from a different phone", "warn")
        return err("This account is linked to a different phone. Ask your teacher to unlink it.", 403, "device")
    if not bound:
        other = one("SELECT st.name FROM devices d JOIN students st ON st.student_id=d.student_id WHERE d.device_id=?", (dev,))
        if other:
            log(f"Blocked: {other['name']}'s phone was used to mark {st['name']}", "warn")
            return err("This phone is already linked to another student.", 403, "device")
    if one("SELECT 1 FROM attendance WHERE student_id=? AND date=? AND subject=?", (sid, today(), s["subject"])):
        log(f"Duplicate attempt by {st['name']} for {s['subject']}", "warn")
        return err("Your attendance is already marked for this class.", 409, "duplicate")

    late = (now - datetime.fromisoformat(s["created_at"])).total_seconds() > setting("late_after") * 60
    status = "Late" if late else "Present"
    try:
        db().execute("INSERT INTO attendance(student_id,date,time,subject,status) VALUES(?,?,?,?,?)",
                     (sid, today(), now.strftime("%H:%M:%S"), s["subject"], status))
        if not bound:  # first successful scan links this phone to the student
            db().execute("INSERT INTO devices(student_id,device_id,created_at) VALUES(?,?,?)", (sid, dev, ts(now)))
        db().commit()
    except sqlite3.IntegrityError:  # two taps at the same instant
        db().rollback()
        return err("This attendance could not be saved. If you already scanned, you are all set.", 409, "duplicate")
    db().execute("DELETE FROM scan_fails WHERE student_id=?", (sid,))
    db().commit()
    log(f"{st['name']} marked attendance" + (" (late)" if late else ""), "success")
    return jsonify(ok=True, name=st["name"], status=status, subject=s["subject"],
                   message="Attendance marked successfully")


# ---------------------------------------------------------------- settings
@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    if request.method == "POST":
        d = request.get_json(silent=True) or {}
        for k in ("late_after", "low_threshold", "default_minutes"):
            try:
                v = int(d[k])
            except (KeyError, TypeError, ValueError):
                return err("Please enter whole numbers only.")
            if not 1 <= v <= 100:
                return err("Values must be between 1 and 100.")
            db().execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (k, str(v)))
        db().commit()
        return jsonify(ok=True)
    return jsonify({r["key"]: int(r["value"]) for r in rows("SELECT * FROM settings")} | {"subjects": SUBJECTS})


@app.errorhandler(404)
def not_found(_):
    if request.path.startswith("/api/"):
        return err("Not found.", 404)
    return render_template("scan.html", token="", notfound=True), 404


init()  # runs on import too, so gunicorn / PythonAnywhere also get a database
if os.environ.get("ADMIN_USER") and os.environ.get("ADMIN_PASSWORD"):  # optional: skip the /setup page
    _c = connect()
    if _c.execute("SELECT COUNT(*) FROM teachers").fetchone()[0] == 0:
        _c.execute("INSERT INTO teachers(username,password_hash) VALUES(?,?)",
                   (os.environ["ADMIN_USER"].lower(), generate_password_hash(os.environ["ADMIN_PASSWORD"])))
        _c.commit()
    _c.close()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=os.environ.get("FLASK_DEBUG") == "1")
