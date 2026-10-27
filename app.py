"""CampusHub - Smart Campus Facility, Booking & Inventory Management System.

A thin Flask layer over the MySQL database. Every business rule (no double
booking, stock limits, maintenance blocking, valid times, valid references) is
enforced by MySQL constraints, triggers and stored procedures. The app collects
input, calls the database, and shows either the result or the database's own
explanation of why it refused.
"""
import csv
import io
import os
import secrets
import sys
from datetime import date, datetime, timedelta

from flask import (Flask, Response, abort, flash, g, jsonify, redirect, render_template, request,
                   url_for)
from werkzeug.security import check_password_hash

import auth as A
import charts
import db
import queries as Q
import ui
from dberrors import explain

app = Flask(__name__)
_secret = os.getenv("SECRET_KEY", "")
if not _secret or _secret in ("change-me", "campushub-dev-key-change-me") or len(_secret) < 16:
    # Without a fixed key every restart signs everyone out - set SECRET_KEY in .env (see README).
    _secret = secrets.token_hex(32)
    print("WARNING: SECRET_KEY is not set in .env - using a temporary key; sessions end when the app restarts.",
          file=sys.stderr)
app.config.update(
    SECRET_KEY=_secret,
    SESSION_COOKIE_HTTPONLY=True,                     # JavaScript can't read the session cookie
    SESSION_COOKIE_SAMESITE="Lax",                    # not sent on cross-site POSTs
    SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE") == "1",   # set to 1 when served over HTTPS
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
)
ui.register(app)

PER_PAGE = 12
BOOTSTRAP_CDN = "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css"
LOCAL_BOOTSTRAP = os.path.join(app.static_folder, "vendor", "bootstrap.min.css")
OPEN_MINUTES = 12 * 60          # facilities are open 08:00-20:00 for utilization %
TIMELINE_START, TIMELINE_END = 7 * 60, 21 * 60


# ---------------------------------------------------------------- helpers
def today():
    return date.today()


def arg_int(name, default=None, source=None):
    raw = (source or request.args).get(name, "")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def arg_date(name, default=None):
    raw = request.args.get(name, "")
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return default


def form_int(name):
    return arg_int(name, None, request.form)


def safe_next(default):
    """Only same-site paths are accepted as redirect targets (no open redirects)."""
    nxt = request.form.get("next") or request.args.get("next") or ""
    if nxt.startswith("/") and not nxt.startswith("//") and "\\" not in nxt and not nxt.startswith("/login"):
        return nxt
    return default


def flash_db_error(err):
    info = explain(err)
    flash({"title": "Rejected by MySQL", "text": info["message"], "source": info["source"]}, "danger")


def flash_ok(text, title="Done"):
    flash({"title": title, "text": text}, "success")


def person_from_form():
    if request.form.get("user_type") == "faculty":
        return None, form_int("faculty_id")
    return form_int("student_id"), None


# ---------------------------------------------------------------- login & access control
# Deny by default: endpoints listed here are open to students and faculty (with record-level
# checks inside the views). Everything else is for administrators only.
PUBLIC_ENDPOINTS = {"login", "static"}
SELF_SERVICE = {"dashboard", "logout", "change_password", "availability", "api_facility_day", "facilities",
                "facility_detail", "bookings", "new_booking", "booking_detail", "cancel_booking", "my_loans"}
FACULTY_EXTRA = {"report_fault"}


@app.before_request
def guard():
    endpoint = request.endpoint
    if endpoint is None or endpoint == "static":
        return None
    A.load_current_user()
    if request.method == "POST":
        A.check_csrf()
    if endpoint in PUBLIC_ENDPOINTS:
        return None
    if g.user is None:
        nxt = request.full_path.rstrip("?") if request.method == "GET" else None
        return redirect(url_for("login", next=nxt))
    if g.user["must_change_password"] and endpoint not in ("change_password", "logout"):
        return redirect(url_for("change_password"))
    role = g.user["role"]
    if role == "ADMIN" or endpoint in SELF_SERVICE or (role == "FACULTY" and endpoint in FACULTY_EXTRA):
        return None
    abort(403)


@app.after_request
def security_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    if getattr(g, "user", None):
        resp.headers.setdefault("Cache-Control", "no-store")     # signed-in pages are not cached
    return resp


def mask_others(rows):
    """Students and faculty see other people's bookings only as 'Booked' (no names, no links)."""
    if A.is_admin():
        return rows
    out = []
    for r in rows:
        r = dict(r)
        if not A.owns(r):
            r.update(booked_by="Booked", purpose="Booked", hidden=True)
        out.append(r)
    return out


