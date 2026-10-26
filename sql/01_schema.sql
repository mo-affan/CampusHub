-- CampusHub : 01_schema.sql  (MySQL 8.0.16+, InnoDB)
DROP DATABASE IF EXISTS campushub;
CREATE DATABASE campushub CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE campushub;

CREATE TABLE department (
  department_id   INT AUTO_INCREMENT PRIMARY KEY,
  department_name VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE facility_type (
  facility_type_id INT AUTO_INCREMENT PRIMARY KEY,
  type_name        VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE admin (
  admin_id INT AUTO_INCREMENT PRIMARY KEY,
  name     VARCHAR(100) NOT NULL,
  email    VARCHAR(120) NOT NULL UNIQUE,
  role     ENUM('FACILITY_ADMIN','DEPARTMENT_ADMIN','SUPER_ADMIN') NOT NULL DEFAULT 'FACILITY_ADMIN'
);

CREATE TABLE student (
  student_id      INT AUTO_INCREMENT PRIMARY KEY,
  registration_no VARCHAR(15)  NOT NULL UNIQUE,
  name            VARCHAR(100) NOT NULL,
  email           VARCHAR(120) NOT NULL UNIQUE,
  phone           VARCHAR(15),
  department_id   INT NOT NULL,
  CONSTRAINT chk_student_email CHECK (email LIKE '%_@_%._%'),
  CONSTRAINT fk_student_dept FOREIGN KEY (department_id)
    REFERENCES department(department_id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE faculty (
  faculty_id    INT AUTO_INCREMENT PRIMARY KEY,
  employee_code VARCHAR(10)  NOT NULL UNIQUE,
  name          VARCHAR(100) NOT NULL,
  email         VARCHAR(120) NOT NULL UNIQUE,
  designation   VARCHAR(50),
  department_id INT NOT NULL,
  CONSTRAINT fk_faculty_dept FOREIGN KEY (department_id)
    REFERENCES department(department_id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE facility (
  facility_id      INT AUTO_INCREMENT PRIMARY KEY,
  facility_name    VARCHAR(100) NOT NULL UNIQUE,
  facility_type_id INT NOT NULL,
  admin_id         INT NOT NULL,
  building         VARCHAR(50)  NOT NULL,
  capacity         INT NOT NULL,
  status           ENUM('AVAILABLE','UNDER_MAINTENANCE','INACTIVE') NOT NULL DEFAULT 'AVAILABLE',
  CONSTRAINT chk_capacity CHECK (capacity > 0),
  CONSTRAINT fk_facility_type  FOREIGN KEY (facility_type_id) REFERENCES facility_type(facility_type_id),
  CONSTRAINT fk_facility_admin FOREIGN KEY (admin_id)         REFERENCES admin(admin_id)
);

CREATE TABLE booking (
  booking_id   INT AUTO_INCREMENT PRIMARY KEY,
  facility_id  INT  NOT NULL,
  student_id   INT  NULL,
  faculty_id   INT  NULL,
  booking_date DATE NOT NULL,
  start_time   TIME NOT NULL,
  end_time     TIME NOT NULL,
  purpose      VARCHAR(200),
  status       ENUM('CONFIRMED','CANCELLED','COMPLETED') NOT NULL DEFAULT 'CONFIRMED',
  created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT chk_booking_time   CHECK (end_time > start_time),
  CONSTRAINT chk_booking_person CHECK ((student_id IS NULL) <> (faculty_id IS NULL)),
  CONSTRAINT fk_booking_facility FOREIGN KEY (facility_id) REFERENCES facility(facility_id),
  -- ON DELETE RESTRICT is required: MySQL forbids CHECK constraints on columns
  -- that use SET NULL / CASCADE referential actions (error 3823).
  CONSTRAINT fk_booking_student FOREIGN KEY (student_id) REFERENCES student(student_id) ON DELETE RESTRICT,
  CONSTRAINT fk_booking_faculty FOREIGN KEY (faculty_id) REFERENCES faculty(faculty_id) ON DELETE RESTRICT
);

CREATE TABLE equipment (
  equipment_id        INT AUTO_INCREMENT PRIMARY KEY,
  facility_id         INT NOT NULL,
  equipment_name      VARCHAR(100) NOT NULL,
  quantity            INT NOT NULL,
  available_qty       INT NOT NULL,
  availability_status ENUM('AVAILABLE','ALL_ISSUED','UNDER_REPAIR') NOT NULL DEFAULT 'AVAILABLE',
  CONSTRAINT chk_equipment_qty CHECK (quantity >= 0 AND available_qty BETWEEN 0 AND quantity),
  CONSTRAINT fk_equipment_facility FOREIGN KEY (facility_id) REFERENCES facility(facility_id)
);

CREATE TABLE equipment_issue (
  issue_id     INT AUTO_INCREMENT PRIMARY KEY,
  equipment_id INT  NOT NULL,
  student_id   INT  NULL,
  faculty_id   INT  NULL,
  issue_date   DATE NOT NULL,
  due_date     DATE NOT NULL,
  return_date  DATE NULL,
  status       ENUM('ISSUED','RETURNED') NOT NULL DEFAULT 'ISSUED',
  CONSTRAINT chk_issue_person CHECK ((student_id IS NULL) <> (faculty_id IS NULL)),
  CONSTRAINT chk_issue_dates  CHECK (due_date >= issue_date AND (return_date IS NULL OR return_date >= issue_date)),
  CONSTRAINT chk_issue_return CHECK ((status = 'RETURNED') = (return_date IS NOT NULL)),
  CONSTRAINT fk_issue_equipment FOREIGN KEY (equipment_id) REFERENCES equipment(equipment_id),
  CONSTRAINT fk_issue_student   FOREIGN KEY (student_id)   REFERENCES student(student_id) ON DELETE RESTRICT,
  CONSTRAINT fk_issue_faculty   FOREIGN KEY (faculty_id)   REFERENCES faculty(faculty_id) ON DELETE RESTRICT
);

CREATE TABLE maintenance (
  maintenance_id    INT AUTO_INCREMENT PRIMARY KEY,
  facility_id       INT NOT NULL,
  admin_id          INT NOT NULL,
  issue_description VARCHAR(255) NOT NULL,
  reported_date     DATE NOT NULL,
  completion_date   DATE NULL,
  status            ENUM('REPORTED','IN_PROGRESS','COMPLETED') NOT NULL DEFAULT 'REPORTED',
  CONSTRAINT chk_maint_dates CHECK (completion_date IS NULL OR completion_date >= reported_date),
  CONSTRAINT fk_maint_facility FOREIGN KEY (facility_id) REFERENCES facility(facility_id),
  CONSTRAINT fk_maint_admin    FOREIGN KEY (admin_id)    REFERENCES admin(admin_id)
);

-- Indexes (foreign-key columns are indexed automatically by InnoDB)
CREATE INDEX idx_booking_slot   ON booking (facility_id, booking_date, start_time);
CREATE INDEX idx_booking_date   ON booking (booking_date);
CREATE INDEX idx_issue_status   ON equipment_issue (status);
CREATE INDEX idx_facility_cap   ON facility (capacity);
