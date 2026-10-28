"""
Baseline-based fault analyser for Smart Manufacturing ERP.

Reads existing sensor_readings from smart_manufacturing_erp, detects sustained
statistical outliers, and records them in faults/fault_evidence.

This is an initial statistical anomaly detector, not a trained ML model.
It does not generate sensor data or alter machine state.

Run from the repository root:
    python machine_monitor/fault_analyser.py
"""

import os
import time
from datetime import datetime, timedelta

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

POLL_SECONDS = float(os.getenv("FAULT_ANALYSER_POLL_SECONDS", "5"))
FRESHNESS_SECONDS = 5
DETECTION_WINDOW_READINGS = 10
BASELINE_LIMIT = 100
MIN_BASELINE_READINGS = 30
CONSECUTIVE_ANOMALIES = 3
ROBUST_Z_THRESHOLD = 4.5
MODEL_VERSION = "robust-stat-v3"
# A gap longer than this between detections is treated as a new occurrence
# of the same still-open incident. It does NOT create a duplicate incident.
RECURRENCE_GAP_SECONDS = 60

# Map only the three sensors used by this demo to appropriate categories.
# Other sensors are deliberately skipped until the existing categories support
# defensible diagnoses for them; do not label unrelated signals as faults.
FAULT_CODE_BY_SENSOR = {
    # These codes are set by align_fault_types.sql; IDs are preserved so
    # existing faults/work orders continue referencing the same categories.
    "spindle temperature": "SPINDLE_TEMP_ANOMALY",
    "vibration": "MACHINE_VIBRATION",
    "joint temperature": "MOTOR_OVERHEATING",
}


def connect():
    if not DB_CONFIG["password"]:
        raise RuntimeError(
            "DB_PASSWORD is missing. Check machine_monitor/.env."
        )
    return mysql.connector.connect(**DB_CONFIG)


def load_sensors(conn):
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT s.sensor_id, s.sensor_type, s.unit,
               m.machine_id, m.name AS machine_name, m.criticality
        FROM sensors s
        JOIN machines m ON m.machine_id = s.machine_id
        ORDER BY m.name, s.sensor_id
    """)
    rows = cur.fetchall()
    cur.close()
    return rows


def load_fault_types(conn):
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT fault_type_id, fault_code, name FROM fault_types")
    rows = cur.fetchall()
    cur.close()
    return {row["fault_code"]: row for row in rows}


def get_recent_values(conn, sensor_id, limit):
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT reading_id, recorded_at, value
        FROM sensor_readings
        WHERE sensor_id = %s
        ORDER BY recorded_at DESC, reading_id DESC
        LIMIT %s
    """, (sensor_id, limit))
    rows = cur.fetchall()
    cur.close()
    return list(reversed(rows))


def median(values):
    values = sorted(values)
    n = len(values)
    middle = n // 2
    if n % 2:
        return float(values[middle])
    return (values[middle - 1] + values[middle]) / 2.0


def robust_baseline(values):
    """Return median and robust sigma estimate (1.4826 * MAD)."""
    center = median(values)
    mad = median([abs(value - center) for value in values])
    sigma = 1.4826 * mad

    # If the readings are almost constant, fall back to standard deviation.
    if sigma <= 1e-9:
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        sigma = variance ** 0.5

    return center, sigma


def severity_for(score, criticality):
    if score >= 8.0 and criticality == "HIGH":
        return "CRITICAL"
    if score >= 8.0:
        return "HIGH"
    if score >= 6.0:
        return "HIGH"
    return "MEDIUM"


def sensor_fault_type(sensor, fault_types):
    key = str(sensor.get("sensor_type", "")).strip().lower()
    code = FAULT_CODE_BY_SENSOR.get(key)
    return fault_types.get(code) if code else None


