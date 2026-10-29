"""
Generate simulated telemetry for the Machine Monitor dashboard.

This script ONLY inserts rows into sensor_readings in smart_manufacturing_erp.
It does not create, update, resolve, classify, or otherwise modify faults.
Run from this directory with: python simulator.py
Stop with Ctrl+C.
"""
import os
import random
import time
import argparse
import threading
from datetime import datetime

import mysql.connector
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME", "smart_manufacturing_erp"),
}

# (baseline, noise standard deviation), keyed by lower-case sensor_type.
SENSOR_PROFILES = {
    "spindle temperature": (58.0, 4.0),
    "vibration": (2.0, 0.45),
    "spindle load": (48.0, 12.0),
    "belt speed": (1.2, 0.08),
    "joint temperature": (55.0, 4.0),
    "motor current": (3.2, 0.35),
    "barrel temperature": (185.0, 5.0),
    "injection pressure": (95.0, 8.0),
    "seal temperature": (170.0, 4.0),
    "throughput": (42.0, 3.0),
}

ACTIVE_ANOMALIES = {}  # sensor_id -> anomaly mode; shared with terminal control thread
ANOMALY_LOCK = threading.Lock()
STOP_EVENT = threading.Event()


def connect():
    if not DB_CONFIG["password"]:
        raise RuntimeError(
            "DB_PASSWORD is missing. Add it to machine_monitor/.env."
        )
    return mysql.connector.connect(**DB_CONFIG)


def load_sensors(conn):
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("""
            SELECT s.sensor_id, s.sensor_type, s.unit,
                   m.machine_id, m.name AS machine_name,
                   pl.name AS line_name
            FROM sensors s
            JOIN machines m ON m.machine_id = s.machine_id
            LEFT JOIN production_lines pl ON pl.line_id = m.line_id
            ORDER BY pl.name, m.name, s.sensor_id
        """)
        rows = cur.fetchall()
    finally:
        cur.close()

    if not rows:
        raise RuntimeError(
            "No sensors were found in smart_manufacturing_erp.sensors."
        )
    return rows


def generate_value(sensor, cycle=0):
    key = str(sensor.get("sensor_type", "")).strip().lower()
    baseline, noise = SENSOR_PROFILES.get(key, (10.0, 1.0))
    value = random.gauss(baseline, noise)

    # Interactive anomalies alter telemetry only. They never write fault rows.
    with ANOMALY_LOCK:
        mode = ACTIVE_ANOMALIES.get(sensor["sensor_id"])

    if mode == "High / spike":
        value = random.gauss(baseline + max(6 * noise, abs(baseline) * 0.45), max(noise * 0.15, 0.05))
    elif mode == "Low / drop":
        value = random.gauss(max(0.0, baseline - max(6 * noise, abs(baseline) * 0.45)), max(noise * 0.15, 0.05))
    elif mode == "Unstable / fluctuating":
        value = random.gauss(baseline + random.choice([-1, 1]) * max(5 * noise, abs(baseline) * 0.35), max(noise, 0.1))

    return round(max(0.0, value), 3)


