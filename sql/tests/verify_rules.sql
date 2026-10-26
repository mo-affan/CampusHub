-- =============================================================================
-- CampusHub : sql/tests/verify_rules.sql   - automated rule tests for MySQL
--
-- Run in MySQL Workbench (open the file, click the lightning bolt) after 01-03.
-- It creates a throw-away facility 'ZZ SelfTest Room', exercises every booking,
-- inventory and maintenance rule against the REAL triggers, procedures and
-- constraints, removes everything it created, and prints one PASS/FAIL row per test.
-- Your own data is not modified (test bookings use a date 400 days ahead).
--
-- Not covered here (needs two sessions): concurrent booking. Manual steps
-- (use an AVAILABLE facility id instead of 1):
--   Tab A:  START TRANSACTION;
--           SELECT * FROM campushub.facility WHERE facility_id = 1 FOR UPDATE;
--           INSERT INTO campushub.booking (facility_id, student_id, faculty_id, booking_date,
--                  start_time, end_time, purpose)
--           VALUES (1, 1, NULL, CURDATE() + INTERVAL 30 DAY, '07:00', '08:00', 'lock test A');
--   Tab B:  CALL campushub.sp_create_booking(1, 2, NULL, CURDATE() + INTERVAL 30 DAY,
--                                            '07:30', '08:30', 'lock test B', @id);
--           -> Tab B waits (the row lock is held by Tab A)
--   Tab A:  COMMIT;   -> Tab B continues and fails: "Time slot overlaps an existing booking"
--   Clean up: SET SQL_SAFE_UPDATES = 0;
--             DELETE FROM campushub.booking WHERE purpose LIKE 'lock test%';
--             SET SQL_SAFE_UPDATES = 1;
-- =============================================================================
USE campushub;

