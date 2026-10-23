"""
live_data_simulator.py
------------------------
Continuously inserts new rows into MachineStatusLog, CycleEvent, and
SensorReading so the database keeps changing over time — simulating
machines reporting live data.

Run this in its own terminal window and just leave it running while you
demo the dashboard. Press Ctrl+C to stop it.

Requires: pip install mysql-connector-python
"""

import time
import random
from datetime import datetime, timedelta
import mysql.connector

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "your_password",
    "database": "smart_manufacturing_ot",
}

TICK_SECONDS = 5

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
STATUS_WEIGHTS = [40, 40, 40, 10, 6, 4]

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

NEW_CHECK_CHANCE = 0.05        # per machine, per tick, chance a new check gets scheduled
CHECK_PROGRESS_CHANCE = 0.20   # per open check, per tick, chance it advances

open_status_row = {}
open_maintenance_checks = {}   # check_id -> {"machine_id": int, "status": str}
fractional_units = {}          # machine_id -> leftover fractional production progress


def get_connection():
    return mysql.connector.connect(**DB_CONFIG)


def close_open_status(cursor, machine_id, end_time):
    if machine_id in open_status_row:
        log_id, _, _ = open_status_row[machine_id]
        cursor.execute(
            "UPDATE MachineStatusLog SET end_time = %s WHERE log_id = %s",
            (end_time, log_id),
        )
        del open_status_row[machine_id]


def open_new_status(cursor, machine_id, now):
    status = random.choices(STATUS_OPTIONS, weights=STATUS_WEIGHTS, k=1)[0]
    reason_code = random.choice(REASON_CODES[status]) if status in REASON_CODES else None

    cursor.execute(
        """INSERT INTO MachineStatusLog (machine_id, status, start_time, end_time, reason_code)
           VALUES (%s, %s, %s, NULL, %s)""",
        (machine_id, status, now, reason_code),
    )
    log_id = cursor.lastrowid
    open_status_row[machine_id] = (log_id, status, now)
    return status


def load_open_status_rows(cursor):
    """
    On startup, adopt any status rows already open (end_time IS NULL) in the
    database instead of assuming none exist. Without this, restarting the
    script resets the in-memory open_status_row dict to empty, so the next
    tick opens a brand-new row per machine and orphans the old one forever —
    which is exactly how duplicate "open" rows (and inflated machine counts
    on the dashboard) pile up across restarts.

    If a machine somehow has more than one open row (e.g. from a previous
    run of this bug), all but the most recent get closed out here too.
    """
    cursor.execute(
        """SELECT log_id, machine_id, status, start_time
           FROM MachineStatusLog
           WHERE end_time IS NULL
           ORDER BY machine_id, start_time DESC"""
    )
    rows = cursor.fetchall()

    seen_machines = set()
    stale_log_ids = []

    for log_id, machine_id, status, start_time in rows:
        if machine_id in seen_machines:
            # older duplicate open row for a machine we've already adopted — close it
            stale_log_ids.append(log_id)
            continue
        open_status_row[machine_id] = (log_id, status, start_time)
        seen_machines.add(machine_id)

    if stale_log_ids:
        format_ids = ",".join(str(i) for i in stale_log_ids)
        cursor.execute(
            f"UPDATE MachineStatusLog SET end_time = NOW() WHERE log_id IN ({format_ids})"
        )
        print(f"Closed {len(stale_log_ids)} stale duplicate open status row(s) from a previous run.")

    if seen_machines:
        print(f"Adopted {len(seen_machines)} already-open status row(s) from the database.")


def insert_cycle_event(cursor, machine_id, ideal_cycle_time, now, status):
    """Returns the number of units inserted this tick (0 if none)."""
    if status != "running":
        return 0

    actual_cycle = ideal_cycle_time * random.uniform(0.9, 1.3)

    # Carry fractional progress across ticks instead of forcing at least 1
    # unit per tick. For machines whose cycle time is longer than TICK_SECONDS
    # (e.g. a 30s injection cycle vs a 10s tick), rounding up to a minimum of 1
    # unit every tick massively overstates real output. Accumulating fractional
    # progress and only emitting a unit once it's actually "complete" removes
    # that bias.
    fractional_units[machine_id] = fractional_units.get(machine_id, 0.0) + (TICK_SECONDS / actual_cycle)
    units_produced = int(fractional_units[machine_id])
    fractional_units[machine_id] -= units_produced

    if units_produced == 0:
        return 0  # nothing completed yet this tick — normal for slow machines

    defect_rate = random.choices([0.0, 0.03, 0.06, 0.10], weights=[70, 18, 8, 4], k=1)[0]
    defect_units = min(round(units_produced * defect_rate), units_produced)
    good_units = units_produced - defect_units

    cursor.execute(
        """INSERT INTO CycleEvent (machine_id, event_time, units_produced, good_units, defect_units)
           VALUES (%s, %s, %s, %s, %s)""",
        (machine_id, now, units_produced, good_units, defect_units),
    )
    return units_produced


