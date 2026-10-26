-- CampusHub : 02_logic.sql  (triggers, stored procedures, views)
USE campushub;
DELIMITER $$

-- T1: reject overlapping bookings and bookings of unavailable facilities
CREATE TRIGGER trg_booking_before_insert
BEFORE INSERT ON booking
FOR EACH ROW
BEGIN
  IF (SELECT status FROM facility WHERE facility_id = NEW.facility_id) <> 'AVAILABLE' THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Facility is under maintenance or inactive';
  END IF;
  IF NEW.status = 'CONFIRMED' AND EXISTS (
       SELECT 1 FROM booking b
       WHERE b.facility_id  = NEW.facility_id
         AND b.booking_date = NEW.booking_date
         AND b.status       = 'CONFIRMED'
         AND b.start_time   < NEW.end_time
         AND b.end_time     > NEW.start_time) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Time slot overlaps an existing booking';
  END IF;
END$$

-- T2: check stock and decrement it when equipment is issued
CREATE TRIGGER trg_issue_before_insert
BEFORE INSERT ON equipment_issue
FOR EACH ROW
BEGIN
  IF NEW.status = 'ISSUED' THEN
    IF (SELECT available_qty FROM equipment WHERE equipment_id = NEW.equipment_id) < 1 THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'No unit of this equipment is available';
    END IF;
    UPDATE equipment
       SET available_qty = available_qty - 1,
           availability_status = IF(available_qty = 0, 'ALL_ISSUED', 'AVAILABLE')
     WHERE equipment_id = NEW.equipment_id;
  END IF;
END$$

-- T3: restore stock when equipment is returned
CREATE TRIGGER trg_issue_after_update
AFTER UPDATE ON equipment_issue
FOR EACH ROW
BEGIN
  IF OLD.status = 'ISSUED' AND NEW.status = 'RETURNED' THEN
    UPDATE equipment
       SET available_qty = available_qty + 1,
           availability_status = 'AVAILABLE'
     WHERE equipment_id = NEW.equipment_id;
  END IF;
END$$

-- T4: an open maintenance request takes the facility out of service
CREATE TRIGGER trg_maint_after_insert
AFTER INSERT ON maintenance
FOR EACH ROW
BEGIN
  IF NEW.status <> 'COMPLETED' THEN
    UPDATE facility SET status = 'UNDER_MAINTENANCE' WHERE facility_id = NEW.facility_id;
  END IF;
END$$

-- T5: when the last open request is completed, the facility is available again
CREATE TRIGGER trg_maint_after_update
AFTER UPDATE ON maintenance
FOR EACH ROW
BEGIN
  IF NEW.status = 'COMPLETED' AND OLD.status <> 'COMPLETED'
     AND NOT EXISTS (SELECT 1 FROM maintenance
                     WHERE facility_id = NEW.facility_id AND status <> 'COMPLETED') THEN
    UPDATE facility SET status = 'AVAILABLE' WHERE facility_id = NEW.facility_id;
  END IF;
END$$

-- P1: create a booking inside a transaction, locking the facility row
CREATE PROCEDURE sp_create_booking(
  IN p_facility_id INT, IN p_student_id INT, IN p_faculty_id INT,
  IN p_date DATE, IN p_start TIME, IN p_end TIME, IN p_purpose VARCHAR(200),
  OUT p_booking_id INT)
BEGIN
  DECLARE v_lock INT;
  DECLARE EXIT HANDLER FOR SQLEXCEPTION
  BEGIN
    ROLLBACK;
    RESIGNAL;
  END;
  START TRANSACTION;
    -- serialises concurrent bookings of the same facility
    SELECT facility_id INTO v_lock FROM facility WHERE facility_id = p_facility_id FOR UPDATE;
    INSERT INTO booking (facility_id, student_id, faculty_id, booking_date, start_time, end_time, purpose)
    VALUES (p_facility_id, p_student_id, p_faculty_id, p_date, p_start, p_end, p_purpose);
    SET p_booking_id = LAST_INSERT_ID();
  COMMIT;