@app.context_processor
def inject_globals():
    alert_total = None
    try:
        if A.is_admin():
            alert_total = db.scalar("""
                SELECT (SELECT COUNT(*) FROM equipment_issue WHERE status = 'ISSUED' AND due_date < %s)
                     + (SELECT COUNT(*) FROM equipment e WHERE e.available_qty = 0 OR e.available_qty * 4 <= e.quantity)
                     + (SELECT COUNT(*) FROM maintenance WHERE status <> 'COMPLETED')""", (today(),))
    except Exception:          # the error page must render even when MySQL is down
        pass
    # Use a local copy of Bootstrap when present (works offline), otherwise the CDN
    bootstrap_css = (url_for("static", filename="vendor/bootstrap.min.css")
                     if os.path.exists(LOCAL_BOOTSTRAP) else BOOTSTRAP_CDN)
    user = getattr(g, "user", None)
    return {"today": today(), "alert_total": alert_total, "bootstrap_css": bootstrap_css,
            "current_user": user, "is_admin": bool(user and user["role"] == "ADMIN"),
            "role_label": A.ROLE_LABELS.get(user["role"]) if user else None, "csrf_field": A.csrf_field}


@app.errorhandler(db.Error)
def database_error(err):
    info = explain(err)
    return render_template("error.html", info=info), 503


@app.errorhandler(404)
def not_found(_err):
    return render_template("error.html", info={"message": "That page or record does not exist.",
                                               "source": "Not found", "code": 404}), 404


@app.errorhandler(403)
def forbidden(_err):
    return render_template("error.html", info={"message": "Your account does not have access to this page.",
                                               "source": "Access denied", "code": 403}), 403


@app.errorhandler(400)
def bad_request(err):
    msg = ("This form has expired or was not sent from CampusHub. Go back, reload the page and try again."
           if getattr(err, "description", "") == "csrf" else "The request could not be understood.")
    return render_template("error.html", info={"message": msg, "source": "Request rejected", "code": 400}), 400


# ---------------------------------------------------------------- sign in / out
@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("dashboard"))
    setup = None
    try:
        if Q.account_count() == 0:
            setup = "no_accounts"
    except db.Error as e:
        if getattr(e, "errno", None) != 1146:          # 1146 = table doesn't exist (migration 07 not run)
            raise
        setup = "no_table"
    role = request.form.get("role") or request.args.get("role") or "STUDENT"
    role = role if role in A.ROLES else "STUDENT"
    error, status = None, 200
    if request.method == "POST" and setup != "no_table":
        acc, error = A.authenticate(role, request.form.get("login", ""), request.form.get("password", ""))
        if acc:
            A.start_session(acc)
            if acc["must_change_password"]:
                flash({"title": "Choose a new password", "text": "You signed in with a temporary password. "
                       "Please set your own password to continue."}, "warning")
                return redirect(url_for("change_password"))
            return redirect(safe_next(url_for("dashboard")))
        status = 401
    return render_template("login.html", setup=setup, role=role, error=error,
                           login_value=request.form.get("login", ""), nxt=safe_next("")), status


@app.post("/logout")
def logout():
    A.end_session()
    flash({"title": "Signed out", "text": "You have been signed out of CampusHub."}, "success")
    return redirect(url_for("login"))


@app.route("/account/password", methods=["GET", "POST"])
def change_password():
    errors = []
    if request.method == "POST":
        f = request.form
        current, new, confirm = f.get("current", ""), f.get("new", ""), f.get("confirm", "")
        acc = Q.get_account(g.user["account_id"])
        if not check_password_hash(acc["password_hash"], current):
            errors.append("Your current password is not correct.")
        elif new != confirm:
            errors.append("The two new passwords do not match.")
        elif new == current:
            errors.append("The new password must be different from the current one.")
        else:
            problems = A.password_problems(new)
            if problems:
                errors.append("The new password needs " + " and ".join(problems) + ".")
        if not errors:
            new_hash = A.hash_password(new)
            Q.set_password(g.user["account_id"], new_hash, False, datetime.now())
            A.refresh_fingerprint(new_hash)
            flash_ok("Your password was changed. Other signed-in sessions of this account were signed out.",
                     "Password changed")
            return redirect(url_for("dashboard"))
    return render_template("change_password.html", errors=errors, min_length=A.MIN_LENGTH), (400 if errors else 200)


