"""CampusHub - Smart Campus Facility, Booking & Inventory Management System.

A thin Flask layer over the MySQL database: every business rule (no double
booking, stock limits, maintenance blocking) is enforced by MySQL constraints,
triggers and stored procedures. This app only collects input, calls the
database and shows the result or the database's error message.
"""
from datetime import date, timedelta

from flask import Flask, flash, redirect, render_template, request, url_for
from mysql.connector import Error

import db

app = Flask(__name__)
app.secret_key = "campushub-dev-key"


def db_error(e):
    """Turn a MySQL error into a readable message (trigger SIGNALs come through as e.msg)."""
    return getattr(e, "msg", None) or str(e)


def people():
    students = db.query("SELECT student_id, registration_no, name FROM student ORDER BY name")
    faculty = db.query("SELECT faculty_id, employee_code, name FROM faculty ORDER BY name")
    return students, faculty


def split_person(form):
    """Return (student_id, faculty_id) from the form; exactly one is set."""
    if form.get("user_type") == "faculty":
        return None, form.get("faculty_id") or None
    return form.get("student_id") or None, None


# ---------------------------------------------------------------- dashboard
@app.route("/")
def dashboard():
    stats = {
        "available": db.one("SELECT COUNT(*) AS n FROM facility WHERE status = 'AVAILABLE'")["n"],
        "total_fac": db.one("SELECT COUNT(*) AS n FROM facility")["n"],
        "today": db.one("SELECT COUNT(*) AS n FROM booking WHERE booking_date = CURDATE() AND status = 'CONFIRMED'")["n"],
        "issued": db.one("SELECT COUNT(*) AS n FROM equipment_issue WHERE status = 'ISSUED'")["n"],
        "overdue": db.one("SELECT COUNT(*) AS n FROM vw_current_issues WHERE due_status = 'OVERDUE'")["n"],
        "open_maint": db.one("SELECT COUNT(*) AS n FROM maintenance WHERE status <> 'COMPLETED'")["n"],
    }
    upcoming = db.query(
        """SELECT b.booking_id, f.facility_name, b.booking_date, b.start_time, b.end_time,
                  COALESCE(s.name, fa.name) AS booked_by, b.purpose
           FROM booking b
           JOIN facility f      ON f.facility_id = b.facility_id
           LEFT JOIN student s  ON s.student_id  = b.student_id
           LEFT JOIN faculty fa ON fa.faculty_id = b.faculty_id
           WHERE b.status = 'CONFIRMED' AND b.booking_date >= CURDATE()
           ORDER BY b.booking_date, b.start_time LIMIT 8""")
    return render_template("dashboard.html", stats=stats, upcoming=upcoming)


# ---------------------------------------------------------------- facilities
@app.route("/facilities", methods=["GET", "POST"])
def facilities():
    if request.method == "POST":
        f = request.form
        try:
            db.execute(
                """INSERT INTO facility (facility_name, facility_type_id, admin_id, building, capacity)
                   VALUES (%s, %s, %s, %s, %s)""",
                (f["facility_name"], f["facility_type_id"], f["admin_id"], f["building"], f["capacity"]))
            flash(f"Facility '{f['facility_name']}' added.", "success")
        except Error as e:
            flash(db_error(e), "danger")
        return redirect(url_for("facilities"))

    type_id = request.args.get("type", "")
    building = request.args.get("building", "")
    min_cap = request.args.get("min_cap", "")
    sql = """SELECT f.facility_id, f.facility_name, ft.type_name, f.building, f.capacity,
                    f.status, a.name AS admin_name
             FROM facility f
             JOIN facility_type ft ON ft.facility_type_id = f.facility_type_id
             JOIN admin a          ON a.admin_id = f.admin_id
             WHERE 1 = 1"""
    params = []
    if type_id:
        sql += " AND f.facility_type_id = %s"
        params.append(type_id)
    if building:
        sql += " AND f.building = %s"
        params.append(building)
    if min_cap:
        sql += " AND f.capacity >= %s"
        params.append(min_cap)
    sql += " ORDER BY f.facility_name"
    rows = db.query(sql, params)
    types = db.query("SELECT * FROM facility_type ORDER BY type_name")
    buildings = db.query("SELECT DISTINCT building FROM facility ORDER BY building")
    admins = db.query("SELECT admin_id, name FROM admin ORDER BY name")
    return render_template("facilities.html", rows=rows, types=types, buildings=buildings,
                           admins=admins, sel={"type": type_id, "building": building, "min_cap": min_cap})


