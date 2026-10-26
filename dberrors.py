"""Turn MySQL errors into clear messages that also name the database rule
that produced them - useful for users and for explaining the DBMS concepts."""
import re

# Messages raised with SIGNAL inside triggers / procedures (MySQL error 1644)
SIGNAL_SOURCES = {
    "Time slot overlaps": "Trigger trg_booking_before_insert (overlap check)",
    "Facility is under maintenance": "Trigger trg_booking_before_insert (facility status check)",
    "No unit of this equipment": "Trigger trg_issue_before_insert (stock check)",
    "This item is not currently issued": "Procedure sp_return_equipment",
}

CHECK_MESSAGES = {
    "chk_booking_time": "End time must be after start time.",
    "chk_booking_person": "A booking must be made by exactly one person: a student or a faculty member.",
    "chk_issue_person": "Equipment must be issued to exactly one person: a student or a faculty member.",
    "chk_capacity": "Capacity must be greater than zero.",
    "chk_equipment_qty": "Available quantity must stay between 0 and the total quantity.",
    "chk_issue_dates": "Due and return dates cannot be before the issue date.",
    "chk_issue_return": "A returned item must have a return date (and only returned items may have one).",
    "chk_maint_dates": "Completion date cannot be before the reported date.",
    "chk_student_email": "Please enter a valid e-mail address.",
}

CONNECTION_ERRORS = {2003, 2005, 2006, 2013, 1045, 1049}


def explain(err):
    """Return {'message', 'source', 'code'} for a mysql.connector Error (or similar)."""
    code = getattr(err, "errno", None)
    msg = getattr(err, "msg", None) or str(err)

    if code == 1644 or code is None and any(k in msg for k in SIGNAL_SOURCES):
        source = next((s for k, s in SIGNAL_SOURCES.items() if msg.startswith(k)), "Database trigger")
        return {"message": msg if msg.endswith(".") else msg + ".", "source": source, "code": code}
    if code == 3819:
        m = re.search(r"'([A-Za-z0-9_]+)'", msg)
        name = m.group(1) if m else "check constraint"
        return {"message": CHECK_MESSAGES.get(name, "A CHECK constraint rejected the values."),
                "source": f"CHECK constraint {name}", "code": code}
    if code == 1452:
        return {"message": "The selected facility, person or item does not exist.",
                "source": "FOREIGN KEY constraint (referential integrity)", "code": code}
    if code == 1451:
        return {"message": "This record is still referenced by other records, so it cannot be deleted.",
                "source": "FOREIGN KEY ... ON DELETE RESTRICT", "code": code}
    if code == 1062:
        m = re.search(r"Duplicate entry '([^']*)'", msg)
        value = f" '{m.group(1)}'" if m else ""
        return {"message": f"That value{value} already exists - it must be unique.",
                "source": "UNIQUE constraint", "code": code}
    if code == 1048:
        return {"message": "A required value is missing.", "source": "NOT NULL constraint", "code": code}
    if code in (1292, 1366, 1265):
        return {"message": "One of the values has the wrong format (check dates, times and numbers).",
                "source": "Column data type", "code": code}
    if code in CONNECTION_ERRORS:
        return {"message": "CampusHub cannot reach the MySQL database. Check that MySQL is running and the "
                           "settings in .env are correct.", "source": "Database connection", "code": code}
    return {"message": msg, "source": "MySQL", "code": code}