# ---------------------------------------------------------------- dashboard
@app.route("/")
def dashboard():
    t = today()
    if not A.is_admin():
        owner = A.owner()
        return render_template("home.html", k=Q.my_home(owner, t),
                               upcoming=Q.list_bookings("upcoming", {}, "", 1, 6, t, owner=owner).items,
                               loans=Q.list_issues("current", "", 1, 6, t, owner=owner).items)
    kpis = Q.dashboard_kpis(t)

    week0 = t - timedelta(days=t.weekday())
    start, end = week0 - timedelta(weeks=7), week0 + timedelta(weeks=2, days=6)
    weeks = [start + timedelta(weeks=i) for i in range(10)]
    buckets = {s: [0] * 10 for s in ("COMPLETED", "CONFIRMED", "CANCELLED")}
    for r in Q.booking_activity(start, end):
        idx = (ui.as_date(r["booking_date"]) - start).days // 7
        buckets[r["status"]][idx] += int(r["n"])
    activity = charts.stacked_columns(
        [w.strftime("%d %b") for w in weeks],
        [{"name": "Completed", "cls": "c-completed", "values": buckets["COMPLETED"]},
         {"name": "Confirmed", "cls": "c-confirmed", "values": buckets["CONFIRMED"]},
         {"name": "Cancelled", "cls": "c-cancelled", "values": buckets["CANCELLED"]}],
        highlight_index=7, aria="Bookings per week")

    dist_rows = {r["status"]: int(r["n"]) for r in Q.status_distribution(t - timedelta(days=90), t + timedelta(days=30))}
    distribution = [{"label": "Confirmed", "value": dist_rows.get("CONFIRMED", 0), "cls": "c-confirmed"},
                    {"label": "Completed", "value": dist_rows.get("COMPLETED", 0), "cls": "c-completed"},
                    {"label": "Cancelled", "value": dist_rows.get("CANCELLED", 0), "cls": "c-cancelled"}]
    donut = charts.donut(distribution, center_label="bookings")

    util = Q.utilization(t - timedelta(days=29), t, limit=7)
    busiest = max([float(r["hours"]) for r in util] + [1e-9])
    for r in util:
        r["pct"] = min(100.0, float(r["hours"]) * 60 / (30 * OPEN_MINUTES) * 100)   # true utilization (label)
        r["bar"] = float(r["hours"]) / busiest * 100                                # bar length relative to busiest

    return render_template(
        "dashboard.html", k=kpis, activity=activity, donut=donut, distribution=distribution,
        util=util, stock=Q.stock_overview(6), recent=Q.recent_bookings(6), maint=Q.recent_maintenance(5),
        low=Q.low_stock_items()[:3], overdue=Q.overdue_issues(t, 3), conflicts=Q.booking_conflicts(t)[:2])


# ---------------------------------------------------------------- facilities
@app.route("/facilities", methods=["GET", "POST"])
def facilities():
    if request.method == "POST":
        A.require_admin()
        f = request.form
        try:
            Q.add_facility(f.get("facility_name", "").strip(), form_int("facility_type_id"), form_int("admin_id"),
                           f.get("building", "").strip(), form_int("capacity"))
            flash_ok(f"Facility '{f.get('facility_name')}' was added.")
        except db.Error as e:
            flash_db_error(e)
        return redirect(url_for("facilities"))

    filters = {"q": request.args.get("q", ""), "type": arg_int("type"), "building": request.args.get("building", ""),
               "min_cap": arg_int("min_cap"), "status": request.args.get("status", "")}
    if filters["status"] not in ("", "AVAILABLE", "UNDER_MAINTENANCE", "INACTIVE"):
        filters["status"] = ""
    page = Q.list_facilities(filters, request.args.get("sort", "name"), arg_int("page", 1), PER_PAGE, today())
    return render_template("facilities.html", page=page, filters=filters, sort=request.args.get("sort", "name"),
                           types=Q.facility_types(), buildings=Q.buildings(), admins=Q.admins(),
                           counts=Q.facility_status_counts())


@app.route("/facilities/<int:facility_id>")
def facility_detail(facility_id):
    fac = Q.get_facility(facility_id)
    if not fac:
        abort(404)
    t = today()
    days = [t + timedelta(days=i) for i in range(7)]
    week = mask_others(Q.facility_bookings(facility_id, days[0], days[-1], include_cancelled=False))
    rows = []
    for d in days:
        items = [b for b in week if ui.as_date(b["booking_date"]) == d]
        rows.append({"label": d.strftime("%a %d %b"), "date": d, "items": _blocks(items)})
    stats = Q.facility_stats(facility_id, t)
    return render_template("facility_detail.html", f=fac, stats=stats, timeline=rows,
                           equipment=Q.facility_equipment(facility_id),
                           upcoming=mask_others([b for b in Q.facility_bookings(facility_id, t, t + timedelta(days=60))
                                                 if b["status"] == "CONFIRMED"][:8]),
                           maintenance=Q.facility_maintenance(facility_id))


@app.post("/facilities/<int:facility_id>/status")
def facility_status(facility_id):
    active = request.form.get("active") == "1"
    try:
        n = Q.set_facility_active(facility_id, active)
        if n:
            flash_ok("Facility reactivated." if active else "Facility deactivated - it can no longer be booked.")
        else:
            flash({"title": "Nothing changed", "text": "Only available facilities can be deactivated and only "
                   "inactive ones reactivated. Maintenance status is managed by the maintenance module."}, "warning")
    except db.Error as e:
        flash_db_error(e)
    return redirect(url_for("facility_detail", facility_id=facility_id))


# ---------------------------------------------------------------- availability
def _blocks(bookings):
    out = []
    span = TIMELINE_END - TIMELINE_START
    for b in bookings:
        s, e = ui.to_minutes(b["start_time"]), ui.to_minutes(b["end_time"])
        s2, e2 = max(s, TIMELINE_START), min(e, TIMELINE_END)
        if e2 <= s2:
            continue
        out.append({**b, "left": (s2 - TIMELINE_START) / span * 100, "width": (e2 - s2) / span * 100})
    return out


