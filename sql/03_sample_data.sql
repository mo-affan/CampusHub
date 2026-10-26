-- CampusHub : 03_sample_data.sql
USE campushub;

INSERT INTO department (department_name) VALUES
('Computer Science and Engineering'), ('AI and Machine Learning'),
('Electronics and Communication'), ('Mechanical Engineering'), ('Business School');

INSERT INTO facility_type (type_name) VALUES
('Classroom'), ('Computer Lab'), ('Seminar Hall'), ('Auditorium'), ('Sports Facility');

INSERT INTO admin (name, email, role) VALUES
('R. Karthik',  'karthik.admin@campushub.edu', 'FACILITY_ADMIN'),
('S. Priya',    'priya.admin@campushub.edu',   'DEPARTMENT_ADMIN'),
('M. Venkatesh','venkat.admin@campushub.edu',  'SUPER_ADMIN');

INSERT INTO student (registration_no, name, email, phone, department_id) VALUES
('24BCE1101','Aarav Sharma',  'aarav.s@campushub.edu',  '9840011101', 1),
('24BCE1102','Diya Nair',     'diya.n@campushub.edu',   '9840011102', 1),
('24BAI1201','Rohan Iyer',    'rohan.i@campushub.edu',  '9840011201', 2),
('24BAI1202','Sneha Reddy',   'sneha.r@campushub.edu',  '9840011202', 2),
('24BEC1301','Karan Mehta',   'karan.m@campushub.edu',  '9840011301', 3),
('24BME1401','Ananya Das',    'ananya.d@campushub.edu', '9840011401', 4),
('24BBA1501','Vikram Rao',    'vikram.r@campushub.edu', '9840011501', 5),
('24BAI1203','Meera Pillai',  'meera.p@campushub.edu',  '9840011203', 2);

INSERT INTO faculty (employee_code, name, email, designation, department_id) VALUES
('F1001','Dr. Arun Kumar',    'arun.k@campushub.edu',    'Professor',           1),
('F1002','Dr. Lakshmi Menon', 'lakshmi.m@campushub.edu', 'Associate Professor', 2),
('F1003','Dr. Rajesh Gupta',  'rajesh.g@campushub.edu',  'Assistant Professor', 3),
('F1004','Dr. Fatima Sheikh', 'fatima.s@campushub.edu',  'Professor',           4),
('F1005','Dr. Nikhil Joshi',  'nikhil.j@campushub.edu',  'Assistant Professor', 5);

INSERT INTO facility (facility_name, facility_type_id, admin_id, building, capacity) VALUES
('SJT 301 Classroom',       1, 1, 'SJT', 60),
('SJT 412 AI Lab',          2, 1, 'SJT', 40),
('TT 105 Networks Lab',     2, 1, 'TT',  36),
('Anna Seminar Hall',       3, 2, 'Main Block', 150),
('Channa Reddy Auditorium', 4, 3, 'Main Block', 600),
('Indoor Badminton Court',  5, 1, 'Sports Complex', 20),
('MGB 210 Classroom',       1, 2, 'MGB', 70),
('SMV Seminar Hall',        3, 2, 'SMV', 120);

