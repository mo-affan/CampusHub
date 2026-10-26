# CampusHub – Smart Campus Facility, Booking & Inventory Management System

BCSE302P Database Systems Lab · MySQL 8.0 + Python Flask

## What you need

- **MySQL 8.0.16 or newer** (MySQL Community Server) and **MySQL Workbench**
- **Python 3.9+**

## Step 1 – Create the database (MySQL Workbench)

1. Open MySQL Workbench and connect to your local server (usually `root`).
2. **File → Open SQL Script…** and open `sql/01_schema.sql`. Click the lightning bolt ⚡ to run it.
3. Do the same, **in this order**, for:
   - `sql/02_logic.sql` (triggers, stored procedures, views)
   - `sql/03_sample_data.sql`
4. Click the refresh icon in the Schemas panel: you should see `campushub` with 10 tables and 4 views.

(Command-line alternative: `mysql -u root -p < sql/01_schema.sql`, then the same for 02 and 03.)

## Step 2 – Run the web app

Open a terminal **in this folder**.

**Windows**
```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

**macOS / Linux**
```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Open `.env` in any editor and set `DB_PASSWORD` to your MySQL root password. Then:

```
python app.py
```

Open **http://127.0.0.1:5000** in your browser.

## Demo script (for the presentation)

1. **Availability** → date 16 Oct 2026, 10:00–12:00 → 5 facilities free (Anna Seminar Hall is already booked; Networks Lab and Badminton Court are under maintenance).
2. **Book** SJT 301 Classroom, 18 Oct 2026, 14:00–15:00 → *Booking confirmed*.
3. **New booking** for Anna Seminar Hall, 16 Oct 2026, 11:00–13:00 → *Rejected: Time slot overlaps an existing booking*.
4. **Inventory** → issue *Document Camera* (0 left) → *Rejected: No unit of this equipment is available*.
5. **Maintenance** → report a fault in SJT 301 → it becomes UNDER_MAINTENANCE; booking it now is rejected. Click *Mark completed* to reopen it.
6. **Reports** → most-booked facilities, department usage, monthly stats, overdue equipment.

## Screenshot checklist for the report

| Report section | Screenshot |
| --- | --- |
| 4 Database implementation | Workbench Schemas panel showing the 10 tables + 4 views |
| 5.2 User interface | Dashboard, Availability search results, New booking form, Reports page |
| 6.1 TC2 / TC7 / TC11 | The red "Rejected by database" alerts from demo steps 3, 4 and 5 |
| 6.2 Outputs | Reports page, Inventory page (stock + overdue items) |
| 6.3 Concurrency (TC19) | Two Workbench tabs: `CALL sp_create_booking(1, 1, NULL, '2026-10-18', '16:00', '17:00', 'A', @id);` in both – second one errors |

## Project structure

```
app.py            Flask routes (one query or stored-procedure call each)
db.py             MySQL connection pool and query helpers
templates/        Bootstrap 5 pages
sql/01_schema.sql      tables, constraints, indexes
sql/02_logic.sql       5 triggers, 4 stored procedures, 4 views
sql/03_sample_data.sql sample data
sql/04_queries.sql     the 10 report queries (run in Workbench)
```

## Troubleshooting

- `Access denied for user 'root'` → wrong password in `.env`.
- `Unknown database 'campushub'` → run Step 1 first.
- `Check constraint ... is violated` errors never appear on MySQL older than 8.0.16 – upgrade if a test that should fail passes.
- Re-running `01_schema.sql` drops and recreates the database (all changes reset), then run 02 and 03 again.