# ---------------------------------------------------------------- availability (Q1)
@app.route("/availability")
def availability():
    d = request.args.get("date", "")
    s = request.args.get("start", "")
    e = request.args.get("end", "")
    type_id = request.args.get("type", "")
    min_cap = request.args.get("min_cap", "")
    rows = None
    if d and s and e:
        sql = """SELECT f.facility_id, f.facility_name, ft.type_name, f.building, f.capacity
                 FROM facility f
                 JOIN facility_type ft ON ft.facility_type_id = f.facility_type_id
                 WHERE f.status = 'AVAILABLE'
                   AND NOT EXISTS (SELECT 1 FROM booking b
                                   WHERE b.facility_id = f.facility_id
                                     AND b.booking_date = %s
                                     AND b.status = 'CONFIRMED'
                                     AND b.start_time < %s
                                     AND b.end_time   > %s)"""
        params = [d, e, s]
        if type_id:
            sql += " AND f.facility_type_id = %s"
            params.append(type_id)
        if min_cap:
            sql += " AND f.capacity >= %s"
            params.append(min_cap)
        sql += " ORDER BY f.capacity"
        rows = db.query(sql, params)
    types = db.query("SELECT * FROM facility_type ORDER BY type_name")
    return render_template("availability.html", rows=rows, types=types,
                           sel={"date": d, "start": s, "end": e, "type": type_id, "min_cap": min_cap})


# ---------------------------------------------------------------- bookings
@app.route("/bookings")
def bookings():
    status = request.args.get("status", "")
    sql = """SELECT b.booking_id, f.facility_name, b.booking_date, b.start_time, b.end_time,
                    COALESCE(s.name, fa.name) AS booked_by,
                    IF(s.student_id IS NOT NULL, 'Student', 'Faculty') AS user_type,
                    b.purpose, b.status
             FROM booking b
             JOIN facility f      ON f.facility_id = b.facility_id
             LEFT JOIN student s  ON s.student_id  = b.student_id
             LEFT JOIN faculty fa ON fa.faculty_id = b.faculty_id"""
    params = []
    if status:
        sql += " WHERE b.status = %s"
        params.append(status)
    sql += " ORDER BY b.booking_date DESC, b.start_time DESC"
    return render_template("bookings.html", rows=db.query(sql, params), status=status)


@app.route("/bookings/new", methods=["GET", "POST"])
def new_booking():
    if request.method == "POST":
        f = request.form
        student_id, faculty_id = split_person(f)
        try:
            args = db.call("sp_create_booking",
                           (f["facility_id"], student_id, faculty_id, f["date"],
                            f["start"], f["end"], f.get("purpose", ""), 0))
            flash(f"Booking #{args[7]} confirmed.", "success")
            return redirect(url_for("bookings"))
        except Error as e:
            flash(db_error(e), "danger")      # e.g. 'Time slot overlaps an existing booking'
            return redirect(url_for("new_booking", **{k: f.get(k, "") for k in ("facility_id", "date", "start", "end")}))

    facilities_ = db.query("SELECT facility_id, facility_name, capacity, status FROM facility ORDER BY facility_name")
    students, faculty = people()
    return render_template("booking_form.html", facilities=facilities_, students=students,
                           faculty=faculty, pre=request.args)


@app.post("/bookings/<int:booking_id>/cancel")
def cancel_booking(booking_id):
    try:
        n = db.execute("UPDATE booking SET status = 'CANCELLED' WHERE booking_id = %s AND status = 'CONFIRMED'",
                       (booking_id,))
        flash(f"Booking #{booking_id} cancelled." if n else "Only confirmed bookings can be cancelled.",
              "success" if n else "warning")
    except Error as e:
        flash(db_error(e), "danger")
    return redirect(url_for("bookings"))


# ---------------------------------------------------------------- inventory
@app.route("/equipment", methods=["GET", "POST"])
def equipment():
    if request.method == "POST":
        f = request.form
        student_id, faculty_id = split_person(f)
        try:
            args = db.call("sp_issue_equipment",
                           (f["equipment_id"], student_id, faculty_id, int(f.get("days") or 7), 0))
            flash(f"Equipment issued (issue #{args[4]}).", "success")
        except Error as e:
            flash(db_error(e), "danger")      # e.g. 'No unit of this equipment is available'
        return redirect(url_for("equipment"))

    stock = db.query("SELECT * FROM vw_equipment_availability ORDER BY facility_name, equipment_name")
    issues = db.query("SELECT * FROM vw_current_issues ORDER BY issue_date")
    students, faculty = people()
    return render_template("equipment.html", stock=stock, issues=issues,
                           students=students, faculty=faculty)


