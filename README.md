# CampusHub – Smart Campus Facility, Booking & Inventory Management System

BCSE302P Database Systems Lab · MySQL 8.0+ (tested target: MySQL 26.7 on Windows) · Python Flask

Team: Mohammed Affan (24BAI0014) · Hardik Gupta (24BCI0017) · Arham Sadiq K (24BAI0335)

CampusHub keeps every rule in MySQL itself (constraints, triggers, stored procedures, views).
The Flask app is a thin console over the database: when MySQL rejects something, the page shows
the database's own reason and which trigger or constraint raised it.

---

## 1. What you need

- **MySQL 8.0.16 or newer** + **MySQL Workbench** (CHECK constraints need 8.0.16+)
- **Python 3.9+**
- No other installs: the UI uses Bootstrap CSS from a CDN (an offline copy is optional, see 4.3) and no JavaScript libraries.

## 2. First-time setup (empty laptop)

In MySQL Workbench, **File → Open SQL Script…**, run each file with the ⚡ button, **in this order**:

| File | What it does |
| --- | --- |
| `sql/01_schema.sql` | Creates the `campushub` database: 10 tables, constraints, indexes. ⚠ **Drops the database if it already exists.** |
| `sql/02_logic.sql` | 5 triggers, 4 stored procedures, 4 views |
| `sql/03_sample_data.sql` | Small base dataset (8 facilities, 23 bookings) |
| `sql/05_extended_sample_data.sql` | *Optional, recommended for the review:* larger demo dataset (see section 5) |
| `sql/07_add_user_accounts.sql` | The `user_account` table for sign-in (section 6) |

Then the app (PowerShell, inside the project folder):

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
notepad .env        # set DB_PASSWORD, and paste a SECRET_KEY (see 4.1)
python manage_accounts.py create-admin     # first administrator login
python app.py
```

Open **http://127.0.0.1:5000** and sign in.

## 3. Upgrading a laptop that already runs CampusHub (keep your data)

Your existing database stays as it is. **Do not run `01_schema.sql` again** – it drops the database.
The only schema change is one **new** table for logins (`sql/07_add_user_accounts.sql`). It doesn't touch your
existing tables, triggers, procedures, views or rows.

```powershell
cd path\to\CampusHub
git pull                              # or: git fetch origin; git checkout feature/ui-upgrade
venv\Scripts\activate
pip install -r requirements.txt      # same three packages as before
```

Then:

1. Workbench: run `sql/07_add_user_accounts.sql`.
2. Add a `SECRET_KEY` line to `.env` (section 4.1).
3. `python manage_accounts.py create-admin` creates your administrator login. For the review you can also run
   `python manage_accounts.py demo-logins` (section 6.3).
4. `python app.py` and sign in.

(If your folder is not a git clone: `git clone -b feature/ui-upgrade https://github.com/mo-affan/CampusHub.git`,
then copy your old `.env` into the new folder.)

Optional, in Workbench:

1. `sql/05_extended_sample_data.sql` – adds the demo dataset next to your rows (never edits or deletes existing rows).
2. `sql/tests/verify_rules.sql` – runs 20 rule checks on your MySQL and prints PASS/FAIL (cleans up after itself).

## 4. Configuration

### 4.1 `.env`

| Key | Default | Meaning |
| --- | --- | --- |
| `DB_HOST` / `DB_PORT` | `localhost` / `3306` | MySQL server |
| `DB_USER` / `DB_PASSWORD` | `root` / – | MySQL login |
| `DB_NAME` | `campushub` | database name |
| `DB_POOL_SIZE` | `5` | connection-pool size |
| `SECRET_KEY` | – | signs the login cookie. **Set it**: run `python -c "import secrets; print(secrets.token_hex(32))"` and paste the result. Without it the app picks a temporary key and everyone is signed out whenever it restarts. |
| `SESSION_COOKIE_SECURE` | `0` | set to `1` only when CampusHub is served over HTTPS |
| `FLASK_DEBUG` | `0` | `1` shows Flask's debugger (never on a shared network) |

### 4.2 Port already in use

`set FLASK_RUN_PORT=5001` does not apply to `python app.py`; instead run `flask --app app run --port 5001`.

### 4.3 Working without internet (optional)

The page loads Bootstrap's CSS from jsDelivr. For a review room with no Wi-Fi, download it once:

```powershell
mkdir static\vendor
Invoke-WebRequest https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css -OutFile static\vendor\bootstrap.min.css
```

The app uses the local file automatically when it exists.

## 5. Demo data (`05` / `06`)

