"""
generate_ot_data.py
--------------------
Generates realistic-looking random data for the OT side of the
Smart Manufacturing schema (MachineStatusLog, CycleEvent, SensorReading,
MaintenanceCheck) and writes it out as a MySQL-ready .sql file of
INSERT statements.

Usage:
    python generate_ot_data.py

Output:
    ot_sample_data.sql
"""

import random
from datetime import datetime, timedelta

random.seed(42)  # reproducible results

# ---------------------------------------------------------------
# CONFIG — matches the Machine table you already inserted
# ---------------------------------------------------------------
# machine_id: (machine_type, ideal_cycle_time_sec)
MACHINES = {
    1: ("cnc", 25.00),
    2: ("conveyor", 5.00),
    3: ("robot_arm", 12.00),
    4: ("injection_molding", 30.00),
    5: ("conveyor", 5.00),
    6: ("packaging", 8.00),
}

SENSOR_MAP = {
    "cnc": [("spindle_temp", 40, 90), ("vibration", 0, 10), ("spindle_load", 0, 100)],
    "conveyor": [("belt_speed", 0, 2), ("vibration", 0, 8)],
    "robot_arm": [("joint_temp", 30, 70), ("motor_current", 0, 20)],
    "injection_molding": [("barrel_temp", 180, 250), ("injection_pressure", 50, 150)],
    "packaging": [("seal_temp", 100, 180), ("throughput", 20, 60)],
}

STATUS_OPTIONS = ["running", "running", "running", "idle", "down", "fault"]
# weighted so "running" is most common; adjust as you like

REASON_CODES = {
    "down": ["scheduled_maintenance", "material_shortage", "shift_change"],
    "fault": ["sensor_error", "mechanical_jam", "overheat_shutdown"],
}

# --- Maintenance check config ---
CHECK_TYPES = ["preventive", "corrective", "inspection", "calibration"]
TECHNICIANS = ["R. Sharma", "A. Patil", "S. Kulkarni"]
MAINTENANCE_NOTES = {
    "preventive": "Routine preventive maintenance per schedule",
    "corrective": "Fault reported, corrective action required",
    "inspection": "Scheduled inspection of components",
    "calibration": "Sensor/instrument calibration check",
}
# status weights: completed, scheduled, in_progress, overdue
MAINTENANCE_STATUS_WEIGHTS = [40, 30, 15, 15]

DAYS_OF_HISTORY = 3
SIM_START = datetime(2026, 7, 1, 6, 0, 0)  # factory day starts 6 AM

# ---------------------------------------------------------------
# GENERATORS
# ---------------------------------------------------------------

def generate_status_log(machine_id):
    """Generate a day's worth of status blocks for one machine on one day."""
    rows = []
    current_time = SIM_START
    day_end = current_time + timedelta(hours=16)  # 16-hour production day

    while current_time < day_end:
        status = random.choices(
            STATUS_OPTIONS, weights=[40, 40, 40, 10, 6, 4], k=1
        )[0]

        if status == "running":
            duration = timedelta(minutes=random.randint(30, 120))
        elif status == "idle":
            duration = timedelta(minutes=random.randint(5, 20))
        else:  # down / fault
            duration = timedelta(minutes=random.randint(10, 45))

        end_time = min(current_time + duration, day_end)
        reason_code = "NULL"
        if status in REASON_CODES:
            reason_code = f"'{random.choice(REASON_CODES[status])}'"

        rows.append(
            f"({machine_id}, '{status}', '{current_time}', '{end_time}', {reason_code})"
        )
        current_time = end_time

    return rows


def generate_cycle_events(machine_id, ideal_cycle_time, batch_minutes=5):
    """
    Generate one CycleEvent row per batch_minutes-minute window, summarizing
    how many units were produced in that window (based on ideal cycle time
    with some real-world variance). This keeps row counts reasonable while
    still supporting accurate Performance/Quality calculations.
    """
    rows = []
    current_time = SIM_START
    day_end = current_time + timedelta(hours=16)
    batch_seconds = batch_minutes * 60

    while current_time < day_end:
        # actual cycle time varies around the ideal (machine isn't perfect)
        actual_cycle = ideal_cycle_time * random.uniform(0.9, 1.3)
        units_produced = max(1, round(batch_seconds / actual_cycle))

        defect_rate = random.choices(
            [0.0, 0.03, 0.06, 0.10], weights=[70, 18, 8, 4], k=1
        )[0]
        defect_units = round(units_produced * defect_rate)
        defect_units = min(defect_units, units_produced)
        good_units = units_produced - defect_units

        rows.append(
            f"({machine_id}, '{current_time}', {units_produced}, {good_units}, {defect_units})"
        )
        current_time += timedelta(seconds=batch_seconds)

    return rows


