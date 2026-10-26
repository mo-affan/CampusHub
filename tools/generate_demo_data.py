"""Generate sql/05_extended_sample_data.sql and sql/06_remove_extended_sample_data.sql.

The demo dataset is deterministic (fixed random seed) and every date is stored
as an offset from the day the script is loaded (CURDATE()), so the dashboard
always shows recent history and upcoming bookings no matter when you run it.

Before writing any SQL the generator checks the same rules MySQL enforces:
  * no two CONFIRMED bookings of one facility overlap (trigger T1)
  * no booking for a facility that is unavailable at load time or that was under
    maintenance on that day (keeps history consistent with triggers T4/T5)
  * end_time > start_time, exactly one of student/faculty (CHECK constraints)
  * issued units never exceed stock (trigger T2), issue/due/return dates valid
  * every referenced name exists (foreign keys)

Run:  python tools/generate_demo_data.py
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEMO_DOMAIN = "demo.campushub.edu"
SEED = 20261026

# --------------------------------------------------------------------------- master data
EXISTING_DEPARTMENTS = [
    "Computer Science and Engineering", "AI and Machine Learning",
    "Electronics and Communication", "Mechanical Engineering", "Business School",
]
NEW_DEPARTMENTS = [
    "Civil Engineering", "Electrical and Electronics Engineering", "Biotechnology",
    "Information Technology", "Physical Sciences",
]
DEPT_CODE = {
    "Computer Science and Engineering": "BCE", "AI and Machine Learning": "BAI",
    "Electronics and Communication": "BEC", "Mechanical Engineering": "BME",
    "Business School": "BBA", "Civil Engineering": "BCL",
    "Electrical and Electronics Engineering": "BEE", "Biotechnology": "BBT",
    "Information Technology": "BIT", "Physical Sciences": "BPS",
}
NEW_FACILITY_TYPES = ["Conference Room"]

ADMINS = [  # name, email-local, role
    ("A. Ramesh", "ramesh.a", "FACILITY_ADMIN"),
    ("K. Deepa", "deepa.k", "FACILITY_ADMIN"),
    ("J. Thomas", "thomas.j", "DEPARTMENT_ADMIN"),
]

FIRST = ["Aditya", "Kavya", "Rahul", "Ishita", "Varun", "Nandini", "Arjun", "Pooja", "Siddharth",
         "Tanvi", "Harish", "Lakshmi", "Nikhil", "Divya", "Pranav", "Sanjana", "Karthik", "Riya",
         "Abhinav", "Meghana", "Rohit", "Shreya", "Vikas", "Anjali", "Yash", "Keerthana", "Manoj",
         "Bhavana", "Gautam", "Sahana", "Irfan", "Neha", "Dev", "Aishwarya", "Kiran", "Fathima",
         "Suresh", "Priyanka", "Amit", "Swathi"]
LAST = ["Menon", "Iyer", "Reddy", "Nair", "Sharma", "Rao", "Patel", "Krishnan", "Das", "Pillai",
        "Kulkarni", "Joshi", "Verma", "Bhat", "Chatterjee", "Shetty", "Varma", "Hegde", "Agarwal",
        "Naidu", "Mishra", "Gupta", "Kumar", "Thomas", "Sinha", "Banerjee", "Ahmed", "Mehta"]
FACULTY_NAMES = ["Dr. Ananya Krishnan", "Dr. Vivek Raman", "Dr. Sunita Rao", "Dr. Pradeep Nair",
                 "Dr. Meera Subramanian", "Dr. Ashok Verma", "Dr. Kavitha Iyer", "Dr. Rajiv Menon",
                 "Dr. Sneha Kulkarni", "Dr. Farhan Ali", "Dr. Geetha Ramesh", "Dr. Manish Tiwari",
                 "Dr. Revathi Sundar", "Dr. Joseph Mathew", "Dr. Leela Prasad"]
DESIGNATIONS = ["Professor", "Associate Professor", "Assistant Professor", "Assistant Professor (Senior)"]


@dataclass
class Facility:
    name: str
    ftype: str
    building: str
    capacity: int
    admin: str            # admin email-local
    weight: float         # how busy (0..1)
    status: str = "AVAILABLE"
    equipment: list = field(default_factory=list)   # (name, quantity)


FACILITIES = [
    Facility("PRP 104 Classroom", "Classroom", "PRP", 60, "ramesh.a", 0.55, equipment=[("Document Camera", 2)]),
    Facility("PRP 216 Classroom", "Classroom", "PRP", 72, "ramesh.a", 0.45),
    Facility("TT 312 Classroom", "Classroom", "TT", 60, "ramesh.a", 0.35),
    Facility("TT 120 Classroom", "Classroom", "TT", 54, "ramesh.a", 0.20),
    Facility("GDN 118 Classroom", "Classroom", "GDN", 48, "deepa.k", 0.10),
    Facility("SMV 205 Classroom", "Classroom", "SMV", 90, "deepa.k", 0.40),
    Facility("SJT 516 Data Science Lab", "Computer Lab", "SJT", 36, "ramesh.a", 0.85,
             equipment=[("GPU Workstation", 6), ("Raspberry Pi 5 Kit", 12), ("Logitech Webcam", 8)]),
    Facility("SJT 619 IoT Lab", "Computer Lab", "SJT", 32, "ramesh.a", 0.60,
             equipment=[("Arduino Uno Kit", 20), ("ESP32 Dev Board", 15), ("Digital Multimeter", 10)]),
    Facility("TT 418 Embedded Systems Lab", "Computer Lab", "TT", 30, "deepa.k", 0.50,
             equipment=[("Oscilloscope", 4), ("Logic Analyzer", 3), ("Soldering Station", 6)]),
    Facility("MGB 302 CAD Lab", "Computer Lab", "MGB", 40, "deepa.k", 0.45,
             equipment=[("3D Mouse", 5), ("Graphics Tablet", 8), ("A3 Plotter", 1)]),
    Facility("GDN 210 Biotech Lab", "Computer Lab", "GDN", 24, "deepa.k", 0.30,
             equipment=[("Micropipette Set", 10), ("Centrifuge", 2), ("Microscope", 8)]),
    Facility("PRP Seminar Hall", "Seminar Hall", "PRP", 140, "thomas.j", 0.80,
             equipment=[("Laser Projector", 2), ("Wireless Microphone", 8), ("Podium Laptop", 2)]),
    Facility("GDN Seminar Hall", "Seminar Hall", "GDN", 100, "thomas.j", 0.40,
             equipment=[("Projector", 2), ("Collar Microphone", 6)]),
    Facility("TT Mini Seminar Hall", "Seminar Hall", "TT", 60, "thomas.j", 0.35,
             equipment=[("Smart Display 75 inch", 1), ("Portable Speaker", 3)]),
    Facility("Lakeview Auditorium", "Auditorium", "Main Block", 450, "thomas.j", 0.50,
             equipment=[("Stage Light Set", 4), ("Line Array Speaker", 4), ("Cordless Mic Kit", 10)]),
    Facility("Basketball Court A", "Sports Facility", "Sports Complex", 30, "ramesh.a", 0.75,
             equipment=[("Basketball", 20), ("Scoreboard Remote", 1)]),
    Facility("Table Tennis Hall", "Sports Facility", "Sports Complex", 16, "ramesh.a", 0.55,
             equipment=[("TT Racket", 16), ("TT Ball Box", 10)]),
    Facility("Indoor Gym", "Sports Facility", "Sports Complex", 50, "ramesh.a", 0.40,
             equipment=[("Resistance Band Set", 12), ("Stopwatch", 6)]),
    Facility("Swimming Pool", "Sports Facility", "Sports Complex", 40, "ramesh.a", 0.45,
             equipment=[("Kickboard", 20)]),
    Facility("Admin Block Conference Room", "Conference Room", "Main Block", 24, "thomas.j", 0.30,
             equipment=[("Video Conference Kit", 1), ("Presentation Clicker", 4)]),
    Facility("Research Park Board Room", "Conference Room", "Research Park", 18, "thomas.j", 0.08,
             equipment=[("Conference Phone", 1)]),
    Facility("Old Workshop Hall", "Classroom", "Workshop Block", 80, "deepa.k", 0.0, status="INACTIVE"),
]
FAC = {f.name: f for f in FACILITIES}

# Maintenance: (facility, admin, description, reported_offset, completed_offset or None, status)
MAINTENANCE = [
    ("SJT 516 Data Science Lab", "ramesh.a", "Two GPU workstations overheating", -58, -55, "COMPLETED"),
    ("SJT 516 Data Science Lab", "ramesh.a", "Network switch port failures", -24, -23, "COMPLETED"),
    ("PRP Seminar Hall", "thomas.j", "Projector lamp replacement", -50, -49, "COMPLETED"),
    ("PRP Seminar Hall", "thomas.j", "Sound system humming", -17, -15, "COMPLETED"),
    ("Lakeview Auditorium", "thomas.j", "Stage curtain motor jammed", -40, -36, "COMPLETED"),
    ("Basketball Court A", "ramesh.a", "Backboard ring loose", -33, -32, "COMPLETED"),
    ("Basketball Court A", "ramesh.a", "Court floodlight not working", -9, -8, "COMPLETED"),
    ("MGB 302 CAD Lab", "deepa.k", "AC unit leaking water", -46, -43, "COMPLETED"),
    ("GDN 210 Biotech Lab", "deepa.k", "Fume hood fan inspection", -28, -26, "COMPLETED"),
    ("SMV 205 Classroom", "deepa.k", "Broken chairs replaced", -21, -20, "COMPLETED"),
    ("Indoor Gym", "ramesh.a", "Treadmill belt slipping", -13, -11, "COMPLETED"),
    ("TT 312 Classroom", "ramesh.a", "Whiteboard replacement", -37, -36, "COMPLETED"),
    ("Admin Block Conference Room", "thomas.j", "Video conference camera firmware update", -6, -5, "COMPLETED"),
    ("Swimming Pool", "ramesh.a", "Pool tiles cracked near deep end", -52, -44, "COMPLETED"),
    ("Table Tennis Hall", "ramesh.a", "Table net clamps broken", -19, -18, "COMPLETED"),
    # still open -> these facilities end up UNDER_MAINTENANCE (trigger T4)
    ("TT 418 Embedded Systems Lab", "deepa.k", "Bench power supplies tripping", -4, None, "IN_PROGRESS"),
    ("Swimming Pool", "ramesh.a", "Filtration pump making noise", -3, None, "REPORTED"),
    ("Swimming Pool", "ramesh.a", "Chlorine dosing unit fault", -2, None, "IN_PROGRESS"),
]

PURPOSES = {
    "Classroom": ["Extra class – Data Structures", "Tutorial – Engineering Mathematics", "Quiz preparation",
                  "Project review meeting", "Club meeting – Coding Club", "Remedial class – Physics",
                  "Placement aptitude session", "Study group – DBMS"],
    "Computer Lab": ["Lab session – Machine Learning", "Hackathon practice", "Workshop on Docker",
                     "Capstone project work", "Coding contest", "IoT mini-project build", "CAD practice session",
                     "Research experiment run"],
    "Seminar Hall": ["Guest lecture – Cloud Security", "Department seminar", "Workshop on Research Writing",
                     "IEEE student branch talk", "Club orientation", "Alumni interaction", "Startup pitch session"],
    "Auditorium": ["Cultural fest rehearsal", "Convocation rehearsal", "Tech talk – Generative AI",
                   "Annual day practice", "Freshers orientation"],
    "Sports Facility": ["Team practice", "Inter-hostel match", "Coaching session", "Fitness training",
                        "Tournament qualifier"],
    "Conference Room": ["Faculty meeting", "PhD progress review", "Industry MoU discussion",
                        "Accreditation planning", "Interview panel"],
}
SLOTS = {  # (start, end) in HH:MM
    "Classroom": [("08:00", "09:00"), ("09:00", "10:00"), ("10:00", "11:00"), ("11:00", "12:00"),
                  ("14:00", "15:00"), ("15:00", "16:00"), ("16:00", "17:00")],
    "Computer Lab": [("09:00", "11:00"), ("11:00", "13:00"), ("14:00", "16:00"), ("16:00", "18:00")],
    "Seminar Hall": [("09:30", "11:30"), ("10:00", "12:00"), ("12:00", "13:00"), ("14:00", "16:00"),
                     ("15:00", "17:00")],
    "Auditorium": [("09:00", "12:00"), ("14:00", "17:00"), ("17:00", "20:00")],
    "Sports Facility": [("06:30", "08:00"), ("16:00", "17:30"), ("17:30", "19:00"), ("19:00", "20:30")],
    "Conference Room": [("10:00", "11:00"), ("11:30", "12:30"), ("15:00", "16:00"), ("16:30", "17:30")],
}
DAY_RANGE = range(-42, 22)       # six weeks back, three weeks ahead


def minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def q(s) -> str:
    """SQL string literal (single quotes doubled; backslashes doubled for MySQL)."""
    return "'" + str(s).replace("\\", "\\\\").replace("'", "''") + "'"


# --------------------------------------------------------------------------- model building
def build_model():
    rnd = random.Random(SEED)

    # students: 6 per department -> 60
    students, used_emails = [], set()
    for d_i, dept in enumerate(EXISTING_DEPARTMENTS + NEW_DEPARTMENTS):
        for k in range(6):
            first, last = rnd.choice(FIRST), rnd.choice(LAST)
            year = 22 + (k % 4)
            reg = f"{year}{DEPT_CODE[dept]}{2000 + d_i * 10 + k}"
            local = f"{first}.{last}".lower()
            email = f"{local}@{DEMO_DOMAIN}"
            n = 2
            while email in used_emails:
                email = f"{local}{n}@{DEMO_DOMAIN}"
                n += 1
            used_emails.add(email)
            phone = f"9{rnd.randint(100000000, 999999999)}"
            students.append({"reg": reg, "name": f"{first} {last}", "email": email, "phone": phone, "dept": dept})

    faculty = []
    for i, name in enumerate(FACULTY_NAMES):
        dept = (EXISTING_DEPARTMENTS + NEW_DEPARTMENTS)[i % 10]
        local = name.replace("Dr. ", "").lower().replace(" ", ".")
        faculty.append({"code": f"F{2001 + i}", "name": name, "email": f"{local}@{DEMO_DOMAIN}",
                        "designation": DESIGNATIONS[i % len(DESIGNATIONS)], "dept": dept})

    # facility closed windows (maintenance periods) per facility: list of (start_off, end_off)
    closed = {}
    open_from = {}
    for fac, _a, _d, rep, comp, status in MAINTENANCE:
        if comp is None:
            open_from[fac] = min(open_from.get(fac, 99), rep)
        else:
            closed.setdefault(fac, []).append((rep, comp))

    # bookings
    bookings = []
    taken = {}   # (facility, day) -> list of (start_min, end_min)
    for day in DAY_RANGE:
        for f in FACILITIES:
            if f.status != "AVAILABLE" or f.weight == 0:
                continue
            if f.name in open_from and day >= open_from[f.name]:
                continue                                   # facility closed for open maintenance
            if any(a <= day <= b for a, b in closed.get(f.name, [])):
                continue                                   # closed during completed repair
            p = f.weight * 0.19
            if rnd.random() > p:
                continue
            count = 1 + (rnd.random() < f.weight * 0.5)
            slots = SLOTS[f.ftype][:]
            rnd.shuffle(slots)
            for start, end in slots[:count]:
                s, e = minutes(start), minutes(end)
                if any(s < b and e > a for a, b in taken.get((f.name, day), [])):
                    continue
                taken.setdefault((f.name, day), []).append((s, e))
                use_faculty = f.ftype in ("Seminar Hall", "Auditorium", "Conference Room") and rnd.random() < 0.7 \
                    or rnd.random() < 0.15
                person = rnd.choice(faculty) if use_faculty else rnd.choice(students)
                if day < 0:
                    status = "CANCELLED" if rnd.random() < 0.12 else "COMPLETED"
                else:
                    status = "CANCELLED" if rnd.random() < 0.10 else "CONFIRMED"
                lead_days = rnd.randint(1, 10)
                created_hours = max(2, (lead_days - day) * 24 + rnd.randint(0, 20)) if day >= 0 \
                    else (lead_days - day) * 24 + rnd.randint(0, 20)
                bookings.append({"facility": f.name, "day": day, "start": start, "end": end,
                                 "purpose": rnd.choice(PURPOSES[f.ftype]), "status": status,
                                 "reg": person.get("reg"), "code": person.get("code"),
                                 "created_hours": created_hours})

    # guaranteed demo situations ------------------------------------------------
    def force(fac, day, start, end, purpose, status, person):
        s, e = minutes(start), minutes(end)
        lst = taken.setdefault((fac, day), [])
        clash = [b for b in bookings if b["facility"] == fac and b["day"] == day
                 and minutes(b["start"]) < e and minutes(b["end"]) > s]
        for b in clash:
            bookings.remove(b)
            lst.remove((minutes(b["start"]), minutes(b["end"])))
        lst.append((s, e))
        bookings.append({"facility": fac, "day": day, "start": start, "end": end, "purpose": purpose,
                         "status": status, "reg": person.get("reg"), "code": person.get("code"),
                         "created_hours": rnd.randint(30, 120)})

    # back-to-back pair (allowed by the overlap rule)
    force("PRP Seminar Hall", 2, "10:00", "12:00", "Guest lecture – Cloud Security", "CONFIRMED", faculty[0])
    force("PRP Seminar Hall", 2, "12:00", "13:00", "Speaker lunch Q&A", "CONFIRMED", faculty[1])
    # bookings today so the dashboard has activity
    force("SJT 516 Data Science Lab", 0, "16:00", "18:00", "Capstone project work", "CONFIRMED", students[3])
    force("Basketball Court A", 0, "17:30", "19:00", "Team practice", "CONFIRMED", students[11])
    force("Admin Block Conference Room", 0, "15:00", "16:00", "Accreditation planning", "CONFIRMED", faculty[4])
    # tomorrow: a confirmed booking the review page can try to double-book
    force("Lakeview Auditorium", 1, "14:00", "17:00", "Tech talk – Generative AI", "CONFIRMED", faculty[2])

    bookings.sort(key=lambda b: (b["day"], b["facility"], b["start"]))

    # equipment issues ------------------------------------------------------------
    people = students + faculty

    def pick():
        p = rnd.choice(people)
        return p.get("reg"), p.get("code")

    issues = []
    current = [  # (equipment, count, overdue_count)
        ("A3 Plotter", 1, 0), ("Video Conference Kit", 1, 1), ("Centrifuge", 2, 1),
        ("Oscilloscope", 3, 1), ("GPU Workstation", 5, 1), ("Raspberry Pi 5 Kit", 3, 0),
        ("Arduino Uno Kit", 4, 1), ("Wireless Microphone", 2, 0), ("Basketball", 3, 1),
        ("Graphics Tablet", 2, 0), ("Laser Projector", 1, 0),
    ]
    for name, count, overdue in current:
        for i in range(count):
            reg, code = pick()
            if i < overdue:
                issue_off = -rnd.randint(10, 20)
                due_off = issue_off + rnd.randint(3, 7)            # already past
            else:
                issue_off = -rnd.randint(0, 6)
                due_off = rnd.randint(1, 10)                       # due in the future
            issues.append({"equipment": name, "reg": reg, "code": code, "issue": issue_off, "due": due_off,
                           "ret": None, "status": "ISSUED"})
    history_items = [e for f in FACILITIES for e, _qty in f.equipment]
    for _ in range(30):
        name = rnd.choice(history_items)
        reg, code = pick()
        issue_off = -rnd.randint(8, 70)
        due_off = issue_off + rnd.randint(2, 14)
        late = rnd.random() < 0.2
        ret_off = min(-1, due_off + (rnd.randint(1, 4) if late else -rnd.randint(0, due_off - issue_off)))
        ret_off = max(ret_off, issue_off)
        issues.append({"equipment": name, "reg": reg, "code": code, "issue": issue_off, "due": due_off,
                       "ret": ret_off, "status": "RETURNED"})
    issues.sort(key=lambda r: r["issue"])

    return {"students": students, "faculty": faculty, "bookings": bookings, "issues": issues}


# --------------------------------------------------------------------------- validation
def validate(model):
    errors = []
    regs = {s["reg"] for s in model["students"]}
    codes = {f["code"] for f in model["faculty"]}
    if len(regs) != len(model["students"]):
        errors.append("duplicate registration numbers")
    if len({s["email"] for s in model["students"]} | {f["email"] for f in model["faculty"]}) != \
            len(model["students"]) + len(model["faculty"]):
        errors.append("duplicate e-mails")
    for s in model["students"]:
        if len(s["reg"]) > 15:
            errors.append(f"reg too long {s['reg']}")
    open_from, closed = {}, {}
    for fac, admin, _d, rep, comp, status in MAINTENANCE:
        if fac not in FAC:
            errors.append(f"maintenance facility missing {fac}")
        if admin not in {a[1] for a in ADMINS}:
            errors.append(f"maintenance admin missing {admin}")
        if comp is not None and comp < rep:
            errors.append(f"completion before report {fac}")
        if (comp is None) != (status != "COMPLETED"):
            errors.append(f"status/completion mismatch {fac}")
        if comp is None:
            open_from[fac] = min(open_from.get(fac, 99), rep)
        else:
            closed.setdefault(fac, []).append((rep, comp))
    by_slot = {}
    for b in model["bookings"]:
        f = FAC.get(b["facility"])
        if f is None:
            errors.append(f"booking facility missing {b['facility']}")
            continue
        if f.status != "AVAILABLE":
            errors.append(f"booking on non-available facility {f.name}")
        if minutes(b["end"]) <= minutes(b["start"]):
            errors.append(f"bad times {b}")
        if (b["reg"] is None) == (b["code"] is None):
            errors.append(f"person rule {b}")
        if b["reg"] and b["reg"] not in regs:
            errors.append(f"unknown student {b['reg']}")
        if b["code"] and b["code"] not in codes:
            errors.append(f"unknown faculty {b['code']}")
        if f.name in open_from and b["day"] >= open_from[f.name]:
            errors.append(f"booking during open maintenance {f.name} {b['day']}")
        if any(a <= b["day"] <= c for a, c in closed.get(f.name, [])):
            errors.append(f"booking during repair window {f.name} {b['day']}")
        if b["day"] < 0 and b["status"] == "CONFIRMED":
            errors.append("past booking left CONFIRMED")
        if b["created_hours"] < 1:
            errors.append("created_at in the future")
        by_slot.setdefault((b["facility"], b["day"]), []).append(b)
    for key, lst in by_slot.items():
        conf = [b for b in lst if b["status"] == "CONFIRMED"]
        for i, x in enumerate(conf):
            for y in conf[i + 1:]:
                if minutes(x["start"]) < minutes(y["end"]) and minutes(x["end"]) > minutes(y["start"]):
                    errors.append(f"overlap {key} {x['start']} {y['start']}")
    stock = {e: qty for f in FACILITIES for e, qty in f.equipment}
    issued = {}
    for r in model["issues"]:
        if r["equipment"] not in stock:
            errors.append(f"unknown equipment {r['equipment']}")
        if r["due"] < r["issue"]:
            errors.append(f"due before issue {r}")
        if r["ret"] is not None and r["ret"] < r["issue"]:
            errors.append(f"return before issue {r}")
        if (r["status"] == "RETURNED") != (r["ret"] is not None):
            errors.append(f"return rule {r}")
        if (r["reg"] is None) == (r["code"] is None):
            errors.append(f"issue person rule {r}")
        if r["status"] == "ISSUED":
            issued[r["equipment"]] = issued.get(r["equipment"], 0) + 1
    for e, n in issued.items():
        if n > stock[e]:
            errors.append(f"over-issued {e}: {n} > {stock[e]}")
    eq_names = [e for f in FACILITIES for e, _ in f.equipment]
    if len(eq_names) != len(set(eq_names)):
        errors.append("equipment names must be unique within the demo set")
    return errors


# --------------------------------------------------------------------------- SQL writers
HEADER = """-- =============================================================================
-- CampusHub : 05_extended_sample_data.sql   (generated by tools/generate_demo_data.py)
--
-- Adds a richer DEMO dataset on top of 03_sample_data.sql:
--   {n_dept} new departments, {n_admin} admins, {n_stu} students, {n_fac} faculty, {n_facil} facilities,
--   {n_eq} equipment items, {n_book} bookings, {n_iss} equipment issues, {n_maint} maintenance records.
--
-- * Safe to re-run: if the demo facilities already exist the script stops and changes nothing.
-- * Never touches existing rows. Demo people use e-mails ending in @{domain};
--   demo facilities are listed in 06_remove_extended_sample_data.sql, which removes them again.
-- * All dates are relative to the day you run it (CURDATE()), so the dashboard always shows
--   recent history and upcoming bookings.
-- * Respects every rule: rows go in through the normal triggers (T1 overlap/status check,
--   T2 stock decrement, T4 maintenance status), inside one transaction. Any error = full ROLLBACK.
--
-- Run AFTER 01, 02 and 03.  In MySQL Workbench: open this file and click the lightning bolt.
-- =============================================================================
USE campushub;