-- Bookings (inserted before maintenance rows, so the facility-status check passes)
INSERT INTO booking (facility_id, student_id, faculty_id, booking_date, start_time, end_time, purpose, status) VALUES
(4, NULL, 1, '2026-08-20','10:00','12:00','Guest lecture on cloud computing','COMPLETED'),
(5, NULL, 2, '2026-08-28','14:00','17:00','AI symposium','COMPLETED'),
(2, 3, NULL, '2026-08-29','16:00','18:00','ML club workshop','COMPLETED'),
(6, 6, NULL, '2026-09-02','17:00','18:00','Badminton practice','COMPLETED'),
(4, NULL, 3, '2026-09-05','09:00','11:00','IEEE student branch meet','COMPLETED'),
(2, 4, NULL, '2026-09-09','14:00','16:00','Hackathon preparation','COMPLETED'),
(1, NULL, 1, '2026-09-10','11:00','12:00','Extra class - DBMS','COMPLETED'),
(4, 1, NULL, '2026-09-15','15:00','17:00','Coding club orientation','COMPLETED'),
(8, NULL, 5, '2026-09-18','10:00','13:00','Business plan pitch','COMPLETED'),
(3, 5, NULL, '2026-09-22','09:00','11:00','Networking lab practice','COMPLETED'),
(5, NULL, 4, '2026-09-26','10:00','16:00','Mechanical expo','COMPLETED'),
(2, NULL, 2, '2026-10-01','09:00','12:00','Deep learning lab session','COMPLETED'),
(6, 6, NULL, '2026-10-03','17:00','18:00','Badminton practice','CANCELLED'),
(4, 7, NULL, '2026-10-07','14:00','16:00','Entrepreneurship talk','COMPLETED'),
(2, 8, NULL, '2026-10-12','15:00','17:00','Kaggle study group','COMPLETED'),
(4, NULL, 1, '2026-10-16','10:00','12:00','Workshop on SQL tuning','CONFIRMED'),
(2, 3, NULL, '2026-10-16','14:00','16:00','ML club workshop','CONFIRMED'),
(1, 2, NULL, '2026-10-17','09:00','10:00','Project team meeting','CONFIRMED'),
(5, NULL, 2, '2026-10-24','10:00','13:00','AI research day','CONFIRMED'),
(7, NULL, 5, '2026-10-20','11:00','12:00','Case study session','CONFIRMED');

INSERT INTO equipment (facility_id, equipment_name, quantity, available_qty) VALUES
(4, 'Epson Projector',      3, 3),
(4, 'Wireless Microphone',  6, 6),
(2, 'NVIDIA Jetson Nano Kit',5, 5),
(2, 'Dell Laptop',         10, 10),
(3, 'Cisco Router 2901',    4, 4),
(6, 'Badminton Racket',    12, 12),
(5, 'PA Speaker System',    2, 2),
(8, 'Document Camera',      1, 1);

-- Issues: the trigger decrements available_qty for every row inserted as ISSUED
INSERT INTO equipment_issue (equipment_id, student_id, faculty_id, issue_date, due_date, return_date, status) VALUES
(3, 3, NULL, '2026-09-01','2026-09-15','2026-09-14','RETURNED'),
(4, 4, NULL, '2026-09-09','2026-09-10','2026-09-10','RETURNED'),
(1, NULL, 1, '2026-10-05','2026-10-19', NULL,'ISSUED'),
(3, 8, NULL, '2026-10-06','2026-10-20', NULL,'ISSUED'),
(3, 3, NULL, '2026-10-01','2026-10-08', NULL,'ISSUED'),
(6, 6, NULL, '2026-10-10','2026-10-11', NULL,'ISSUED'),
(8, NULL, 5, '2026-10-09','2026-10-23', NULL,'ISSUED'),
(5, 5, NULL, '2026-09-22','2026-09-23','2026-09-23','RETURNED');

-- Maintenance: open requests switch the facility to UNDER_MAINTENANCE (trigger T4)
INSERT INTO maintenance (facility_id, admin_id, issue_description, reported_date, completion_date, status) VALUES
(4, 2, 'Projector screen motor not working', '2026-08-25','2026-08-27','COMPLETED'),
(3, 1, 'Two routers failing POST',           '2026-09-24','2026-09-30','COMPLETED'),
(4, 2, 'Air conditioning leaking',           '2026-09-29','2026-10-02','COMPLETED'),
(6, 1, 'Court floor lines repainting',       '2026-10-11', NULL,      'IN_PROGRESS'),
(3, 1, 'Network switch replacement',         '2026-10-12', NULL,      'REPORTED');