def find_anomaly(conn, sensor):
    # The latest 10 readings form the detection wave. Older readings establish
    # the baseline only. Do not analyse a wave unless its newest reading is
    # fresh, and do not treat stale telemetry as a new fault.
    rows = get_recent_values(
        conn, sensor["sensor_id"],
        BASELINE_LIMIT + DETECTION_WINDOW_READINGS
    )
    if len(rows) < MIN_BASELINE_READINGS + DETECTION_WINDOW_READINGS:
        return None

    baseline_rows = rows[:-DETECTION_WINDOW_READINGS]
    wave_rows = rows[-DETECTION_WINDOW_READINGS:]
    now = datetime.now()

    newest_at = wave_rows[-1]["recorded_at"]
    if isinstance(newest_at, str):
        newest_at = datetime.fromisoformat(newest_at)
    newest_age = (now - newest_at).total_seconds()
    if newest_age < -2 or newest_age > FRESHNESS_SECONDS:
        return None

    baseline_values = [float(row["value"]) for row in baseline_rows]
    center, sigma = robust_baseline(baseline_values)
    if sigma <= 1e-9:
        return None

    wave_values = [float(row["value"]) for row in wave_rows]
    scores = [(value - center) / sigma for value in wave_values]

    # Require a sustained anomaly across the 10-reading wave: at least 7 of
    # 10 values must exceed the robust threshold in the same direction.
    high_count = sum(score >= ROBUST_Z_THRESHOLD for score in scores)
    low_count = sum(score <= -ROBUST_Z_THRESHOLD for score in scores)
    if high_count < 7 and low_count < 7:
        return None

    latest = wave_rows[-1]
    return {
        "observed": float(latest["value"]),
        "expected": center,
        "score": abs(scores[-1]),
        "reading_at": latest["recorded_at"],
        "sensor_id": sensor["sensor_id"],
        "latest_reading_id": latest["reading_id"],
        "wave_anomaly_count": max(high_count, low_count),
        "wave_size": DETECTION_WINDOW_READINGS,
    }


def record_fault(conn, sensor, fault_type, anomaly):
    now = datetime.now()
    cur = conn.cursor(dictionary=True)

    # Do not create repeated rows while the same machine/type is active.
    cur.execute("""
        SELECT fault_id, last_seen_at, occurrence_count
        FROM faults
        WHERE machine_id = %s
          AND fault_type_id = %s
          AND status IN ('OPEN', 'ASSIGNED')
        ORDER BY fault_id DESC
        LIMIT 1
    """, (sensor["machine_id"], fault_type["fault_type_id"]))
    existing = cur.fetchone()

    score = anomaly["score"]
    severity = severity_for(score, sensor["criticality"])
    summary = (
        f"{sensor['machine_name']}: sustained abnormal "
        f"{sensor['sensor_type']} ({anomaly['observed']:.3f} {sensor['unit'] or ''}); "
        f"baseline median {anomaly['expected']:.3f}."
    )[:255]

    if existing:
        fault_id = existing["fault_id"]
        last_seen = existing.get("last_seen_at")
        if isinstance(last_seen, str):
            last_seen = datetime.fromisoformat(last_seen)
        # A continuously detected anomaly refreshes the same incident without
        # inflating occurrence_count every poll. A sufficiently long gap means
        # the anomaly has reappeared, so count one new occurrence on that incident.
        new_occurrence = (
            last_seen is not None
            and (now - last_seen).total_seconds() >= RECURRENCE_GAP_SECONDS
        )
        if new_occurrence:
            cur.execute("""
                UPDATE faults
                SET last_seen_at = %s,
                    occurrence_count = COALESCE(occurrence_count, 1) + 1,
                    confidence = %s,
                    severity = %s,
                    summary = %s
                WHERE fault_id = %s
            """, (now, min(0.999, 0.75 + min(score, 10.0) * 0.02),
                  severity, summary, fault_id))
        else:
            cur.execute("""
                UPDATE faults
                SET last_seen_at = %s,
                    confidence = %s,
                    severity = %s,
                    summary = %s
                WHERE fault_id = %s
            """, (now, min(0.999, 0.75 + min(score, 10.0) * 0.02),
                  severity, summary, fault_id))
        created = False
    else:
        cur.execute("""
            INSERT INTO faults (
                machine_id, fault_type_id, severity, confidence, summary,
                est_ttf_hrs, model_version, status, detected_at,
                last_seen_at, occurrence_count
            )
            VALUES (%s, %s, %s, %s, %s, NULL, %s, 'OPEN', %s, %s, 1)
        """, (
            sensor["machine_id"],
            fault_type["fault_type_id"],
            severity,
            min(0.999, 0.75 + min(score, 10.0) * 0.02),
            summary,
            MODEL_VERSION,
            now,
            now,
        ))
        fault_id = cur.lastrowid
        created = True

    cur.execute("""
        INSERT INTO fault_evidence
            (fault_id, sensor_id, observed_value, expected_value, unit)
        VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            observed_value = VALUES(observed_value),
            expected_value = VALUES(expected_value),
            unit = VALUES(unit)
    """, (
        fault_id,
        sensor["sensor_id"],
        anomaly["observed"],
        anomaly["expected"],
        sensor["unit"],
    ))
    cur.close()
    return fault_id, created


