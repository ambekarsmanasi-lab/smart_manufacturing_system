-- Smart Manufacturing Maintenance System with Real Time Fault Detection
-- Fresh-install schema + demo seed data for MySQL 8.0+
-- Database: smart_manufacturing_erp
-- Demo logins are listed in README.md. Change them before any real deployment.

CREATE DATABASE IF NOT EXISTS smart_manufacturing_erp
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE smart_manufacturing_erp;

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

CREATE TABLE IF NOT EXISTS production_lines (
  line_id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(80) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS machines (
  machine_id INT AUTO_INCREMENT PRIMARY KEY,
  line_id INT NOT NULL,
  name VARCHAR(80) NOT NULL UNIQUE,
  machine_type VARCHAR(50) NULL,
  criticality ENUM('LOW','MEDIUM','HIGH') NOT NULL DEFAULT 'MEDIUM',
  CONSTRAINT fk_machines_line FOREIGN KEY (line_id)
    REFERENCES production_lines(line_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS sensors (
  sensor_id INT AUTO_INCREMENT PRIMARY KEY,
  machine_id INT NOT NULL,
  sensor_type VARCHAR(40) NOT NULL,
  unit VARCHAR(15) NULL,
  CONSTRAINT fk_sensors_machine FOREIGN KEY (machine_id)
    REFERENCES machines(machine_id),
  INDEX idx_sensors_machine_type (machine_id, sensor_type)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS sensor_readings (
  reading_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  sensor_id INT NOT NULL,
  recorded_at DATETIME NOT NULL,
  value DOUBLE NOT NULL,
  CONSTRAINT fk_readings_sensor FOREIGN KEY (sensor_id)
    REFERENCES sensors(sensor_id),
  INDEX idx_readings_sensor_time (sensor_id, recorded_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS fault_types (
  fault_type_id INT AUTO_INCREMENT PRIMARY KEY,
  fault_code VARCHAR(30) NOT NULL UNIQUE,
  name VARCHAR(100) NOT NULL,
  category ENUM('FAULT','PREDICTIVE_MAINTENANCE') NOT NULL,
  recommended_action TEXT NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS sensor_fault_type_map (
  sensor_id INT NOT NULL,
  fault_type_id INT NOT NULL,
  PRIMARY KEY (sensor_id, fault_type_id),
  CONSTRAINT fk_sensorfault_sensor FOREIGN KEY (sensor_id)
    REFERENCES sensors(sensor_id),
  CONSTRAINT fk_sensorfault_type FOREIGN KEY (fault_type_id)
    REFERENCES fault_types(fault_type_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS faults (
  fault_id INT AUTO_INCREMENT PRIMARY KEY,
  machine_id INT NOT NULL,
  fault_type_id INT NOT NULL,
  severity ENUM('LOW','MEDIUM','HIGH','CRITICAL') NOT NULL,
  confidence DECIMAL(4,3) NULL,
  summary VARCHAR(255) NULL,
  est_ttf_hrs INT NULL,
  model_version VARCHAR(20) NULL,
  status ENUM('OPEN','ASSIGNED','RESOLVED','DISMISSED') NOT NULL DEFAULT 'OPEN',
  detected_at DATETIME NOT NULL,
  last_seen_at DATETIME NOT NULL,
  occurrence_count INT NOT NULL DEFAULT 1,
  resolved_at DATETIME NULL,
  CONSTRAINT fk_faults_machine FOREIGN KEY (machine_id)
    REFERENCES machines(machine_id),
  CONSTRAINT fk_faults_type FOREIGN KEY (fault_type_id)
    REFERENCES fault_types(fault_type_id),
  INDEX idx_fault_machine_type_status (machine_id, fault_type_id, status),
  INDEX idx_fault_status_severity (status, severity)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS fault_evidence (
  fault_id INT NOT NULL,
  sensor_id INT NOT NULL,
  observed_value DOUBLE NULL,
  expected_value DOUBLE NULL,
  unit VARCHAR(15) NULL,
  PRIMARY KEY (fault_id, sensor_id),
  CONSTRAINT fk_evidence_fault FOREIGN KEY (fault_id)
    REFERENCES faults(fault_id),
  CONSTRAINT fk_evidence_sensor FOREIGN KEY (sensor_id)
    REFERENCES sensors(sensor_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(50) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  role ENUM('maintenance_head','technician') NOT NULL,
  created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS technicians (
  technician_id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL UNIQUE,
  availability ENUM('AVAILABLE','ON_LEAVE','OFF_SHIFT') NOT NULL DEFAULT 'AVAILABLE',
  max_active_orders INT NOT NULL DEFAULT 3,
  CONSTRAINT fk_technicians_user FOREIGN KEY (user_id)
    REFERENCES users(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS skills (
  skill_id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(60) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS technician_skills (
  technician_id INT NOT NULL,
  skill_id INT NOT NULL,
  proficiency TINYINT NOT NULL,
  PRIMARY KEY (technician_id, skill_id),
  CONSTRAINT chk_technician_proficiency CHECK (proficiency BETWEEN 1 AND 3),
  CONSTRAINT fk_techskills_technician FOREIGN KEY (technician_id)
    REFERENCES technicians(technician_id),
  CONSTRAINT fk_techskills_skill FOREIGN KEY (skill_id)
    REFERENCES skills(skill_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS fault_type_skills (
  fault_type_id INT NOT NULL,
  skill_id INT NOT NULL,
  min_proficiency TINYINT NOT NULL DEFAULT 1,
  PRIMARY KEY (fault_type_id, skill_id),
  CONSTRAINT chk_min_proficiency CHECK (min_proficiency BETWEEN 1 AND 3),
  CONSTRAINT fk_faultskills_type FOREIGN KEY (fault_type_id)
    REFERENCES fault_types(fault_type_id),
  CONSTRAINT fk_faultskills_skill FOREIGN KEY (skill_id)
    REFERENCES skills(skill_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS work_orders (
  work_order_id INT AUTO_INCREMENT PRIMARY KEY,
  fault_id INT NOT NULL,
  assigned_to INT NOT NULL,
  assigned_by INT NOT NULL,
  suggested_technician_id INT NULL,
  assignment_method ENUM('SYSTEM_SUGGESTED','MANUAL_OVERRIDE') NOT NULL,
  override_reason VARCHAR(255) NULL,
  priority ENUM('LOW','MEDIUM','HIGH','URGENT') NOT NULL,
  status ENUM('ASSIGNED','IN_PROGRESS','SUBMITTED','COMPLETED','REWORK') NOT NULL DEFAULT 'ASSIGNED',
  instructions TEXT NULL,
  assigned_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  due_at DATETIME NULL,
  started_at DATETIME NULL,
  completed_at DATETIME NULL,
  CONSTRAINT fk_workorders_fault FOREIGN KEY (fault_id)
    REFERENCES faults(fault_id),
  CONSTRAINT fk_workorders_assigned FOREIGN KEY (assigned_to)
    REFERENCES technicians(technician_id),
  CONSTRAINT fk_workorders_assigner FOREIGN KEY (assigned_by)
    REFERENCES users(id),
  CONSTRAINT fk_workorders_suggested FOREIGN KEY (suggested_technician_id)
    REFERENCES technicians(technician_id),
  INDEX idx_workorders_assigned_status (assigned_to, status)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS work_order_activity (
  activity_id INT AUTO_INCREMENT PRIMARY KEY,
  work_order_id INT NOT NULL,
  activity_type ENUM('STARTED','PAUSED','RESUMED','REPORT_SUBMITTED','REPORT_APPROVED','REPORT_REJECTED','COMPLETED') NOT NULL,
  reason VARCHAR(255) NULL,
  notes TEXT NULL,
  recorded_by INT NOT NULL,
  recorded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_activity_workorder FOREIGN KEY (work_order_id)
    REFERENCES work_orders(work_order_id),
  CONSTRAINT fk_activity_user FOREIGN KEY (recorded_by)
    REFERENCES users(id),
  INDEX idx_activity_workorder_time (work_order_id, recorded_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS work_order_reports (
  report_id INT AUTO_INCREMENT PRIMARY KEY,
  work_order_id INT NOT NULL,
  findings TEXT NOT NULL,
  action_taken TEXT NOT NULL,
  parts_used VARCHAR(255) NULL,
  time_spent_mins INT NULL,
  submitted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  review_status ENUM('PENDING_REVIEW','APPROVED','REJECTED') NOT NULL DEFAULT 'PENDING_REVIEW',
  review_comment TEXT NULL,
  reviewed_by INT NULL,
  reviewed_at DATETIME NULL,
  CONSTRAINT fk_reports_workorder FOREIGN KEY (work_order_id)
    REFERENCES work_orders(work_order_id),
  CONSTRAINT fk_reports_reviewer FOREIGN KEY (reviewed_by)
    REFERENCES users(id),
  INDEX idx_reports_review_status (review_status)
) ENGINE=InnoDB;

SET FOREIGN_KEY_CHECKS = 1;

-- Seed master data. Explicit IDs make the demo relationships predictable.
INSERT INTO production_lines (line_id, name) VALUES
  (1,'Line A'), (2,'Line B')
ON DUPLICATE KEY UPDATE name=VALUES(name);

INSERT INTO machines (machine_id,line_id,name,machine_type,criticality) VALUES
  (1,1,'CNC-01','CNC Machine','HIGH'),
  (2,1,'Conveyor-A','Conveyor','MEDIUM'),
  (3,1,'RobotArm-01','Robotic Arm','HIGH'),
  (4,2,'Injection-01','Injection Moulding','HIGH'),
  (5,2,'Conveyor-B','Conveyor','MEDIUM'),
  (6,2,'Packaging-01','Packaging Machine','HIGH')
ON DUPLICATE KEY UPDATE line_id=VALUES(line_id), name=VALUES(name),
  machine_type=VALUES(machine_type), criticality=VALUES(criticality);

INSERT INTO sensors (sensor_id,machine_id,sensor_type,unit) VALUES
  (1,1,'spindle temperature','°C'),
  (2,1,'vibration','mm/s'),
  (3,1,'spindle load','%'),
  (4,2,'vibration','mm/s'),
  (5,2,'belt speed','m/s'),
  (6,3,'joint temperature','°C'),
  (7,3,'motor current','A'),
  (8,4,'barrel temperature','°C'),
  (9,4,'injection pressure','bar'),
  (10,5,'vibration','mm/s'),
  (11,5,'belt speed','m/s'),
  (12,6,'seal temperature','°C'),
  (13,6,'throughput','units/min')
ON DUPLICATE KEY UPDATE machine_id=VALUES(machine_id),
  sensor_type=VALUES(sensor_type), unit=VALUES(unit);

INSERT INTO fault_types (fault_type_id,fault_code,name,category,recommended_action) VALUES
  (1,'SPINDLE_TEMP_ANOMALY','Spindle Temperature Anomaly','FAULT',
   'Verify the temperature reading; inspect cooling flow, lubrication, spindle load and sensor mounting. Follow machine isolation procedures. Record confirmed findings and repair.'),
  (2,'MACHINE_VIBRATION','Excessive Machine Vibration','FAULT',
   'Verify the reading; inspect bearing condition, mounting, alignment and imbalance. Follow site isolation procedures and record the confirmed cause.'),
  (3,'MOTOR_OVERHEATING','Motor or Joint Overheating','FAULT',
   'Verify temperature independently; inspect loading, cooling and electrical connections under approved safety procedures. Record findings and corrective action.')
ON DUPLICATE KEY UPDATE fault_code=VALUES(fault_code), name=VALUES(name),
  category=VALUES(category), recommended_action=VALUES(recommended_action);

INSERT INTO sensor_fault_type_map (sensor_id,fault_type_id) VALUES
  (1,1),(2,2),(4,2),(6,3)
ON DUPLICATE KEY UPDATE fault_type_id=VALUES(fault_type_id);

INSERT INTO users (id,username,password_hash,role) VALUES
  (1,'head_demo','pbkdf2:sha256:600000$smedemo2026$Mrp7WfkmrKJrzdy7xTng/mkNzqUb9nSaHCoSzFhA8SE=','maintenance_head'),
  (2,'tech01','pbkdf2:sha256:600000$smedemo2026$Mrp7WfkmrKJrzdy7xTng/mkNzqUb9nSaHCoSzFhA8SE=','technician'),
  (3,'tech02','pbkdf2:sha256:600000$smedemo2026$Mrp7WfkmrKJrzdy7xTng/mkNzqUb9nSaHCoSzFhA8SE=','technician'),
  (4,'tech03','pbkdf2:sha256:600000$smedemo2026$Mrp7WfkmrKJrzdy7xTng/mkNzqUb9nSaHCoSzFhA8SE=','technician')
ON DUPLICATE KEY UPDATE username=VALUES(username),
  password_hash=VALUES(password_hash), role=VALUES(role);

INSERT INTO technicians (technician_id,user_id,availability,max_active_orders) VALUES
  (1,2,'AVAILABLE',3),(2,3,'AVAILABLE',3),(3,4,'AVAILABLE',2)
ON DUPLICATE KEY UPDATE user_id=VALUES(user_id),
  availability=VALUES(availability), max_active_orders=VALUES(max_active_orders);

INSERT INTO skills (skill_id,name) VALUES
  (1,'SPINDLE_TEMP_ANOMALY'),
  (2,'MACHINE_VIBRATION'),
  (3,'MOTOR_OVERHEATING')
ON DUPLICATE KEY UPDATE name=VALUES(name);

INSERT INTO technician_skills (technician_id,skill_id,proficiency) VALUES
  (1,1,3),(1,2,2),(2,2,3),(2,3,2),(3,1,2),(3,3,3)
ON DUPLICATE KEY UPDATE proficiency=VALUES(proficiency);

INSERT INTO fault_type_skills (fault_type_id,skill_id,min_proficiency) VALUES
  (1,1,1),(2,2,1),(3,3,1)
ON DUPLICATE KEY UPDATE min_proficiency=VALUES(min_proficiency);

-- Baseline sensor history: enough normal readings for the analyser to learn a
-- baseline. Start simulator.py after import; new readings must be fresh.
INSERT INTO sensor_readings (sensor_id, recorded_at, value)
SELECT seed.sensor_id, seed.recorded_at, seed.value
FROM (
SELECT 1 AS sensor_id, DATE_SUB(NOW(), INTERVAL 322 SECOND) AS recorded_at, 59.2307 AS value
UNION ALL
SELECT 1 AS sensor_id, DATE_SUB(NOW(), INTERVAL 324 SECOND) AS recorded_at, 57.7373 AS value
UNION ALL
SELECT 1 AS sensor_id, DATE_SUB(NOW(), INTERVAL 326 SECOND) AS recorded_at, 56.3508 AS value
UNION ALL
SELECT 1 AS sensor_id, DATE_SUB(NOW(), INTERVAL 328 SECOND) AS recorded_at, 56.0751 AS value
UNION ALL
SELECT 1 AS sensor_id, DATE_SUB(NOW(), INTERVAL 330 SECOND) AS recorded_at, 57.2077 AS value
UNION ALL
SELECT 1 AS sensor_id, DATE_SUB(NOW(), INTERVAL 332 SECOND) AS recorded_at, 60.2856 AS value
UNION ALL
SELECT 1 AS sensor_id, DATE_SUB(NOW(), INTERVAL 334 SECOND) AS recorded_at, 57.9956 AS value
UNION ALL
SELECT 1 AS sensor_id, DATE_SUB(NOW(), INTERVAL 336 SECOND) AS recorded_at, 54.5555 AS value
UNION ALL
SELECT 1 AS sensor_id, DATE_SUB(NOW(), INTERVAL 338 SECOND) AS recorded_at, 57.4217 AS value
UNION ALL
SELECT 1 AS sensor_id, DATE_SUB(NOW(), INTERVAL 340 SECOND) AS recorded_at, 58.3447 AS value
UNION ALL
SELECT 1 AS sensor_id, DATE_SUB(NOW(), INTERVAL 342 SECOND) AS recorded_at, 55.9039 AS value
UNION ALL
SELECT 1 AS sensor_id, DATE_SUB(NOW(), INTERVAL 344 SECOND) AS recorded_at, 57.7813 AS value
UNION ALL
SELECT 1 AS sensor_id, DATE_SUB(NOW(), INTERVAL 346 SECOND) AS recorded_at, 60.0161 AS value
UNION ALL
SELECT 1 AS sensor_id, DATE_SUB(NOW(), INTERVAL 348 SECOND) AS recorded_at, 56.7878 AS value
UNION ALL
SELECT 1 AS sensor_id, DATE_SUB(NOW(), INTERVAL 350 SECOND) AS recorded_at, 55.3655 AS value
UNION ALL
SELECT 1 AS sensor_id, DATE_SUB(NOW(), INTERVAL 352 SECOND) AS recorded_at, 57.1959 AS value
UNION ALL
SELECT 1 AS sensor_id, DATE_SUB(NOW(), INTERVAL 354 SECOND) AS recorded_at, 59.1383 AS value
UNION ALL
SELECT 1 AS sensor_id, DATE_SUB(NOW(), INTERVAL 356 SECOND) AS recorded_at, 56.4455 AS value
UNION ALL
SELECT 1 AS sensor_id, DATE_SUB(NOW(), INTERVAL 358 SECOND) AS recorded_at, 57.9734 AS value
UNION ALL
SELECT 1 AS sensor_id, DATE_SUB(NOW(), INTERVAL 360 SECOND) AS recorded_at, 58.1937 AS value
UNION ALL
SELECT 1 AS sensor_id, DATE_SUB(NOW(), INTERVAL 362 SECOND) AS recorded_at, 57.8035 AS value
UNION ALL
SELECT 1 AS sensor_id, DATE_SUB(NOW(), INTERVAL 364 SECOND) AS recorded_at, 57.8818 AS value
UNION ALL
SELECT 1 AS sensor_id, DATE_SUB(NOW(), INTERVAL 366 SECOND) AS recorded_at, 55.4923 AS value
UNION ALL
SELECT 1 AS sensor_id, DATE_SUB(NOW(), INTERVAL 368 SECOND) AS recorded_at, 61.4021 AS value
UNION ALL
SELECT 1 AS sensor_id, DATE_SUB(NOW(), INTERVAL 370 SECOND) AS recorded_at, 57.8880 AS value
UNION ALL
SELECT 1 AS sensor_id, DATE_SUB(NOW(), INTERVAL 372 SECOND) AS recorded_at, 60.1368 AS value
UNION ALL
SELECT 1 AS sensor_id, DATE_SUB(NOW(), INTERVAL 374 SECOND) AS recorded_at, 57.8818 AS value
UNION ALL
SELECT 1 AS sensor_id, DATE_SUB(NOW(), INTERVAL 376 SECOND) AS recorded_at, 56.7675 AS value
UNION ALL
SELECT 1 AS sensor_id, DATE_SUB(NOW(), INTERVAL 378 SECOND) AS recorded_at, 55.6592 AS value
UNION ALL
SELECT 1 AS sensor_id, DATE_SUB(NOW(), INTERVAL 380 SECOND) AS recorded_at, 56.2616 AS value
UNION ALL
SELECT 1 AS sensor_id, DATE_SUB(NOW(), INTERVAL 382 SECOND) AS recorded_at, 57.7989 AS value
UNION ALL
SELECT 1 AS sensor_id, DATE_SUB(NOW(), INTERVAL 384 SECOND) AS recorded_at, 56.7517 AS value
UNION ALL
SELECT 1 AS sensor_id, DATE_SUB(NOW(), INTERVAL 386 SECOND) AS recorded_at, 60.0858 AS value
UNION ALL
SELECT 1 AS sensor_id, DATE_SUB(NOW(), INTERVAL 388 SECOND) AS recorded_at, 57.9297 AS value
UNION ALL
SELECT 1 AS sensor_id, DATE_SUB(NOW(), INTERVAL 390 SECOND) AS recorded_at, 58.1564 AS value
UNION ALL
SELECT 1 AS sensor_id, DATE_SUB(NOW(), INTERVAL 392 SECOND) AS recorded_at, 60.5389 AS value
UNION ALL
SELECT 1 AS sensor_id, DATE_SUB(NOW(), INTERVAL 394 SECOND) AS recorded_at, 58.6033 AS value
UNION ALL
SELECT 1 AS sensor_id, DATE_SUB(NOW(), INTERVAL 396 SECOND) AS recorded_at, 55.1958 AS value
UNION ALL
SELECT 1 AS sensor_id, DATE_SUB(NOW(), INTERVAL 398 SECOND) AS recorded_at, 59.2921 AS value
UNION ALL
SELECT 1 AS sensor_id, DATE_SUB(NOW(), INTERVAL 400 SECOND) AS recorded_at, 55.8610 AS value
UNION ALL
SELECT 2 AS sensor_id, DATE_SUB(NOW(), INTERVAL 322 SECOND) AS recorded_at, 1.8439 AS value
UNION ALL
SELECT 2 AS sensor_id, DATE_SUB(NOW(), INTERVAL 324 SECOND) AS recorded_at, 2.1275 AS value
UNION ALL
SELECT 2 AS sensor_id, DATE_SUB(NOW(), INTERVAL 326 SECOND) AS recorded_at, 2.0205 AS value
UNION ALL
SELECT 2 AS sensor_id, DATE_SUB(NOW(), INTERVAL 328 SECOND) AS recorded_at, 1.7779 AS value
UNION ALL
SELECT 2 AS sensor_id, DATE_SUB(NOW(), INTERVAL 330 SECOND) AS recorded_at, 2.0765 AS value
UNION ALL
SELECT 2 AS sensor_id, DATE_SUB(NOW(), INTERVAL 332 SECOND) AS recorded_at, 2.3434 AS value
UNION ALL
SELECT 2 AS sensor_id, DATE_SUB(NOW(), INTERVAL 334 SECOND) AS recorded_at, 1.7665 AS value
UNION ALL
SELECT 2 AS sensor_id, DATE_SUB(NOW(), INTERVAL 336 SECOND) AS recorded_at, 1.8799 AS value
UNION ALL
SELECT 2 AS sensor_id, DATE_SUB(NOW(), INTERVAL 338 SECOND) AS recorded_at, 1.7922 AS value
UNION ALL
SELECT 2 AS sensor_id, DATE_SUB(NOW(), INTERVAL 340 SECOND) AS recorded_at, 1.9777 AS value
UNION ALL
SELECT 2 AS sensor_id, DATE_SUB(NOW(), INTERVAL 342 SECOND) AS recorded_at, 1.9210 AS value
UNION ALL
SELECT 2 AS sensor_id, DATE_SUB(NOW(), INTERVAL 344 SECOND) AS recorded_at, 1.9395 AS value
UNION ALL
SELECT 2 AS sensor_id, DATE_SUB(NOW(), INTERVAL 346 SECOND) AS recorded_at, 1.7776 AS value
UNION ALL
SELECT 2 AS sensor_id, DATE_SUB(NOW(), INTERVAL 348 SECOND) AS recorded_at, 2.0133 AS value
UNION ALL
SELECT 2 AS sensor_id, DATE_SUB(NOW(), INTERVAL 350 SECOND) AS recorded_at, 1.9502 AS value
UNION ALL
SELECT 2 AS sensor_id, DATE_SUB(NOW(), INTERVAL 352 SECOND) AS recorded_at, 2.2683 AS value
UNION ALL
SELECT 2 AS sensor_id, DATE_SUB(NOW(), INTERVAL 354 SECOND) AS recorded_at, 1.9758 AS value
UNION ALL
SELECT 2 AS sensor_id, DATE_SUB(NOW(), INTERVAL 356 SECOND) AS recorded_at, 1.7900 AS value
UNION ALL
SELECT 2 AS sensor_id, DATE_SUB(NOW(), INTERVAL 358 SECOND) AS recorded_at, 1.8143 AS value
UNION ALL
SELECT 2 AS sensor_id, DATE_SUB(NOW(), INTERVAL 360 SECOND) AS recorded_at, 1.9678 AS value
UNION ALL
SELECT 2 AS sensor_id, DATE_SUB(NOW(), INTERVAL 362 SECOND) AS recorded_at, 1.9180 AS value
UNION ALL
SELECT 2 AS sensor_id, DATE_SUB(NOW(), INTERVAL 364 SECOND) AS recorded_at, 1.9065 AS value
UNION ALL
SELECT 2 AS sensor_id, DATE_SUB(NOW(), INTERVAL 366 SECOND) AS recorded_at, 2.1539 AS value
UNION ALL
SELECT 2 AS sensor_id, DATE_SUB(NOW(), INTERVAL 368 SECOND) AS recorded_at, 2.0019 AS value
UNION ALL
SELECT 2 AS sensor_id, DATE_SUB(NOW(), INTERVAL 370 SECOND) AS recorded_at, 1.9441 AS value
UNION ALL
SELECT 2 AS sensor_id, DATE_SUB(NOW(), INTERVAL 372 SECOND) AS recorded_at, 1.8580 AS value
UNION ALL
SELECT 2 AS sensor_id, DATE_SUB(NOW(), INTERVAL 374 SECOND) AS recorded_at, 1.8774 AS value
UNION ALL
SELECT 2 AS sensor_id, DATE_SUB(NOW(), INTERVAL 376 SECOND) AS recorded_at, 2.0884 AS value
UNION ALL
SELECT 2 AS sensor_id, DATE_SUB(NOW(), INTERVAL 378 SECOND) AS recorded_at, 2.1365 AS value
UNION ALL
SELECT 2 AS sensor_id, DATE_SUB(NOW(), INTERVAL 380 SECOND) AS recorded_at, 2.1055 AS value
UNION ALL
SELECT 2 AS sensor_id, DATE_SUB(NOW(), INTERVAL 382 SECOND) AS recorded_at, 2.0584 AS value
UNION ALL
SELECT 2 AS sensor_id, DATE_SUB(NOW(), INTERVAL 384 SECOND) AS recorded_at, 2.0257 AS value
UNION ALL
SELECT 2 AS sensor_id, DATE_SUB(NOW(), INTERVAL 386 SECOND) AS recorded_at, 2.2601 AS value
UNION ALL
SELECT 2 AS sensor_id, DATE_SUB(NOW(), INTERVAL 388 SECOND) AS recorded_at, 2.1420 AS value
UNION ALL
SELECT 2 AS sensor_id, DATE_SUB(NOW(), INTERVAL 390 SECOND) AS recorded_at, 2.1413 AS value
UNION ALL
SELECT 2 AS sensor_id, DATE_SUB(NOW(), INTERVAL 392 SECOND) AS recorded_at, 1.9085 AS value
UNION ALL
SELECT 2 AS sensor_id, DATE_SUB(NOW(), INTERVAL 394 SECOND) AS recorded_at, 2.0760 AS value
UNION ALL
SELECT 2 AS sensor_id, DATE_SUB(NOW(), INTERVAL 396 SECOND) AS recorded_at, 1.9686 AS value
UNION ALL
SELECT 2 AS sensor_id, DATE_SUB(NOW(), INTERVAL 398 SECOND) AS recorded_at, 1.9286 AS value
UNION ALL
SELECT 2 AS sensor_id, DATE_SUB(NOW(), INTERVAL 400 SECOND) AS recorded_at, 1.8843 AS value
UNION ALL
SELECT 3 AS sensor_id, DATE_SUB(NOW(), INTERVAL 322 SECOND) AS recorded_at, 51.5812 AS value
UNION ALL
SELECT 3 AS sensor_id, DATE_SUB(NOW(), INTERVAL 324 SECOND) AS recorded_at, 50.8768 AS value
UNION ALL
SELECT 3 AS sensor_id, DATE_SUB(NOW(), INTERVAL 326 SECOND) AS recorded_at, 50.1835 AS value
UNION ALL
SELECT 3 AS sensor_id, DATE_SUB(NOW(), INTERVAL 328 SECOND) AS recorded_at, 49.8152 AS value
UNION ALL
SELECT 3 AS sensor_id, DATE_SUB(NOW(), INTERVAL 330 SECOND) AS recorded_at, 49.6415 AS value
UNION ALL
SELECT 3 AS sensor_id, DATE_SUB(NOW(), INTERVAL 332 SECOND) AS recorded_at, 50.0518 AS value
UNION ALL
SELECT 3 AS sensor_id, DATE_SUB(NOW(), INTERVAL 334 SECOND) AS recorded_at, 51.2520 AS value
UNION ALL
SELECT 3 AS sensor_id, DATE_SUB(NOW(), INTERVAL 336 SECOND) AS recorded_at, 45.5320 AS value
UNION ALL
SELECT 3 AS sensor_id, DATE_SUB(NOW(), INTERVAL 338 SECOND) AS recorded_at, 46.1388 AS value
UNION ALL
SELECT 3 AS sensor_id, DATE_SUB(NOW(), INTERVAL 340 SECOND) AS recorded_at, 47.4019 AS value
UNION ALL
SELECT 3 AS sensor_id, DATE_SUB(NOW(), INTERVAL 342 SECOND) AS recorded_at, 48.9527 AS value
UNION ALL
SELECT 3 AS sensor_id, DATE_SUB(NOW(), INTERVAL 344 SECOND) AS recorded_at, 49.3495 AS value
UNION ALL
SELECT 3 AS sensor_id, DATE_SUB(NOW(), INTERVAL 346 SECOND) AS recorded_at, 46.6153 AS value
UNION ALL
SELECT 3 AS sensor_id, DATE_SUB(NOW(), INTERVAL 348 SECOND) AS recorded_at, 43.6122 AS value
UNION ALL
SELECT 3 AS sensor_id, DATE_SUB(NOW(), INTERVAL 350 SECOND) AS recorded_at, 47.7613 AS value
UNION ALL
SELECT 3 AS sensor_id, DATE_SUB(NOW(), INTERVAL 352 SECOND) AS recorded_at, 43.3564 AS value
UNION ALL
SELECT 3 AS sensor_id, DATE_SUB(NOW(), INTERVAL 354 SECOND) AS recorded_at, 47.9764 AS value
UNION ALL
SELECT 3 AS sensor_id, DATE_SUB(NOW(), INTERVAL 356 SECOND) AS recorded_at, 51.5292 AS value
UNION ALL
SELECT 3 AS sensor_id, DATE_SUB(NOW(), INTERVAL 358 SECOND) AS recorded_at, 42.6401 AS value
UNION ALL
SELECT 3 AS sensor_id, DATE_SUB(NOW(), INTERVAL 360 SECOND) AS recorded_at, 53.9419 AS value
UNION ALL
SELECT 3 AS sensor_id, DATE_SUB(NOW(), INTERVAL 362 SECOND) AS recorded_at, 46.0715 AS value
UNION ALL
SELECT 3 AS sensor_id, DATE_SUB(NOW(), INTERVAL 364 SECOND) AS recorded_at, 41.6716 AS value
UNION ALL
SELECT 3 AS sensor_id, DATE_SUB(NOW(), INTERVAL 366 SECOND) AS recorded_at, 43.0882 AS value
UNION ALL
SELECT 3 AS sensor_id, DATE_SUB(NOW(), INTERVAL 368 SECOND) AS recorded_at, 40.4970 AS value
UNION ALL
SELECT 3 AS sensor_id, DATE_SUB(NOW(), INTERVAL 370 SECOND) AS recorded_at, 48.0082 AS value
UNION ALL
SELECT 3 AS sensor_id, DATE_SUB(NOW(), INTERVAL 372 SECOND) AS recorded_at, 47.9105 AS value
UNION ALL
SELECT 3 AS sensor_id, DATE_SUB(NOW(), INTERVAL 374 SECOND) AS recorded_at, 48.8610 AS value
UNION ALL
SELECT 3 AS sensor_id, DATE_SUB(NOW(), INTERVAL 376 SECOND) AS recorded_at, 48.4752 AS value
UNION ALL
SELECT 3 AS sensor_id, DATE_SUB(NOW(), INTERVAL 378 SECOND) AS recorded_at, 49.8851 AS value
UNION ALL
SELECT 3 AS sensor_id, DATE_SUB(NOW(), INTERVAL 380 SECOND) AS recorded_at, 46.5093 AS value
UNION ALL
SELECT 3 AS sensor_id, DATE_SUB(NOW(), INTERVAL 382 SECOND) AS recorded_at, 43.4884 AS value
UNION ALL
SELECT 3 AS sensor_id, DATE_SUB(NOW(), INTERVAL 384 SECOND) AS recorded_at, 49.0795 AS value
UNION ALL
SELECT 3 AS sensor_id, DATE_SUB(NOW(), INTERVAL 386 SECOND) AS recorded_at, 48.4563 AS value
UNION ALL
SELECT 3 AS sensor_id, DATE_SUB(NOW(), INTERVAL 388 SECOND) AS recorded_at, 50.7757 AS value
UNION ALL
SELECT 3 AS sensor_id, DATE_SUB(NOW(), INTERVAL 390 SECOND) AS recorded_at, 49.6519 AS value
UNION ALL
SELECT 3 AS sensor_id, DATE_SUB(NOW(), INTERVAL 392 SECOND) AS recorded_at, 46.5100 AS value
UNION ALL
SELECT 3 AS sensor_id, DATE_SUB(NOW(), INTERVAL 394 SECOND) AS recorded_at, 49.9342 AS value
UNION ALL
SELECT 3 AS sensor_id, DATE_SUB(NOW(), INTERVAL 396 SECOND) AS recorded_at, 44.5710 AS value
UNION ALL
SELECT 3 AS sensor_id, DATE_SUB(NOW(), INTERVAL 398 SECOND) AS recorded_at, 46.6990 AS value
UNION ALL
SELECT 3 AS sensor_id, DATE_SUB(NOW(), INTERVAL 400 SECOND) AS recorded_at, 44.7575 AS value
UNION ALL
SELECT 4 AS sensor_id, DATE_SUB(NOW(), INTERVAL 322 SECOND) AS recorded_at, 1.9186 AS value
UNION ALL
SELECT 4 AS sensor_id, DATE_SUB(NOW(), INTERVAL 324 SECOND) AS recorded_at, 1.8312 AS value
UNION ALL
SELECT 4 AS sensor_id, DATE_SUB(NOW(), INTERVAL 326 SECOND) AS recorded_at, 1.9105 AS value
UNION ALL
SELECT 4 AS sensor_id, DATE_SUB(NOW(), INTERVAL 328 SECOND) AS recorded_at, 2.0472 AS value
UNION ALL
SELECT 4 AS sensor_id, DATE_SUB(NOW(), INTERVAL 330 SECOND) AS recorded_at, 1.8206 AS value
UNION ALL
SELECT 4 AS sensor_id, DATE_SUB(NOW(), INTERVAL 332 SECOND) AS recorded_at, 2.0851 AS value
UNION ALL
SELECT 4 AS sensor_id, DATE_SUB(NOW(), INTERVAL 334 SECOND) AS recorded_at, 2.0816 AS value
UNION ALL
SELECT 4 AS sensor_id, DATE_SUB(NOW(), INTERVAL 336 SECOND) AS recorded_at, 2.0056 AS value
UNION ALL
SELECT 4 AS sensor_id, DATE_SUB(NOW(), INTERVAL 338 SECOND) AS recorded_at, 1.8903 AS value
UNION ALL
SELECT 4 AS sensor_id, DATE_SUB(NOW(), INTERVAL 340 SECOND) AS recorded_at, 2.1495 AS value
UNION ALL
SELECT 4 AS sensor_id, DATE_SUB(NOW(), INTERVAL 342 SECOND) AS recorded_at, 1.9145 AS value
UNION ALL
SELECT 4 AS sensor_id, DATE_SUB(NOW(), INTERVAL 344 SECOND) AS recorded_at, 1.9953 AS value
UNION ALL
SELECT 4 AS sensor_id, DATE_SUB(NOW(), INTERVAL 346 SECOND) AS recorded_at, 2.1135 AS value
UNION ALL
SELECT 4 AS sensor_id, DATE_SUB(NOW(), INTERVAL 348 SECOND) AS recorded_at, 1.8916 AS value
UNION ALL
SELECT 4 AS sensor_id, DATE_SUB(NOW(), INTERVAL 350 SECOND) AS recorded_at, 2.0903 AS value
UNION ALL
SELECT 4 AS sensor_id, DATE_SUB(NOW(), INTERVAL 352 SECOND) AS recorded_at, 1.9251 AS value
UNION ALL
SELECT 4 AS sensor_id, DATE_SUB(NOW(), INTERVAL 354 SECOND) AS recorded_at, 2.1507 AS value
UNION ALL
SELECT 4 AS sensor_id, DATE_SUB(NOW(), INTERVAL 356 SECOND) AS recorded_at, 1.9515 AS value
UNION ALL
SELECT 4 AS sensor_id, DATE_SUB(NOW(), INTERVAL 358 SECOND) AS recorded_at, 1.9607 AS value
UNION ALL
SELECT 4 AS sensor_id, DATE_SUB(NOW(), INTERVAL 360 SECOND) AS recorded_at, 2.0571 AS value
UNION ALL
SELECT 4 AS sensor_id, DATE_SUB(NOW(), INTERVAL 362 SECOND) AS recorded_at, 2.0232 AS value
UNION ALL
SELECT 4 AS sensor_id, DATE_SUB(NOW(), INTERVAL 364 SECOND) AS recorded_at, 1.9294 AS value
UNION ALL
SELECT 4 AS sensor_id, DATE_SUB(NOW(), INTERVAL 366 SECOND) AS recorded_at, 2.0955 AS value
UNION ALL
SELECT 4 AS sensor_id, DATE_SUB(NOW(), INTERVAL 368 SECOND) AS recorded_at, 1.8026 AS value
UNION ALL
SELECT 4 AS sensor_id, DATE_SUB(NOW(), INTERVAL 370 SECOND) AS recorded_at, 2.1305 AS value
UNION ALL
SELECT 4 AS sensor_id, DATE_SUB(NOW(), INTERVAL 372 SECOND) AS recorded_at, 2.1430 AS value
UNION ALL
SELECT 4 AS sensor_id, DATE_SUB(NOW(), INTERVAL 374 SECOND) AS recorded_at, 1.9839 AS value
UNION ALL
SELECT 4 AS sensor_id, DATE_SUB(NOW(), INTERVAL 376 SECOND) AS recorded_at, 1.9494 AS value
UNION ALL
SELECT 4 AS sensor_id, DATE_SUB(NOW(), INTERVAL 378 SECOND) AS recorded_at, 2.0170 AS value
UNION ALL
SELECT 4 AS sensor_id, DATE_SUB(NOW(), INTERVAL 380 SECOND) AS recorded_at, 1.7071 AS value
UNION ALL
SELECT 4 AS sensor_id, DATE_SUB(NOW(), INTERVAL 382 SECOND) AS recorded_at, 1.9244 AS value
UNION ALL
SELECT 4 AS sensor_id, DATE_SUB(NOW(), INTERVAL 384 SECOND) AS recorded_at, 2.1266 AS value
UNION ALL
SELECT 4 AS sensor_id, DATE_SUB(NOW(), INTERVAL 386 SECOND) AS recorded_at, 1.9250 AS value
UNION ALL
SELECT 4 AS sensor_id, DATE_SUB(NOW(), INTERVAL 388 SECOND) AS recorded_at, 2.0472 AS value
UNION ALL
SELECT 4 AS sensor_id, DATE_SUB(NOW(), INTERVAL 390 SECOND) AS recorded_at, 2.0939 AS value
UNION ALL
SELECT 4 AS sensor_id, DATE_SUB(NOW(), INTERVAL 392 SECOND) AS recorded_at, 2.1504 AS value
UNION ALL
SELECT 4 AS sensor_id, DATE_SUB(NOW(), INTERVAL 394 SECOND) AS recorded_at, 2.0612 AS value
UNION ALL
SELECT 4 AS sensor_id, DATE_SUB(NOW(), INTERVAL 396 SECOND) AS recorded_at, 1.9873 AS value
UNION ALL
SELECT 4 AS sensor_id, DATE_SUB(NOW(), INTERVAL 398 SECOND) AS recorded_at, 2.1483 AS value
UNION ALL
SELECT 4 AS sensor_id, DATE_SUB(NOW(), INTERVAL 400 SECOND) AS recorded_at, 2.0203 AS value
UNION ALL
SELECT 5 AS sensor_id, DATE_SUB(NOW(), INTERVAL 322 SECOND) AS recorded_at, 1.1923 AS value
UNION ALL
SELECT 5 AS sensor_id, DATE_SUB(NOW(), INTERVAL 324 SECOND) AS recorded_at, 1.2802 AS value
UNION ALL
SELECT 5 AS sensor_id, DATE_SUB(NOW(), INTERVAL 326 SECOND) AS recorded_at, 1.1977 AS value
UNION ALL
SELECT 5 AS sensor_id, DATE_SUB(NOW(), INTERVAL 328 SECOND) AS recorded_at, 1.2083 AS value
UNION ALL
SELECT 5 AS sensor_id, DATE_SUB(NOW(), INTERVAL 330 SECOND) AS recorded_at, 1.1848 AS value
UNION ALL
SELECT 5 AS sensor_id, DATE_SUB(NOW(), INTERVAL 332 SECOND) AS recorded_at, 1.2382 AS value
UNION ALL
SELECT 5 AS sensor_id, DATE_SUB(NOW(), INTERVAL 334 SECOND) AS recorded_at, 1.1625 AS value
UNION ALL
SELECT 5 AS sensor_id, DATE_SUB(NOW(), INTERVAL 336 SECOND) AS recorded_at, 1.2168 AS value
UNION ALL
SELECT 5 AS sensor_id, DATE_SUB(NOW(), INTERVAL 338 SECOND) AS recorded_at, 1.1776 AS value
UNION ALL
SELECT 5 AS sensor_id, DATE_SUB(NOW(), INTERVAL 340 SECOND) AS recorded_at, 1.3004 AS value
UNION ALL
SELECT 5 AS sensor_id, DATE_SUB(NOW(), INTERVAL 342 SECOND) AS recorded_at, 1.2283 AS value
UNION ALL
SELECT 5 AS sensor_id, DATE_SUB(NOW(), INTERVAL 344 SECOND) AS recorded_at, 1.2025 AS value
UNION ALL
SELECT 5 AS sensor_id, DATE_SUB(NOW(), INTERVAL 346 SECOND) AS recorded_at, 1.2114 AS value
UNION ALL
SELECT 5 AS sensor_id, DATE_SUB(NOW(), INTERVAL 348 SECOND) AS recorded_at, 1.1757 AS value
UNION ALL
SELECT 5 AS sensor_id, DATE_SUB(NOW(), INTERVAL 350 SECOND) AS recorded_at, 1.2099 AS value
UNION ALL
SELECT 5 AS sensor_id, DATE_SUB(NOW(), INTERVAL 352 SECOND) AS recorded_at, 1.2386 AS value
UNION ALL
SELECT 5 AS sensor_id, DATE_SUB(NOW(), INTERVAL 354 SECOND) AS recorded_at, 1.1497 AS value
UNION ALL
SELECT 5 AS sensor_id, DATE_SUB(NOW(), INTERVAL 356 SECOND) AS recorded_at, 1.1449 AS value
UNION ALL
SELECT 5 AS sensor_id, DATE_SUB(NOW(), INTERVAL 358 SECOND) AS recorded_at, 1.2058 AS value
UNION ALL
SELECT 5 AS sensor_id, DATE_SUB(NOW(), INTERVAL 360 SECOND) AS recorded_at, 1.1757 AS value
UNION ALL
SELECT 5 AS sensor_id, DATE_SUB(NOW(), INTERVAL 362 SECOND) AS recorded_at, 1.2226 AS value
UNION ALL
SELECT 5 AS sensor_id, DATE_SUB(NOW(), INTERVAL 364 SECOND) AS recorded_at, 1.1897 AS value
UNION ALL
SELECT 5 AS sensor_id, DATE_SUB(NOW(), INTERVAL 366 SECOND) AS recorded_at, 1.2278 AS value
UNION ALL
SELECT 5 AS sensor_id, DATE_SUB(NOW(), INTERVAL 368 SECOND) AS recorded_at, 1.1258 AS value
UNION ALL
SELECT 5 AS sensor_id, DATE_SUB(NOW(), INTERVAL 370 SECOND) AS recorded_at, 1.2292 AS value
UNION ALL
SELECT 5 AS sensor_id, DATE_SUB(NOW(), INTERVAL 372 SECOND) AS recorded_at, 1.2259 AS value
UNION ALL
SELECT 5 AS sensor_id, DATE_SUB(NOW(), INTERVAL 374 SECOND) AS recorded_at, 1.2103 AS value
UNION ALL
SELECT 5 AS sensor_id, DATE_SUB(NOW(), INTERVAL 376 SECOND) AS recorded_at, 1.2432 AS value
UNION ALL
SELECT 5 AS sensor_id, DATE_SUB(NOW(), INTERVAL 378 SECOND) AS recorded_at, 1.2145 AS value
UNION ALL
SELECT 5 AS sensor_id, DATE_SUB(NOW(), INTERVAL 380 SECOND) AS recorded_at, 1.1294 AS value
UNION ALL
SELECT 5 AS sensor_id, DATE_SUB(NOW(), INTERVAL 382 SECOND) AS recorded_at, 1.2005 AS value
UNION ALL
SELECT 5 AS sensor_id, DATE_SUB(NOW(), INTERVAL 384 SECOND) AS recorded_at, 1.1902 AS value
UNION ALL
SELECT 5 AS sensor_id, DATE_SUB(NOW(), INTERVAL 386 SECOND) AS recorded_at, 1.1777 AS value
UNION ALL
SELECT 5 AS sensor_id, DATE_SUB(NOW(), INTERVAL 388 SECOND) AS recorded_at, 1.2878 AS value
UNION ALL
SELECT 5 AS sensor_id, DATE_SUB(NOW(), INTERVAL 390 SECOND) AS recorded_at, 1.1946 AS value
UNION ALL
SELECT 5 AS sensor_id, DATE_SUB(NOW(), INTERVAL 392 SECOND) AS recorded_at, 1.1323 AS value
UNION ALL
SELECT 5 AS sensor_id, DATE_SUB(NOW(), INTERVAL 394 SECOND) AS recorded_at, 1.2107 AS value
UNION ALL
SELECT 5 AS sensor_id, DATE_SUB(NOW(), INTERVAL 396 SECOND) AS recorded_at, 1.2207 AS value
UNION ALL
SELECT 5 AS sensor_id, DATE_SUB(NOW(), INTERVAL 398 SECOND) AS recorded_at, 1.1452 AS value
UNION ALL
SELECT 5 AS sensor_id, DATE_SUB(NOW(), INTERVAL 400 SECOND) AS recorded_at, 1.2037 AS value
UNION ALL
SELECT 6 AS sensor_id, DATE_SUB(NOW(), INTERVAL 322 SECOND) AS recorded_at, 57.1669 AS value
UNION ALL
SELECT 6 AS sensor_id, DATE_SUB(NOW(), INTERVAL 324 SECOND) AS recorded_at, 57.1563 AS value
UNION ALL
SELECT 6 AS sensor_id, DATE_SUB(NOW(), INTERVAL 326 SECOND) AS recorded_at, 51.9127 AS value
UNION ALL
SELECT 6 AS sensor_id, DATE_SUB(NOW(), INTERVAL 328 SECOND) AS recorded_at, 53.4820 AS value
UNION ALL
SELECT 6 AS sensor_id, DATE_SUB(NOW(), INTERVAL 330 SECOND) AS recorded_at, 56.2610 AS value
UNION ALL
SELECT 6 AS sensor_id, DATE_SUB(NOW(), INTERVAL 332 SECOND) AS recorded_at, 54.1588 AS value
UNION ALL
SELECT 6 AS sensor_id, DATE_SUB(NOW(), INTERVAL 334 SECOND) AS recorded_at, 54.5419 AS value
UNION ALL
SELECT 6 AS sensor_id, DATE_SUB(NOW(), INTERVAL 336 SECOND) AS recorded_at, 57.8169 AS value
UNION ALL
SELECT 6 AS sensor_id, DATE_SUB(NOW(), INTERVAL 338 SECOND) AS recorded_at, 52.9686 AS value
UNION ALL
SELECT 6 AS sensor_id, DATE_SUB(NOW(), INTERVAL 340 SECOND) AS recorded_at, 55.0323 AS value
UNION ALL
SELECT 6 AS sensor_id, DATE_SUB(NOW(), INTERVAL 342 SECOND) AS recorded_at, 54.2397 AS value
UNION ALL
SELECT 6 AS sensor_id, DATE_SUB(NOW(), INTERVAL 344 SECOND) AS recorded_at, 50.9284 AS value
UNION ALL
SELECT 6 AS sensor_id, DATE_SUB(NOW(), INTERVAL 346 SECOND) AS recorded_at, 53.3454 AS value
UNION ALL
SELECT 6 AS sensor_id, DATE_SUB(NOW(), INTERVAL 348 SECOND) AS recorded_at, 54.8456 AS value
UNION ALL
SELECT 6 AS sensor_id, DATE_SUB(NOW(), INTERVAL 350 SECOND) AS recorded_at, 55.3731 AS value
UNION ALL
SELECT 6 AS sensor_id, DATE_SUB(NOW(), INTERVAL 352 SECOND) AS recorded_at, 54.5319 AS value
UNION ALL
SELECT 6 AS sensor_id, DATE_SUB(NOW(), INTERVAL 354 SECOND) AS recorded_at, 54.0223 AS value
UNION ALL
SELECT 6 AS sensor_id, DATE_SUB(NOW(), INTERVAL 356 SECOND) AS recorded_at, 55.3986 AS value
UNION ALL
SELECT 6 AS sensor_id, DATE_SUB(NOW(), INTERVAL 358 SECOND) AS recorded_at, 52.8616 AS value
UNION ALL
SELECT 6 AS sensor_id, DATE_SUB(NOW(), INTERVAL 360 SECOND) AS recorded_at, 53.2109 AS value
UNION ALL
SELECT 6 AS sensor_id, DATE_SUB(NOW(), INTERVAL 362 SECOND) AS recorded_at, 54.0856 AS value
UNION ALL
SELECT 6 AS sensor_id, DATE_SUB(NOW(), INTERVAL 364 SECOND) AS recorded_at, 55.4591 AS value
UNION ALL
SELECT 6 AS sensor_id, DATE_SUB(NOW(), INTERVAL 366 SECOND) AS recorded_at, 57.3368 AS value
UNION ALL
SELECT 6 AS sensor_id, DATE_SUB(NOW(), INTERVAL 368 SECOND) AS recorded_at, 57.2253 AS value
UNION ALL
SELECT 6 AS sensor_id, DATE_SUB(NOW(), INTERVAL 370 SECOND) AS recorded_at, 51.9827 AS value
UNION ALL
SELECT 6 AS sensor_id, DATE_SUB(NOW(), INTERVAL 372 SECOND) AS recorded_at, 53.2046 AS value
UNION ALL
SELECT 6 AS sensor_id, DATE_SUB(NOW(), INTERVAL 374 SECOND) AS recorded_at, 54.8563 AS value
UNION ALL
SELECT 6 AS sensor_id, DATE_SUB(NOW(), INTERVAL 376 SECOND) AS recorded_at, 56.2218 AS value
UNION ALL
SELECT 6 AS sensor_id, DATE_SUB(NOW(), INTERVAL 378 SECOND) AS recorded_at, 55.9130 AS value
UNION ALL
SELECT 6 AS sensor_id, DATE_SUB(NOW(), INTERVAL 380 SECOND) AS recorded_at, 56.9326 AS value
UNION ALL
SELECT 6 AS sensor_id, DATE_SUB(NOW(), INTERVAL 382 SECOND) AS recorded_at, 52.2606 AS value
UNION ALL
SELECT 6 AS sensor_id, DATE_SUB(NOW(), INTERVAL 384 SECOND) AS recorded_at, 53.8898 AS value
UNION ALL
SELECT 6 AS sensor_id, DATE_SUB(NOW(), INTERVAL 386 SECOND) AS recorded_at, 53.8535 AS value
UNION ALL
SELECT 6 AS sensor_id, DATE_SUB(NOW(), INTERVAL 388 SECOND) AS recorded_at, 54.2812 AS value
UNION ALL
SELECT 6 AS sensor_id, DATE_SUB(NOW(), INTERVAL 390 SECOND) AS recorded_at, 57.1054 AS value
UNION ALL
SELECT 6 AS sensor_id, DATE_SUB(NOW(), INTERVAL 392 SECOND) AS recorded_at, 56.5825 AS value
UNION ALL
SELECT 6 AS sensor_id, DATE_SUB(NOW(), INTERVAL 394 SECOND) AS recorded_at, 56.2678 AS value
UNION ALL
SELECT 6 AS sensor_id, DATE_SUB(NOW(), INTERVAL 396 SECOND) AS recorded_at, 54.5731 AS value
UNION ALL
SELECT 6 AS sensor_id, DATE_SUB(NOW(), INTERVAL 398 SECOND) AS recorded_at, 54.3020 AS value
UNION ALL
SELECT 6 AS sensor_id, DATE_SUB(NOW(), INTERVAL 400 SECOND) AS recorded_at, 56.6932 AS value
UNION ALL
SELECT 7 AS sensor_id, DATE_SUB(NOW(), INTERVAL 322 SECOND) AS recorded_at, 3.0244 AS value
UNION ALL
SELECT 7 AS sensor_id, DATE_SUB(NOW(), INTERVAL 324 SECOND) AS recorded_at, 3.3749 AS value
UNION ALL
SELECT 7 AS sensor_id, DATE_SUB(NOW(), INTERVAL 326 SECOND) AS recorded_at, 3.0291 AS value
UNION ALL
SELECT 7 AS sensor_id, DATE_SUB(NOW(), INTERVAL 328 SECOND) AS recorded_at, 3.2211 AS value
UNION ALL
SELECT 7 AS sensor_id, DATE_SUB(NOW(), INTERVAL 330 SECOND) AS recorded_at, 3.1181 AS value
UNION ALL
SELECT 7 AS sensor_id, DATE_SUB(NOW(), INTERVAL 332 SECOND) AS recorded_at, 3.2793 AS value
UNION ALL
SELECT 7 AS sensor_id, DATE_SUB(NOW(), INTERVAL 334 SECOND) AS recorded_at, 3.5186 AS value
UNION ALL
SELECT 7 AS sensor_id, DATE_SUB(NOW(), INTERVAL 336 SECOND) AS recorded_at, 3.0330 AS value
UNION ALL
SELECT 7 AS sensor_id, DATE_SUB(NOW(), INTERVAL 338 SECOND) AS recorded_at, 3.2364 AS value
UNION ALL
SELECT 7 AS sensor_id, DATE_SUB(NOW(), INTERVAL 340 SECOND) AS recorded_at, 3.3410 AS value
UNION ALL
SELECT 7 AS sensor_id, DATE_SUB(NOW(), INTERVAL 342 SECOND) AS recorded_at, 3.1728 AS value
UNION ALL
SELECT 7 AS sensor_id, DATE_SUB(NOW(), INTERVAL 344 SECOND) AS recorded_at, 3.0625 AS value
UNION ALL
SELECT 7 AS sensor_id, DATE_SUB(NOW(), INTERVAL 346 SECOND) AS recorded_at, 3.0196 AS value
UNION ALL
SELECT 7 AS sensor_id, DATE_SUB(NOW(), INTERVAL 348 SECOND) AS recorded_at, 3.2694 AS value
UNION ALL
SELECT 7 AS sensor_id, DATE_SUB(NOW(), INTERVAL 350 SECOND) AS recorded_at, 3.1810 AS value
UNION ALL
SELECT 7 AS sensor_id, DATE_SUB(NOW(), INTERVAL 352 SECOND) AS recorded_at, 3.3473 AS value
UNION ALL
SELECT 7 AS sensor_id, DATE_SUB(NOW(), INTERVAL 354 SECOND) AS recorded_at, 3.1297 AS value
UNION ALL
SELECT 7 AS sensor_id, DATE_SUB(NOW(), INTERVAL 356 SECOND) AS recorded_at, 2.8521 AS value
UNION ALL
SELECT 7 AS sensor_id, DATE_SUB(NOW(), INTERVAL 358 SECOND) AS recorded_at, 3.4815 AS value
UNION ALL
SELECT 7 AS sensor_id, DATE_SUB(NOW(), INTERVAL 360 SECOND) AS recorded_at, 3.3213 AS value
UNION ALL
SELECT 7 AS sensor_id, DATE_SUB(NOW(), INTERVAL 362 SECOND) AS recorded_at, 3.3877 AS value
UNION ALL
SELECT 7 AS sensor_id, DATE_SUB(NOW(), INTERVAL 364 SECOND) AS recorded_at, 3.3143 AS value
UNION ALL
SELECT 7 AS sensor_id, DATE_SUB(NOW(), INTERVAL 366 SECOND) AS recorded_at, 3.3781 AS value
UNION ALL
SELECT 7 AS sensor_id, DATE_SUB(NOW(), INTERVAL 368 SECOND) AS recorded_at, 3.2611 AS value
UNION ALL
SELECT 7 AS sensor_id, DATE_SUB(NOW(), INTERVAL 370 SECOND) AS recorded_at, 3.2363 AS value
UNION ALL
SELECT 7 AS sensor_id, DATE_SUB(NOW(), INTERVAL 372 SECOND) AS recorded_at, 3.4704 AS value
UNION ALL
SELECT 7 AS sensor_id, DATE_SUB(NOW(), INTERVAL 374 SECOND) AS recorded_at, 3.3782 AS value
UNION ALL
SELECT 7 AS sensor_id, DATE_SUB(NOW(), INTERVAL 376 SECOND) AS recorded_at, 3.2232 AS value
UNION ALL
SELECT 7 AS sensor_id, DATE_SUB(NOW(), INTERVAL 378 SECOND) AS recorded_at, 3.3792 AS value
UNION ALL
SELECT 7 AS sensor_id, DATE_SUB(NOW(), INTERVAL 380 SECOND) AS recorded_at, 3.1551 AS value
UNION ALL
SELECT 7 AS sensor_id, DATE_SUB(NOW(), INTERVAL 382 SECOND) AS recorded_at, 2.9972 AS value
UNION ALL
SELECT 7 AS sensor_id, DATE_SUB(NOW(), INTERVAL 384 SECOND) AS recorded_at, 3.2772 AS value
UNION ALL
SELECT 7 AS sensor_id, DATE_SUB(NOW(), INTERVAL 386 SECOND) AS recorded_at, 3.2624 AS value
UNION ALL
SELECT 7 AS sensor_id, DATE_SUB(NOW(), INTERVAL 388 SECOND) AS recorded_at, 2.9805 AS value
UNION ALL
SELECT 7 AS sensor_id, DATE_SUB(NOW(), INTERVAL 390 SECOND) AS recorded_at, 3.1121 AS value
UNION ALL
SELECT 7 AS sensor_id, DATE_SUB(NOW(), INTERVAL 392 SECOND) AS recorded_at, 3.2512 AS value
UNION ALL
SELECT 7 AS sensor_id, DATE_SUB(NOW(), INTERVAL 394 SECOND) AS recorded_at, 3.2361 AS value
UNION ALL
SELECT 7 AS sensor_id, DATE_SUB(NOW(), INTERVAL 396 SECOND) AS recorded_at, 3.0262 AS value
UNION ALL
SELECT 7 AS sensor_id, DATE_SUB(NOW(), INTERVAL 398 SECOND) AS recorded_at, 3.3316 AS value
UNION ALL
SELECT 7 AS sensor_id, DATE_SUB(NOW(), INTERVAL 400 SECOND) AS recorded_at, 3.1632 AS value
UNION ALL
SELECT 8 AS sensor_id, DATE_SUB(NOW(), INTERVAL 322 SECOND) AS recorded_at, 184.2186 AS value
UNION ALL
SELECT 8 AS sensor_id, DATE_SUB(NOW(), INTERVAL 324 SECOND) AS recorded_at, 187.0996 AS value
UNION ALL
SELECT 8 AS sensor_id, DATE_SUB(NOW(), INTERVAL 326 SECOND) AS recorded_at, 188.4652 AS value
UNION ALL
SELECT 8 AS sensor_id, DATE_SUB(NOW(), INTERVAL 328 SECOND) AS recorded_at, 184.7388 AS value
UNION ALL
SELECT 8 AS sensor_id, DATE_SUB(NOW(), INTERVAL 330 SECOND) AS recorded_at, 184.1533 AS value
UNION ALL
SELECT 8 AS sensor_id, DATE_SUB(NOW(), INTERVAL 332 SECOND) AS recorded_at, 187.9522 AS value
UNION ALL
SELECT 8 AS sensor_id, DATE_SUB(NOW(), INTERVAL 334 SECOND) AS recorded_at, 185.3040 AS value
UNION ALL
SELECT 8 AS sensor_id, DATE_SUB(NOW(), INTERVAL 336 SECOND) AS recorded_at, 184.3849 AS value
UNION ALL
SELECT 8 AS sensor_id, DATE_SUB(NOW(), INTERVAL 338 SECOND) AS recorded_at, 184.9498 AS value
UNION ALL
SELECT 8 AS sensor_id, DATE_SUB(NOW(), INTERVAL 340 SECOND) AS recorded_at, 182.7310 AS value
UNION ALL
SELECT 8 AS sensor_id, DATE_SUB(NOW(), INTERVAL 342 SECOND) AS recorded_at, 187.4555 AS value
UNION ALL
SELECT 8 AS sensor_id, DATE_SUB(NOW(), INTERVAL 344 SECOND) AS recorded_at, 182.7457 AS value
UNION ALL
SELECT 8 AS sensor_id, DATE_SUB(NOW(), INTERVAL 346 SECOND) AS recorded_at, 184.4517 AS value
UNION ALL
SELECT 8 AS sensor_id, DATE_SUB(NOW(), INTERVAL 348 SECOND) AS recorded_at, 185.6138 AS value
UNION ALL
SELECT 8 AS sensor_id, DATE_SUB(NOW(), INTERVAL 350 SECOND) AS recorded_at, 183.3796 AS value
UNION ALL
SELECT 8 AS sensor_id, DATE_SUB(NOW(), INTERVAL 352 SECOND) AS recorded_at, 186.0963 AS value
UNION ALL
SELECT 8 AS sensor_id, DATE_SUB(NOW(), INTERVAL 354 SECOND) AS recorded_at, 185.8738 AS value
UNION ALL
SELECT 8 AS sensor_id, DATE_SUB(NOW(), INTERVAL 356 SECOND) AS recorded_at, 187.9243 AS value
UNION ALL
SELECT 8 AS sensor_id, DATE_SUB(NOW(), INTERVAL 358 SECOND) AS recorded_at, 186.4193 AS value
UNION ALL
SELECT 8 AS sensor_id, DATE_SUB(NOW(), INTERVAL 360 SECOND) AS recorded_at, 183.3640 AS value
UNION ALL
SELECT 8 AS sensor_id, DATE_SUB(NOW(), INTERVAL 362 SECOND) AS recorded_at, 186.9119 AS value
UNION ALL
SELECT 8 AS sensor_id, DATE_SUB(NOW(), INTERVAL 364 SECOND) AS recorded_at, 186.7034 AS value
UNION ALL
SELECT 8 AS sensor_id, DATE_SUB(NOW(), INTERVAL 366 SECOND) AS recorded_at, 184.6785 AS value
UNION ALL
SELECT 8 AS sensor_id, DATE_SUB(NOW(), INTERVAL 368 SECOND) AS recorded_at, 185.5055 AS value
UNION ALL
SELECT 8 AS sensor_id, DATE_SUB(NOW(), INTERVAL 370 SECOND) AS recorded_at, 186.6262 AS value
UNION ALL
SELECT 8 AS sensor_id, DATE_SUB(NOW(), INTERVAL 372 SECOND) AS recorded_at, 186.1377 AS value
UNION ALL
SELECT 8 AS sensor_id, DATE_SUB(NOW(), INTERVAL 374 SECOND) AS recorded_at, 186.0359 AS value
UNION ALL
SELECT 8 AS sensor_id, DATE_SUB(NOW(), INTERVAL 376 SECOND) AS recorded_at, 185.2286 AS value
UNION ALL
SELECT 8 AS sensor_id, DATE_SUB(NOW(), INTERVAL 378 SECOND) AS recorded_at, 187.3290 AS value
UNION ALL
SELECT 8 AS sensor_id, DATE_SUB(NOW(), INTERVAL 380 SECOND) AS recorded_at, 184.1749 AS value
UNION ALL
SELECT 8 AS sensor_id, DATE_SUB(NOW(), INTERVAL 382 SECOND) AS recorded_at, 185.2333 AS value
UNION ALL
SELECT 8 AS sensor_id, DATE_SUB(NOW(), INTERVAL 384 SECOND) AS recorded_at, 185.5343 AS value
UNION ALL
SELECT 8 AS sensor_id, DATE_SUB(NOW(), INTERVAL 386 SECOND) AS recorded_at, 184.5987 AS value
UNION ALL
SELECT 8 AS sensor_id, DATE_SUB(NOW(), INTERVAL 388 SECOND) AS recorded_at, 186.7219 AS value
UNION ALL
SELECT 8 AS sensor_id, DATE_SUB(NOW(), INTERVAL 390 SECOND) AS recorded_at, 186.1941 AS value
UNION ALL
SELECT 8 AS sensor_id, DATE_SUB(NOW(), INTERVAL 392 SECOND) AS recorded_at, 184.5467 AS value
UNION ALL
SELECT 8 AS sensor_id, DATE_SUB(NOW(), INTERVAL 394 SECOND) AS recorded_at, 187.0730 AS value
UNION ALL
SELECT 8 AS sensor_id, DATE_SUB(NOW(), INTERVAL 396 SECOND) AS recorded_at, 183.8645 AS value
UNION ALL
SELECT 8 AS sensor_id, DATE_SUB(NOW(), INTERVAL 398 SECOND) AS recorded_at, 185.8778 AS value
UNION ALL
SELECT 8 AS sensor_id, DATE_SUB(NOW(), INTERVAL 400 SECOND) AS recorded_at, 182.5989 AS value
UNION ALL
SELECT 9 AS sensor_id, DATE_SUB(NOW(), INTERVAL 322 SECOND) AS recorded_at, 102.3661 AS value
UNION ALL
SELECT 9 AS sensor_id, DATE_SUB(NOW(), INTERVAL 324 SECOND) AS recorded_at, 93.0847 AS value
UNION ALL
SELECT 9 AS sensor_id, DATE_SUB(NOW(), INTERVAL 326 SECOND) AS recorded_at, 93.0235 AS value
UNION ALL
SELECT 9 AS sensor_id, DATE_SUB(NOW(), INTERVAL 328 SECOND) AS recorded_at, 93.1242 AS value
UNION ALL
SELECT 9 AS sensor_id, DATE_SUB(NOW(), INTERVAL 330 SECOND) AS recorded_at, 94.4752 AS value
UNION ALL
SELECT 9 AS sensor_id, DATE_SUB(NOW(), INTERVAL 332 SECOND) AS recorded_at, 96.7146 AS value
UNION ALL
SELECT 9 AS sensor_id, DATE_SUB(NOW(), INTERVAL 334 SECOND) AS recorded_at, 95.5301 AS value
UNION ALL
SELECT 9 AS sensor_id, DATE_SUB(NOW(), INTERVAL 336 SECOND) AS recorded_at, 99.0946 AS value
UNION ALL
SELECT 9 AS sensor_id, DATE_SUB(NOW(), INTERVAL 338 SECOND) AS recorded_at, 91.7597 AS value
UNION ALL
SELECT 9 AS sensor_id, DATE_SUB(NOW(), INTERVAL 340 SECOND) AS recorded_at, 96.8658 AS value
UNION ALL
SELECT 9 AS sensor_id, DATE_SUB(NOW(), INTERVAL 342 SECOND) AS recorded_at, 99.6461 AS value
UNION ALL
SELECT 9 AS sensor_id, DATE_SUB(NOW(), INTERVAL 344 SECOND) AS recorded_at, 93.5586 AS value
UNION ALL
SELECT 9 AS sensor_id, DATE_SUB(NOW(), INTERVAL 346 SECOND) AS recorded_at, 99.6713 AS value
UNION ALL
SELECT 9 AS sensor_id, DATE_SUB(NOW(), INTERVAL 348 SECOND) AS recorded_at, 92.9374 AS value
UNION ALL
SELECT 9 AS sensor_id, DATE_SUB(NOW(), INTERVAL 350 SECOND) AS recorded_at, 95.0189 AS value
UNION ALL
SELECT 9 AS sensor_id, DATE_SUB(NOW(), INTERVAL 352 SECOND) AS recorded_at, 95.8804 AS value
UNION ALL
SELECT 9 AS sensor_id, DATE_SUB(NOW(), INTERVAL 354 SECOND) AS recorded_at, 94.4778 AS value
UNION ALL
SELECT 9 AS sensor_id, DATE_SUB(NOW(), INTERVAL 356 SECOND) AS recorded_at, 93.3926 AS value
UNION ALL
SELECT 9 AS sensor_id, DATE_SUB(NOW(), INTERVAL 358 SECOND) AS recorded_at, 94.2893 AS value
UNION ALL
SELECT 9 AS sensor_id, DATE_SUB(NOW(), INTERVAL 360 SECOND) AS recorded_at, 93.9444 AS value
UNION ALL
SELECT 9 AS sensor_id, DATE_SUB(NOW(), INTERVAL 362 SECOND) AS recorded_at, 91.7720 AS value
UNION ALL
SELECT 9 AS sensor_id, DATE_SUB(NOW(), INTERVAL 364 SECOND) AS recorded_at, 93.2429 AS value
UNION ALL
SELECT 9 AS sensor_id, DATE_SUB(NOW(), INTERVAL 366 SECOND) AS recorded_at, 89.7212 AS value
UNION ALL
SELECT 9 AS sensor_id, DATE_SUB(NOW(), INTERVAL 368 SECOND) AS recorded_at, 96.3939 AS value
UNION ALL
SELECT 9 AS sensor_id, DATE_SUB(NOW(), INTERVAL 370 SECOND) AS recorded_at, 94.3404 AS value
UNION ALL
SELECT 9 AS sensor_id, DATE_SUB(NOW(), INTERVAL 372 SECOND) AS recorded_at, 92.9855 AS value
UNION ALL
SELECT 9 AS sensor_id, DATE_SUB(NOW(), INTERVAL 374 SECOND) AS recorded_at, 91.8954 AS value
UNION ALL
SELECT 9 AS sensor_id, DATE_SUB(NOW(), INTERVAL 376 SECOND) AS recorded_at, 95.1492 AS value
UNION ALL
SELECT 9 AS sensor_id, DATE_SUB(NOW(), INTERVAL 378 SECOND) AS recorded_at, 93.3668 AS value
UNION ALL
SELECT 9 AS sensor_id, DATE_SUB(NOW(), INTERVAL 380 SECOND) AS recorded_at, 96.4026 AS value
UNION ALL
SELECT 9 AS sensor_id, DATE_SUB(NOW(), INTERVAL 382 SECOND) AS recorded_at, 95.7364 AS value
UNION ALL
SELECT 9 AS sensor_id, DATE_SUB(NOW(), INTERVAL 384 SECOND) AS recorded_at, 99.0881 AS value
UNION ALL
SELECT 9 AS sensor_id, DATE_SUB(NOW(), INTERVAL 386 SECOND) AS recorded_at, 97.9369 AS value
UNION ALL
SELECT 9 AS sensor_id, DATE_SUB(NOW(), INTERVAL 388 SECOND) AS recorded_at, 96.2097 AS value
UNION ALL
SELECT 9 AS sensor_id, DATE_SUB(NOW(), INTERVAL 390 SECOND) AS recorded_at, 91.6659 AS value
UNION ALL
SELECT 9 AS sensor_id, DATE_SUB(NOW(), INTERVAL 392 SECOND) AS recorded_at, 95.0583 AS value
UNION ALL
SELECT 9 AS sensor_id, DATE_SUB(NOW(), INTERVAL 394 SECOND) AS recorded_at, 93.0510 AS value
UNION ALL
SELECT 9 AS sensor_id, DATE_SUB(NOW(), INTERVAL 396 SECOND) AS recorded_at, 89.9381 AS value
UNION ALL
SELECT 9 AS sensor_id, DATE_SUB(NOW(), INTERVAL 398 SECOND) AS recorded_at, 93.2642 AS value
UNION ALL
SELECT 9 AS sensor_id, DATE_SUB(NOW(), INTERVAL 400 SECOND) AS recorded_at, 94.5797 AS value
UNION ALL
SELECT 10 AS sensor_id, DATE_SUB(NOW(), INTERVAL 322 SECOND) AS recorded_at, 2.2236 AS value
UNION ALL
SELECT 10 AS sensor_id, DATE_SUB(NOW(), INTERVAL 324 SECOND) AS recorded_at, 2.3503 AS value
UNION ALL
SELECT 10 AS sensor_id, DATE_SUB(NOW(), INTERVAL 326 SECOND) AS recorded_at, 1.9640 AS value
UNION ALL
SELECT 10 AS sensor_id, DATE_SUB(NOW(), INTERVAL 328 SECOND) AS recorded_at, 2.1286 AS value
UNION ALL
SELECT 10 AS sensor_id, DATE_SUB(NOW(), INTERVAL 330 SECOND) AS recorded_at, 2.1326 AS value
UNION ALL
SELECT 10 AS sensor_id, DATE_SUB(NOW(), INTERVAL 332 SECOND) AS recorded_at, 2.2661 AS value
UNION ALL
SELECT 10 AS sensor_id, DATE_SUB(NOW(), INTERVAL 334 SECOND) AS recorded_at, 1.9865 AS value
UNION ALL
SELECT 10 AS sensor_id, DATE_SUB(NOW(), INTERVAL 336 SECOND) AS recorded_at, 2.2063 AS value
UNION ALL
SELECT 10 AS sensor_id, DATE_SUB(NOW(), INTERVAL 338 SECOND) AS recorded_at, 1.8504 AS value
UNION ALL
SELECT 10 AS sensor_id, DATE_SUB(NOW(), INTERVAL 340 SECOND) AS recorded_at, 2.0128 AS value
UNION ALL
SELECT 10 AS sensor_id, DATE_SUB(NOW(), INTERVAL 342 SECOND) AS recorded_at, 2.1432 AS value
UNION ALL
SELECT 10 AS sensor_id, DATE_SUB(NOW(), INTERVAL 344 SECOND) AS recorded_at, 1.8383 AS value
UNION ALL
SELECT 10 AS sensor_id, DATE_SUB(NOW(), INTERVAL 346 SECOND) AS recorded_at, 2.1368 AS value
UNION ALL
SELECT 10 AS sensor_id, DATE_SUB(NOW(), INTERVAL 348 SECOND) AS recorded_at, 2.0624 AS value
UNION ALL
SELECT 10 AS sensor_id, DATE_SUB(NOW(), INTERVAL 350 SECOND) AS recorded_at, 2.0278 AS value
UNION ALL
SELECT 10 AS sensor_id, DATE_SUB(NOW(), INTERVAL 352 SECOND) AS recorded_at, 2.0369 AS value
UNION ALL
SELECT 10 AS sensor_id, DATE_SUB(NOW(), INTERVAL 354 SECOND) AS recorded_at, 2.0216 AS value
UNION ALL
SELECT 10 AS sensor_id, DATE_SUB(NOW(), INTERVAL 356 SECOND) AS recorded_at, 2.2210 AS value
UNION ALL
SELECT 10 AS sensor_id, DATE_SUB(NOW(), INTERVAL 358 SECOND) AS recorded_at, 1.9434 AS value
UNION ALL
SELECT 10 AS sensor_id, DATE_SUB(NOW(), INTERVAL 360 SECOND) AS recorded_at, 2.0786 AS value
UNION ALL
SELECT 10 AS sensor_id, DATE_SUB(NOW(), INTERVAL 362 SECOND) AS recorded_at, 2.0470 AS value
UNION ALL
SELECT 10 AS sensor_id, DATE_SUB(NOW(), INTERVAL 364 SECOND) AS recorded_at, 2.1216 AS value
UNION ALL
SELECT 10 AS sensor_id, DATE_SUB(NOW(), INTERVAL 366 SECOND) AS recorded_at, 2.1326 AS value
UNION ALL
SELECT 10 AS sensor_id, DATE_SUB(NOW(), INTERVAL 368 SECOND) AS recorded_at, 2.0966 AS value
UNION ALL
SELECT 10 AS sensor_id, DATE_SUB(NOW(), INTERVAL 370 SECOND) AS recorded_at, 2.4354 AS value
UNION ALL
SELECT 10 AS sensor_id, DATE_SUB(NOW(), INTERVAL 372 SECOND) AS recorded_at, 1.9827 AS value
UNION ALL
SELECT 10 AS sensor_id, DATE_SUB(NOW(), INTERVAL 374 SECOND) AS recorded_at, 2.0580 AS value
UNION ALL
SELECT 10 AS sensor_id, DATE_SUB(NOW(), INTERVAL 376 SECOND) AS recorded_at, 2.0288 AS value
UNION ALL
SELECT 10 AS sensor_id, DATE_SUB(NOW(), INTERVAL 378 SECOND) AS recorded_at, 2.0677 AS value
UNION ALL
SELECT 10 AS sensor_id, DATE_SUB(NOW(), INTERVAL 380 SECOND) AS recorded_at, 1.9968 AS value
UNION ALL
SELECT 10 AS sensor_id, DATE_SUB(NOW(), INTERVAL 382 SECOND) AS recorded_at, 1.9523 AS value
UNION ALL
SELECT 10 AS sensor_id, DATE_SUB(NOW(), INTERVAL 384 SECOND) AS recorded_at, 2.2805 AS value
UNION ALL
SELECT 10 AS sensor_id, DATE_SUB(NOW(), INTERVAL 386 SECOND) AS recorded_at, 2.0959 AS value
UNION ALL
SELECT 10 AS sensor_id, DATE_SUB(NOW(), INTERVAL 388 SECOND) AS recorded_at, 2.0738 AS value
UNION ALL
SELECT 10 AS sensor_id, DATE_SUB(NOW(), INTERVAL 390 SECOND) AS recorded_at, 2.2120 AS value
UNION ALL
SELECT 10 AS sensor_id, DATE_SUB(NOW(), INTERVAL 392 SECOND) AS recorded_at, 2.0573 AS value
UNION ALL
SELECT 10 AS sensor_id, DATE_SUB(NOW(), INTERVAL 394 SECOND) AS recorded_at, 2.0643 AS value
UNION ALL
SELECT 10 AS sensor_id, DATE_SUB(NOW(), INTERVAL 396 SECOND) AS recorded_at, 2.2134 AS value
UNION ALL
SELECT 10 AS sensor_id, DATE_SUB(NOW(), INTERVAL 398 SECOND) AS recorded_at, 2.1353 AS value
UNION ALL
SELECT 10 AS sensor_id, DATE_SUB(NOW(), INTERVAL 400 SECOND) AS recorded_at, 2.2217 AS value
UNION ALL
SELECT 11 AS sensor_id, DATE_SUB(NOW(), INTERVAL 322 SECOND) AS recorded_at, 1.2096 AS value
UNION ALL
SELECT 11 AS sensor_id, DATE_SUB(NOW(), INTERVAL 324 SECOND) AS recorded_at, 1.0563 AS value
UNION ALL
SELECT 11 AS sensor_id, DATE_SUB(NOW(), INTERVAL 326 SECOND) AS recorded_at, 1.1817 AS value
UNION ALL
SELECT 11 AS sensor_id, DATE_SUB(NOW(), INTERVAL 328 SECOND) AS recorded_at, 1.1021 AS value
UNION ALL
SELECT 11 AS sensor_id, DATE_SUB(NOW(), INTERVAL 330 SECOND) AS recorded_at, 1.1093 AS value
UNION ALL
SELECT 11 AS sensor_id, DATE_SUB(NOW(), INTERVAL 332 SECOND) AS recorded_at, 1.1706 AS value
UNION ALL
SELECT 11 AS sensor_id, DATE_SUB(NOW(), INTERVAL 334 SECOND) AS recorded_at, 1.1679 AS value
UNION ALL
SELECT 11 AS sensor_id, DATE_SUB(NOW(), INTERVAL 336 SECOND) AS recorded_at, 1.1747 AS value
UNION ALL
SELECT 11 AS sensor_id, DATE_SUB(NOW(), INTERVAL 338 SECOND) AS recorded_at, 1.2162 AS value
UNION ALL
SELECT 11 AS sensor_id, DATE_SUB(NOW(), INTERVAL 340 SECOND) AS recorded_at, 1.1699 AS value
UNION ALL
SELECT 11 AS sensor_id, DATE_SUB(NOW(), INTERVAL 342 SECOND) AS recorded_at, 1.1698 AS value
UNION ALL
SELECT 11 AS sensor_id, DATE_SUB(NOW(), INTERVAL 344 SECOND) AS recorded_at, 1.1654 AS value
UNION ALL
SELECT 11 AS sensor_id, DATE_SUB(NOW(), INTERVAL 346 SECOND) AS recorded_at, 1.0846 AS value
UNION ALL
SELECT 11 AS sensor_id, DATE_SUB(NOW(), INTERVAL 348 SECOND) AS recorded_at, 1.1827 AS value
UNION ALL
SELECT 11 AS sensor_id, DATE_SUB(NOW(), INTERVAL 350 SECOND) AS recorded_at, 1.2098 AS value
UNION ALL
SELECT 11 AS sensor_id, DATE_SUB(NOW(), INTERVAL 352 SECOND) AS recorded_at, 1.1801 AS value
UNION ALL
SELECT 11 AS sensor_id, DATE_SUB(NOW(), INTERVAL 354 SECOND) AS recorded_at, 1.1377 AS value
UNION ALL
SELECT 11 AS sensor_id, DATE_SUB(NOW(), INTERVAL 356 SECOND) AS recorded_at, 1.1888 AS value
UNION ALL
SELECT 11 AS sensor_id, DATE_SUB(NOW(), INTERVAL 358 SECOND) AS recorded_at, 1.0370 AS value
UNION ALL
SELECT 11 AS sensor_id, DATE_SUB(NOW(), INTERVAL 360 SECOND) AS recorded_at, 1.1866 AS value
UNION ALL
SELECT 11 AS sensor_id, DATE_SUB(NOW(), INTERVAL 362 SECOND) AS recorded_at, 1.1813 AS value
UNION ALL
SELECT 11 AS sensor_id, DATE_SUB(NOW(), INTERVAL 364 SECOND) AS recorded_at, 1.1490 AS value
UNION ALL
SELECT 11 AS sensor_id, DATE_SUB(NOW(), INTERVAL 366 SECOND) AS recorded_at, 1.1212 AS value
UNION ALL
SELECT 11 AS sensor_id, DATE_SUB(NOW(), INTERVAL 368 SECOND) AS recorded_at, 1.1290 AS value
UNION ALL
SELECT 11 AS sensor_id, DATE_SUB(NOW(), INTERVAL 370 SECOND) AS recorded_at, 1.1150 AS value
UNION ALL
SELECT 11 AS sensor_id, DATE_SUB(NOW(), INTERVAL 372 SECOND) AS recorded_at, 1.2157 AS value
UNION ALL
SELECT 11 AS sensor_id, DATE_SUB(NOW(), INTERVAL 374 SECOND) AS recorded_at, 1.1195 AS value
UNION ALL
SELECT 11 AS sensor_id, DATE_SUB(NOW(), INTERVAL 376 SECOND) AS recorded_at, 1.1112 AS value
UNION ALL
SELECT 11 AS sensor_id, DATE_SUB(NOW(), INTERVAL 378 SECOND) AS recorded_at, 1.1369 AS value
UNION ALL
SELECT 11 AS sensor_id, DATE_SUB(NOW(), INTERVAL 380 SECOND) AS recorded_at, 1.1867 AS value
UNION ALL
SELECT 11 AS sensor_id, DATE_SUB(NOW(), INTERVAL 382 SECOND) AS recorded_at, 1.0772 AS value
UNION ALL
SELECT 11 AS sensor_id, DATE_SUB(NOW(), INTERVAL 384 SECOND) AS recorded_at, 1.1640 AS value
UNION ALL
SELECT 11 AS sensor_id, DATE_SUB(NOW(), INTERVAL 386 SECOND) AS recorded_at, 1.1448 AS value
UNION ALL
SELECT 11 AS sensor_id, DATE_SUB(NOW(), INTERVAL 388 SECOND) AS recorded_at, 1.2016 AS value
UNION ALL
SELECT 11 AS sensor_id, DATE_SUB(NOW(), INTERVAL 390 SECOND) AS recorded_at, 1.1536 AS value
UNION ALL
SELECT 11 AS sensor_id, DATE_SUB(NOW(), INTERVAL 392 SECOND) AS recorded_at, 1.1369 AS value
UNION ALL
SELECT 11 AS sensor_id, DATE_SUB(NOW(), INTERVAL 394 SECOND) AS recorded_at, 1.1596 AS value
UNION ALL
SELECT 11 AS sensor_id, DATE_SUB(NOW(), INTERVAL 396 SECOND) AS recorded_at, 1.2172 AS value
UNION ALL
SELECT 11 AS sensor_id, DATE_SUB(NOW(), INTERVAL 398 SECOND) AS recorded_at, 1.2377 AS value
UNION ALL
SELECT 11 AS sensor_id, DATE_SUB(NOW(), INTERVAL 400 SECOND) AS recorded_at, 1.1910 AS value
UNION ALL
SELECT 12 AS sensor_id, DATE_SUB(NOW(), INTERVAL 322 SECOND) AS recorded_at, 167.4142 AS value
UNION ALL
SELECT 12 AS sensor_id, DATE_SUB(NOW(), INTERVAL 324 SECOND) AS recorded_at, 171.1454 AS value
UNION ALL
SELECT 12 AS sensor_id, DATE_SUB(NOW(), INTERVAL 326 SECOND) AS recorded_at, 171.6814 AS value
UNION ALL
SELECT 12 AS sensor_id, DATE_SUB(NOW(), INTERVAL 328 SECOND) AS recorded_at, 171.3724 AS value
UNION ALL
SELECT 12 AS sensor_id, DATE_SUB(NOW(), INTERVAL 330 SECOND) AS recorded_at, 166.6000 AS value
UNION ALL
SELECT 12 AS sensor_id, DATE_SUB(NOW(), INTERVAL 332 SECOND) AS recorded_at, 170.7152 AS value
UNION ALL
SELECT 12 AS sensor_id, DATE_SUB(NOW(), INTERVAL 334 SECOND) AS recorded_at, 169.0564 AS value
UNION ALL
SELECT 12 AS sensor_id, DATE_SUB(NOW(), INTERVAL 336 SECOND) AS recorded_at, 169.3622 AS value
UNION ALL
SELECT 12 AS sensor_id, DATE_SUB(NOW(), INTERVAL 338 SECOND) AS recorded_at, 171.3659 AS value
UNION ALL
SELECT 12 AS sensor_id, DATE_SUB(NOW(), INTERVAL 340 SECOND) AS recorded_at, 170.7434 AS value
UNION ALL
SELECT 12 AS sensor_id, DATE_SUB(NOW(), INTERVAL 342 SECOND) AS recorded_at, 169.1401 AS value
UNION ALL
SELECT 12 AS sensor_id, DATE_SUB(NOW(), INTERVAL 344 SECOND) AS recorded_at, 169.5087 AS value
UNION ALL
SELECT 12 AS sensor_id, DATE_SUB(NOW(), INTERVAL 346 SECOND) AS recorded_at, 171.0419 AS value
UNION ALL
SELECT 12 AS sensor_id, DATE_SUB(NOW(), INTERVAL 348 SECOND) AS recorded_at, 171.5379 AS value
UNION ALL
SELECT 12 AS sensor_id, DATE_SUB(NOW(), INTERVAL 350 SECOND) AS recorded_at, 170.2158 AS value
UNION ALL
SELECT 12 AS sensor_id, DATE_SUB(NOW(), INTERVAL 352 SECOND) AS recorded_at, 172.7247 AS value
UNION ALL
SELECT 12 AS sensor_id, DATE_SUB(NOW(), INTERVAL 354 SECOND) AS recorded_at, 170.2401 AS value
UNION ALL
SELECT 12 AS sensor_id, DATE_SUB(NOW(), INTERVAL 356 SECOND) AS recorded_at, 171.3338 AS value
UNION ALL
SELECT 12 AS sensor_id, DATE_SUB(NOW(), INTERVAL 358 SECOND) AS recorded_at, 170.0212 AS value
UNION ALL
SELECT 12 AS sensor_id, DATE_SUB(NOW(), INTERVAL 360 SECOND) AS recorded_at, 167.2111 AS value
UNION ALL
SELECT 12 AS sensor_id, DATE_SUB(NOW(), INTERVAL 362 SECOND) AS recorded_at, 169.9272 AS value
UNION ALL
SELECT 12 AS sensor_id, DATE_SUB(NOW(), INTERVAL 364 SECOND) AS recorded_at, 168.8815 AS value
UNION ALL
SELECT 12 AS sensor_id, DATE_SUB(NOW(), INTERVAL 366 SECOND) AS recorded_at, 168.6455 AS value
UNION ALL
SELECT 12 AS sensor_id, DATE_SUB(NOW(), INTERVAL 368 SECOND) AS recorded_at, 168.5979 AS value
UNION ALL
SELECT 12 AS sensor_id, DATE_SUB(NOW(), INTERVAL 370 SECOND) AS recorded_at, 168.6319 AS value
UNION ALL
SELECT 12 AS sensor_id, DATE_SUB(NOW(), INTERVAL 372 SECOND) AS recorded_at, 170.2388 AS value
UNION ALL
SELECT 12 AS sensor_id, DATE_SUB(NOW(), INTERVAL 374 SECOND) AS recorded_at, 171.5136 AS value
UNION ALL
SELECT 12 AS sensor_id, DATE_SUB(NOW(), INTERVAL 376 SECOND) AS recorded_at, 166.6574 AS value
UNION ALL
SELECT 12 AS sensor_id, DATE_SUB(NOW(), INTERVAL 378 SECOND) AS recorded_at, 168.1597 AS value
UNION ALL
SELECT 12 AS sensor_id, DATE_SUB(NOW(), INTERVAL 380 SECOND) AS recorded_at, 170.4536 AS value
UNION ALL
SELECT 12 AS sensor_id, DATE_SUB(NOW(), INTERVAL 382 SECOND) AS recorded_at, 170.0026 AS value
UNION ALL
SELECT 12 AS sensor_id, DATE_SUB(NOW(), INTERVAL 384 SECOND) AS recorded_at, 172.3722 AS value
UNION ALL
SELECT 12 AS sensor_id, DATE_SUB(NOW(), INTERVAL 386 SECOND) AS recorded_at, 169.3053 AS value
UNION ALL
SELECT 12 AS sensor_id, DATE_SUB(NOW(), INTERVAL 388 SECOND) AS recorded_at, 172.0336 AS value
UNION ALL
SELECT 12 AS sensor_id, DATE_SUB(NOW(), INTERVAL 390 SECOND) AS recorded_at, 166.9627 AS value
UNION ALL
SELECT 12 AS sensor_id, DATE_SUB(NOW(), INTERVAL 392 SECOND) AS recorded_at, 167.5482 AS value
UNION ALL
SELECT 12 AS sensor_id, DATE_SUB(NOW(), INTERVAL 394 SECOND) AS recorded_at, 170.4448 AS value
UNION ALL
SELECT 12 AS sensor_id, DATE_SUB(NOW(), INTERVAL 396 SECOND) AS recorded_at, 169.4183 AS value
UNION ALL
SELECT 12 AS sensor_id, DATE_SUB(NOW(), INTERVAL 398 SECOND) AS recorded_at, 170.3715 AS value
UNION ALL
SELECT 12 AS sensor_id, DATE_SUB(NOW(), INTERVAL 400 SECOND) AS recorded_at, 168.0509 AS value
UNION ALL
SELECT 13 AS sensor_id, DATE_SUB(NOW(), INTERVAL 322 SECOND) AS recorded_at, 43.2308 AS value
UNION ALL
SELECT 13 AS sensor_id, DATE_SUB(NOW(), INTERVAL 324 SECOND) AS recorded_at, 43.1056 AS value
UNION ALL
SELECT 13 AS sensor_id, DATE_SUB(NOW(), INTERVAL 326 SECOND) AS recorded_at, 43.0453 AS value
UNION ALL
SELECT 13 AS sensor_id, DATE_SUB(NOW(), INTERVAL 328 SECOND) AS recorded_at, 40.9270 AS value
UNION ALL
SELECT 13 AS sensor_id, DATE_SUB(NOW(), INTERVAL 330 SECOND) AS recorded_at, 41.3856 AS value
UNION ALL
SELECT 13 AS sensor_id, DATE_SUB(NOW(), INTERVAL 332 SECOND) AS recorded_at, 43.7496 AS value
UNION ALL
SELECT 13 AS sensor_id, DATE_SUB(NOW(), INTERVAL 334 SECOND) AS recorded_at, 38.9155 AS value
UNION ALL
SELECT 13 AS sensor_id, DATE_SUB(NOW(), INTERVAL 336 SECOND) AS recorded_at, 40.6704 AS value
UNION ALL
SELECT 13 AS sensor_id, DATE_SUB(NOW(), INTERVAL 338 SECOND) AS recorded_at, 45.5337 AS value
UNION ALL
SELECT 13 AS sensor_id, DATE_SUB(NOW(), INTERVAL 340 SECOND) AS recorded_at, 39.6619 AS value
UNION ALL
SELECT 13 AS sensor_id, DATE_SUB(NOW(), INTERVAL 342 SECOND) AS recorded_at, 44.1931 AS value
UNION ALL
SELECT 13 AS sensor_id, DATE_SUB(NOW(), INTERVAL 344 SECOND) AS recorded_at, 43.0077 AS value
UNION ALL
SELECT 13 AS sensor_id, DATE_SUB(NOW(), INTERVAL 346 SECOND) AS recorded_at, 40.0119 AS value
UNION ALL
SELECT 13 AS sensor_id, DATE_SUB(NOW(), INTERVAL 348 SECOND) AS recorded_at, 42.1603 AS value
UNION ALL
SELECT 13 AS sensor_id, DATE_SUB(NOW(), INTERVAL 350 SECOND) AS recorded_at, 42.6870 AS value
UNION ALL
SELECT 13 AS sensor_id, DATE_SUB(NOW(), INTERVAL 352 SECOND) AS recorded_at, 40.9366 AS value
UNION ALL
SELECT 13 AS sensor_id, DATE_SUB(NOW(), INTERVAL 354 SECOND) AS recorded_at, 43.1448 AS value
UNION ALL
SELECT 13 AS sensor_id, DATE_SUB(NOW(), INTERVAL 356 SECOND) AS recorded_at, 42.0339 AS value
UNION ALL
SELECT 13 AS sensor_id, DATE_SUB(NOW(), INTERVAL 358 SECOND) AS recorded_at, 45.3602 AS value
UNION ALL
SELECT 13 AS sensor_id, DATE_SUB(NOW(), INTERVAL 360 SECOND) AS recorded_at, 41.2469 AS value
UNION ALL
SELECT 13 AS sensor_id, DATE_SUB(NOW(), INTERVAL 362 SECOND) AS recorded_at, 41.2149 AS value
UNION ALL
SELECT 13 AS sensor_id, DATE_SUB(NOW(), INTERVAL 364 SECOND) AS recorded_at, 42.1833 AS value
UNION ALL
SELECT 13 AS sensor_id, DATE_SUB(NOW(), INTERVAL 366 SECOND) AS recorded_at, 41.9295 AS value
UNION ALL
SELECT 13 AS sensor_id, DATE_SUB(NOW(), INTERVAL 368 SECOND) AS recorded_at, 40.7035 AS value
UNION ALL
SELECT 13 AS sensor_id, DATE_SUB(NOW(), INTERVAL 370 SECOND) AS recorded_at, 43.2852 AS value
UNION ALL
SELECT 13 AS sensor_id, DATE_SUB(NOW(), INTERVAL 372 SECOND) AS recorded_at, 40.7662 AS value
UNION ALL
SELECT 13 AS sensor_id, DATE_SUB(NOW(), INTERVAL 374 SECOND) AS recorded_at, 41.8458 AS value
UNION ALL
SELECT 13 AS sensor_id, DATE_SUB(NOW(), INTERVAL 376 SECOND) AS recorded_at, 42.5193 AS value
UNION ALL
SELECT 13 AS sensor_id, DATE_SUB(NOW(), INTERVAL 378 SECOND) AS recorded_at, 41.8528 AS value
UNION ALL
SELECT 13 AS sensor_id, DATE_SUB(NOW(), INTERVAL 380 SECOND) AS recorded_at, 43.3549 AS value
UNION ALL
SELECT 13 AS sensor_id, DATE_SUB(NOW(), INTERVAL 382 SECOND) AS recorded_at, 41.2995 AS value
UNION ALL
SELECT 13 AS sensor_id, DATE_SUB(NOW(), INTERVAL 384 SECOND) AS recorded_at, 44.3982 AS value
UNION ALL
SELECT 13 AS sensor_id, DATE_SUB(NOW(), INTERVAL 386 SECOND) AS recorded_at, 43.2501 AS value
UNION ALL
SELECT 13 AS sensor_id, DATE_SUB(NOW(), INTERVAL 388 SECOND) AS recorded_at, 40.2112 AS value
UNION ALL
SELECT 13 AS sensor_id, DATE_SUB(NOW(), INTERVAL 390 SECOND) AS recorded_at, 39.8663 AS value
UNION ALL
SELECT 13 AS sensor_id, DATE_SUB(NOW(), INTERVAL 392 SECOND) AS recorded_at, 42.7139 AS value
UNION ALL
SELECT 13 AS sensor_id, DATE_SUB(NOW(), INTERVAL 394 SECOND) AS recorded_at, 43.7202 AS value
UNION ALL
SELECT 13 AS sensor_id, DATE_SUB(NOW(), INTERVAL 396 SECOND) AS recorded_at, 42.4962 AS value
UNION ALL
SELECT 13 AS sensor_id, DATE_SUB(NOW(), INTERVAL 398 SECOND) AS recorded_at, 39.9750 AS value
UNION ALL
SELECT 13 AS sensor_id, DATE_SUB(NOW(), INTERVAL 400 SECOND) AS recorded_at, 41.5490 AS value
) AS seed
WHERE NOT EXISTS (SELECT 1 FROM sensor_readings LIMIT 1);


-- A small amount of initial maintenance data so both dashboards have useful
-- records immediately. These examples are clearly marked as demo records.
INSERT INTO faults
  (fault_id,machine_id,fault_type_id,severity,confidence,summary,est_ttf_hrs,
   model_version,status,detected_at,last_seen_at,occurrence_count,resolved_at)
VALUES
  (1,1,2,'HIGH',0.931,'DEMO RECORD: sustained abnormal vibration on CNC-01.',8,
   'demo-seed','OPEN',NOW()-INTERVAL 12 MINUTE,NOW()-INTERVAL 2 MINUTE,1,NULL),
  (2,3,3,'MEDIUM',0.884,'DEMO RECORD: elevated joint temperature on RobotArm-01.',12,
   'demo-seed','ASSIGNED',NOW()-INTERVAL 45 MINUTE,NOW()-INTERVAL 20 MINUTE,2,NULL)
ON DUPLICATE KEY UPDATE machine_id=VALUES(machine_id), fault_type_id=VALUES(fault_type_id),
  severity=VALUES(severity), confidence=VALUES(confidence), summary=VALUES(summary),
  model_version=VALUES(model_version), status=VALUES(status);

INSERT INTO fault_evidence (fault_id,sensor_id,observed_value,expected_value,unit) VALUES
  (1,2,8.10,2.05,'mm/s'),
  (2,6,89.20,55.10,'°C')
ON DUPLICATE KEY UPDATE observed_value=VALUES(observed_value),
  expected_value=VALUES(expected_value), unit=VALUES(unit);

INSERT INTO work_orders
  (work_order_id,fault_id,assigned_to,assigned_by,suggested_technician_id,
   assignment_method,override_reason,priority,status,instructions,assigned_at,due_at,started_at,completed_at)
VALUES
  (1,2,3,1,2,'SYSTEM_SUGGESTED',NULL,'MEDIUM','IN_PROGRESS',
   'Verify the joint-temperature reading. Inspect cooling, loading and connections under approved safety procedures. Record findings before closing the job.',
   NOW()-INTERVAL 35 MINUTE,NOW()+INTERVAL 2 HOUR,NOW()-INTERVAL 20 MINUTE,NULL)
ON DUPLICATE KEY UPDATE fault_id=VALUES(fault_id), assigned_to=VALUES(assigned_to),
  assigned_by=VALUES(assigned_by), suggested_technician_id=VALUES(suggested_technician_id),
  assignment_method=VALUES(assignment_method), priority=VALUES(priority), status=VALUES(status),
  instructions=VALUES(instructions);

INSERT INTO work_order_activity
  (activity_id,work_order_id,activity_type,reason,notes,recorded_by,recorded_at) VALUES
  (1,1,'STARTED',NULL,'Demo seed: technician started inspection.',3,NOW()-INTERVAL 20 MINUTE)
ON DUPLICATE KEY UPDATE work_order_id=VALUES(work_order_id),
  activity_type=VALUES(activity_type), notes=VALUES(notes), recorded_by=VALUES(recorded_by);

INSERT INTO work_order_reports
  (report_id,work_order_id,findings,action_taken,parts_used,time_spent_mins,
   submitted_at,review_status,review_comment,reviewed_by,reviewed_at) VALUES
  (1,1,'Demo record only: inspection is in progress; no confirmed root cause yet.',
   'Initial inspection recorded; continue diagnosis before marking the job complete.',
   NULL,15,NOW()-INTERVAL 10 MINUTE,'PENDING_REVIEW',NULL,NULL,NULL)
ON DUPLICATE KEY UPDATE work_order_id=VALUES(work_order_id),
  findings=VALUES(findings), action_taken=VALUES(action_taken),
  review_status=VALUES(review_status);

-- Baseline readings are intentionally seeded as historical normal values.
-- The live simulator adds fresh values; use --demo-fault to demonstrate detection.