END$$

-- P2: issue one unit of equipment
CREATE PROCEDURE sp_issue_equipment(
  IN p_equipment_id INT, IN p_student_id INT, IN p_faculty_id INT, IN p_days INT,
  OUT p_issue_id INT)
BEGIN
  DECLARE v_lock INT;
  DECLARE EXIT HANDLER FOR SQLEXCEPTION
  BEGIN
    ROLLBACK;
    RESIGNAL;
  END;
  START TRANSACTION;
    SELECT equipment_id INTO v_lock FROM equipment WHERE equipment_id = p_equipment_id FOR UPDATE;
    INSERT INTO equipment_issue (equipment_id, student_id, faculty_id, issue_date, due_date)
    VALUES (p_equipment_id, p_student_id, p_faculty_id, CURDATE(), CURDATE() + INTERVAL p_days DAY);
    SET p_issue_id = LAST_INSERT_ID();
  COMMIT;
END$$

-- P3: return issued equipment
CREATE PROCEDURE sp_return_equipment(IN p_issue_id INT)
BEGIN
  IF (SELECT status FROM equipment_issue WHERE issue_id = p_issue_id) <> 'ISSUED' THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'This item is not currently issued';
  END IF;
  UPDATE equipment_issue SET status = 'RETURNED', return_date = CURDATE()
   WHERE issue_id = p_issue_id;
END$$

-- P4: record a maintenance request
CREATE PROCEDURE sp_record_maintenance(
  IN p_facility_id INT, IN p_admin_id INT, IN p_description VARCHAR(255),
  OUT p_maintenance_id INT)
BEGIN
  INSERT INTO maintenance (facility_id, admin_id, issue_description, reported_date)
  VALUES (p_facility_id, p_admin_id, p_description, CURDATE());
  SET p_maintenance_id = LAST_INSERT_ID();
END$$

DELIMITER ;

-- Views (report layer)
CREATE VIEW vw_facility_usage AS
SELECT f.facility_id, f.facility_name, ft.type_name, f.building, f.capacity,
       COUNT(b.booking_id) AS total_bookings,
       ROUND(COALESCE(SUM(TIME_TO_SEC(TIMEDIFF(b.end_time, b.start_time))) / 3600, 0), 1) AS hours_booked
FROM facility f
JOIN facility_type ft ON ft.facility_type_id = f.facility_type_id
LEFT JOIN booking b ON b.facility_id = f.facility_id AND b.status <> 'CANCELLED'
GROUP BY f.facility_id, f.facility_name, ft.type_name, f.building, f.capacity;

CREATE VIEW vw_equipment_availability AS
SELECT e.equipment_id, e.equipment_name, f.facility_name,
       e.quantity, e.available_qty, (e.quantity - e.available_qty) AS issued_qty,
       e.availability_status
FROM equipment e JOIN facility f ON f.facility_id = e.facility_id;

CREATE VIEW vw_current_issues AS
SELECT ei.issue_id, e.equipment_name,
       COALESCE(s.name, fa.name) AS issued_to,
       IF(s.student_id IS NOT NULL, 'Student', 'Faculty') AS user_type,
       ei.issue_date, ei.due_date,
       IF(ei.due_date < CURDATE(), 'OVERDUE', 'ON TIME') AS due_status
FROM equipment_issue ei
JOIN equipment e     ON e.equipment_id = ei.equipment_id
LEFT JOIN student s  ON s.student_id  = ei.student_id
LEFT JOIN faculty fa ON fa.faculty_id = ei.faculty_id
WHERE ei.status = 'ISSUED';

CREATE VIEW vw_maintenance_history AS
SELECT m.maintenance_id, f.facility_name, m.issue_description, a.name AS handled_by,
       m.reported_date, m.completion_date, m.status,
       DATEDIFF(COALESCE(m.completion_date, CURDATE()), m.reported_date) AS days_open
FROM maintenance m
JOIN facility f ON f.facility_id = m.facility_id
JOIN admin a    ON a.admin_id    = m.admin_id;