DROP PROCEDURE IF EXISTS sp_load_demo_data;
DELIMITER $$
CREATE PROCEDURE sp_load_demo_data()
load_demo: BEGIN
  DECLARE v_missing INT DEFAULT 0;
  DECLARE EXIT HANDLER FOR SQLEXCEPTION
  BEGIN
    ROLLBACK;
    RESIGNAL;
  END;

  IF EXISTS (SELECT 1 FROM facility WHERE facility_name = 'SJT 516 Data Science Lab') THEN
    SELECT 'Demo data is already loaded - nothing changed. Run 06_remove_extended_sample_data.sql first to reload it.' AS message;
    LEAVE load_demo;
  END IF;

  -- Prerequisite: the base data from 03_sample_data.sql (departments and facility types it creates)
  IF (SELECT COUNT(*) FROM department WHERE department_name IN ({base_depts})) < {n_base_depts}
     OR (SELECT COUNT(*) FROM facility_type WHERE type_name IN ({base_types})) < {n_base_types} THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Run 03_sample_data.sql before 05_extended_sample_data.sql';
  END IF;

  START TRANSACTION;
"""

FOOTER = """
  COMMIT;
  SELECT 'Extended demo data loaded.' AS message,
         (SELECT COUNT(*) FROM facility)        AS facilities,
         (SELECT COUNT(*) FROM booking)         AS bookings,
         (SELECT COUNT(*) FROM equipment_issue) AS equipment_issues,
         (SELECT COUNT(*) FROM maintenance)     AS maintenance_records;
