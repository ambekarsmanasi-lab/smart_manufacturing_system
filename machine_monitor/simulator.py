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


def generate_value(sensor, cycle=0, demo_fault="none", start_cycle=40, duration_cycles=35):
    key = str(sensor.get("sensor_type", "")).strip().lower()
    baseline, noise = SENSOR_PROFILES.get(key, (10.0, 1.0))
    value = random.gauss(baseline, noise)

    # Demo injection only changes sensor telemetry. It NEVER writes to faults.
    active = start_cycle <= cycle < start_cycle + duration_cycles
    if active:
        if demo_fault == "spindle-temperature" and key == "spindle temperature":
            value = random.gauss(95.0, 1.2)
        elif demo_fault == "vibration" and key == "vibration":
            value = random.gauss(8.0, 0.25)
        elif demo_fault == "joint-temperature" and key == "joint temperature":
            value = random.gauss(90.0, 1.2)
    return round(max(0.0, value), 3)


def main():
    parser = argparse.ArgumentParser(description="Telemetry simulator for Smart Manufacturing ERP")
    parser.add_argument("--demo-fault", choices=["none", "spindle-temperature", "vibration", "joint-temperature"], default="none",
                        help="Inject one controlled anomaly into telemetry; no fault rows are written by this simulator.")
    parser.add_argument("--start-cycle", type=int, default=40,
                        help="Cycle to begin injection (default: 40, allowing baseline readings first).")
    parser.add_argument("--duration-cycles", type=int, default=35,
                        help="Number of cycles to inject the anomaly (default: 35).")
    args = parser.parse_args()
    if args.start_cycle < 1 or args.duration_cycles < 10:
        parser.error("--start-cycle must be >= 1 and --duration-cycles must be >= 10")
    interval = float(os.getenv("SIMULATOR_INTERVAL", "2"))
    if interval < 0.5:
        raise ValueError("SIMULATOR_INTERVAL must be at least 0.5 seconds.")

    conn = connect()
    try:
        sensors = load_sensors(conn)
        print("Connected to smart_manufacturing_erp.")
        print(f"Loaded {len(sensors)} sensors.")
        print(f"Inserting sensor readings every {interval:g} seconds.")
        print(f"Demo fault: {args.demo_fault}; start cycle={args.start_cycle}; duration={args.duration_cycles} cycles.")
        print("This simulator writes ONLY to sensor_readings; it never writes to faults. Press Ctrl+C to stop.\n")

        cycle = 0
        while True:
            cur = conn.cursor()
            try:
                now = datetime.now()
                rows = [
                    (sensor["sensor_id"], now, generate_value(
                        sensor, cycle=cycle + 1, demo_fault=args.demo_fault,
                        start_cycle=args.start_cycle, duration_cycles=args.duration_cycles
                    ))
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
            if cycle == args.start_cycle:
                print(f"[{datetime.now():%H:%M:%S}] DEMO ANOMALY STARTED: {args.demo_fault}")
            if cycle == args.start_cycle + args.duration_cycles:
                print(f"[{datetime.now():%H:%M:%S}] DEMO ANOMALY ENDED; normal telemetry resumed")
            if cycle == 1 or cycle % 5 == 0:
                print(f"[{datetime.now():%H:%M:%S}] cycle={cycle}, inserted={len(sensors)} readings")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nSimulator stopped.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
