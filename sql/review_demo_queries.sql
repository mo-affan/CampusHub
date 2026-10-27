-- =============================================================================
-- CampusHub : review_demo_queries.sql   - Workbench proof for every slide of the review deck
--
-- How to use: open this file in MySQL Workbench, put the cursor inside ONE query and press
-- Ctrl+Enter (runs only the statement under the cursor). Each block is labelled with the
-- slide it belongs to. Everything here only READS data, except the optional concurrency
-- demo at the very end (slide 19), which adds two test bookings and deletes them again.
--
-- Demo logins (after: python manage_accounts.py demo-logins), password Campus@2026
--   student 24BCE1101 (Aarav Sharma) · faculty F1001 · admin karthik.admin@campushub.edu
-- =============================================================================
USE campushub;


-- ---------------------------------------------------------------- Slide 4 · Database design
SHOW TABLES;                                   -- 11 tables (10 core + user_account) and 4 views

SHOW CREATE TABLE booking;                     -- PK, 3 foreign keys, 2 CHECKs, index idx_booking_slot


-- ---------------------------------------------------------------- Slide 5 · Rules inside MySQL
SELECT TRIGGER_NAME, ACTION_TIMING, EVENT_MANIPULATION, EVENT_OBJECT_TABLE
FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA = 'campushub'
ORDER BY EVENT_OBJECT_TABLE;                   -- 5 triggers

SELECT ROUTINE_NAME FROM information_schema.ROUTINES
WHERE ROUTINE_SCHEMA = 'campushub' AND ROUTINE_TYPE = 'PROCEDURE';   -- 4 procedures

SELECT TABLE_NAME AS view_name FROM information_schema.VIEWS
WHERE TABLE_SCHEMA = 'campushub';              -- 4 views


-- ---------------------------------------------------------------- Slide 6 · Sign-in and roles
SELECT role, COUNT(*) AS accounts FROM user_account GROUP BY role;

-- run again right after signing in: last_login_at changes; only a hash is stored
SELECT ua.role, COALESCE(s.name, f.name, a.name) AS person,
       LEFT(ua.password_hash, 30) AS stored_hash, ua.failed_attempts, ua.last_login_at
FROM user_account ua
LEFT JOIN student s ON s.student_id = ua.student_id
LEFT JOIN faculty f ON f.faculty_id = ua.faculty_id
LEFT JOIN admin   a ON a.admin_id   = ua.admin_id
ORDER BY ua.last_login_at DESC LIMIT 5;


-- ---------------------------------------------------------------- Slide 7 · Student sees only own data
-- rows returned = the "Upcoming bookings" card on Aarav's home page
SELECT b.booking_id, f.facility_name, b.booking_date, b.start_time, b.end_time
FROM booking b
JOIN facility f ON f.facility_id = b.facility_id
JOIN student  s ON s.student_id  = b.student_id
WHERE s.registration_no = '24BCE1101'
  AND b.status = 'CONFIRMED' AND b.booking_date >= CURDATE()
ORDER BY b.booking_date, b.start_time;


-- ---------------------------------------------------------------- Slides 8, 9, 10 · Bookings
-- latest bookings: new row after a booking; NO new row after a rejected double booking
SELECT b.booking_id, f.facility_name, COALESCE(s.name, fa.name) AS booked_by,
       b.booking_date, b.start_time, b.end_time, b.status
FROM booking b
JOIN facility f ON f.facility_id = b.facility_id
LEFT JOIN student s  ON s.student_id  = b.student_id
LEFT JOIN faculty fa ON fa.faculty_id = b.faculty_id
ORDER BY b.booking_id DESC LIMIT 3;

-- slide 9: the trigger that rejected the double booking
SHOW CREATE TRIGGER trg_booking_before_insert;

-- slide 10: the whole day of that facility (10:00-11:00 and 11:00-12:00 sit side by side; cancelled stays as history)
SELECT x.booking_id, x.start_time, x.end_time, x.status
FROM booking x
JOIN (SELECT facility_id, booking_date FROM booking ORDER BY booking_id DESC LIMIT 1) last
  ON last.facility_id = x.facility_id AND last.booking_date = x.booking_date
ORDER BY x.start_time;


-- ---------------------------------------------------------------- Slides 11, 12 · Equipment (T2 / T3)
-- latest issues with the item's live stock: available_qty drops on issue, rises on return
SELECT ei.issue_id, e.equipment_name, e.quantity, e.available_qty,
       COALESCE(s.name, fa.name) AS issued_to, ei.due_date, ei.status
FROM equipment_issue ei
JOIN equipment e ON e.equipment_id = ei.equipment_id
LEFT JOIN student s  ON s.student_id  = ei.student_id
LEFT JOIN faculty fa ON fa.faculty_id = ei.faculty_id
ORDER BY ei.issue_id DESC LIMIT 3;