END$$
DELIMITER ;

-- Workbench's "Safe Updates" mode would block the set-based DELETE/UPDATE statements; switch it off
-- for this call only and restore your setting afterwards.
SET @campushub_safe_updates = @@SESSION.sql_safe_updates;
SET SESSION sql_safe_updates = 0;
CALL sp_load_demo_data();
SET SESSION sql_safe_updates = @campushub_safe_updates;
DROP PROCEDURE sp_load_demo_data;
"""


def write_load_sql(model) -> str:
    out = []
    w = out.append
    w("  -- 1. Departments and facility types (only the missing ones)")
    for d in NEW_DEPARTMENTS:
        w(f"  INSERT INTO department (department_name) SELECT {q(d)} FROM DUAL "
          f"WHERE NOT EXISTS (SELECT 1 FROM department WHERE department_name = {q(d)});")
    for t in NEW_FACILITY_TYPES:
        w(f"  INSERT INTO facility_type (type_name) SELECT {q(t)} FROM DUAL "
          f"WHERE NOT EXISTS (SELECT 1 FROM facility_type WHERE type_name = {q(t)});")

    w("\n  -- 2. Administrators")
    for name, local, role in ADMINS:
        email = f"{local}@{DEMO_DOMAIN}"
        w(f"  INSERT INTO admin (name, email, role) SELECT {q(name)}, {q(email)}, {q(role)} FROM DUAL "
          f"WHERE NOT EXISTS (SELECT 1 FROM admin WHERE email = {q(email)});")

    w("\n  -- 3. Students (department looked up by name)")
    for s in model["students"]:
        w(f"  INSERT INTO student (registration_no, name, email, phone, department_id) "
          f"SELECT {q(s['reg'])}, {q(s['name'])}, {q(s['email'])}, {q(s['phone'])}, department_id "
          f"FROM department WHERE department_name = {q(s['dept'])} "
          f"AND NOT EXISTS (SELECT 1 FROM student WHERE registration_no = {q(s['reg'])} OR email = {q(s['email'])});")

    w("\n  -- 4. Faculty")
    for f in model["faculty"]:
        w(f"  INSERT INTO faculty (employee_code, name, email, designation, department_id) "
          f"SELECT {q(f['code'])}, {q(f['name'])}, {q(f['email'])}, {q(f['designation'])}, department_id "
          f"FROM department WHERE department_name = {q(f['dept'])} "
          f"AND NOT EXISTS (SELECT 1 FROM faculty WHERE employee_code = {q(f['code'])} OR email = {q(f['email'])});")

    w("\n  -- 5. Facilities (type and managing admin looked up by name / e-mail)")
    for f in FACILITIES:
        email = f"{f.admin}@{DEMO_DOMAIN}"
        w(f"  INSERT INTO facility (facility_name, facility_type_id, admin_id, building, capacity, status) "
          f"SELECT {q(f.name)}, t.facility_type_id, a.admin_id, {q(f.building)}, {f.capacity}, {q(f.status)} "
          f"FROM facility_type t JOIN admin a ON a.email = {q(email)} WHERE t.type_name = {q(f.ftype)};")

    w("\n  -- 6. Equipment (available_qty starts equal to quantity; trigger T2 lowers it on issue)")
    for f in FACILITIES:
        for name, qty in f.equipment:
            w(f"  INSERT INTO equipment (facility_id, equipment_name, quantity, available_qty) "
              f"SELECT facility_id, {q(name)}, {qty}, {qty} FROM facility WHERE facility_name = {q(f.name)};")

    w("""
  -- Sanity check: every lookup above must have matched
  IF (SELECT COUNT(*) FROM facility WHERE facility_name IN ({names})) <> {n} THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Demo load: a facility lookup failed (check 01-03 were run)';
  END IF;""".format(names=", ".join(q(f.name) for f in FACILITIES), n=len(FACILITIES)))

    # bookings via staging table: ids resolved first, then one INSERT ... SELECT per row set
    w("""
  -- 7. Bookings: staged by name, ids resolved, then inserted through trigger T1
  DROP TEMPORARY TABLE IF EXISTS tmp_demo_booking;
  CREATE TEMPORARY TABLE tmp_demo_booking (
    seq INT PRIMARY KEY, facility_name VARCHAR(100), reg_no VARCHAR(15), emp_code VARCHAR(10),
    day_offset INT, start_time TIME, end_time TIME, purpose VARCHAR(200),
    status VARCHAR(10), created_hours INT,
    facility_id INT NULL, student_id INT NULL, faculty_id INT NULL);""")
    rows = []
    for i, b in enumerate(model["bookings"], 1):
        rows.append(f"    ({i}, {q(b['facility'])}, {q(b['reg']) if b['reg'] else 'NULL'}, "
                    f"{q(b['code']) if b['code'] else 'NULL'}, {b['day']}, {q(b['start'])}, {q(b['end'])}, "
                    f"{q(b['purpose'])}, {q(b['status'])}, {b['created_hours']}, NULL, NULL, NULL)")
    w("  INSERT INTO tmp_demo_booking VALUES\n" + ",\n".join(rows) + ";")
    w("""  UPDATE tmp_demo_booking s JOIN facility f ON f.facility_name = s.facility_name SET s.facility_id = f.facility_id;
  UPDATE tmp_demo_booking s JOIN student  st ON st.registration_no = s.reg_no SET s.student_id = st.student_id;
  UPDATE tmp_demo_booking s JOIN faculty  fa ON fa.employee_code  = s.emp_code SET s.faculty_id = fa.faculty_id;
  SELECT COUNT(*) INTO v_missing FROM tmp_demo_booking
   WHERE facility_id IS NULL OR (student_id IS NULL AND faculty_id IS NULL);
  IF v_missing > 0 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Demo load: unresolved booking references';
  END IF;
  INSERT INTO booking (facility_id, student_id, faculty_id, booking_date, start_time, end_time, purpose, status, created_at)
  SELECT facility_id, student_id, faculty_id, CURDATE() + INTERVAL day_offset DAY, start_time, end_time,
         purpose, status, NOW() - INTERVAL created_hours HOUR
  FROM tmp_demo_booking ORDER BY seq;""")

    w("""
  -- 8. Equipment issues: ids resolved first so the INSERT does not read `equipment`
  --    (trigger T2 updates `equipment`; MySQL forbids a statement reading the table its trigger updates)
  DROP TEMPORARY TABLE IF EXISTS tmp_demo_issue;
  CREATE TEMPORARY TABLE tmp_demo_issue (
    seq INT PRIMARY KEY, equipment_name VARCHAR(100), reg_no VARCHAR(15), emp_code VARCHAR(10),
    issue_offset INT, due_offset INT, return_offset INT NULL, status VARCHAR(10),
    equipment_id INT NULL, student_id INT NULL, faculty_id INT NULL);""")
    rows = []
    for i, r in enumerate(model["issues"], 1):
        rows.append(f"    ({i}, {q(r['equipment'])}, {q(r['reg']) if r['reg'] else 'NULL'}, "
                    f"{q(r['code']) if r['code'] else 'NULL'}, {r['issue']}, {r['due']}, "
                    f"{r['ret'] if r['ret'] is not None else 'NULL'}, {q(r['status'])}, NULL, NULL, NULL)")
    w("  INSERT INTO tmp_demo_issue VALUES\n" + ",\n".join(rows) + ";")
    demo_fac_names = ", ".join(q(f.name) for f in FACILITIES)
    w(f"""  UPDATE tmp_demo_issue s
    JOIN equipment e ON e.equipment_name = s.equipment_name
    JOIN facility  f ON f.facility_id = e.facility_id AND f.facility_name IN ({demo_fac_names})
     SET s.equipment_id = e.equipment_id;
  UPDATE tmp_demo_issue s JOIN student st ON st.registration_no = s.reg_no SET s.student_id = st.student_id;
  UPDATE tmp_demo_issue s JOIN faculty fa ON fa.employee_code  = s.emp_code SET s.faculty_id = fa.faculty_id;
  SELECT COUNT(*) INTO v_missing FROM tmp_demo_issue
   WHERE equipment_id IS NULL OR (student_id IS NULL AND faculty_id IS NULL);
  IF v_missing > 0 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Demo load: unresolved equipment issue references';
  END IF;
  INSERT INTO equipment_issue (equipment_id, student_id, faculty_id, issue_date, due_date, return_date, status)
  SELECT equipment_id, student_id, faculty_id, CURDATE() + INTERVAL issue_offset DAY,
         CURDATE() + INTERVAL due_offset DAY,
         IF(return_offset IS NULL, NULL, CURDATE() + INTERVAL return_offset DAY), status
  FROM tmp_demo_issue ORDER BY seq;""")

    w("""
  -- 9. Maintenance: completed history first, then open requests (trigger T4 closes those facilities)
  DROP TEMPORARY TABLE IF EXISTS tmp_demo_maint;
  CREATE TEMPORARY TABLE tmp_demo_maint (
    seq INT PRIMARY KEY, facility_name VARCHAR(100), admin_email VARCHAR(120), issue_description VARCHAR(255),
    reported_offset INT, completed_offset INT NULL, status VARCHAR(12),
    facility_id INT NULL, admin_id INT NULL);""")
    rows = []
    ordered = sorted(MAINTENANCE, key=lambda m: (m[4] is None, m[3]))
    for i, (fac, admin, desc, rep, comp, status) in enumerate(ordered, 1):
        rows.append(f"    ({i}, {q(fac)}, {q(admin + '@' + DEMO_DOMAIN)}, {q(desc)}, {rep}, "
                    f"{comp if comp is not None else 'NULL'}, {q(status)}, NULL, NULL)")
    w("  INSERT INTO tmp_demo_maint VALUES\n" + ",\n".join(rows) + ";")
    w("""  UPDATE tmp_demo_maint s JOIN facility f ON f.facility_name = s.facility_name SET s.facility_id = f.facility_id;
  UPDATE tmp_demo_maint s JOIN admin    a ON a.email = s.admin_email SET s.admin_id = a.admin_id;
  SELECT COUNT(*) INTO v_missing FROM tmp_demo_maint WHERE facility_id IS NULL OR admin_id IS NULL;
  IF v_missing > 0 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Demo load: unresolved maintenance references';
  END IF;
  INSERT INTO maintenance (facility_id, admin_id, issue_description, reported_date, completion_date, status)
  SELECT facility_id, admin_id, issue_description, CURDATE() + INTERVAL reported_offset DAY,
         IF(completed_offset IS NULL, NULL, CURDATE() + INTERVAL completed_offset DAY), status
  FROM tmp_demo_maint ORDER BY seq;

  DROP TEMPORARY TABLE IF EXISTS tmp_demo_booking;
  DROP TEMPORARY TABLE IF EXISTS tmp_demo_issue;
  DROP TEMPORARY TABLE IF EXISTS tmp_demo_maint;""")
    return "\n".join(out)


REMOVE_SQL = """-- =============================================================================
-- CampusHub : 06_remove_extended_sample_data.sql   (generated by tools/generate_demo_data.py)
--
-- Removes ONLY the demo dataset added by 05_extended_sample_data.sql:
--   * the {n_facil} demo facilities listed below, their equipment, bookings, issues and maintenance
--   * demo students, faculty and admins (e-mail ending @{domain}) and their bookings / issues
--   * the demo-only departments and facility type, if nothing else uses them
-- Your original 03 sample data and anything else you added stay untouched, with one exception:
-- if a demo person still had one of YOUR equipment items issued, it is first marked RETURNED
-- (trigger T3 restores your stock) before that demo person's records are removed.
-- A demo admin still referenced by your own facilities/maintenance rows is kept.
-- Runs in one transaction; any error = full ROLLBACK.
-- =============================================================================
USE campushub;