`sql/05_extended_sample_data.sql` adds 5 departments, 3 admins, 60 students, 15 faculty, 22 facilities,
36 equipment items, 138 bookings, 57 equipment issues and 18 maintenance requests.

- **Dates are relative to the day you run it** (6 weeks of history, 3 weeks ahead), so the dashboard is never empty.
- **Rerun-safe:** if the demo data is already there it prints a message and changes nothing.
- **Goes through the real rules:** rows are inserted inside one transaction and pass through the normal
  triggers (T1 overlap/status, T2 stock, T4 maintenance). Any error rolls back everything.
- **Easy to tell apart:** demo people use e-mails ending in `@demo.campushub.edu`.
- **Needs 03 first** (it reuses its departments and facility types) and stops with a clear message otherwise.
- `sql/06_remove_extended_sample_data.sql` removes the demo rows again and leaves your own data untouched
  (equipment your own students borrowed from demo facilities is returned first so stock stays correct).
- To change the dataset, edit and run `python tools/generate_demo_data.py`, which validates every rule before writing both files.

## 6. Sign-in and roles

### 6.1 Who can do what

| | Student | Faculty | Admin |
| --- | :-: | :-: | :-: |
| See facilities, availability timeline | ✔ | ✔ | ✔ |
| Book a facility (always in their own name) | ✔ | ✔ | ✔ (for anyone) |
| See and cancel **their own** bookings | ✔ | ✔ | all bookings |
| See the equipment issued to them | ✔ | ✔ | all issues |
| Report a fault | – | ✔ | ✔ |
| Inventory, maintenance, reports, people, alerts, search, review mode, DB status | – | – | ✔ |
| Create logins, reset passwords, disable / unlock accounts | – | – | ✔ |

Students and faculty see other people's bookings only as "Booked": no names, purposes or links.

### 6.2 How it is secured

- **Passwords** are stored only as salted **scrypt** hashes (Werkzeug) in `user_account.password_hash`, never as text.
- **New and reset passwords are temporary.** The admin sees them once, and the person must choose their own at first sign-in
  (at least 8 characters, with letters and numbers).
- **Lockout:** 5 wrong passwords lock the account for 15 minutes; an admin can unlock it. Unknown logins get the same
  answer, taking the same time, as wrong passwords, so the page doesn't reveal which accounts exist.
- **Sessions:** a signed HttpOnly, SameSite=Lax cookie that lasts 8 hours. The session is renewed at sign-in (no session fixation).
  Changing, resetting or disabling an account signs it out everywhere. Sign-out is POST-only.
- **CSRF tokens** on every form; requests without a valid token are rejected (HTTP 400).
- **Deny by default:** `app.py` lists the pages students and faculty may open; everything else is admin-only (HTTP 403).
  Record-level checks return 404 for someone else's booking, so its existence isn't revealed.
- Bookings by students and faculty always use the signed-in person's id; ids typed into the form are ignored.
- `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy` and `Cache-Control: no-store` headers on signed-in pages.

Not included (future work): password reset by e-mail, two-factor sign-in, an audit log of sign-ins, and rate limiting by IP address.

### 6.3 Account tools

```powershell
python manage_accounts.py create-admin    # first administrator (asks for the e-mail and a password)
python manage_accounts.py reset-admin     # an administrator who is locked out or forgot the password
python manage_accounts.py demo-logins     # DEMO ONLY - see below
python manage_accounts.py status
```

`demo-logins` gives **everyone who has no login** the same password, `Campus@2026`, so you can show each role in the review
(student `24BCE1101`, faculty `F1001`, admin `karthik.admin@campushub.edu`). Anyone who knows that password can sign in
as anyone, so use it only on your own laptop. For real users, create logins from the **Accounts** page instead.

## 7. Features