def main():
    last_handled_reading_id = {}
    last_status = None
    last_missing_codes = None
    last_unmapped_sensors = None

    print("Smart Manufacturing ERP — fault analyser")
    print(f"Detector: {MODEL_VERSION}")
    print(f"Detection wave: latest {DETECTION_WINDOW_READINGS} readings per sensor.")
    print(f"Freshness limit: {FRESHNESS_SECONDS} seconds.")
    print("Waiting silently when no fresh sensor data is available.")
    print("Press Ctrl+C to stop.\\n")

    while True:
        conn = None
        try:
            conn = connect()
            sensors = load_sensors(conn)
            fault_types = load_fault_types(conn)

            if not sensors:
                if last_status != "no_sensors":
                    print("No sensors found in smart_manufacturing_erp.")
                    last_status = "no_sensors"
            else:
                fresh_count = 0
                for sensor in sensors:
                    cur = conn.cursor()
                    cur.execute("""
                        SELECT MAX(recorded_at)
                        FROM sensor_readings
                        WHERE sensor_id = %s
                    """, (sensor["sensor_id"],))
                    result = cur.fetchone()
                    cur.close()
                    latest_at = result[0] if result else None
                    if latest_at is not None:
                        age = (datetime.now() - latest_at).total_seconds()
                        if -2 <= age <= FRESHNESS_SECONDS:
                            fresh_count += 1

                status = "fresh" if fresh_count else "waiting"
                if status != last_status:
                    if status == "fresh":
                        print(f"Live telemetry resumed ({fresh_count}/{len(sensors)} sensors fresh).")
                    # No repeating "successful analysis" or waiting messages.
                    last_status = status

                missing_codes = sorted({
                    code for s in sensors
                    if (code := FAULT_CODE_BY_SENSOR.get(
                        str(s.get("sensor_type", "")).strip().lower()
                    )) and code not in fault_types
                })
                unmapped_sensors = sorted({
                    str(s.get("sensor_type", "")).strip()
                    for s in sensors
                    if str(s.get("sensor_type", "")).strip().lower()
                    not in FAULT_CODE_BY_SENSOR
                })
                if missing_codes and missing_codes != last_missing_codes:
                    print("Warning: no matching fault_types rows for: "
                          + ", ".join(missing_codes))
                last_missing_codes = missing_codes
                if unmapped_sensors and unmapped_sensors != last_unmapped_sensors:
                    print("Skipping sensors without a configured fault category: "
                          + ", ".join(unmapped_sensors))
                last_unmapped_sensors = unmapped_sensors

                if fresh_count:
                    for sensor in sensors:
                        fault_type = sensor_fault_type(sensor, fault_types)
                        if not fault_type:
                            continue

                        anomaly = find_anomaly(conn, sensor)
                        if anomaly is None:
                            continue

                        sensor_id = sensor["sensor_id"]
                        reading_id = anomaly["latest_reading_id"]
                        if last_handled_reading_id.get(sensor_id) == reading_id:
                            continue

                        fault_id, created = record_fault(
                            conn, sensor, fault_type, anomaly
                        )
                        conn.commit()
                        last_handled_reading_id[sensor_id] = reading_id
                        label = "REGISTERED NEW INCIDENT" if created else "UPDATED EXISTING INCIDENT"
                        print(
                            f"{label} #{fault_id}: {sensor['machine_name']} / "
                            f"{fault_type['name']} — {sensor['sensor_type']}="
                            f"{anomaly['observed']:.3f} {sensor['unit'] or ''}; "
                            f"{anomaly['wave_anomaly_count']}/{anomaly['wave_size']} "
                            f"recent readings anomalous (baseline {anomaly['expected']:.3f})."
                        )

                if conn.is_connected():
                    conn.commit()

        except KeyboardInterrupt:
            print("\\nFault analyser stopped.")
            break
        except mysql.connector.Error as exc:
            if last_status != "db_error":
                print(f"Database error: {exc}")
                last_status = "db_error"
        except Exception as exc:
            print(f"Analyser error: {exc}")
        finally:
            if conn is not None and conn.is_connected():
                conn.close()

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