def generate_sensor_readings(machine_id, machine_type):
    """Generate sensor readings every ~2 minutes during the production day."""
    rows = []
    sensors = SENSOR_MAP[machine_type]
    current_time = SIM_START
    day_end = current_time + timedelta(hours=16)

    while current_time < day_end:
        for sensor_type, low, high in sensors:
            value = round(random.uniform(low, high), 2)
            rows.append(
                f"({machine_id}, '{sensor_type}', {value}, '{current_time}')"
            )
        current_time += timedelta(minutes=random.randint(4, 6))

    return rows


def generate_maintenance_checks(machine_id, base_start):
    """
    Generate a handful of maintenance checks per machine, scattered from
    a few days before base_start to about a week and a half after it.
    Unlike status/cycle/sensor data, this isn't a per-day event, so it's
    only generated once per machine (not once per simulated day).
    """
    rows = []
    num_checks = random.randint(2, 4)

    for _ in range(num_checks):
        check_type = random.choice(CHECK_TYPES)
        offset_days = random.randint(-5, 10)
        scheduled_date = (base_start + timedelta(days=offset_days)).date()

        status = random.choices(
            ["completed", "scheduled", "in_progress", "overdue"],
            weights=MAINTENANCE_STATUS_WEIGHTS, k=1
        )[0]

        completed_date = f"'{scheduled_date}'" if status == "completed" else "NULL"
        technician = f"'{random.choice(TECHNICIANS)}'"
        notes = f"'{MAINTENANCE_NOTES[check_type]}'"

        rows.append(
            f"({machine_id}, '{check_type}', '{scheduled_date}', "
            f"{completed_date}, '{status}', {technician}, {notes})"
        )

    return rows


# ---------------------------------------------------------------
# MAIN — loop over days and machines, write SQL file
# ---------------------------------------------------------------

def main():
    status_rows = []
    cycle_rows = []
    sensor_rows = []
    maintenance_rows = []

    global SIM_START
    base_start = SIM_START

    for day in range(DAYS_OF_HISTORY):
        SIM_START = base_start + timedelta(days=day)
        for machine_id, (machine_type, ideal_cycle_time) in MACHINES.items():
            status_rows.extend(generate_status_log(machine_id))
            cycle_rows.extend(generate_cycle_events(machine_id, ideal_cycle_time))
            sensor_rows.extend(generate_sensor_readings(machine_id, machine_type))

    # Maintenance checks aren't a daily event, so generate once per machine
    # (using the original base_start, not the day-shifted SIM_START above).
    for machine_id in MACHINES:
        maintenance_rows.extend(generate_maintenance_checks(machine_id, base_start))

    with open("ot_sample_data.sql", "w") as f:
        f.write("USE smart_manufacturing_ot;\n\n")

        f.write("-- MachineStatusLog\n")
        f.write(
            "INSERT INTO MachineStatusLog (machine_id, status, start_time, end_time, reason_code) VALUES\n"
        )
        f.write(",\n".join(status_rows) + ";\n\n")

        f.write("-- CycleEvent\n")
        f.write(
            "INSERT INTO CycleEvent (machine_id, event_time, units_produced, good_units, defect_units) VALUES\n"
        )
        f.write(",\n".join(cycle_rows) + ";\n\n")

        f.write("-- SensorReading\n")
        f.write(
            "INSERT INTO SensorReading (machine_id, sensor_type, value, reading_time) VALUES\n"
        )
        f.write(",\n".join(sensor_rows) + ";\n\n")

        f.write("-- MaintenanceCheck\n")
        f.write(
            "INSERT INTO MaintenanceCheck (machine_id, check_type, scheduled_date, completed_date, status, technician, notes) VALUES\n"
        )
        f.write(",\n".join(maintenance_rows) + ";\n")

    print(f"Generated {len(status_rows)} status rows, "
          f"{len(cycle_rows)} cycle rows, "
          f"{len(sensor_rows)} sensor rows, "
          f"{len(maintenance_rows)} maintenance rows.")
    print("Written to ot_sample_data.sql")


if __name__ == "__main__":
    main()
