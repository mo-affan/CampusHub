-- CampusHub : 04_queries.sql  (reports and searches)
USE campushub;

-- Q1 Facilities free on a given date and slot
SET @d = '2026-10-16', @s = '10:00', @e = '12:00';
SELECT f.facility_name, ft.type_name, f.building, f.capacity
FROM facility f JOIN facility_type ft ON ft.facility_type_id = f.facility_type_id
WHERE f.status = 'AVAILABLE'
  AND NOT EXISTS (SELECT 1 FROM booking b
                  WHERE b.facility_id = f.facility_id AND b.booking_date = @d
                    AND b.status = 'CONFIRMED' AND b.start_time < @e AND b.end_time > @s)
ORDER BY f.capacity;

-- Q2 All bookings of one facility
SELECT b.booking_id, b.booking_date, b.start_time, b.end_time,
       COALESCE(s.name, fa.name) AS booked_by, b.purpose, b.status
FROM booking b
LEFT JOIN student s  ON s.student_id  = b.student_id
LEFT JOIN faculty fa ON fa.faculty_id = b.faculty_id
WHERE b.facility_id = 4
ORDER BY b.booking_date DESC;

-- Q3 Most frequently booked facilities
SELECT facility_name, total_bookings, hours_booked
FROM vw_facility_usage ORDER BY total_bookings DESC, hours_booked DESC LIMIT 5;

-- Q4 Equipment currently issued
SELECT * FROM vw_current_issues ORDER BY issue_date;

-- Q5 Facilities with more than one maintenance record
SELECT f.facility_name, COUNT(*) AS maintenance_count
FROM maintenance m JOIN facility f ON f.facility_id = m.facility_id
GROUP BY f.facility_id, f.facility_name
HAVING COUNT(*) > 1;

-- Q6 Bookings by department (student or faculty department)
SELECT d.department_name, COUNT(*) AS bookings
FROM booking b
LEFT JOIN student s  ON s.student_id  = b.student_id
LEFT JOIN faculty fa ON fa.faculty_id = b.faculty_id
JOIN department d ON d.department_id = COALESCE(s.department_id, fa.department_id)
WHERE b.status <> 'CANCELLED'
GROUP BY d.department_id, d.department_name
ORDER BY bookings DESC;

-- Q7 Facilities with capacity above a given value
SELECT facility_name, building, capacity FROM facility WHERE capacity > 100 ORDER BY capacity DESC;

-- Q8 Monthly booking statistics
SELECT DATE_FORMAT(booking_date, '%Y-%m') AS month,
       COUNT(*) AS total,
       SUM(status = 'CANCELLED') AS cancelled
FROM booking GROUP BY month ORDER BY month;

-- Q9 Equipment availability
SELECT * FROM vw_equipment_availability ORDER BY availability_status DESC, equipment_name;

-- Q10 Maintenance history
SELECT * FROM vw_maintenance_history ORDER BY reported_date DESC;