DROP PROCEDURE IF EXISTS sp_campushub_selftest;
DELIMITER $$
CREATE PROCEDURE sp_campushub_selftest()
selftest: BEGIN
  DECLARE v_student INT;
  DECLARE v_faculty INT;
  DECLARE v_admin   INT;
  DECLARE v_type    INT;
  DECLARE v_fac     INT;
  DECLARE v_eq      INT;
  DECLARE v_maint   INT;
  DECLARE v_b1      INT;
  DECLARE v_b2      INT;
  DECLARE v_issue   INT;
  DECLARE v_tmp     INT;
  DECLARE v_d       DATE;
  DECLARE v_failed  INT DEFAULT 0;
  DECLARE v_errno   INT;
  DECLARE v_msg     VARCHAR(512);
  DECLARE v_n       INT;
  DECLARE v_n2      INT;
  DECLARE v_s       VARCHAR(30);

  DROP TEMPORARY TABLE IF EXISTS tmp_selftest;
  CREATE TEMPORARY TABLE tmp_selftest (
    test_no INT, test_name VARCHAR(100), expected VARCHAR(200), result VARCHAR(8), detail VARCHAR(512));

  SELECT MIN(student_id) INTO v_student FROM student;
  SELECT MIN(faculty_id) INTO v_faculty FROM faculty;
  SELECT MIN(admin_id) INTO v_admin FROM admin;
  SELECT MIN(facility_type_id) INTO v_type FROM facility_type;
  SET v_d = CURDATE() + INTERVAL 400 DAY;

  IF v_student IS NULL OR v_admin IS NULL OR v_type IS NULL THEN
    SELECT 'FAIL: need at least one student, admin and facility type - run 03_sample_data.sql first' AS result;
    LEAVE selftest;
  END IF;

  -- remove leftovers of an interrupted earlier run
  DELETE ei FROM equipment_issue ei JOIN equipment e ON e.equipment_id = ei.equipment_id
    JOIN facility f ON f.facility_id = e.facility_id WHERE f.facility_name LIKE 'ZZ SelfTest Room%';
  DELETE e FROM equipment e JOIN facility f ON f.facility_id = e.facility_id WHERE f.facility_name LIKE 'ZZ SelfTest Room%';
  DELETE b FROM booking b JOIN facility f ON f.facility_id = b.facility_id WHERE f.facility_name LIKE 'ZZ SelfTest Room%';
  DELETE m FROM maintenance m JOIN facility f ON f.facility_id = m.facility_id WHERE f.facility_name LIKE 'ZZ SelfTest Room%';
  DELETE FROM facility WHERE facility_name LIKE 'ZZ SelfTest Room%';

  INSERT INTO facility (facility_name, facility_type_id, admin_id, building, capacity)
  VALUES ('ZZ SelfTest Room', v_type, v_admin, 'Test Block', 10);
  SET v_fac = LAST_INSERT_ID();

  -- 1. valid booking -----------------------------------------------------------
  BEGIN
    DECLARE CONTINUE HANDLER FOR SQLEXCEPTION
    BEGIN GET DIAGNOSTICS CONDITION 1 v_errno = MYSQL_ERRNO, v_msg = MESSAGE_TEXT; SET v_failed = 1; END;
    SET v_failed = 0, v_msg = NULL, v_b1 = NULL;
    CALL sp_create_booking(v_fac, v_student, NULL, v_d, '10:00', '12:00', 'selftest', v_b1);
  END;
  INSERT INTO tmp_selftest VALUES (1, 'Valid booking is accepted', 'sp_create_booking returns a booking id',
    IF(v_failed = 0 AND v_b1 IS NOT NULL, 'PASS', 'FAIL'), IFNULL(v_msg, CONCAT('booking_id ', v_b1)));

  -- 2. overlapping booking ---------------------------------------------------------
  SELECT COUNT(*) INTO v_n FROM booking WHERE facility_id = v_fac;
  BEGIN
    DECLARE CONTINUE HANDLER FOR SQLEXCEPTION
    BEGIN GET DIAGNOSTICS CONDITION 1 v_errno = MYSQL_ERRNO, v_msg = MESSAGE_TEXT; SET v_failed = 1; END;
    SET v_failed = 0, v_msg = NULL, v_tmp = NULL;
    CALL sp_create_booking(v_fac, v_student, NULL, v_d, '11:00', '13:00', 'selftest', v_tmp);
  END;
  SELECT COUNT(*) INTO v_n2 FROM booking WHERE facility_id = v_fac;
  INSERT INTO tmp_selftest VALUES (2, 'Overlapping booking is rejected', 'trigger T1: Time slot overlaps an existing booking',
    IF(v_failed = 1 AND v_msg LIKE 'Time slot overlaps%', 'PASS', 'FAIL'), v_msg);
  INSERT INTO tmp_selftest VALUES (3, 'Failed booking leaves no partial row', 'ROLLBACK in sp_create_booking: row count unchanged',
    IF(v_failed = 1 AND v_n = v_n2, 'PASS', 'FAIL'), CONCAT('before ', v_n, ', after ', v_n2));

  -- 4. back-to-back ------------------------------------------------------------------
  BEGIN
    DECLARE CONTINUE HANDLER FOR SQLEXCEPTION
    BEGIN GET DIAGNOSTICS CONDITION 1 v_errno = MYSQL_ERRNO, v_msg = MESSAGE_TEXT; SET v_failed = 1; END;
    SET v_failed = 0, v_msg = NULL, v_b2 = NULL;
    CALL sp_create_booking(v_fac, v_student, NULL, v_d, '12:00', '13:00', 'selftest', v_b2);
  END;
  INSERT INTO tmp_selftest VALUES (4, 'Back-to-back booking is allowed', '12:00-13:00 after 10:00-12:00 succeeds',
    IF(v_failed = 0 AND v_b2 IS NOT NULL, 'PASS', 'FAIL'), IFNULL(v_msg, CONCAT('booking_id ', v_b2)));

  -- 5. end before start ------------------------------------------------------------------
  BEGIN
    DECLARE CONTINUE HANDLER FOR SQLEXCEPTION
    BEGIN GET DIAGNOSTICS CONDITION 1 v_errno = MYSQL_ERRNO, v_msg = MESSAGE_TEXT; SET v_failed = 1; END;
    SET v_failed = 0, v_msg = NULL, v_errno = NULL, v_tmp = NULL;
    CALL sp_create_booking(v_fac, v_student, NULL, v_d, '15:00', '14:00', 'selftest', v_tmp);
  END;
  INSERT INTO tmp_selftest VALUES (5, 'End time before start is rejected', 'CHECK chk_booking_time (error 3819)',
    IF(v_failed = 1 AND v_errno = 3819, 'PASS', 'FAIL'), v_msg);

  -- 6. both student and faculty -------------------------------------------------------------
  IF v_faculty IS NULL THEN
    INSERT INTO tmp_selftest VALUES (6, 'Student AND faculty on one booking is rejected', 'CHECK chk_booking_person', 'SKIP', 'no faculty rows');
  ELSE
    BEGIN
      DECLARE CONTINUE HANDLER FOR SQLEXCEPTION
      BEGIN GET DIAGNOSTICS CONDITION 1 v_errno = MYSQL_ERRNO, v_msg = MESSAGE_TEXT; SET v_failed = 1; END;
      SET v_failed = 0, v_msg = NULL, v_errno = NULL, v_tmp = NULL;
      CALL sp_create_booking(v_fac, v_student, v_faculty, v_d, '16:00', '17:00', 'selftest', v_tmp);
    END;
    INSERT INTO tmp_selftest VALUES (6, 'Student AND faculty on one booking is rejected', 'CHECK chk_booking_person (error 3819)',
      IF(v_failed = 1 AND v_errno = 3819, 'PASS', 'FAIL'), v_msg);
  END IF;

  -- 7. invalid facility reference -------------------------------------------------------------
  BEGIN
    DECLARE CONTINUE HANDLER FOR SQLEXCEPTION
    BEGIN GET DIAGNOSTICS CONDITION 1 v_errno = MYSQL_ERRNO, v_msg = MESSAGE_TEXT; SET v_failed = 1; END;
    SET v_failed = 0, v_msg = NULL, v_errno = NULL, v_tmp = NULL;
    CALL sp_create_booking(999999999, v_student, NULL, v_d, '08:00', '09:00', 'selftest', v_tmp);
  END;
  INSERT INTO tmp_selftest VALUES (7, 'Booking a non-existent facility is rejected', 'FOREIGN KEY fk_booking_facility (error 1452)',
    IF(v_failed = 1 AND v_errno = 1452, 'PASS', 'FAIL'), v_msg);

  -- 8. cancel then rebook the same slot -------------------------------------------------------
  UPDATE booking SET status = 'CANCELLED' WHERE booking_id = v_b1;
  BEGIN
    DECLARE CONTINUE HANDLER FOR SQLEXCEPTION
    BEGIN GET DIAGNOSTICS CONDITION 1 v_errno = MYSQL_ERRNO, v_msg = MESSAGE_TEXT; SET v_failed = 1; END;
    SET v_failed = 0, v_msg = NULL, v_tmp = NULL;
    CALL sp_create_booking(v_fac, v_student, NULL, v_d, '10:00', '12:00', 'selftest', v_tmp);
  END;
  INSERT INTO tmp_selftest VALUES (8, 'Cancelled slot can be booked again', 'cancelled rows are ignored by trigger T1',
    IF(v_failed = 0 AND v_tmp IS NOT NULL, 'PASS', 'FAIL'), IFNULL(v_msg, CONCAT('booking_id ', v_tmp)));

  -- 9-11. maintenance -------------------------------------------------------------------------
  INSERT INTO maintenance (facility_id, admin_id, issue_description, reported_date)
  VALUES (v_fac, v_admin, 'selftest fault', CURDATE());
  SET v_maint = LAST_INSERT_ID();
  SELECT status INTO v_s FROM facility WHERE facility_id = v_fac;
  INSERT INTO tmp_selftest VALUES (9, 'Open maintenance closes the facility', 'trigger T4 sets UNDER_MAINTENANCE',
    IF(v_s = 'UNDER_MAINTENANCE', 'PASS', 'FAIL'), CONCAT('status = ', v_s));

  BEGIN
    DECLARE CONTINUE HANDLER FOR SQLEXCEPTION
    BEGIN GET DIAGNOSTICS CONDITION 1 v_errno = MYSQL_ERRNO, v_msg = MESSAGE_TEXT; SET v_failed = 1; END;
    SET v_failed = 0, v_msg = NULL, v_tmp = NULL;
    CALL sp_create_booking(v_fac, v_student, NULL, v_d + INTERVAL 1 DAY, '10:00', '11:00', 'selftest', v_tmp);
  END;
  INSERT INTO tmp_selftest VALUES (10, 'Facility under maintenance cannot be booked', 'trigger T1: Facility is under maintenance or inactive',
    IF(v_failed = 1 AND v_msg LIKE 'Facility is under maintenance%', 'PASS', 'FAIL'), v_msg);

  UPDATE maintenance SET status = 'COMPLETED', completion_date = CURDATE() WHERE maintenance_id = v_maint;
  SELECT status INTO v_s FROM facility WHERE facility_id = v_fac;
  INSERT INTO tmp_selftest VALUES (11, 'Completing maintenance reopens the facility', 'trigger T5 sets AVAILABLE',
    IF(v_s = 'AVAILABLE', 'PASS', 'FAIL'), CONCAT('status = ', v_s));

  -- 12-15. equipment ---------------------------------------------------------------------------
  INSERT INTO equipment (facility_id, equipment_name, quantity, available_qty)
  VALUES (v_fac, 'ZZ SelfTest Kit', 1, 1);
  SET v_eq = LAST_INSERT_ID();

  BEGIN
    DECLARE CONTINUE HANDLER FOR SQLEXCEPTION
    BEGIN GET DIAGNOSTICS CONDITION 1 v_errno = MYSQL_ERRNO, v_msg = MESSAGE_TEXT; SET v_failed = 1; END;
    SET v_failed = 0, v_msg = NULL, v_issue = NULL;
    CALL sp_issue_equipment(v_eq, v_student, NULL, 3, v_issue);
  END;
  SELECT available_qty, availability_status INTO v_n, v_s FROM equipment WHERE equipment_id = v_eq;
  INSERT INTO tmp_selftest VALUES (12, 'Issuing equipment lowers stock', 'trigger T2: available 1 -> 0, ALL_ISSUED',
    IF(v_failed = 0 AND v_n = 0 AND v_s = 'ALL_ISSUED', 'PASS', 'FAIL'), IFNULL(v_msg, CONCAT('available ', v_n, ', ', v_s)));

  BEGIN
    DECLARE CONTINUE HANDLER FOR SQLEXCEPTION
    BEGIN GET DIAGNOSTICS CONDITION 1 v_errno = MYSQL_ERRNO, v_msg = MESSAGE_TEXT; SET v_failed = 1; END;
    SET v_failed = 0, v_msg = NULL, v_tmp = NULL;
    CALL sp_issue_equipment(v_eq, v_student, NULL, 3, v_tmp);
  END;
  INSERT INTO tmp_selftest VALUES (13, 'Issuing with no stock left is rejected', 'trigger T2: No unit of this equipment is available',
    IF(v_failed = 1 AND v_msg LIKE 'No unit of this equipment%', 'PASS', 'FAIL'), v_msg);

  BEGIN
    DECLARE CONTINUE HANDLER FOR SQLEXCEPTION
    BEGIN GET DIAGNOSTICS CONDITION 1 v_errno = MYSQL_ERRNO, v_msg = MESSAGE_TEXT; SET v_failed = 1; END;
    SET v_failed = 0, v_msg = NULL;
    CALL sp_return_equipment(v_issue);
  END;
  SELECT available_qty, availability_status INTO v_n, v_s FROM equipment WHERE equipment_id = v_eq;
  INSERT INTO tmp_selftest VALUES (14, 'Returning equipment restores stock', 'trigger T3: available 0 -> 1, AVAILABLE',
    IF(v_failed = 0 AND v_n = 1 AND v_s = 'AVAILABLE', 'PASS', 'FAIL'), IFNULL(v_msg, CONCAT('available ', v_n, ', ', v_s)));

  BEGIN
    DECLARE CONTINUE HANDLER FOR SQLEXCEPTION
    BEGIN GET DIAGNOSTICS CONDITION 1 v_errno = MYSQL_ERRNO, v_msg = MESSAGE_TEXT; SET v_failed = 1; END;
    SET v_failed = 0, v_msg = NULL;
    CALL sp_return_equipment(v_issue);
  END;
  INSERT INTO tmp_selftest VALUES (15, 'Returning the same item twice is rejected', 'sp_return_equipment: This item is not currently issued',
    IF(v_failed = 1 AND v_msg LIKE 'This item is not currently issued%', 'PASS', 'FAIL'), v_msg);

  -- 16-18. constraints -------------------------------------------------------------------------
  BEGIN
    DECLARE CONTINUE HANDLER FOR SQLEXCEPTION
    BEGIN GET DIAGNOSTICS CONDITION 1 v_errno = MYSQL_ERRNO, v_msg = MESSAGE_TEXT; SET v_failed = 1; END;
    SET v_failed = 0, v_msg = NULL, v_errno = NULL;
    INSERT INTO facility (facility_name, facility_type_id, admin_id, building, capacity)
    VALUES ('ZZ SelfTest Room', v_type, v_admin, 'Test Block', 10);
  END;
  INSERT INTO tmp_selftest VALUES (16, 'Duplicate facility name is rejected', 'UNIQUE facility_name (error 1062)',
    IF(v_failed = 1 AND v_errno = 1062, 'PASS', 'FAIL'), v_msg);

  BEGIN
    DECLARE CONTINUE HANDLER FOR SQLEXCEPTION
    BEGIN GET DIAGNOSTICS CONDITION 1 v_errno = MYSQL_ERRNO, v_msg = MESSAGE_TEXT; SET v_failed = 1; END;
    SET v_failed = 0, v_msg = NULL, v_errno = NULL;
    INSERT INTO facility (facility_name, facility_type_id, admin_id, building, capacity)
    VALUES ('ZZ SelfTest Room 2', v_type, v_admin, 'Test Block', 0);
  END;
  INSERT INTO tmp_selftest VALUES (17, 'Capacity 0 is rejected', 'CHECK chk_capacity (error 3819)',
    IF(v_failed = 1 AND v_errno = 3819, 'PASS', 'FAIL'), v_msg);

  BEGIN
    DECLARE CONTINUE HANDLER FOR SQLEXCEPTION
    BEGIN GET DIAGNOSTICS CONDITION 1 v_errno = MYSQL_ERRNO, v_msg = MESSAGE_TEXT; SET v_failed = 1; END;
    SET v_failed = 0, v_msg = NULL, v_errno = NULL;
    DELETE FROM facility WHERE facility_id = v_fac;
  END;
  INSERT INTO tmp_selftest VALUES (18, 'Deleting a facility that has bookings is blocked', 'ON DELETE RESTRICT (error 1451)',
    IF(v_failed = 1 AND v_errno = 1451, 'PASS', 'FAIL'), v_msg);

  -- 19-20. schema objects --------------------------------------------------------------------
  SELECT COUNT(*) INTO v_n FROM information_schema.TRIGGERS
   WHERE TRIGGER_SCHEMA = DATABASE() AND TRIGGER_NAME IN ('trg_booking_before_insert', 'trg_issue_before_insert',
         'trg_issue_after_update', 'trg_maint_after_insert', 'trg_maint_after_update');
  SELECT COUNT(*) INTO v_n2 FROM information_schema.ROUTINES
   WHERE ROUTINE_SCHEMA = DATABASE() AND ROUTINE_TYPE = 'PROCEDURE' AND ROUTINE_NAME IN ('sp_create_booking',
         'sp_issue_equipment', 'sp_return_equipment', 'sp_record_maintenance');
  INSERT INTO tmp_selftest VALUES (19, 'All 5 triggers and 4 procedures exist', 'information_schema counts 5 and 4',
    IF(v_n = 5 AND v_n2 = 4, 'PASS', 'FAIL'), CONCAT(v_n, ' triggers, ', v_n2, ' procedures'));
  SELECT COUNT(*) INTO v_n FROM information_schema.VIEWS
   WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME IN ('vw_facility_usage', 'vw_equipment_availability',
         'vw_current_issues', 'vw_maintenance_history');
  SELECT COUNT(*) INTO v_n2 FROM information_schema.STATISTICS
   WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'booking' AND INDEX_NAME = 'idx_booking_slot';
  INSERT INTO tmp_selftest VALUES (20, 'All 4 views and the booking slot index exist', 'information_schema counts 4 views + idx_booking_slot',
    IF(v_n = 4 AND v_n2 > 0, 'PASS', 'FAIL'), CONCAT(v_n, ' views, idx_booking_slot columns ', v_n2));

  -- clean up everything the test created ------------------------------------------------------
  DELETE FROM equipment_issue WHERE equipment_id = v_eq;
  DELETE FROM equipment WHERE equipment_id = v_eq;
  DELETE FROM booking WHERE facility_id = v_fac;
  DELETE FROM maintenance WHERE facility_id = v_fac;
  DELETE FROM facility WHERE facility_name LIKE 'ZZ SelfTest Room%';

  SELECT test_no AS `#`, test_name AS test, expected, result, detail FROM tmp_selftest ORDER BY test_no;
  SELECT SUM(result = 'PASS') AS passed, SUM(result = 'FAIL') AS failed, SUM(result = 'SKIP') AS skipped
    FROM tmp_selftest;
  DROP TEMPORARY TABLE IF EXISTS tmp_selftest;
END$$
DELIMITER ;

-- Workbench's "Safe Updates" mode would block the set-based DELETE/UPDATE statements; switch it off
-- for this call only and restore your setting afterwards.
SET @campushub_safe_updates = @@SESSION.sql_safe_updates;
SET SESSION sql_safe_updates = 0;
CALL sp_campushub_selftest();
SET SESSION sql_safe_updates = @campushub_safe_updates;
DROP PROCEDURE sp_campushub_selftest;