@app.post("/issues/<int:issue_id>/return")
def return_equipment(issue_id):
    try:
        db.call("sp_return_equipment", (issue_id,))
        flash(f"Issue #{issue_id} returned; stock restored.", "success")
    except Error as e:
        flash(db_error(e), "danger")
    return redirect(url_for("equipment"))


# ---------------------------------------------------------------- maintenance
@app.route("/maintenance", methods=["GET", "POST"])
def maintenance():
    if request.method == "POST":
        f = request.form
        try:
            args = db.call("sp_record_maintenance",
                           (f["facility_id"], f["admin_id"], f["description"], 0))
            flash(f"Maintenance request #{args[3]} logged; facility is now under maintenance.", "success")
        except Error as e:
            flash(db_error(e), "danger")
        return redirect(url_for("maintenance"))

    rows = db.query("SELECT * FROM vw_maintenance_history ORDER BY reported_date DESC, maintenance_id DESC")
    facilities_ = db.query("SELECT facility_id, facility_name, status FROM facility ORDER BY facility_name")
    admins = db.query("SELECT admin_id, name FROM admin ORDER BY name")
    return render_template("maintenance.html", rows=rows, facilities=facilities_, admins=admins)


@app.post("/maintenance/<int:mid>/complete")
def complete_maintenance(mid):
    try:
        db.execute("""UPDATE maintenance SET status = 'COMPLETED', completion_date = CURDATE()
                      WHERE maintenance_id = %s AND status <> 'COMPLETED'""", (mid,))
        flash(f"Request #{mid} completed.", "success")
    except Error as e:
        flash(db_error(e), "danger")
    return redirect(url_for("maintenance"))


# ---------------------------------------------------------------- students (master data)
@app.route("/students", methods=["GET", "POST"])
def students():
    if request.method == "POST":
        f = request.form
        try:
            db.execute("""INSERT INTO student (registration_no, name, email, phone, department_id)
                          VALUES (%s, %s, %s, %s, %s)""",
                       (f["registration_no"], f["name"], f["email"], f.get("phone") or None, f["department_id"]))
            flash(f"Student {f['registration_no']} added.", "success")
        except Error as e:
            flash(db_error(e), "danger")      # e.g. duplicate registration number
        return redirect(url_for("students"))
    rows = db.query("""SELECT s.*, d.department_name FROM student s
                       JOIN department d ON d.department_id = s.department_id
                       ORDER BY s.registration_no""")
    depts = db.query("SELECT * FROM department ORDER BY department_name")
    return render_template("students.html", rows=rows, depts=depts)


# ---------------------------------------------------------------- reports
@app.route("/reports")
def reports():
    data = {
        "top": db.query("""SELECT facility_name, type_name, total_bookings, hours_booked
                           FROM vw_facility_usage
                           ORDER BY total_bookings DESC, hours_booked DESC LIMIT 5"""),
        "dept": db.query("""SELECT d.department_name, COUNT(*) AS bookings
                            FROM booking b
                            LEFT JOIN student s  ON s.student_id  = b.student_id
                            LEFT JOIN faculty fa ON fa.faculty_id = b.faculty_id
                            JOIN department d ON d.department_id = COALESCE(s.department_id, fa.department_id)
                            WHERE b.status <> 'CANCELLED'
                            GROUP BY d.department_id, d.department_name
                            ORDER BY bookings DESC"""),
        "monthly": db.query("""SELECT DATE_FORMAT(booking_date, '%Y-%m') AS month,
                                      COUNT(*) AS total, SUM(status = 'CANCELLED') AS cancelled
                               FROM booking GROUP BY month ORDER BY month"""),
        "repeat": db.query("""SELECT f.facility_name, COUNT(*) AS maintenance_count
                              FROM maintenance m JOIN facility f ON f.facility_id = m.facility_id
                              GROUP BY f.facility_id, f.facility_name
                              HAVING COUNT(*) > 1"""),
        "overdue": db.query("SELECT * FROM vw_current_issues WHERE due_status = 'OVERDUE' ORDER BY due_date"),
        "big": db.query("SELECT facility_name, building, capacity FROM facility WHERE capacity > 100 ORDER BY capacity DESC"),
    }
    return render_template("reports.html", **data)


@app.template_filter("hm")
def hm(value):
    """MySQL TIME columns arrive as timedelta; show them as HH:MM."""
    if isinstance(value, timedelta):
        mins = int(value.total_seconds()) // 60
        return f"{mins // 60:02d}:{mins % 60:02d}"
    return str(value)[:5] if value is not None else ""


@app.context_processor
def inject_today():
    return {"today": date.today()}


if __name__ == "__main__":
    app.run(debug=True)