| Area | What you can do |
| --- | --- |
| **Dashboard** | 8 live KPIs; weekly booking chart; booking-status donut; facility utilization; alerts (overdue, low stock, bookings on closed facilities); recent bookings and maintenance; quick actions |
| **Facilities** | Search, type/building/status/capacity filters, sorting, pagination; add facility; facility page with today's timeline, upcoming bookings, equipment and maintenance history; activate / deactivate |
| **Availability** | Day timeline of every facility with the "now" line; free-facility search for a date and time range; previous/next day |
| **Bookings** | Tabs (upcoming / needs closing / completed / cancelled / all), filters, reference search (`BK-000021`); new-booking form showing the facility's schedule for the chosen day and warning about clashes before you submit; booking detail page; cancel (with confirmation) and complete; close all past bookings in one step |
| **Inventory** | Stock bars, low/out-of-stock flags, issue equipment, overdue returns, issue history with current/overdue/returned tabs, return |
| **Maintenance** | Report a fault, start work, complete; status tabs; days-open indicator; list of facilities out of service |
| **People** | Students, faculty and admins with booking counts; add a student |
| **Reports** | Filter by date range, department, facility type and booking status; 9 report blocks; 11 CSV exports |
| **Global search** | Facilities, bookings, people, equipment and maintenance from the top bar (press `/`) |
| **Alerts** | Overdue returns, low stock, bookings that clash with maintenance, open maintenance, bookings needing closure |
| **DB status** | Server version, connection latency, row counts per table, list of triggers / procedures / views / indexes |
| **Review mode** | A guided walk-through of every rule with live buttons (section 9) |
| **Sign-in** | Student / faculty / admin logins, personal home page, "My bookings", "My equipment", fault reporting, Accounts page (section 6) |

## 8. Where each DBMS concept appears

| Feature | Concept | Object |
| --- | --- | --- |
| New booking | Stored procedure, transaction, row lock (`SELECT … FOR UPDATE`), COMMIT/ROLLBACK | `sp_create_booking` |
| Double-booking rejected | BEFORE INSERT trigger, interval overlap `start < other.end AND end > other.start`, `SIGNAL` | `trg_booking_before_insert` (T1) |
| Facility under maintenance can't be booked | Trigger reading another table's status | T1 |
| End before start / both student and faculty | CHECK constraints | `chk_booking_time`, `chk_booking_person` |
| Unknown facility or person | Foreign keys | `fk_booking_*` |
| Delete a facility with bookings | `ON DELETE RESTRICT` | foreign keys |
| Duplicate e-mail / registration no. | UNIQUE constraints | `student`, `faculty`, `admin` |
| Issue equipment | Procedure + AFTER INSERT trigger lowering stock; rejects when stock is 0 | `sp_issue_equipment`, T2 |
| Return equipment | AFTER UPDATE trigger restoring stock | `sp_return_equipment`, T3 |
| Fault report closes facility | AFTER INSERT trigger | `sp_record_maintenance`, T4 |
| Last request completed reopens facility | AFTER UPDATE trigger with `NOT EXISTS` | T5 |
| Utilization, stock, overdue lists | Views, joins, aggregates | `vw_facility_usage`, `vw_equipment_availability`, `vw_current_issues`, `vw_maintenance_history` |
| Reports | `GROUP BY`, `HAVING`, `CASE`, date functions, subqueries | `queries.py` → `report_*` |
| Fast overlap check | Composite index | `idx_booking_slot` |
| Search / filters | Parameterized queries, `LIKE … ESCAPE` | all of `queries.py` |
| DB status page | `information_schema` | `queries.schema_objects` |
| Logins | New table with CHECK (exactly one owner per role), UNIQUE per person, FKs with RESTRICT; additive migration | `user_account`, `sql/07_add_user_accounts.sql` |
| "My bookings" / privacy | Row-level filtering with a parameterized `WHERE student_id = %s` | `queries.owner_clause` |

## 9. Live demo script (about 8 minutes)

Sign in as an **admin**, then open **Review mode** from the dashboard (`/review`). Every step there has a button that runs the
real operation; the targets (facility, slot, out-of-stock item) are chosen from your current data, so the script always works.

Sign-in demo (about 2 minutes, best in a second browser or a private window):
sign in as a **student**. Show the personal home page and that the menu has no admin pages. Open `/reports` to get
"You don't have access". Make a booking (it is always in your own name). Then in the admin window, open **Accounts**
and reset that student's password: the student's window is signed out on the next click.