DROP PROCEDURE IF EXISTS sp_remove_demo_data;
DELIMITER $$
CREATE PROCEDURE sp_remove_demo_data()
BEGIN
  DECLARE EXIT HANDLER FOR SQLEXCEPTION
  BEGIN
    ROLLBACK;
    RESIGNAL;
  END;
  START TRANSACTION;

  DROP TEMPORARY TABLE IF EXISTS tmp_rm_fac;
  DROP TEMPORARY TABLE IF EXISTS tmp_rm_eq;
  DROP TEMPORARY TABLE IF EXISTS tmp_rm_stu;
  DROP TEMPORARY TABLE IF EXISTS tmp_rm_fcl;
  CREATE TEMPORARY TABLE tmp_rm_fac (id INT PRIMARY KEY);
  CREATE TEMPORARY TABLE tmp_rm_eq  (id INT PRIMARY KEY);
  CREATE TEMPORARY TABLE tmp_rm_stu (id INT PRIMARY KEY);
  CREATE TEMPORARY TABLE tmp_rm_fcl (id INT PRIMARY KEY);
  INSERT INTO tmp_rm_fac SELECT facility_id FROM facility WHERE facility_name IN ({names});
  INSERT INTO tmp_rm_eq  SELECT e.equipment_id FROM equipment e JOIN tmp_rm_fac t ON t.id = e.facility_id;
  INSERT INTO tmp_rm_stu SELECT student_id FROM student WHERE email LIKE '%@{domain}';
  INSERT INTO tmp_rm_fcl SELECT faculty_id FROM faculty WHERE email LIKE '%@{domain}';

  -- your own (non-demo) equipment still issued to a demo person: return it first (T3 restores stock)
  UPDATE equipment_issue SET status = 'RETURNED', return_date = GREATEST(CURDATE(), issue_date)
   WHERE status = 'ISSUED' AND student_id IN (SELECT id FROM tmp_rm_stu)
     AND equipment_id NOT IN (SELECT id FROM tmp_rm_eq);
  UPDATE equipment_issue SET status = 'RETURNED', return_date = GREATEST(CURDATE(), issue_date)
   WHERE status = 'ISSUED' AND faculty_id IN (SELECT id FROM tmp_rm_fcl)
     AND equipment_id NOT IN (SELECT id FROM tmp_rm_eq);

  -- child rows first (all foreign keys are ON DELETE RESTRICT)
  DELETE FROM equipment_issue WHERE equipment_id IN (SELECT id FROM tmp_rm_eq);
  DELETE FROM equipment_issue WHERE student_id   IN (SELECT id FROM tmp_rm_stu);
  DELETE FROM equipment_issue WHERE faculty_id   IN (SELECT id FROM tmp_rm_fcl);
  DELETE FROM booking         WHERE facility_id  IN (SELECT id FROM tmp_rm_fac);
  DELETE FROM booking         WHERE student_id   IN (SELECT id FROM tmp_rm_stu);
  DELETE FROM booking         WHERE faculty_id   IN (SELECT id FROM tmp_rm_fcl);
  DELETE FROM maintenance     WHERE facility_id  IN (SELECT id FROM tmp_rm_fac);
  DELETE FROM equipment       WHERE equipment_id IN (SELECT id FROM tmp_rm_eq);
  DELETE FROM facility        WHERE facility_id  IN (SELECT id FROM tmp_rm_fac);
  DELETE FROM student         WHERE student_id   IN (SELECT id FROM tmp_rm_stu);
  DELETE FROM faculty         WHERE faculty_id   IN (SELECT id FROM tmp_rm_fcl);
  DELETE FROM admin WHERE email LIKE '%@{domain}'
     AND admin_id NOT IN (SELECT admin_id FROM facility)
     AND admin_id NOT IN (SELECT admin_id FROM maintenance);
  DELETE FROM department WHERE department_name IN ({depts})
     AND department_id NOT IN (SELECT department_id FROM student)
     AND department_id NOT IN (SELECT department_id FROM faculty);
  DELETE FROM facility_type WHERE type_name IN ({types})
     AND facility_type_id NOT IN (SELECT facility_type_id FROM facility);

  DROP TEMPORARY TABLE IF EXISTS tmp_rm_fac;
  DROP TEMPORARY TABLE IF EXISTS tmp_rm_eq;
  DROP TEMPORARY TABLE IF EXISTS tmp_rm_stu;
  DROP TEMPORARY TABLE IF EXISTS tmp_rm_fcl;
  COMMIT;
  SELECT 'Demo data removed.' AS message,
         (SELECT COUNT(*) FROM facility) AS facilities_left,
         (SELECT COUNT(*) FROM booking)  AS bookings_left;