-- slide 12: items that MySQL will refuse to issue (stock 0)
SELECT equipment_name, quantity, available_qty, availability_status
FROM equipment WHERE available_qty = 0;


-- ---------------------------------------------------------------- Slide 13 · Reports and views
SELECT facility_name, total_bookings, hours_booked
FROM vw_facility_usage ORDER BY total_bookings DESC LIMIT 5;          -- view + LEFT JOIN + GROUP BY

SELECT d.department_name, COUNT(*) AS bookings
FROM booking b
LEFT JOIN student s  ON s.student_id  = b.student_id
LEFT JOIN faculty fa ON fa.faculty_id = b.faculty_id
JOIN department d ON d.department_id = COALESCE(s.department_id, fa.department_id)
WHERE b.status <> 'CANCELLED'
GROUP BY d.department_name ORDER BY bookings DESC;                    -- bookings by department

SELECT f.facility_name, COUNT(*) AS requests
FROM maintenance m JOIN facility f ON f.facility_id = m.facility_id
GROUP BY f.facility_name HAVING COUNT(*) > 1;                         -- HAVING


-- ---------------------------------------------------------------- Slides 14, 15 · Maintenance (T4 / T5)
-- latest requests next to the facility's live status:
-- after the faculty report -> UNDER_MAINTENANCE (T4); after the admin completes it -> AVAILABLE (T5)
SELECT m.maintenance_id, f.facility_name, f.status AS facility_status,
       m.issue_description, m.status AS request_status, m.reported_date, m.completion_date
FROM maintenance m JOIN facility f ON f.facility_id = m.facility_id
ORDER BY m.maintenance_id DESC LIMIT 3;


-- ---------------------------------------------------------------- Slide 16 · Dashboard numbers
-- each column must equal the matching card on the admin dashboard
SELECT
  (SELECT COUNT(*) FROM facility)                                                    AS total_facilities,
  (SELECT COUNT(*) FROM facility WHERE status = 'AVAILABLE')                         AS available_now,
  (SELECT COUNT(*) FROM booking WHERE status = 'CONFIRMED' AND booking_date >= CURDATE()) AS upcoming,
  (SELECT COUNT(*) FROM booking WHERE status <> 'CANCELLED' AND booking_date = CURDATE()) AS today,
  (SELECT SUM(available_qty) FROM equipment)                                         AS units_available,
  (SELECT COUNT(*) FROM equipment_issue WHERE status = 'ISSUED')                     AS on_loan,
  (SELECT COUNT(*) FROM maintenance WHERE status <> 'COMPLETED')                     AS open_maintenance,
  (SELECT COUNT(*) FROM equipment_issue WHERE status = 'ISSUED' AND due_date < CURDATE()) AS overdue;


-- ---------------------------------------------------------------- Slide 17 · Accounts and security
-- after "Reset password" for Diya Nair: must_change_password = 1, new password_changed_at
SELECT s.name, ua.role, ua.must_change_password, ua.is_active, ua.failed_attempts,
       ua.locked_until, ua.password_changed_at
FROM user_account ua JOIN student s ON s.student_id = ua.student_id
WHERE s.registration_no IN ('24BCE1101', '24BCE1102');

-- the CHECK that ties every login to exactly one person
SELECT CONSTRAINT_NAME, CHECK_CLAUSE FROM information_schema.CHECK_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA = 'campushub' AND CONSTRAINT_NAME = 'chk_account_owner';


-- ---------------------------------------------------------------- Slide 18 · Testing
-- open sql/tests/verify_rules.sql and run it with the lightning bolt: 20 rows, all PASS


-- ---------------------------------------------------------------- Slide 19 · Concurrency (OPTIONAL, writes test rows)
-- Needs TWO query tabs. Uses facility 1 and the date 30 days ahead; change 1 if that facility is not AVAILABLE.
-- TAB A (run these three, do NOT commit yet):
--   START TRANSACTION;
--   SELECT * FROM campushub.facility WHERE facility_id = 1 FOR UPDATE;
--   INSERT INTO campushub.booking (facility_id, student_id, faculty_id, booking_date, start_time, end_time, purpose)
--   VALUES (1, 1, NULL, CURDATE() + INTERVAL 30 DAY, '07:00', '08:00', 'lock test A');
-- TAB B (it WAITS - the spinner keeps turning):
--   CALL campushub.sp_create_booking(1, 2, NULL, CURDATE() + INTERVAL 30 DAY, '07:30', '08:30', 'lock test B', @id);
-- TAB A:
--   COMMIT;          -- Tab B now fails: "Time slot overlaps an existing booking"
-- CLEAN UP (either tab):
--   SET SQL_SAFE_UPDATES = 0;
--   DELETE FROM campushub.booking WHERE purpose LIKE 'lock test%';
--   SET SQL_SAFE_UPDATES = 1;