1. **Dashboard** – explain that each KPI is a live `COUNT` / view; click "Overdue returns" to drill down.
2. **Availability** – free facilities for tomorrow 10:00–12:00.
3. **Valid booking** – confirmed; open its `BK-…` page and point at "How MySQL stored it".
4. **Double-booking** – same facility, overlapping slot → red *Rejected by MySQL – trigger trg_booking_before_insert*.
5. **Back-to-back** – the slot that starts exactly when the other ends → accepted (strict `<` in the overlap rule).
6. **Facility under maintenance** – rejected by T1.
7. **End time before start** – rejected by CHECK `chk_booking_time`.
8. **Out-of-stock equipment** – rejected by T2; stock unchanged.
9. **Issue and return** – stock goes down (T2) and back up (T3); returning twice is rejected.
10. **Maintenance** – report a fault → facility becomes UNDER_MAINTENANCE (T4); complete → AVAILABLE (T5).
11. **Reports** – change the filters, export a CSV.
12. **SQL injection** – search for `' OR '1'='1` → no rows (parameterized query).
13. **Concurrency** (Workbench, two query tabs; use a facility that is AVAILABLE – Review mode shows the exact ids):
    ```sql
    -- Tab A: take the facility's row lock and add a booking, but do not commit yet
    START TRANSACTION;
    SELECT * FROM campushub.facility WHERE facility_id = 1 FOR UPDATE;
    INSERT INTO campushub.booking (facility_id, student_id, faculty_id, booking_date, start_time, end_time, purpose)
    VALUES (1, 1, NULL, CURDATE() + INTERVAL 30 DAY, '07:00', '08:00', 'lock test A');

    -- Tab B: an overlapping booking through the procedure -> it WAITS on the lock
    CALL campushub.sp_create_booking(1, 2, NULL, CURDATE() + INTERVAL 30 DAY, '07:30', '08:30', 'lock test B', @id);

    -- Tab A
    COMMIT;   -- Tab B continues, sees A's committed row and fails: "Time slot overlaps an existing booking"

    -- Clean up (either tab)
    SET SQL_SAFE_UPDATES = 0;
    DELETE FROM campushub.booking WHERE purpose LIKE 'lock test%';
    SET SQL_SAFE_UPDATES = 1;
    ```

## 10. Testing

- `sql/tests/verify_rules.sql` – 20 automatic PASS/FAIL checks on your MySQL (bookings, overlap, rollback,
  back-to-back, CHECKs, FKs, RESTRICT, UNIQUE, all five triggers, schema-object counts). It uses a throwaway
  facility and dates 400+ days ahead and deletes everything it created.
- See `HANDOVER.md` for the full test record, including what has and has not been run on real MySQL.

## 11. Project structure

```
app.py            Flask routes (thin: read form → call queries.py → render) + access control
auth.py           password hashing, sign-in, sessions, CSRF, role and ownership checks
manage_accounts.py  command-line account tools (first admin, demo logins)
queries.py        every SQL statement (parameterized), pagination, report filters
db.py             MySQL connection pool and helpers
dberrors.py       turns MySQL error codes into readable messages + the trigger/constraint that raised them
charts.py         server-side SVG charts (no JavaScript library)
ui.py             template filters, status badges, icons
templates/        Jinja pages; _macros.html holds the reusable components (KPI card, pager, empty state …)
static/css, js    design system and small progressive enhancements (the app works without JS)
sql/01–04         schema, logic, base data, report queries (unchanged)
sql/05, 06        demo data load / remove
sql/07            migration: user_account table for logins
sql/tests/        verify_rules.sql
tools/            generate_demo_data.py
docs/             report, ER diagram, screenshots (docs/screenshots/ui-upgrade = this version)
```

## 12. Limitations and future work

- Sign-in has no e-mail password reset, no two-factor login and no sign-in audit log (section 6.2). It runs on Flask's
  development server, so for real use put it behind HTTPS with a production server (e.g. waitress) and set `SESSION_COOKIE_SECURE=1`.
- Equipment status `UNDER_REPAIR` is stored but not enforced by T2 (stock alone decides).
- No recurring bookings, waiting lists or approval workflow.
- Past bookings are not completed automatically; use "Close past bookings" on the Bookings page
  (a MySQL `EVENT` could do it nightly).
- No e-mail or push notifications; the Alerts page lists what needs attention.
- Charts are static SVG (no hover tooltips).

## 13. Troubleshooting

- `Access denied for user 'root'` → wrong `DB_PASSWORD` in `.env`.
- `Unknown database 'campushub'` → run section 2 first.
- "The database did not respond as expected" page → MySQL service not running (Windows: Services → MySQL… → Start) or wrong `.env` settings.
- `Run 03_sample_data.sql before 05_extended_sample_data.sql` → load 03 first.
- `Demo data is already loaded` → nothing to do; run 06 first if you want to reload it.
- Rules that should fail but pass → MySQL older than 8.0.16 ignores CHECK constraints.
- Sign-in page says "Logins are not set up yet" → run `sql/07_add_user_accounts.sql`, then `python manage_accounts.py create-admin`.
- "No accounts exist yet" → `python manage_accounts.py create-admin`.
- Locked out as the only admin → `python manage_accounts.py reset-admin`.
- Signed out every time the app restarts → set `SECRET_KEY` in `.env`.
- "This form has expired" → you were signed out or the page was open too long; reload it and submit again.
