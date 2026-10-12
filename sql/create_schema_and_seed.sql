-- ============================================================
-- create_schema_and_seed.sql
-- Smart Manufacturing OT Schema — Tables + Seed Data
-- Run this FIRST, then run ot_sample_data.sql
-- ============================================================
CREATE DATABASE IF NOT EXISTS smart_manufacturing_ot;
USE smart_manufacturing_ot;

-- Safe re-run: drop child tables first, then parents
SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS MaintenanceCheck;
DROP TABLE IF EXISTS SensorReading;
DROP TABLE IF EXISTS CycleEvent;
DROP TABLE IF EXISTS MachineStatusLog;
DROP TABLE IF EXISTS Machine;
DROP TABLE IF EXISTS ProductionLine;
SET FOREIGN_KEY_CHECKS = 1;


-- ------------------------------------------------------------
-- 1. Production Lines
-- ------------------------------------------------------------
CREATE TABLE ProductionLine (
    line_id       INT AUTO_INCREMENT PRIMARY KEY,
    line_name     VARCHAR(50) NOT NULL,
    plant_name    VARCHAR(50) NOT NULL
);

-- ------------------------------------------------------------
-- 2. Machines
-- ------------------------------------------------------------
CREATE TABLE Machine (
    machine_id           INT AUTO_INCREMENT PRIMARY KEY,
    line_id              INT NOT NULL,
    machine_name         VARCHAR(50) NOT NULL,
    machine_type         ENUM('cnc','conveyor','robot_arm','injection_molding','packaging') NOT NULL,
    ideal_cycle_time_sec DECIMAL(6,2) NOT NULL,
    FOREIGN KEY (line_id) REFERENCES ProductionLine(line_id)
);

-- ------------------------------------------------------------
-- 3. Machine Status Log (drives Availability)
-- ------------------------------------------------------------
CREATE TABLE MachineStatusLog (
    log_id       INT AUTO_INCREMENT PRIMARY KEY,
    machine_id   INT NOT NULL,
    status       ENUM('running','idle','down','fault') NOT NULL,
    start_time   DATETIME NOT NULL,
    end_time     DATETIME NULL,
    reason_code  VARCHAR(50) NULL,
    FOREIGN KEY (machine_id) REFERENCES Machine(machine_id),
    CHECK (end_time IS NULL OR end_time >= start_time)
);

-- ------------------------------------------------------------
-- 4. Cycle Events (drives Performance & Quality)
-- ------------------------------------------------------------
CREATE TABLE CycleEvent (
    event_id       INT AUTO_INCREMENT PRIMARY KEY,
    machine_id     INT NOT NULL,
    event_time     DATETIME NOT NULL,
    units_produced INT NOT NULL DEFAULT 0,
    good_units     INT NOT NULL DEFAULT 0,
    defect_units   INT NOT NULL DEFAULT 0,
    FOREIGN KEY (machine_id) REFERENCES Machine(machine_id),
    CHECK (good_units + defect_units <= units_produced)
);

-- ------------------------------------------------------------
-- 5. Sensor Readings
-- ------------------------------------------------------------
CREATE TABLE SensorReading (
    reading_id    INT AUTO_INCREMENT PRIMARY KEY,
    machine_id    INT NOT NULL,
    sensor_type   ENUM('spindle_temp','vibration','spindle_load',
                        'barrel_temp','injection_pressure',
                        'joint_temp','motor_current',
                        'belt_speed','seal_temp','throughput') NOT NULL,
    value         DECIMAL(8,2) NOT NULL,
    reading_time  DATETIME NOT NULL,
    FOREIGN KEY (machine_id) REFERENCES Machine(machine_id)
);

-- ------------------------------------------------------------
-- 6. Maintenance Checks (powers /api/maintenance)
-- ------------------------------------------------------------
CREATE TABLE MaintenanceCheck (
    check_id        INT AUTO_INCREMENT PRIMARY KEY,
    machine_id      INT NOT NULL,
    check_type      ENUM('preventive','corrective','inspection','calibration') NOT NULL,
    scheduled_date  DATE NOT NULL,
    completed_date  DATE NULL,
    status          ENUM('scheduled','in_progress','completed','overdue') NOT NULL DEFAULT 'scheduled',
    technician      VARCHAR(50) NULL,
    notes           VARCHAR(255) NULL,
    FOREIGN KEY (machine_id) REFERENCES Machine(machine_id)
);

-- ============================================================
-- SEED DATA — Production Lines & Machines
-- ============================================================
INSERT INTO ProductionLine (line_name, plant_name) VALUES
('Line A', 'Plant 1'),
('Line B', 'Plant 1');

INSERT INTO Machine (line_id, machine_name, machine_type, ideal_cycle_time_sec) VALUES
(1, 'CNC-01', 'cnc', 25.00),
(1, 'Conveyor-A', 'conveyor', 5.00),
(1, 'RobotArm-01', 'robot_arm', 12.00),
(2, 'Injection-01', 'injection_molding', 30.00),
(2, 'Conveyor-B', 'conveyor', 5.00),
(2, 'Packaging-01', 'packaging', 8.00);

-- ============================================================
-- Next step: run ot_sample_data.sql to populate
-- MachineStatusLog, CycleEvent, SensorReading, and MaintenanceCheck
-- ============================================================
