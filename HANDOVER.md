# CampusHub UI & feature upgrade – handover

Branch: `feature/ui-upgrade` (created from `main`; `main` is unchanged). Date: 26 Oct 2026.

## 1. Safety notes

- **No schema change, no migration.** Tables, columns, constraints, indexes, the 5 triggers, 4 procedures and
  4 views in `sql/01_schema.sql` and `sql/02_logic.sql` are untouched. The new app reads `information_schema` only for the status page.
- `sql/01`–`04` are unchanged. Never rerun `01_schema.sql` on a database you want to keep: it drops `campushub`.
- `05` only inserts (rerun-safe, one transaction, rollback on any error). `06` deletes only rows it can identify as demo data.
- Every user-supplied value goes through `%s` parameters; sort columns come from whitelists; `LIKE` input is escaped.

## 2. Files

**New**

| File | Purpose |
| --- | --- |
| `queries.py` | All SQL (moved out of `app.py`), pagination, filters, reports, search, alerts, status |
| `dberrors.py` | MySQL error → readable message + which trigger/constraint raised it |
| `charts.py` | Server-side SVG bar and donut charts |
| `ui.py` | Jinja filters (`ref`, `hm`, `date`, `rel_day`, `badge` …), icons, URL helpers |
| `static/css/campushub.css` | Design system (navy/indigo + teal), responsive layout |
| `static/js/campushub.js` | Sidebar, confirmation dialogs, booking-form schedule preview, small helpers (pages work without JS) |
| `templates/_macros.html` | Reusable components: page header, KPI card, empty state, pager, sortable header, stock bar, person picker … |
| `templates/booking_detail.html`, `facility_detail.html`, `issues.html`, `people.html`, `alerts.html`, `search.html`, `status.html`, `review.html`, `error.html` | New pages |
| `sql/05_extended_sample_data.sql`, `sql/06_remove_extended_sample_data.sql` | Demo data load / remove |
| `sql/tests/verify_rules.sql` | 20 PASS/FAIL rule tests to run on MySQL |
| `tools/generate_demo_data.py` | Generates and validates 05 and 06 |
| `docs/screenshots/ui-upgrade/*.png` | 23 screenshots of this version (19 desktop, 4 phone) |
| `HANDOVER.md` | This file |

**Modified**: `app.py` (routes rewritten around `queries.py`; all old URLs still work), `db.py` (pool helpers, `ping`),
`.env.example` (optional keys documented), `README.md`, and the templates `base.html`, `dashboard.html`, `facilities.html`,
`availability.html`, `bookings.html`, `booking_form.html`, `equipment.html`, `maintenance.html`, `reports.html`.

**Replaced**: `templates/students.html` → `templates/people.html` (the `/students` URL is the same; it now has students, faculty and admins tabs).

## 3. Test results

### 3.1 What was run, and where

MySQL could not be installed in the build environment (package and container registries are blocked there).
The app was therefore tested against a **SQLite stand-in** that recreates the CampusHub schema, the same 5 triggers
and 4 views, Python copies of the 4 stored procedures, and returns the same MySQL error numbers (1644, 3819, 1452, 1451, 1062).
`03_sample_data.sql` and `05` were loaded into it from the real files. This proves the Flask code, templates, queries'
logic and error handling, **not** MySQL itself.

**Result: 43 passed, 0 failed** (Flask test client, full HTTP requests):

| # | Test | Result |
| --- | --- | --- |
| S1 | All 29 pages render (HTTP 200), also on an empty database | PASS |
| S2 | Unknown record → 404 page | PASS |
| 1, 1b | Dashboard KPIs equal direct `COUNT`s; charts drawn | PASS |
| 2–2d | Facility search, capacity filter + sort, status filter, pagination | PASS |
| 3 | Valid booking → confirmed, opens its detail page | PASS |
| 4, 17a | Overlap rejected by T1; no partial row left | PASS |
| 5 | Back-to-back booking accepted | PASS |
| 6 | Facility under maintenance rejected | PASS |
| 7–7d | End < start (CHECK), invalid facility / person (FK), malformed date | PASS |
| 7e | Cancelled slot can be rebooked | PASS |
| 8, 9, 17b | Issue lowers stock (T2); out of stock rejected; stock unchanged after rejection | PASS |
| 10, 11 | Return restores stock (T3); double return rejected | PASS |
| 12, 12b | T4 closes facility; T5 reopens only after the last open request | PASS |
| 13–13c | Report totals, most-booked facility, department filter match independent queries | PASS |
| 14–14d | Bookings pagination, date filter, `BK-` reference search, overdue tab | PASS |
| 15–15c | All 11 CSV exports; formula injection neutralised; filters respected | PASS |
| 16–16c | `' OR '1'='1` in search, filters and sort is harmless; `%` / `_` matched literally | PASS |
| 18, 18b | Database down → friendly 503 page; empty states | PASS |
| R1 | Review mode finds live demo targets | PASS |
| D1, D2 | `06` leaves exactly the original 03 data; `05` loads again after `06` | PASS |

Also checked: 23 screenshots (desktop 1440 px and phone 390 px) reviewed visually; all templates have balanced tags.

### 3.2 Not yet run on real MySQL (please do this once)

| Item | How to verify on your laptop |
| --- | --- |
| Triggers, procedures, constraints with this app | Workbench → open `sql/tests/verify_rules.sql` → ⚡. Expect 20 rows, all `PASS`, and a second result tab showing `passed 20, failed 0`. |
| `05` on MySQL 26.7 | Run `sql/05_extended_sample_data.sql`. Expect no error; then `SELECT COUNT(*) FROM booking;` grows by 138. Running it a second time prints "Demo data is already loaded". |
| `06` on MySQL | Optional: run it, check counts return to your previous values, then run `05` again. |
| App on MySQL | `python app.py`, open every sidebar page, then follow Review mode steps 3–10. Each rejection must show "Rejected by MySQL" with the trigger/constraint name. |
| Concurrency | Manual two-tab steps in README section 8, step 13. |
| `information_schema` page | `/status` should list 5 triggers, 4 procedures, 4 views. |

If anything fails, copy the exact error text; the cause will be in MySQL's behaviour (the part the stand-in can't prove).

## 4. Known limitations

See README section 11: no authentication / roles (the UI says "no login"; not presented as security),
`UNDER_REPAIR` not enforced by T2, no recurring bookings, past bookings closed by a button rather than a scheduled event,
no notifications, static charts.