END$$
DELIMITER ;

-- Workbench's "Safe Updates" mode would block the set-based DELETE/UPDATE statements; switch it off
-- for this call only and restore your setting afterwards.
SET @campushub_safe_updates = @@SESSION.sql_safe_updates;
SET SESSION sql_safe_updates = 0;
CALL sp_remove_demo_data();
SET SESSION sql_safe_updates = @campushub_safe_updates;
DROP PROCEDURE sp_remove_demo_data;
"""


def main():
    model = build_model()
    errors = validate(model)
    if errors:
        raise SystemExit("Validation failed:\n  " + "\n  ".join(errors[:30]))
    n_eq = sum(len(f.equipment) for f in FACILITIES)
    base_types = sorted({f.ftype for f in FACILITIES} - set(NEW_FACILITY_TYPES))
    header = HEADER.format(n_dept=len(NEW_DEPARTMENTS), n_admin=len(ADMINS), n_stu=len(model["students"]),
                           n_fac=len(model["faculty"]), n_facil=len(FACILITIES), n_eq=n_eq,
                           n_book=len(model["bookings"]), n_iss=len(model["issues"]),
                           n_maint=len(MAINTENANCE), domain=DEMO_DOMAIN,
                           base_depts=", ".join(q(d) for d in EXISTING_DEPARTMENTS),
                           n_base_depts=len(EXISTING_DEPARTMENTS),
                           base_types=", ".join(q(t) for t in base_types),
                           n_base_types=len(base_types))
    (ROOT / "sql" / "05_extended_sample_data.sql").write_text(
        header + write_load_sql(model) + FOOTER, encoding="utf-8")
    (ROOT / "sql" / "06_remove_extended_sample_data.sql").write_text(
        REMOVE_SQL.format(n_facil=len(FACILITIES), domain=DEMO_DOMAIN,
                          names=", ".join(q(f.name) for f in FACILITIES),
                          depts=", ".join(q(d) for d in NEW_DEPARTMENTS),
                          types=", ".join(q(t) for t in NEW_FACILITY_TYPES)), encoding="utf-8")
    statuses = {}
    for b in model["bookings"]:
        statuses[b["status"]] = statuses.get(b["status"], 0) + 1
    print(f"OK - {len(model['students'])} students, {len(model['faculty'])} faculty, {len(FACILITIES)} facilities, "
          f"{n_eq} equipment, {len(model['bookings'])} bookings {statuses}, {len(model['issues'])} issues "
          f"({sum(r['status'] == 'ISSUED' for r in model['issues'])} current), {len(MAINTENANCE)} maintenance")


if __name__ == "__main__":
    main()
