"""All SQL used by the CampusHub web app, grouped by feature.

Rules followed throughout:
  * every user-supplied value is a %s parameter (never formatted into the SQL text)
  * ORDER BY columns come from fixed whitelists, never from the request
  * lists are fetched with joins / aggregates in one query (no N+1 loops)
  * booking, issue, return and maintenance writes go through the stored
    procedures, so the triggers and transactions in MySQL stay in charge
"""
from datetime import timedelta

import db

LOW_STOCK_SQL = "(e.available_qty = 0 OR e.available_qty * 4 <= e.quantity)"   # <= 25 % left
PERSON_JOIN = """LEFT JOIN student s  ON s.student_id  = {a}.student_id
                 LEFT JOIN faculty fa ON fa.faculty_id = {a}.faculty_id"""


def like(text):
    """LIKE pattern for user text; '!' escapes %, _ and ! so they match literally."""
    text = (text or "").strip()
    return "%" + text.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"


def booking_id_from(text):
    """Accept 'BK-000123', 'bk123' or '123' as a booking reference."""
    t = (text or "").strip().upper().replace("BK-", "").replace("BK", "")
    return int(t) if t.isdigit() else None


class Page:
    def __init__(self, items, page, per_page, total):
        self.items, self.page, self.per_page, self.total = items, page, per_page, total
        self.pages = max(1, -(-total // per_page))
        self.has_prev, self.has_next = page > 1, page < self.pages
        self.first = 0 if total == 0 else (page - 1) * per_page + 1
        self.last = min(total, page * per_page)

    def window(self, size=5):
        start = max(1, min(self.page - size // 2, self.pages - size + 1))
        return range(start, min(self.pages, start + size - 1) + 1)


def paged(select_sql, count_sql, params, page, per_page):
    total = db.scalar(count_sql, params) or 0
    page = max(1, min(page, max(1, -(-total // per_page))))
    items = db.query(select_sql + " LIMIT %s OFFSET %s", list(params) + [per_page, (page - 1) * per_page])
    return Page(items, page, per_page, total)


# ============================================================ lookups for forms / filters
def facility_types():
    return db.query("SELECT facility_type_id, type_name FROM facility_type ORDER BY type_name")


def departments():
    return db.query("SELECT department_id, department_name FROM department ORDER BY department_name")


def buildings():
    return [r["building"] for r in db.query("SELECT DISTINCT building FROM facility ORDER BY building")]


def admins():
    return db.query("SELECT admin_id, name, role FROM admin ORDER BY name")


def facility_options():
    return db.query("""SELECT f.facility_id, f.facility_name, f.capacity, f.status, f.building, ft.type_name
                       FROM facility f JOIN facility_type ft ON ft.facility_type_id = f.facility_type_id
                       ORDER BY ft.type_name, f.facility_name""")


def people():
    students = db.query("""SELECT s.student_id, s.registration_no, s.name, d.department_name
                           FROM student s JOIN department d ON d.department_id = s.department_id
                           ORDER BY s.name""")
    faculty = db.query("""SELECT f.faculty_id, f.employee_code, f.name, d.department_name
                          FROM faculty f JOIN department d ON d.department_id = f.department_id
                          ORDER BY f.name""")
    return students, faculty


# ============================================================ dashboard
def dashboard_kpis(today):
    return db.one(f"""
        SELECT
          (SELECT COUNT(*) FROM facility)                                      AS total_facilities,
          (SELECT COUNT(*) FROM facility WHERE status = 'AVAILABLE')           AS available_facilities,
          (SELECT COUNT(*) FROM facility WHERE status = 'UNDER_MAINTENANCE')   AS maintenance_facilities,
          (SELECT COUNT(*) FROM booking WHERE status = 'CONFIRMED' AND booking_date >= %s) AS upcoming_confirmed,
          (SELECT COUNT(*) FROM booking WHERE status <> 'CANCELLED' AND booking_date = %s) AS bookings_today,
          (SELECT COALESCE(SUM(available_qty), 0) FROM equipment)              AS units_available,
          (SELECT COALESCE(SUM(quantity), 0) FROM equipment)                   AS units_total,
          (SELECT COUNT(*) FROM equipment_issue WHERE status = 'ISSUED')       AS issued_now,
          (SELECT COUNT(*) FROM equipment_issue WHERE status = 'ISSUED' AND due_date < %s) AS overdue,
          (SELECT COUNT(*) FROM maintenance WHERE status <> 'COMPLETED')       AS open_maintenance,
          (SELECT COUNT(*) FROM equipment e WHERE {LOW_STOCK_SQL})             AS low_stock
    """, (today, today, today))


def booking_activity(start, end):
    """Counts per day and status; grouped into weeks in Python."""
    return db.query("""SELECT booking_date, status, COUNT(*) AS n FROM booking
                       WHERE booking_date BETWEEN %s AND %s GROUP BY booking_date, status""", (start, end))


def status_distribution(start, end):
    return db.query("""SELECT status, COUNT(*) AS n FROM booking WHERE booking_date BETWEEN %s AND %s
                       GROUP BY status""", (start, end))


def utilization(start, end, limit=8, type_id=None, dept_id=None):
    """Booked hours per facility in [start, end] (cancelled bookings excluded)."""
    dept_sql = ""
    params = [start, end]
    if dept_id:
        dept_sql = " AND COALESCE(s.department_id, fa.department_id) = %s"
        params.append(dept_id)
    where, wparams = "WHERE f.status <> 'INACTIVE'", []
    if type_id:
        where += " AND f.facility_type_id = %s"
        wparams.append(type_id)
    return db.query(f"""
        SELECT f.facility_id, f.facility_name, ft.type_name, f.status, f.capacity,
               COUNT(x.booking_id) AS bookings,
               COALESCE(SUM(TIME_TO_SEC(x.end_time) - TIME_TO_SEC(x.start_time)), 0) / 3600 AS hours
        FROM facility f
        JOIN facility_type ft ON ft.facility_type_id = f.facility_type_id
        LEFT JOIN (SELECT b.* FROM booking b {PERSON_JOIN.format(a='b')}
                   WHERE b.status <> 'CANCELLED' AND b.booking_date BETWEEN %s AND %s{dept_sql}) x
               ON x.facility_id = f.facility_id
        {where}
        GROUP BY f.facility_id, f.facility_name, ft.type_name, f.status, f.capacity
        ORDER BY hours DESC, f.facility_name
        LIMIT %s""", params + wparams + [limit])


def stock_overview(limit=8):
    return db.query("""SELECT e.equipment_id, e.equipment_name, f.facility_name, e.quantity, e.available_qty
                       FROM equipment e JOIN facility f ON f.facility_id = e.facility_id
                       WHERE e.quantity > 0
                       ORDER BY e.available_qty * 1.0 / e.quantity, e.equipment_name LIMIT %s""", (limit,))


def recent_bookings(limit=6):
    return db.query(f"""
        SELECT b.booking_id, b.booking_date, b.start_time, b.end_time, b.status, b.purpose, b.created_at,
               f.facility_id, f.facility_name, COALESCE(s.name, fa.name) AS booked_by
        FROM booking b JOIN facility f ON f.facility_id = b.facility_id
        {PERSON_JOIN.format(a='b')}
        ORDER BY b.created_at DESC, b.booking_id DESC LIMIT %s""", (limit,))


def recent_maintenance(limit=5):
    return db.query("""
        SELECT m.maintenance_id, m.issue_description, m.reported_date, m.completion_date, m.status,
               f.facility_id, f.facility_name
        FROM maintenance m JOIN facility f ON f.facility_id = m.facility_id
        ORDER BY m.reported_date DESC, m.maintenance_id DESC LIMIT %s""", (limit,))


# ============================================================ alerts
def low_stock_items():
    return db.query(f"""SELECT e.equipment_id, e.equipment_name, e.quantity, e.available_qty,
                               f.facility_id, f.facility_name
                        FROM equipment e JOIN facility f ON f.facility_id = e.facility_id
                        WHERE {LOW_STOCK_SQL}
                        ORDER BY e.available_qty, e.equipment_name""")


def overdue_issues(today, limit=None):
    sql = f"""SELECT ei.issue_id, ei.issue_date, ei.due_date, e.equipment_name, f.facility_name,
                     COALESCE(s.name, fa.name) AS issued_to,
                     IF(s.student_id IS NOT NULL, 'Student', 'Faculty') AS user_type
              FROM equipment_issue ei
              JOIN equipment e ON e.equipment_id = ei.equipment_id
              JOIN facility f  ON f.facility_id  = e.facility_id
              {PERSON_JOIN.format(a='ei')}
              WHERE ei.status = 'ISSUED' AND ei.due_date < %s
              ORDER BY ei.due_date"""
    params = [today]
    if limit:
        sql += " LIMIT %s"
        params.append(limit)
    return db.query(sql, params)


def open_maintenance():
    return db.query("""SELECT m.maintenance_id, m.issue_description, m.reported_date, m.status,
                              f.facility_id, f.facility_name, a.name AS handled_by
                       FROM maintenance m
                       JOIN facility f ON f.facility_id = m.facility_id
                       JOIN admin a    ON a.admin_id    = m.admin_id
                       WHERE m.status <> 'COMPLETED'
                       ORDER BY m.reported_date""")


def booking_conflicts(today):
    """Confirmed upcoming bookings in facilities that are currently not available."""
    return db.query(f"""SELECT b.booking_id, b.booking_date, b.start_time, b.end_time, f.facility_id,
                               f.facility_name, f.status AS facility_status, COALESCE(s.name, fa.name) AS booked_by
                        FROM booking b JOIN facility f ON f.facility_id = b.facility_id
                        {PERSON_JOIN.format(a='b')}
                        WHERE b.status = 'CONFIRMED' AND b.booking_date >= %s AND f.status <> 'AVAILABLE'
                        ORDER BY b.booking_date, b.start_time""", (today,))


# ============================================================ facilities
FACILITY_SORTS = {
    "name": "f.facility_name", "type": "ft.type_name, f.facility_name", "building": "f.building, f.facility_name",
    "capacity": "f.capacity DESC, f.facility_name", "status": "f.status, f.facility_name",
    "upcoming": "upcoming DESC, f.facility_name",
}


def list_facilities(filters, sort, page, per_page, today):
    where, params = ["1 = 1"], []
    if filters.get("q"):
        where.append("(f.facility_name LIKE %s ESCAPE '!' OR f.building LIKE %s ESCAPE '!')")
        params += [like(filters["q"])] * 2
    if filters.get("type"):
        where.append("f.facility_type_id = %s")
        params.append(filters["type"])
    if filters.get("building"):
        where.append("f.building = %s")
        params.append(filters["building"])
    if filters.get("min_cap"):
        where.append("f.capacity >= %s")
        params.append(filters["min_cap"])
    if filters.get("status"):
        where.append("f.status = %s")
        params.append(filters["status"])
    w = " AND ".join(where)
    base = f"""FROM facility f JOIN facility_type ft ON ft.facility_type_id = f.facility_type_id
               JOIN admin a ON a.admin_id = f.admin_id WHERE {w}"""
    select = f"""SELECT f.facility_id, f.facility_name, ft.type_name, f.building, f.capacity, f.status,
                        a.name AS admin_name,
                        (SELECT COUNT(*) FROM booking b WHERE b.facility_id = f.facility_id
                           AND b.status = 'CONFIRMED' AND b.booking_date >= %s) AS upcoming,
                        (SELECT COUNT(*) FROM equipment e WHERE e.facility_id = f.facility_id) AS equipment_count
                 {base} ORDER BY {FACILITY_SORTS.get(sort, FACILITY_SORTS['name'])}"""
    total = db.scalar(f"SELECT COUNT(*) {base}", params) or 0
    page = max(1, min(page, max(1, -(-total // per_page))))
    items = db.query(select + " LIMIT %s OFFSET %s", [today] + params + [per_page, (page - 1) * per_page])
    return Page(items, page, per_page, total)


def facility_status_counts():
    return {r["status"]: r["n"] for r in db.query("SELECT status, COUNT(*) AS n FROM facility GROUP BY status")}


def get_facility(facility_id):
    return db.one("""SELECT f.*, ft.type_name, a.name AS admin_name, a.email AS admin_email
                     FROM facility f JOIN facility_type ft ON ft.facility_type_id = f.facility_type_id
                     JOIN admin a ON a.admin_id = f.admin_id WHERE f.facility_id = %s""", (facility_id,))


def facility_equipment(facility_id):
    return db.query("""SELECT equipment_id, equipment_name, quantity, available_qty, availability_status
                       FROM equipment WHERE facility_id = %s ORDER BY equipment_name""", (facility_id,))


def facility_bookings(facility_id, start, end, include_cancelled=True):
    status_sql = "" if include_cancelled else " AND b.status <> 'CANCELLED'"
    return db.query(f"""SELECT b.booking_id, b.booking_date, b.start_time, b.end_time, b.status, b.purpose,
                               COALESCE(s.name, fa.name) AS booked_by
                        FROM booking b {PERSON_JOIN.format(a='b')}
                        WHERE b.facility_id = %s AND b.booking_date BETWEEN %s AND %s{status_sql}
                        ORDER BY b.booking_date, b.start_time""", (facility_id, start, end))


def facility_maintenance(facility_id):
    return db.query("""SELECT m.maintenance_id, m.issue_description, m.reported_date, m.completion_date, m.status,
                              a.name AS handled_by
                       FROM maintenance m JOIN admin a ON a.admin_id = m.admin_id
                       WHERE m.facility_id = %s ORDER BY m.reported_date DESC""", (facility_id,))


def facility_stats(facility_id, today):
    return db.one("""
        SELECT
          (SELECT COUNT(*) FROM booking WHERE facility_id = %s AND status = 'CONFIRMED'
             AND booking_date BETWEEN %s AND %s) AS next_7_days,
          (SELECT COALESCE(SUM(TIME_TO_SEC(end_time) - TIME_TO_SEC(start_time)), 0) / 3600 FROM booking
             WHERE facility_id = %s AND status <> 'CANCELLED' AND booking_date BETWEEN %s AND %s) AS hours_30d,
          (SELECT COUNT(*) FROM booking WHERE facility_id = %s) AS all_bookings,
          (SELECT COUNT(*) FROM maintenance WHERE facility_id = %s) AS maintenance_count
    """, (facility_id, today, today + timedelta(days=6),
          facility_id, today - timedelta(days=29), today, facility_id, facility_id))


def add_facility(name, type_id, admin_id, building, capacity):
    return db.execute("""INSERT INTO facility (facility_name, facility_type_id, admin_id, building, capacity)
                         VALUES (%s, %s, %s, %s, %s)""", (name, type_id, admin_id, building, capacity))


def set_facility_active(facility_id, active):
    """Only AVAILABLE <-> INACTIVE. UNDER_MAINTENANCE is owned by triggers T4/T5."""
    if active:
        return db.execute("UPDATE facility SET status = 'AVAILABLE' WHERE facility_id = %s AND status = 'INACTIVE'",
                          (facility_id,))
    return db.execute("UPDATE facility SET status = 'INACTIVE' WHERE facility_id = %s AND status = 'AVAILABLE'",
                      (facility_id,))


# ============================================================ availability
def free_facilities(on_date, start, end, type_id=None, min_cap=None):
    sql = """SELECT f.facility_id, f.facility_name, ft.type_name, f.building, f.capacity
             FROM facility f JOIN facility_type ft ON ft.facility_type_id = f.facility_type_id
             WHERE f.status = 'AVAILABLE'
               AND NOT EXISTS (SELECT 1 FROM booking b
                               WHERE b.facility_id = f.facility_id AND b.booking_date = %s
                                 AND b.status = 'CONFIRMED' AND b.start_time < %s AND b.end_time > %s)"""
    params = [on_date, end, start]
    if type_id:
        sql += " AND f.facility_type_id = %s"
        params.append(type_id)
    if min_cap:
        sql += " AND f.capacity >= %s"
        params.append(min_cap)
    return db.query(sql + " ORDER BY f.capacity, f.facility_name", params)


def day_schedule(on_date, type_id=None, building=None):
    where, params = ["f.status <> 'INACTIVE'"], []
    if type_id:
        where.append("f.facility_type_id = %s")
        params.append(type_id)
    if building:
        where.append("f.building = %s")
        params.append(building)
    facilities = db.query(f"""SELECT f.facility_id, f.facility_name, f.capacity, f.status, ft.type_name
                              FROM facility f JOIN facility_type ft ON ft.facility_type_id = f.facility_type_id
                              WHERE {' AND '.join(where)} ORDER BY ft.type_name, f.facility_name""", params)
    bookings = db.query(f"""SELECT b.booking_id, b.facility_id, b.start_time, b.end_time, b.status, b.purpose,
                                   COALESCE(s.name, fa.name) AS booked_by
                            FROM booking b JOIN facility f ON f.facility_id = b.facility_id
                            {PERSON_JOIN.format(a='b')}
                            WHERE b.booking_date = %s AND {' AND '.join(where)}
                            ORDER BY b.start_time""", [on_date] + params)
    return facilities, bookings


def bookings_on(facility_id, on_date):
    return db.query(f"""SELECT b.booking_id, b.start_time, b.end_time, b.status, b.purpose,
                               COALESCE(s.name, fa.name) AS booked_by
                        FROM booking b {PERSON_JOIN.format(a='b')}
                        WHERE b.facility_id = %s AND b.booking_date = %s AND b.status <> 'CANCELLED'
                        ORDER BY b.start_time""", (facility_id, on_date))


# ============================================================ bookings
BOOKING_SORTS = {
    "date": "b.booking_date DESC, b.start_time DESC", "date_asc": "b.booking_date, b.start_time",
    "facility": "f.facility_name, b.booking_date", "status": "b.status, b.booking_date DESC",
    "created": "b.created_at DESC, b.booking_id DESC",
}
BOOKING_VIEWS = {
    "upcoming": ("b.status = 'CONFIRMED' AND b.booking_date >= %s", True),
    "needs_closing": ("b.status = 'CONFIRMED' AND b.booking_date < %s", True),
    "completed": ("b.status = 'COMPLETED'", False),
    "cancelled": ("b.status = 'CANCELLED'", False),
    "all": ("1 = 1", False),
}


def booking_view_counts(today):
    return db.one("""SELECT SUM(status = 'CONFIRMED' AND booking_date >= %s) AS upcoming,
                            SUM(status = 'CONFIRMED' AND booking_date <  %s) AS needs_closing,
                            SUM(status = 'COMPLETED') AS completed,
                            SUM(status = 'CANCELLED') AS cancelled,
                            COUNT(*) AS total
                     FROM booking""", (today, today))


def list_bookings(view, filters, sort, page, per_page, today):
    cond, needs_today = BOOKING_VIEWS.get(view, BOOKING_VIEWS["upcoming"])
    where, params = [cond], ([today] if needs_today else [])
    if filters.get("q"):
        bid = booking_id_from(filters["q"])
        clause = ("(f.facility_name LIKE %s ESCAPE '!' OR b.purpose LIKE %s ESCAPE '!' "
                  "OR s.name LIKE %s ESCAPE '!' OR fa.name LIKE %s ESCAPE '!'")
        params += [like(filters["q"])] * 4
        if bid is not None:
            clause += " OR b.booking_id = %s"
            params.append(bid)
        where.append(clause + ")")
    if filters.get("type"):
        where.append("f.facility_type_id = %s")
        params.append(filters["type"])
    if filters.get("facility"):
        where.append("b.facility_id = %s")
        params.append(filters["facility"])
    if filters.get("date_from"):
        where.append("b.booking_date >= %s")
        params.append(filters["date_from"])
    if filters.get("date_to"):
        where.append("b.booking_date <= %s")
        params.append(filters["date_to"])
    default_sort = "date_asc" if view == "upcoming" else "date"
    base = f"""FROM booking b JOIN facility f ON f.facility_id = b.facility_id
               JOIN facility_type ft ON ft.facility_type_id = f.facility_type_id
               {PERSON_JOIN.format(a='b')}
               WHERE {' AND '.join(where)}"""
    select = f"""SELECT b.booking_id, b.booking_date, b.start_time, b.end_time, b.status, b.purpose, b.created_at,
                        f.facility_id, f.facility_name, ft.type_name,
                        COALESCE(s.name, fa.name) AS booked_by,
                        IF(s.student_id IS NOT NULL, 'Student', 'Faculty') AS user_type
                 {base} ORDER BY {BOOKING_SORTS.get(sort, BOOKING_SORTS[default_sort])}"""
    return paged(select, f"SELECT COUNT(*) {base}", params, page, per_page)


def get_booking(booking_id):
    return db.one(f"""
        SELECT b.*, f.facility_name, f.building, f.capacity, f.status AS facility_status, ft.type_name,
               COALESCE(s.name, fa.name) AS booked_by,
               IF(s.student_id IS NOT NULL, 'Student', 'Faculty') AS user_type,
               COALESCE(s.registration_no, fa.employee_code) AS person_code,
               COALESCE(s.email, fa.email) AS person_email,
               d.department_name
        FROM booking b
        JOIN facility f ON f.facility_id = b.facility_id
        JOIN facility_type ft ON ft.facility_type_id = f.facility_type_id
        {PERSON_JOIN.format(a='b')}
        LEFT JOIN department d ON d.department_id = COALESCE(s.department_id, fa.department_id)
        WHERE b.booking_id = %s""", (booking_id,))


def create_booking(facility_id, student_id, faculty_id, on_date, start, end, purpose):
    """sp_create_booking: locks the facility row (SELECT ... FOR UPDATE), inserts
    (trigger T1 checks status + overlap), COMMIT or ROLLBACK + RESIGNAL."""
    args = db.call("sp_create_booking", (facility_id, student_id, faculty_id, on_date, start, end, purpose, 0))
    return args[7]


def cancel_booking(booking_id):
    return db.execute("UPDATE booking SET status = 'CANCELLED' WHERE booking_id = %s AND status = 'CONFIRMED'",
                      (booking_id,))


def complete_booking(booking_id, today):
    return db.execute("""UPDATE booking SET status = 'COMPLETED'
                         WHERE booking_id = %s AND status = 'CONFIRMED' AND booking_date <= %s""",
                      (booking_id, today))


def complete_past_bookings(today):
    return db.execute("UPDATE booking SET status = 'COMPLETED' WHERE status = 'CONFIRMED' AND booking_date < %s",
                      (today,))


# ============================================================ inventory
EQUIPMENT_SORTS = {
    "name": "e.equipment_name", "facility": "f.facility_name, e.equipment_name",
    "available": "e.available_qty, e.equipment_name", "stock": "e.available_qty * 1.0 / e.quantity, e.equipment_name",
    "total": "e.quantity DESC, e.equipment_name",
}


def inventory_kpis(today):
    return db.one(f"""
        SELECT (SELECT COUNT(*) FROM equipment) AS item_types,
               (SELECT COALESCE(SUM(quantity), 0) FROM equipment) AS units_total,
               (SELECT COALESCE(SUM(available_qty), 0) FROM equipment) AS units_available,
               (SELECT COUNT(*) FROM equipment_issue WHERE status = 'ISSUED') AS issued_now,
               (SELECT COUNT(*) FROM equipment_issue WHERE status = 'ISSUED' AND due_date < %s) AS overdue,
               (SELECT COUNT(*) FROM equipment e WHERE {LOW_STOCK_SQL}) AS low_stock,
               (SELECT COUNT(*) FROM equipment WHERE available_qty = 0) AS out_of_stock
    """, (today,))


def list_equipment(filters, sort, page, per_page):
    where, params = ["1 = 1"], []
    if filters.get("q"):
        where.append("(e.equipment_name LIKE %s ESCAPE '!' OR f.facility_name LIKE %s ESCAPE '!')")
        params += [like(filters["q"])] * 2
    if filters.get("facility"):
        where.append("e.facility_id = %s")
        params.append(filters["facility"])
    stock = filters.get("stock")
    if stock == "out":
        where.append("e.available_qty = 0")
    elif stock == "low":
        where.append(LOW_STOCK_SQL)
    elif stock == "ok":
        where.append(f"NOT {LOW_STOCK_SQL}")
    base = f"FROM equipment e JOIN facility f ON f.facility_id = e.facility_id WHERE {' AND '.join(where)}"
    select = f"""SELECT e.equipment_id, e.equipment_name, e.quantity, e.available_qty, e.availability_status,
                        (e.quantity - e.available_qty) AS issued_qty, f.facility_id, f.facility_name,
                        (SELECT COUNT(*) FROM equipment_issue ei WHERE ei.equipment_id = e.equipment_id) AS times_issued
                 {base} ORDER BY {EQUIPMENT_SORTS.get(sort, EQUIPMENT_SORTS['name'])}"""
    return paged(select, f"SELECT COUNT(*) {base}", params, page, per_page)


def equipment_options():
    return db.query("""SELECT e.equipment_id, e.equipment_name, e.available_qty, e.quantity, f.facility_name
                       FROM equipment e JOIN facility f ON f.facility_id = e.facility_id
                       ORDER BY e.equipment_name, f.facility_name""")


ISSUE_VIEWS = {
    "current": ("ei.status = 'ISSUED'", False),
    "overdue": ("ei.status = 'ISSUED' AND ei.due_date < %s", True),
    "returned": ("ei.status = 'RETURNED'", False),
    "all": ("1 = 1", False),
}


def issue_view_counts(today):
    return db.one("""SELECT SUM(status = 'ISSUED') AS current,
                            SUM(status = 'ISSUED' AND due_date < %s) AS overdue,
                            SUM(status = 'RETURNED') AS returned, COUNT(*) AS total
                     FROM equipment_issue""", (today,))


def list_issues(view, q, page, per_page, today):
    cond, needs_today = ISSUE_VIEWS.get(view, ISSUE_VIEWS["current"])
    where, params = [cond], ([today] if needs_today else [])
    if q:
        where.append("(e.equipment_name LIKE %s ESCAPE '!' OR s.name LIKE %s ESCAPE '!' "
                     "OR fa.name LIKE %s ESCAPE '!' OR s.registration_no LIKE %s ESCAPE '!')")
        params += [like(q)] * 4
    base = f"""FROM equipment_issue ei
               JOIN equipment e ON e.equipment_id = ei.equipment_id
               JOIN facility f  ON f.facility_id  = e.facility_id
               {PERSON_JOIN.format(a='ei')}
               WHERE {' AND '.join(where)}"""
    order = "ei.due_date, ei.issue_id" if view in ("current", "overdue") else "ei.issue_date DESC, ei.issue_id DESC"
    select = f"""SELECT ei.issue_id, ei.issue_date, ei.due_date, ei.return_date, ei.status,
                        e.equipment_id, e.equipment_name, f.facility_name,
                        COALESCE(s.name, fa.name) AS issued_to,
                        IF(s.student_id IS NOT NULL, 'Student', 'Faculty') AS user_type
                 {base} ORDER BY {order}"""
    return paged(select, f"SELECT COUNT(*) {base}", params, page, per_page)


def issue_equipment(equipment_id, student_id, faculty_id, days):
    """sp_issue_equipment: locks the equipment row, inserts (trigger T2 checks + lowers stock)."""
    return db.call("sp_issue_equipment", (equipment_id, student_id, faculty_id, days, 0))[4]


def return_equipment(issue_id):
    """sp_return_equipment: refuses a second return; trigger T3 restores stock."""
    db.call("sp_return_equipment", (issue_id,))


# ============================================================ maintenance
MAINT_VIEWS = {
    "open": "m.status <> 'COMPLETED'", "reported": "m.status = 'REPORTED'",
    "in_progress": "m.status = 'IN_PROGRESS'", "completed": "m.status = 'COMPLETED'", "all": "1 = 1",
}


def maintenance_kpis(today):
    return db.one("""
        SELECT SUM(status <> 'COMPLETED') AS open_count,
               SUM(status = 'REPORTED') AS reported,
               SUM(status = 'IN_PROGRESS') AS in_progress,
               SUM(status = 'COMPLETED' AND completion_date >= %s) AS completed_30d,
               AVG(CASE WHEN status = 'COMPLETED' THEN DATEDIFF(completion_date, reported_date) END) AS avg_days,
               COUNT(*) AS total
        FROM maintenance""", (today - timedelta(days=30),))


def list_maintenance(view, facility_id, q, page, per_page, today):
    where, params = [MAINT_VIEWS.get(view, MAINT_VIEWS["open"])], []
    if facility_id:
        where.append("m.facility_id = %s")
        params.append(facility_id)
    if q:
        where.append("(m.issue_description LIKE %s ESCAPE '!' OR f.facility_name LIKE %s ESCAPE '!')")
        params += [like(q)] * 2
    base = f"""FROM maintenance m JOIN facility f ON f.facility_id = m.facility_id
               JOIN admin a ON a.admin_id = m.admin_id WHERE {' AND '.join(where)}"""
    select = f"""SELECT m.maintenance_id, m.issue_description, m.reported_date, m.completion_date, m.status,
                        f.facility_id, f.facility_name, f.status AS facility_status, a.name AS handled_by,
                        DATEDIFF(COALESCE(m.completion_date, %s), m.reported_date) AS days_open
                 {base} ORDER BY (m.status = 'COMPLETED'), m.reported_date DESC, m.maintenance_id DESC"""
    total = db.scalar(f"SELECT COUNT(*) {base}", params) or 0
    page = max(1, min(page, max(1, -(-total // per_page))))
    items = db.query(select + " LIMIT %s OFFSET %s", [today] + params + [per_page, (page - 1) * per_page])
    return Page(items, page, per_page, total)


def facilities_under_maintenance():
    return db.query("""SELECT f.facility_id, f.facility_name, f.building,
                              (SELECT COUNT(*) FROM maintenance m WHERE m.facility_id = f.facility_id
                                 AND m.status <> 'COMPLETED') AS open_requests
                       FROM facility f WHERE f.status = 'UNDER_MAINTENANCE' ORDER BY f.facility_name""")


def record_maintenance(facility_id, admin_id, description):
    """sp_record_maintenance inserts the request; trigger T4 marks the facility UNDER_MAINTENANCE."""
    return db.call("sp_record_maintenance", (facility_id, admin_id, description, 0))[3]


def start_maintenance(mid):
    return db.execute("UPDATE maintenance SET status = 'IN_PROGRESS' WHERE maintenance_id = %s AND status = 'REPORTED'",
                      (mid,))


def complete_maintenance(mid, today):
    """Trigger T5 reopens the facility when its last open request is completed."""
    return db.execute("""UPDATE maintenance SET status = 'COMPLETED', completion_date = %s
                         WHERE maintenance_id = %s AND status <> 'COMPLETED'""", (today, mid))


# ============================================================ people
def list_students(q, dept, page, per_page):
    where, params = ["1 = 1"], []
    if q:
        where.append("(s.name LIKE %s ESCAPE '!' OR s.registration_no LIKE %s ESCAPE '!' OR s.email LIKE %s ESCAPE '!')")
        params += [like(q)] * 3
    if dept:
        where.append("s.department_id = %s")
        params.append(dept)
    base = f"FROM student s JOIN department d ON d.department_id = s.department_id WHERE {' AND '.join(where)}"
    select = f"""SELECT s.student_id, s.registration_no, s.name, s.email, s.phone, d.department_name,
                        (SELECT COUNT(*) FROM booking b WHERE b.student_id = s.student_id) AS bookings,
                        (SELECT COUNT(*) FROM equipment_issue ei WHERE ei.student_id = s.student_id
                           AND ei.status = 'ISSUED') AS items_out
                 {base} ORDER BY s.registration_no"""
    return paged(select, f"SELECT COUNT(*) {base}", params, page, per_page)


def list_faculty(q, dept):
    where, params = ["1 = 1"], []
    if q:
        where.append("(f.name LIKE %s ESCAPE '!' OR f.employee_code LIKE %s ESCAPE '!')")
        params += [like(q)] * 2
    if dept:
        where.append("f.department_id = %s")
        params.append(dept)
    return db.query(f"""SELECT f.faculty_id, f.employee_code, f.name, f.email, f.designation, d.department_name,
                               (SELECT COUNT(*) FROM booking b WHERE b.faculty_id = f.faculty_id) AS bookings
                        FROM faculty f JOIN department d ON d.department_id = f.department_id
                        WHERE {' AND '.join(where)} ORDER BY f.name""", params)


def add_student(reg, name, email, phone, dept):
    return db.execute("""INSERT INTO student (registration_no, name, email, phone, department_id)
                         VALUES (%s, %s, %s, %s, %s)""", (reg, name, email, phone, dept))


# ============================================================ reports
def _report_where(f, use_status=True):
    where, params = ["b.booking_date BETWEEN %s AND %s"], [f["date_from"], f["date_to"]]
    if f.get("dept"):
        where.append("COALESCE(s.department_id, fa.department_id) = %s")
        params.append(f["dept"])
    if f.get("type"):
        where.append("fc.facility_type_id = %s")
        params.append(f["type"])
    if use_status and f.get("status"):
        where.append("b.status = %s")
        params.append(f["status"])
    return " AND ".join(where), params


REPORT_FROM = f"""FROM booking b JOIN facility fc ON fc.facility_id = b.facility_id
                  JOIN facility_type ft ON ft.facility_type_id = fc.facility_type_id
                  {PERSON_JOIN.format(a='b')}"""


def report_summary(f):
    w, p = _report_where(f)
    return db.one(f"""SELECT COUNT(*) AS total,
                             SUM(b.status = 'CONFIRMED') AS confirmed, SUM(b.status = 'COMPLETED') AS completed,
                             SUM(b.status = 'CANCELLED') AS cancelled,
                             COALESCE(SUM(CASE WHEN b.status <> 'CANCELLED'
                                 THEN TIME_TO_SEC(b.end_time) - TIME_TO_SEC(b.start_time) END), 0) / 3600 AS hours,
                             COUNT(DISTINCT b.facility_id) AS facilities_used
                      {REPORT_FROM} WHERE {w}""", p)


def report_monthly(f):
    w, p = _report_where(f)
    return db.query(f"""SELECT DATE_FORMAT(b.booking_date, %s) AS month, COUNT(*) AS total,
                               SUM(b.status = 'CONFIRMED') AS confirmed, SUM(b.status = 'COMPLETED') AS completed,
                               SUM(b.status = 'CANCELLED') AS cancelled
                        {REPORT_FROM} WHERE {w} GROUP BY month ORDER BY month""", ["%Y-%m"] + p)


def report_top_facilities(f, limit=10):
    w, p = _report_where(f)
    return db.query(f"""SELECT fc.facility_id, fc.facility_name, ft.type_name, fc.building, COUNT(*) AS bookings,
                               COALESCE(SUM(CASE WHEN b.status <> 'CANCELLED'
                                   THEN TIME_TO_SEC(b.end_time) - TIME_TO_SEC(b.start_time) END), 0) / 3600 AS hours
                        {REPORT_FROM} WHERE {w}
                        GROUP BY fc.facility_id, fc.facility_name, ft.type_name, fc.building
                        ORDER BY bookings DESC, hours DESC, fc.facility_name LIMIT %s""", p + [limit])


def report_by_department(f):
    w, p = _report_where(f)
    return db.query(f"""SELECT d.department_name, COUNT(*) AS bookings,
                               SUM(b.status = 'CANCELLED') AS cancelled
                        {REPORT_FROM}
                        JOIN department d ON d.department_id = COALESCE(s.department_id, fa.department_id)
                        WHERE {w}
                        GROUP BY d.department_id, d.department_name ORDER BY bookings DESC, d.department_name""", p)


def report_status_split(f):
    w, p = _report_where(f, use_status=False)
    return db.query(f"SELECT b.status, COUNT(*) AS n {REPORT_FROM} WHERE {w} GROUP BY b.status ORDER BY b.status", p)


def report_utilization(f, limit=12):
    return utilization(f["date_from"], f["date_to"], limit=limit, type_id=f.get("type"), dept_id=f.get("dept"))


def report_equipment():
    return db.query("""SELECT v.*, (v.available_qty = 0 OR v.available_qty * 4 <= v.quantity) AS is_low
                       FROM vw_equipment_availability v ORDER BY v.available_qty * 1.0 / NULLIF(v.quantity, 0),
                       v.equipment_name""")


def report_current_issues():
    return db.query("SELECT * FROM vw_current_issues ORDER BY due_date")


def report_repeat_maintenance(f):
    return db.query("""SELECT f.facility_id, f.facility_name, COUNT(*) AS requests,
                              SUM(m.status <> 'COMPLETED') AS still_open, MAX(m.reported_date) AS last_reported
                       FROM maintenance m JOIN facility f ON f.facility_id = m.facility_id
                       WHERE m.reported_date BETWEEN %s AND %s
                       GROUP BY f.facility_id, f.facility_name HAVING COUNT(*) > 1
                       ORDER BY requests DESC, f.facility_name""", (f["date_from"], f["date_to"]))


def report_maintenance_history(f):
    return db.query("""SELECT * FROM vw_maintenance_history WHERE reported_date BETWEEN %s AND %s
                       ORDER BY reported_date DESC, maintenance_id DESC""", (f["date_from"], f["date_to"]))


def report_large_facilities(min_cap, type_id=None):
    sql = """SELECT f.facility_id, f.facility_name, ft.type_name, f.building, f.capacity, f.status
             FROM facility f JOIN facility_type ft ON ft.facility_type_id = f.facility_type_id
             WHERE f.capacity > %s"""
    params = [min_cap]
    if type_id:
        sql += " AND f.facility_type_id = %s"
        params.append(type_id)
    return db.query(sql + " ORDER BY f.capacity DESC, f.facility_name", params)


# ============================================================ global search
def global_search(text, today, limit=8):
    pat = like(text)
    bid = booking_id_from(text)
    facilities = db.query("""SELECT f.facility_id, f.facility_name, f.building, f.capacity, f.status, ft.type_name
                             FROM facility f JOIN facility_type ft ON ft.facility_type_id = f.facility_type_id
                             WHERE f.facility_name LIKE %s ESCAPE '!' OR f.building LIKE %s ESCAPE '!'
                                OR ft.type_name LIKE %s ESCAPE '!'
                             ORDER BY f.facility_name LIMIT %s""", (pat, pat, pat, limit))
    bk_sql = f"""SELECT b.booking_id, b.booking_date, b.start_time, b.end_time, b.status, b.purpose,
                        f.facility_name, COALESCE(s.name, fa.name) AS booked_by
                 FROM booking b JOIN facility f ON f.facility_id = b.facility_id {PERSON_JOIN.format(a='b')}
                 WHERE b.purpose LIKE %s ESCAPE '!' OR s.name LIKE %s ESCAPE '!' OR fa.name LIKE %s ESCAPE '!'"""
    bk_params = [pat, pat, pat]
    if bid is not None:
        bk_sql += " OR b.booking_id = %s"
        bk_params.append(bid)
    bookings = db.query(bk_sql + " ORDER BY (b.booking_date >= %s) DESC, b.booking_date DESC LIMIT %s",
                        bk_params + [today, limit])
    equipment = db.query("""SELECT e.equipment_id, e.equipment_name, e.available_qty, e.quantity, f.facility_name
                            FROM equipment e JOIN facility f ON f.facility_id = e.facility_id
                            WHERE e.equipment_name LIKE %s ESCAPE '!' ORDER BY e.equipment_name LIMIT %s""",
                         (pat, limit))
    people_rows = db.query("""SELECT 'Student' AS kind, s.student_id AS id, s.name, s.registration_no AS code,
                                     d.department_name
                              FROM student s JOIN department d ON d.department_id = s.department_id
                              WHERE s.name LIKE %s ESCAPE '!' OR s.registration_no LIKE %s ESCAPE '!'
                              UNION ALL
                              SELECT 'Faculty', f.faculty_id, f.name, f.employee_code, d.department_name
                              FROM faculty f JOIN department d ON d.department_id = f.department_id
                              WHERE f.name LIKE %s ESCAPE '!' OR f.employee_code LIKE %s ESCAPE '!'
                              ORDER BY name LIMIT %s""", (pat, pat, pat, pat, limit))
    return {"facilities": facilities, "bookings": bookings, "equipment": equipment, "people": people_rows}


# ============================================================ status / health
def table_counts():
    tables = ["department", "student", "faculty", "admin", "facility_type", "facility", "booking", "equipment",
              "equipment_issue", "maintenance"]
    sql = " UNION ALL ".join(f"SELECT '{t}' AS table_name, COUNT(*) AS row_count FROM {t}" for t in tables)
    return db.query(sql)


def schema_objects():
    """Triggers, procedures, views and indexes of the current database (MySQL information_schema)."""
    return {
        "triggers": db.query("""SELECT TRIGGER_NAME AS name, ACTION_TIMING AS timing, EVENT_MANIPULATION AS event,
                                       EVENT_OBJECT_TABLE AS on_table
                                FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA = DATABASE()
                                ORDER BY EVENT_OBJECT_TABLE, TRIGGER_NAME"""),
        "procedures": db.query("""SELECT ROUTINE_NAME AS name FROM information_schema.ROUTINES
                                  WHERE ROUTINE_SCHEMA = DATABASE() AND ROUTINE_TYPE = 'PROCEDURE'
                                  ORDER BY ROUTINE_NAME"""),
        "views": db.query("""SELECT TABLE_NAME AS name FROM information_schema.VIEWS
                             WHERE TABLE_SCHEMA = DATABASE() ORDER BY TABLE_NAME"""),
        "indexes": db.query("""SELECT TABLE_NAME AS on_table, INDEX_NAME AS name,
                                      GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX SEPARATOR ', ') AS columns
                               FROM information_schema.STATISTICS
                               WHERE TABLE_SCHEMA = DATABASE() AND INDEX_NAME LIKE 'idx%%'
                               GROUP BY TABLE_NAME, INDEX_NAME ORDER BY TABLE_NAME, INDEX_NAME"""),
    }


# ============================================================ review mode
def review_data(today):
    tomorrow = today + timedelta(days=1)
    target = db.one(f"""SELECT b.booking_id, b.facility_id, b.booking_date, b.start_time, b.end_time,
                               f.facility_name, COALESCE(s.name, fa.name) AS booked_by
                        FROM booking b JOIN facility f ON f.facility_id = b.facility_id
                        {PERSON_JOIN.format(a='b')}
                        WHERE b.status = 'CONFIRMED' AND b.booking_date > %s AND f.status = 'AVAILABLE'
                        ORDER BY b.booking_date, b.start_time LIMIT 1""", (today,))
    free = free_facilities(tomorrow, "07:00", "08:00")
    return {
        "tomorrow": tomorrow,
        "target": target,
        "free_facility": free[0] if free else None,
        "maintenance_facility": db.one("""SELECT facility_id, facility_name FROM facility
                                          WHERE status = 'UNDER_MAINTENANCE' ORDER BY facility_name LIMIT 1"""),
        "empty_item": db.one("""SELECT e.equipment_id, e.equipment_name, f.facility_name FROM equipment e
                                JOIN facility f ON f.facility_id = e.facility_id
                                WHERE e.available_qty = 0 ORDER BY e.equipment_name LIMIT 1"""),
        "stock_item": db.one("""SELECT e.equipment_id, e.equipment_name, e.available_qty FROM equipment e
                                WHERE e.available_qty >= 2 ORDER BY e.available_qty DESC LIMIT 1"""),
        "returned_issue": db.one("""SELECT ei.issue_id, e.equipment_name FROM equipment_issue ei
                                    JOIN equipment e ON e.equipment_id = ei.equipment_id
                                    WHERE ei.status = 'RETURNED' ORDER BY ei.issue_id DESC LIMIT 1"""),
        "student": db.one("SELECT student_id, name FROM student ORDER BY student_id LIMIT 1"),
        "faculty": db.one("SELECT faculty_id, name FROM faculty ORDER BY faculty_id LIMIT 1"),
    }
