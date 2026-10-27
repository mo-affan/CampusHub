-- =============================================================================
-- CampusHub : 07_add_user_accounts.sql   (migration: login accounts)
--
-- Adds ONE new table, user_account, that gives students, faculty and administrators
-- a login. Nothing else changes: existing tables, rows, triggers, procedures and
-- views are untouched, so it is safe on a database that already holds your data.
--
-- * Safe to re-run (CREATE TABLE IF NOT EXISTS).
-- * Run AFTER 01 and 02 (it references student, faculty and admin).
-- * No passwords are created here. Passwords are hashed by the app (Werkzeug scrypt),
--   so create accounts with:   python manage_accounts.py create-admin
--   (or demo logins for the review:   python manage_accounts.py demo-logins)
-- * To undo:   DROP TABLE campushub.user_account;
-- =============================================================================
USE campushub;

CREATE TABLE IF NOT EXISTS user_account (
  account_id           INT AUTO_INCREMENT PRIMARY KEY,
  role                 ENUM('STUDENT','FACULTY','ADMIN') NOT NULL,
  student_id           INT NULL,
  faculty_id           INT NULL,
  admin_id             INT NULL,
  password_hash        VARCHAR(255) NOT NULL,          -- salted scrypt hash, never the password
  must_change_password TINYINT(1) NOT NULL DEFAULT 1,  -- temporary password: change at next sign-in
  is_active            TINYINT(1) NOT NULL DEFAULT 1,  -- 0 = disabled, cannot sign in
  failed_attempts      INT NOT NULL DEFAULT 0,
  locked_until         DATETIME NULL,                  -- set after 5 wrong passwords
  last_login_at        DATETIME NULL,
  password_changed_at  DATETIME NULL,
  created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  -- one login per person
  CONSTRAINT uq_account_student UNIQUE (student_id),
  CONSTRAINT uq_account_faculty UNIQUE (faculty_id),
  CONSTRAINT uq_account_admin   UNIQUE (admin_id),
  -- the role says which ONE person column is filled in
  CONSTRAINT chk_account_owner CHECK (
        (role = 'STUDENT' AND student_id IS NOT NULL AND faculty_id IS NULL AND admin_id IS NULL)
     OR (role = 'FACULTY' AND faculty_id IS NOT NULL AND student_id IS NULL AND admin_id IS NULL)
     OR (role = 'ADMIN'   AND admin_id   IS NOT NULL AND student_id IS NULL AND faculty_id IS NULL)),
  CONSTRAINT chk_account_flags CHECK (must_change_password IN (0, 1) AND is_active IN (0, 1) AND failed_attempts >= 0),
  -- RESTRICT (not CASCADE): MySQL does not allow CHECK constraints on columns with
  -- CASCADE / SET NULL actions (error 3823), same reason as in the booking table
  CONSTRAINT fk_account_student FOREIGN KEY (student_id) REFERENCES student(student_id) ON DELETE RESTRICT,
  CONSTRAINT fk_account_faculty FOREIGN KEY (faculty_id) REFERENCES faculty(faculty_id) ON DELETE RESTRICT,
  CONSTRAINT fk_account_admin   FOREIGN KEY (admin_id)   REFERENCES admin(admin_id)     ON DELETE RESTRICT
);

SELECT 'user_account is ready' AS message, COUNT(*) AS existing_accounts FROM user_account;