@app.route("/availability")
def availability():
    t = today()
    on = arg_date("date", t)
    start, end = request.args.get("start", ""), request.args.get("end", "")
    type_id, min_cap, building = arg_int("type"), arg_int("min_cap"), request.args.get("building", "")
    results = None
    if start and end:
        results = Q.free_facilities(on, start, end, type_id, min_cap)
    facs, bookings = Q.day_schedule(on, type_id, building)
    bookings = mask_others(bookings)
    rows = []
    for f in facs:
        if min_cap and f["capacity"] < min_cap:
            continue
        rows.append({**f, "items": _blocks([b for b in bookings if b["facility_id"] == f["facility_id"]])})
    now_pct = None
    if on == t:
        now = datetime.now()
        minute = now.hour * 60 + now.minute
        if TIMELINE_START <= minute <= TIMELINE_END:
            now_pct = (minute - TIMELINE_START) / (TIMELINE_END - TIMELINE_START) * 100
    return render_template("availability.html", on=on, start=start, end=end, type_id=type_id, min_cap=min_cap,
                           building=building, results=results, rows=rows, types=Q.facility_types(),
                           buildings=Q.buildings(), hours=range(TIMELINE_START // 60, TIMELINE_END // 60),
                           prev_day=on - timedelta(days=1), next_day=on + timedelta(days=1), now_pct=now_pct)


@app.get("/api/facilities/<int:facility_id>/day")
def api_facility_day(facility_id):
    on = arg_date("date")
    fac = Q.get_facility(facility_id)
    if not fac or not on:
        return jsonify({"error": "unknown facility or date"}), 404
    items = [{"ref": "" if b.get("hidden") else ui.ref(b["booking_id"]), "start": ui.hm(b["start_time"]), "end": ui.hm(b["end_time"]),
              "status": b["status"], "purpose": b["purpose"], "booked_by": b["booked_by"]}
             for b in mask_others(Q.bookings_on(facility_id, on))]
    return jsonify({"facility": fac["facility_name"], "status": fac["status"], "capacity": fac["capacity"],
                    "date": on.isoformat(), "bookings": items})


# ---------------------------------------------------------------- bookings
@app.route("/bookings")
def bookings():
    t = today()
    view = request.args.get("view", "upcoming")
    if view not in Q.BOOKING_VIEWS:
        view = "upcoming"
    filters = {"q": request.args.get("q", ""), "type": arg_int("type"), "facility": arg_int("facility"),
               "date_from": arg_date("date_from"), "date_to": arg_date("date_to")}
    owner = A.owner()                                   # None for admins = everyone's bookings
    page = Q.list_bookings(view, filters, request.args.get("sort", ""), arg_int("page", 1), PER_PAGE, t, owner=owner)
    return render_template("bookings.html", page=page, view=view, filters=filters,
                           counts=Q.booking_view_counts(t, owner),
                           types=Q.facility_types(), sort=request.args.get("sort", ""))


@app.route("/bookings/new", methods=["GET", "POST"])
def new_booking():
    if request.method == "POST":
        f = request.form
        # students and faculty always book for themselves; only admins choose the person
        student_id, faculty_id = person_from_form() if A.is_admin() else A.owner()
        missing = [label for key, label in (("facility_id", "facility"), ("date", "date"), ("start", "start time"),
                                            ("end", "end time")) if not f.get(key)]
        if missing or not (student_id or faculty_id):
            flash({"title": "Missing details", "text": "Please choose " + ", ".join(missing or ["who is booking"]) + "."},
                  "warning")
            return redirect(safe_next(url_for("new_booking", **{k: f.get(k, "") for k in ("facility_id", "date", "start", "end")})))
        try:
            booking_id = Q.create_booking(form_int("facility_id"), student_id, faculty_id, f["date"], f["start"],
                                          f["end"], f.get("purpose", "").strip()[:200])
            flash_ok(f"Booking {ui.ref(booking_id)} is confirmed.", "Booking confirmed")
            return redirect(safe_next(url_for("booking_detail", booking_id=booking_id)))
        except db.Error as e:
            flash_db_error(e)
            return redirect(safe_next(url_for("new_booking", **{k: f.get(k, "") for k in
                                                               ("facility_id", "date", "start", "end")})))

    students, faculty = Q.people() if A.is_admin() else ([], [])
    pre = {"facility_id": arg_int("facility_id"), "date": request.args.get("date") or (today() + timedelta(days=1)).isoformat(),
           "start": request.args.get("start", ""), "end": request.args.get("end", "")}
    return render_template("booking_form.html", facilities=Q.facility_options(), students=students,
                           faculty=faculty, pre=pre)


@app.route("/bookings/<int:booking_id>")
def booking_detail(booking_id):
    b = Q.get_booking(booking_id)
    if not b or not A.owns(b):            # 404, not 403: don't reveal that someone else's booking exists
        abort(404)
    same_day = mask_others([x for x in Q.bookings_on(b["facility_id"], ui.as_date(b["booking_date"]))
                            if x["booking_id"] != booking_id])
    return render_template("booking_detail.html", b=b, same_day=same_day)


@app.post("/bookings/<int:booking_id>/cancel")
def cancel_booking(booking_id):
    b = Q.get_booking(booking_id)
    if not b or not A.owns(b):
        abort(404)
    try:
        if Q.cancel_booking(booking_id):
            flash_ok(f"Booking {ui.ref(booking_id)} was cancelled. The slot is free again.", "Booking cancelled")
        else:
            flash({"title": "Nothing changed", "text": "Only confirmed bookings can be cancelled."}, "warning")
    except db.Error as e:
        flash_db_error(e)
    return redirect(safe_next(url_for("booking_detail", booking_id=booking_id)))


@app.post("/bookings/<int:booking_id>/complete")
def complete_booking(booking_id):
    try:
        if Q.complete_booking(booking_id, today()):
            flash_ok(f"Booking {ui.ref(booking_id)} marked as completed.")
        else:
            flash({"title": "Nothing changed", "text": "Only confirmed bookings dated today or earlier can be "
                   "marked as completed."}, "warning")
    except db.Error as e:
        flash_db_error(e)
    return redirect(safe_next(url_for("booking_detail", booking_id=booking_id)))


@app.post("/bookings/complete-past")
def complete_past_bookings():
    try:
        n = Q.complete_past_bookings(today())
        flash_ok(f"{n} past confirmed booking{'s' if n != 1 else ''} marked as completed.")
    except db.Error as e:
        flash_db_error(e)
    return redirect(url_for("bookings", view="completed"))


# ---------------------------------------------------------------- inventory
@app.route("/equipment", methods=["GET", "POST"])
def equipment():
    if request.method == "POST":
        student_id, faculty_id = person_from_form()
        days = max(1, min(60, form_int("days") or 7))
        if not form_int("equipment_id") or not (student_id or faculty_id):
            flash({"title": "Missing details", "text": "Choose an item and who it is issued to."}, "warning")
            return redirect(safe_next(url_for("equipment")))
        try:
            issue_id = Q.issue_equipment(form_int("equipment_id"), student_id, faculty_id, days)
            flash_ok(f"Item issued (issue #{issue_id}), due back in {days} day{'s' if days != 1 else ''}. "
                     "Stock was lowered by trigger T2.", "Equipment issued")
        except db.Error as e:
            flash_db_error(e)
        return redirect(safe_next(url_for("equipment")))

    filters = {"q": request.args.get("q", ""), "facility": arg_int("facility"), "stock": request.args.get("stock", "")}
    page = Q.list_equipment(filters, request.args.get("sort", "name"), arg_int("page", 1), PER_PAGE)
    students, faculty = Q.people()
    return render_template("equipment.html", page=page, filters=filters, sort=request.args.get("sort", "name"),
                           k=Q.inventory_kpis(today()), options=Q.equipment_options(), students=students,
                           faculty=faculty, facilities=Q.facility_options(), overdue=Q.overdue_issues(today(), 5),
                           preselect=arg_int("issue"))


@app.route("/equipment/issues")
def issues():
    t = today()
    view = request.args.get("view", "current")
    if view not in Q.ISSUE_VIEWS:
        view = "current"
    page = Q.list_issues(view, request.args.get("q", ""), arg_int("page", 1), PER_PAGE, t)
    return render_template("issues.html", page=page, view=view, q=request.args.get("q", ""),
                           counts=Q.issue_view_counts(t))


@app.post("/issues/<int:issue_id>/return")
def return_equipment(issue_id):
    try:
        Q.return_equipment(issue_id)
        flash_ok(f"Issue #{issue_id} returned. Trigger T3 restored the stock.", "Equipment returned")
    except db.Error as e:
        flash_db_error(e)
    return redirect(safe_next(url_for("issues")))


# ---------------------------------------------------------------- maintenance
@app.route("/maintenance", methods=["GET", "POST"])
def maintenance():
    if request.method == "POST":
        desc = request.form.get("description", "").strip()
        if not desc or not form_int("facility_id") or not form_int("admin_id"):
            flash({"title": "Missing details", "text": "Choose a facility, an administrator and describe the fault."},
                  "warning")
            return redirect(url_for("maintenance"))
        try:
            mid = Q.record_maintenance(form_int("facility_id"), form_int("admin_id"), desc[:255])
            flash_ok(f"Request #{mid} logged. Trigger T4 marked the facility as under maintenance, so it "
                     "cannot be booked until the request is completed.", "Maintenance logged")
        except db.Error as e:
            flash_db_error(e)
        return redirect(url_for("maintenance"))

    t = today()
    view = request.args.get("view", "open")
    if view not in Q.MAINT_VIEWS:
        view = "open"
    page = Q.list_maintenance(view, arg_int("facility"), request.args.get("q", ""), arg_int("page", 1), PER_PAGE, t)
    return render_template("maintenance.html", page=page, view=view, k=Q.maintenance_kpis(t),
                           facilities=Q.facility_options(), admins=Q.admins(),
                           closed=Q.facilities_under_maintenance(), facility_filter=arg_int("facility"),
                           q=request.args.get("q", ""), preselect=arg_int("report"))


@app.post("/maintenance/<int:mid>/start")
def start_maintenance(mid):
    try:
        if Q.start_maintenance(mid):
            flash_ok(f"Request #{mid} is now in progress.")
        else:
            flash({"title": "Nothing changed", "text": "Only newly reported requests can be started."}, "warning")
    except db.Error as e:
        flash_db_error(e)
    return redirect(safe_next(url_for("maintenance")))


@app.post("/maintenance/<int:mid>/complete")
def complete_maintenance(mid):
    try:
        if Q.complete_maintenance(mid, today()):
            flash_ok(f"Request #{mid} completed. If it was the facility's last open request, trigger T5 made the "
                     "facility available again.", "Maintenance completed")
        else:
            flash({"title": "Nothing changed", "text": "That request is already completed."}, "warning")
    except db.Error as e:
        flash_db_error(e)
    return redirect(safe_next(url_for("maintenance")))


# ---------------------------------------------------------------- people
@app.route("/students", methods=["GET", "POST"])
def students():
    if request.method == "POST":
        f = request.form
        try:
            Q.add_student(f.get("registration_no", "").strip(), f.get("name", "").strip(),
                          f.get("email", "").strip(), f.get("phone", "").strip() or None, form_int("department_id"))
            flash_ok(f"Student {f.get('registration_no')} added.")
        except db.Error as e:
            flash_db_error(e)
        return redirect(url_for("students"))
    tab = request.args.get("tab", "students")
    q, dept = request.args.get("q", ""), arg_int("dept")
    page = Q.list_students(q, dept, arg_int("page", 1), 15) if tab == "students" else None
    staff = Q.list_faculty(q, dept) if tab == "faculty" else None
    return render_template("people.html", tab=tab, q=q, dept=dept, page=page, staff=staff,
                           depts=Q.departments())


# ---------------------------------------------------------------- reports
def report_filters():
    t = today()
    f = {"date_from": arg_date("date_from", t - timedelta(days=90)), "date_to": arg_date("date_to", t + timedelta(days=30)),
         "dept": arg_int("dept"), "type": arg_int("type"), "status": request.args.get("status", ""),
         "min_cap": arg_int("min_cap", 100)}
    if f["status"] not in ("", "CONFIRMED", "COMPLETED", "CANCELLED"):
        f["status"] = ""
    if f["date_to"] < f["date_from"]:
        f["date_from"], f["date_to"] = f["date_to"], f["date_from"]
    return f


@app.route("/reports")
def reports():
    f = report_filters()
    monthly = Q.report_monthly(f)
    month_chart = charts.stacked_columns(
        [date.fromisoformat(m["month"] + "-01").strftime("%b %Y") for m in monthly],
        [{"name": "Completed", "cls": "c-completed", "values": [m["completed"] for m in monthly]},
         {"name": "Confirmed", "cls": "c-confirmed", "values": [m["confirmed"] for m in monthly]},
         {"name": "Cancelled", "cls": "c-cancelled", "values": [m["cancelled"] for m in monthly]}],
        height=220, aria="Bookings per month")
    split = {r["status"]: int(r["n"]) for r in Q.report_status_split(f)}
    split_segments = [{"label": "Confirmed", "value": split.get("CONFIRMED", 0), "cls": "c-confirmed"},
                      {"label": "Completed", "value": split.get("COMPLETED", 0), "cls": "c-completed"},
                      {"label": "Cancelled", "value": split.get("CANCELLED", 0), "cls": "c-cancelled"}]
    days = (f["date_to"] - f["date_from"]).days + 1
    util = Q.report_utilization(f)
    busiest = max([float(r["hours"]) for r in util] + [1e-9])
    for r in util:
        r["pct"] = min(100.0, float(r["hours"]) * 60 / (days * OPEN_MINUTES) * 100)
        r["bar"] = float(r["hours"]) / busiest * 100
    depts = Q.report_by_department(f)
    return render_template(
        "reports.html", f=f, days=days, summary=Q.report_summary(f), monthly=monthly, month_chart=month_chart,
        split=split_segments, split_chart=charts.donut(split_segments, center_label="bookings"),
        top=Q.report_top_facilities(f), util=util, depts=depts,
        dept_max=max([int(d["bookings"]) for d in depts] + [1]),
        equipment=Q.report_equipment(), issues=Q.report_current_issues(), overdue=Q.overdue_issues(today()),
        repeat=Q.report_repeat_maintenance(f), history=Q.report_maintenance_history(f)[:15],
        large=Q.report_large_facilities(f["min_cap"], f["type"]),
        all_depts=Q.departments(), types=Q.facility_types())


EXPORTS = {
    "monthly": ("Month,Total,Confirmed,Completed,Cancelled", lambda f: [
        (r["month"], r["total"], r["confirmed"], r["completed"], r["cancelled"]) for r in Q.report_monthly(f)]),
    "top-facilities": ("Facility,Type,Building,Bookings,Hours booked", lambda f: [
        (r["facility_name"], r["type_name"], r["building"], r["bookings"], round(float(r["hours"]), 1))
        for r in Q.report_top_facilities(f, 100)]),
    "utilization": ("Facility,Type,Bookings,Hours booked", lambda f: [
        (r["facility_name"], r["type_name"], r["bookings"], round(float(r["hours"]), 1))
        for r in Q.report_utilization(f, 200)]),
    "departments": ("Department,Bookings,Cancelled", lambda f: [
        (r["department_name"], r["bookings"], r["cancelled"]) for r in Q.report_by_department(f)]),
    "status-split": ("Status,Bookings", lambda f: [(r["status"], r["n"]) for r in Q.report_status_split(f)]),
    "equipment": ("Equipment,Facility,Total,Available,Issued,Status", lambda f: [
        (r["equipment_name"], r["facility_name"], r["quantity"], r["available_qty"], r["issued_qty"],
         r["availability_status"]) for r in Q.report_equipment()]),
    "current-issues": ("Issue,Equipment,Issued to,Type,Issued on,Due,Due status", lambda f: [
        (r["issue_id"], r["equipment_name"], r["issued_to"], r["user_type"], ui.fmt_date(r["issue_date"], "%Y-%m-%d"),
         ui.fmt_date(r["due_date"], "%Y-%m-%d"), r["due_status"]) for r in Q.report_current_issues()]),
    "overdue": ("Issue,Equipment,Facility,Issued to,Type,Due", lambda f: [
        (r["issue_id"], r["equipment_name"], r["facility_name"], r["issued_to"], r["user_type"],
         ui.fmt_date(r["due_date"], "%Y-%m-%d")) for r in Q.overdue_issues(today())]),
    "repeat-maintenance": ("Facility,Requests,Still open,Last reported", lambda f: [
        (r["facility_name"], r["requests"], r["still_open"], ui.fmt_date(r["last_reported"], "%Y-%m-%d"))
        for r in Q.report_repeat_maintenance(f)]),
    "maintenance-history": ("Request,Facility,Issue,Handled by,Reported,Completed,Status,Days open", lambda f: [
        (r["maintenance_id"], r["facility_name"], r["issue_description"], r["handled_by"],
         ui.fmt_date(r["reported_date"], "%Y-%m-%d"), ui.fmt_date(r["completion_date"], "%Y-%m-%d"), r["status"],
         r["days_open"]) for r in Q.report_maintenance_history(f)]),
    "large-facilities": ("Facility,Type,Building,Capacity,Status", lambda f: [
        (r["facility_name"], r["type_name"], r["building"], r["capacity"], r["status"])
        for r in Q.report_large_facilities(f["min_cap"], f["type"])]),
}


def csv_cell(value):
    """Plain text for CSV; cells starting with = + - @ are prefixed so spreadsheets
    never execute them as formulas (CSV injection)."""
    if value is None:
        return ""
    text = str(value)
    if text and text[0] in "=+-@\t\r" and not text.lstrip("-").replace(".", "", 1).isdigit():
        return "'" + text
    return text


@app.get("/reports/export/<key>.csv")
def export_report(key):
    if key not in EXPORTS:
        abort(404)
    header, rows_fn = EXPORTS[key]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header.split(","))
    for row in rows_fn(report_filters()):
        writer.writerow([csv_cell(v) for v in row])
    return Response("﻿" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=campushub_{key}_{today().isoformat()}.csv"})


# ---------------------------------------------------------------- personal pages (students / faculty)
@app.route("/my/loans")
def my_loans():
    if A.is_admin():
        return redirect(url_for("issues"))
    t, owner = today(), A.owner()
    view = request.args.get("view", "current")
    if view not in Q.ISSUE_VIEWS:
        view = "current"
    page = Q.list_issues(view, "", arg_int("page", 1), PER_PAGE, t, owner=owner)
    return render_template("my_loans.html", page=page, view=view, counts=Q.issue_view_counts(t, owner))


@app.route("/report-fault", methods=["GET", "POST"])
def report_fault():
    if A.is_admin():
        return redirect(url_for("maintenance") + "#report-form")
    if request.method == "POST":
        facility_id, desc = form_int("facility_id"), request.form.get("description", "").strip()
        admin_id = Q.facility_admin(facility_id) if facility_id else None
        if not desc or not admin_id:
            flash({"title": "Missing details", "text": "Choose a facility and describe the fault."}, "warning")
            return redirect(url_for("report_fault"))
        text = f"{desc[:200]} (reported by {g.user['name']})"[:255]
        try:
            mid = Q.record_maintenance(facility_id, admin_id, text)
            flash_ok(f"Request #{mid} was sent to the facility's administrator. The facility is now marked as under "
                     "maintenance (trigger T4) until the fault is fixed.", "Fault reported")
            return redirect(url_for("dashboard"))
        except db.Error as e:
            flash_db_error(e)
            return redirect(url_for("report_fault"))
    return render_template("report_fault.html", facilities=Q.facility_options(), open_requests=Q.open_maintenance(),
                           preselect=arg_int("facility"))


# ---------------------------------------------------------------- accounts (admin)
@app.route("/accounts")
def accounts():
    role = request.args.get("tab", "STUDENT")
    role = role if role in Q.ACCOUNT_TABS else "STUDENT"
    q = request.args.get("q", "")
    page = Q.list_people_accounts(role, q, arg_int("page", 1), 15)
    now = datetime.now()
    for p in page.items:
        until = A.as_datetime(p["locked_until"])
        p["locked"] = bool(until and until > now)
    return render_template("accounts.html", tab=role, q=q, page=page, summary=Q.account_summary())


def _temp_password_flash(name, password, title):
    flash({"title": title, "text": f"Temporary password for {name}: {password}  -  give it to them privately. "
           "It is shown only once, and they must choose their own password when they first sign in."}, "success")


@app.post("/accounts/create")
def account_create():
    role, person_id = request.form.get("role", ""), form_int("person_id")
    back = safe_next(url_for("accounts", tab=role))
    if role not in Q.ACCOUNT_TABS or not person_id or not Q.person_exists(role, person_id):
        flash({"title": "Nothing changed", "text": "Choose a person to create a login for."}, "warning")
        return redirect(back)
    password = A.temporary_password()
    try:
        Q.create_account(role, person_id, A.hash_password(password), True, datetime.now())
        acc = Q.find_account_by_person(role, person_id)
        _temp_password_flash(acc["name"], password, "Login created")
    except db.Error as e:
        flash_db_error(e)
    return redirect(back)


def _account_or_404(account_id):
    acc = Q.get_account(account_id)
    if not acc:
        abort(404)
    return acc


@app.post("/accounts/<int:account_id>/reset")
def account_reset(account_id):
    acc = _account_or_404(account_id)
    back = safe_next(url_for("accounts", tab=acc["role"]))
    if account_id == g.user["account_id"]:
        flash({"title": "Nothing changed", "text": "Use 'Change password' to change your own password."}, "warning")
        return redirect(back)
    password = A.temporary_password()
    Q.set_password(account_id, A.hash_password(password), True, datetime.now())
    _temp_password_flash(acc["name"], password, "Password reset")
    return redirect(back)


@app.post("/accounts/<int:account_id>/active")
def account_active(account_id):
    acc = _account_or_404(account_id)
    back = safe_next(url_for("accounts", tab=acc["role"]))
    active = request.form.get("active") == "1"
    if account_id == g.user["account_id"] and not active:
        flash({"title": "Nothing changed", "text": "You can't disable the account you are signed in with."}, "warning")
        return redirect(back)
    Q.set_account_active(account_id, active)
    flash_ok(f"{acc['name']} can {'now' if active else 'no longer'} sign in.",
             "Account enabled" if active else "Account disabled")
    return redirect(back)


@app.post("/accounts/<int:account_id>/unlock")
def account_unlock(account_id):
    acc = _account_or_404(account_id)
    Q.unlock_account(account_id)
    flash_ok(f"{acc['name']} can try signing in again.", "Account unlocked")
    return redirect(safe_next(url_for("accounts", tab=acc["role"])))


# ---------------------------------------------------------------- search, alerts, status, review
@app.route("/search")
def search():
    q = request.args.get("q", "").strip()
    results = Q.global_search(q, today()) if q else None
    return render_template("search.html", q=q, results=results)


@app.route("/alerts")
def alerts():
    t = today()
    return render_template("alerts.html", low=Q.low_stock_items(), overdue=Q.overdue_issues(t),
                           maint=Q.open_maintenance(), conflicts=Q.booking_conflicts(t))


@app.route("/status")
def status():
    info, counts, objects, problems = None, [], None, []
    try:
        info = db.ping()
        counts = Q.table_counts()
        objects = Q.schema_objects()
    except db.Error as e:
        problems.append(explain(e))
    return render_template("status.html", info=info, counts=counts, objects=objects, problems=problems)


@app.route("/review")
def review():
    d = Q.review_data(today())
    plan = {}
    tgt = d["target"]
    if tgt:
        s, e = ui.to_minutes(tgt["start_time"]), ui.to_minutes(tgt["end_time"])
        fmt = lambda mins: f"{mins // 60:02d}:{mins % 60:02d}"  # noqa: E731
        # a slot that starts inside the existing booking -> must be rejected by trigger T1
        plan["overlap"] = (fmt(s + 30), fmt(min(e + 60, 23 * 60)))
        # the slot right after it -> back-to-back, allowed if nothing else is booked there
        b2b = (e, min(e + 60, 23 * 60))
        taken = [(ui.to_minutes(b["start_time"]), ui.to_minutes(b["end_time"]))
                 for b in Q.bookings_on(tgt["facility_id"], ui.as_date(tgt["booking_date"])) if b["status"] == "CONFIRMED"]
        if b2b[1] > b2b[0] and not any(a < b2b[1] and b > b2b[0] for a, b in taken):
            plan["b2b"] = (fmt(b2b[0]), fmt(b2b[1]))
    return render_template("review.html", d=d, plan=plan)


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG") == "1")