def insert_sensor_readings(cursor, machine_id, machine_type, now):
    for sensor_type, low, high in SENSOR_MAP[machine_type]:
        value = round(random.uniform(low, high), 2)
        cursor.execute(
            """INSERT INTO SensorReading (machine_id, sensor_type, value, reading_time)
               VALUES (%s, %s, %s, %s)""",
            (machine_id, sensor_type, value, now),
        )


def maybe_schedule_maintenance(cursor, machine_id, now):
    """Small random chance each tick that a new maintenance check gets scheduled
    for this machine (e.g. a fault triggers a corrective check, or a routine
    preventive check comes due)."""
    if random.random() >= NEW_CHECK_CHANCE:
        return

    check_type = random.choice(CHECK_TYPES)
    # scheduled anywhere from today to ~5 days out
    scheduled_date = (now + timedelta(days=random.randint(0, 5))).date()
    technician = random.choice(TECHNICIANS)
    notes = MAINTENANCE_NOTES[check_type]

    cursor.execute(
        """INSERT INTO MaintenanceCheck
               (machine_id, check_type, scheduled_date, completed_date, status, technician, notes)
           VALUES (%s, %s, %s, NULL, 'scheduled', %s, %s)""",
        (machine_id, check_type, scheduled_date, technician, notes),
    )
    check_id = cursor.lastrowid
    open_maintenance_checks[check_id] = {"machine_id": machine_id, "status": "scheduled"}


def progress_maintenance_checks(cursor, now):
    """Randomly advance a few currently-open maintenance checks each tick,
    moving them through scheduled -> in_progress -> completed (or, less often,
    flipping a scheduled check to overdue)."""
    for check_id, info in list(open_maintenance_checks.items()):
        if random.random() >= CHECK_PROGRESS_CHANCE:
            continue

        status = info["status"]

        if status == "scheduled":
            new_status = random.choices(
                ["in_progress", "overdue"], weights=[70, 30], k=1
            )[0]
            cursor.execute(
                "UPDATE MaintenanceCheck SET status = %s WHERE check_id = %s",
                (new_status, check_id),
            )
            info["status"] = new_status

        elif status in ("in_progress", "overdue"):
            # finish the check
            cursor.execute(
                """UPDATE MaintenanceCheck
                   SET status = 'completed', completed_date = %s
                   WHERE check_id = %s""",
                (now.date(), check_id),
            )
            del open_maintenance_checks[check_id]


def tick(cursor):
    now = datetime.now()
    summary = []  # one entry per machine, for terminal visibility

    for machine_id, (machine_type, ideal_cycle_time) in MACHINES.items():
        changed = machine_id not in open_status_row or random.random() < 0.15

        if changed:
            close_open_status(cursor, machine_id, now)
            status = open_new_status(cursor, machine_id, now)
        else:
            _, status, _ = open_status_row[machine_id]

        units = insert_cycle_event(cursor, machine_id, ideal_cycle_time, now, status)
        insert_sensor_readings(cursor, machine_id, machine_type, now)
        maybe_schedule_maintenance(cursor, machine_id, now)

        summary.append({"machine_id": machine_id, "status": status,
                        "status_changed": changed, "units": units})

    progress_maintenance_checks(cursor, now)
    return summary


def print_tick_summary(summary):
    parts = []
    for m in summary:
        flag = "*" if m["status_changed"] else " "
        parts.append(f"M{m['machine_id']}:{m['status']:<7}{flag}+{m['units']}u")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] " + " | ".join(parts))


def main():
    print(f"Starting live data simulator — inserting new data every {TICK_SECONDS}s.")
    print("Per tick: M<id>:<status> <* = status just changed> +<units completed>u")
    print("Press Ctrl+C to stop.\n")

    conn = get_connection()
    cursor = conn.cursor()

    load_open_status_rows(cursor)
    conn.commit()

    try:
        while True:
            summary = tick(cursor)
            conn.commit()
            print_tick_summary(summary)
            time.sleep(TICK_SECONDS)
    except KeyboardInterrupt:
        print("\nStopping simulator.")
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