def terminal_controls(sensors):
    """Interactive terminal menu running independently of telemetry insertion."""
    sensor_by_id = {sensor["sensor_id"]: sensor for sensor in sensors}

    def choose_sensor(prompt):
        print("\nAvailable sensors:")
        for sensor in sensors:
            print(f"  {sensor['sensor_id']}. {sensor['machine_name']} — {sensor['sensor_type']} ({sensor.get('unit') or 'unit n/a'})")
        try:
            sensor_id = int(input(prompt).strip())
        except (ValueError, EOFError):
            print("Invalid sensor selection.")
            return None
        if sensor_id not in sensor_by_id:
            print("That sensor ID does not exist.")
            return None
        return sensor_id

    while not STOP_EVENT.is_set():
        print("\n========== SMART MANUFACTURING SIMULATOR ==========")
        print("1. Inject a new anomaly")
        print("2. Stop an active anomaly")
        print("3. View active anomalies")
        print("4. Show sensor list")
        print("5. Return to telemetry-only mode / close menu")
        try:
            choice = input("Choose an option: ").strip()
        except EOFError:
            return

        if choice == "1":
            sensor_id = choose_sensor("Enter sensor ID to affect: ")
            if sensor_id is None:
                continue
            print("Anomaly mode: 1. High / spike  2. Low / drop  3. Unstable / fluctuating")
            mode_choice = input("Choose anomaly mode: ").strip()
            modes = {"1": "High / spike", "2": "Low / drop", "3": "Unstable / fluctuating"}
            if mode_choice not in modes:
                print("Invalid anomaly mode.")
                continue
            with ANOMALY_LOCK:
                ACTIVE_ANOMALIES[sensor_id] = modes[mode_choice]
            sensor = sensor_by_id[sensor_id]
            print(f"Started {modes[mode_choice]} anomaly: {sensor['machine_name']} / {sensor['sensor_type']}.")
            print("Normal telemetry continues for every other sensor.")

        elif choice == "2":
            with ANOMALY_LOCK:
                active_ids = list(ACTIVE_ANOMALIES)
            if not active_ids:
                print("No active anomalies.")
                continue
            print("Active anomalies:")
            for sensor_id in active_ids:
                sensor = sensor_by_id[sensor_id]
                print(f"  {sensor_id}. {sensor['machine_name']} — {sensor['sensor_type']} [{ACTIVE_ANOMALIES[sensor_id]}]")
            try:
                sensor_id = int(input("Enter sensor ID whose anomaly should stop: ").strip())
            except (ValueError, EOFError):
                print("Invalid sensor ID.")
                continue
            with ANOMALY_LOCK:
                removed = ACTIVE_ANOMALIES.pop(sensor_id, None)
            if removed:
                print(f"Stopped anomaly for sensor {sensor_id}. Normal readings resumed.")
            else:
                print("That sensor does not have an active anomaly.")

        elif choice == "3":
            with ANOMALY_LOCK:
                active = list(ACTIVE_ANOMALIES.items())
            if not active:
                print("No active anomalies.")
            else:
                print("Active anomalies:")
                for sensor_id, mode in active:
                    sensor = sensor_by_id[sensor_id]
                    print(f"  {sensor['machine_name']} / {sensor['sensor_type']}: {mode}")

        elif choice == "4":
            for sensor in sensors:
                print(f"{sensor['sensor_id']}. {sensor['machine_name']} — {sensor['sensor_type']} ({sensor.get('unit') or 'unit n/a'})")

        elif choice == "5":
            print("Control menu closed; telemetry continues. Press Ctrl+C in the telemetry terminal to stop everything.")
            return
        else:
            print("Choose a number from 1 to 5.")


def main():
    parser = argparse.ArgumentParser(description="Interactive telemetry simulator for Smart Manufacturing ERP")
    parser.add_argument("--interval", type=float, default=float(os.getenv("SIMULATOR_INTERVAL", "2")),
                        help="Seconds between telemetry batches (minimum 0.5).")
    args = parser.parse_args()
    if args.interval < 0.5:
        parser.error("--interval must be at least 0.5 seconds")

    conn = connect()
    try:
        sensors = load_sensors(conn)
        print("Connected to smart_manufacturing_erp.")
        print(f"Loaded {len(sensors)} sensors.")
        print(f"Inserting readings every {args.interval:g} seconds.")
        print("This simulator writes ONLY to sensor_readings; it never writes to faults.")
        print("Interactive control menu starts in a separate input thread. Press Ctrl+C to stop.\n")

        control_thread = threading.Thread(target=terminal_controls, args=(sensors,), daemon=True)
        control_thread.start()
        cycle = 0
        while not STOP_EVENT.is_set():
            cur = conn.cursor()
            try:
                now = datetime.now()
                rows = [
                    (sensor["sensor_id"], now, generate_value(sensor, cycle=cycle + 1))
                    for sensor in sensors
                ]
                cur.executemany("""
                    INSERT INTO sensor_readings (sensor_id, recorded_at, value)
                    VALUES (%s, %s, %s)
                """, rows)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                cur.close()

            cycle += 1
            if cycle == 1 or cycle % 5 == 0:
                with ANOMALY_LOCK:
                    active_count = len(ACTIVE_ANOMALIES)
                print(f"[{datetime.now():%H:%M:%S}] cycle={cycle}, inserted={len(sensors)} readings, active anomalies={active_count}")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nSimulator stopped.")
    finally:
        STOP_EVENT.set()
        conn.close()


if __name__ == "__main__":
    main()
