import os
from datetime import datetime
from statistics import median
from flask import Flask, jsonify, render_template
import mysql.connector
from dotenv import load_dotenv

from state_classifier import classify_machine

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

app = Flask(__name__)

# Keep these values aligned with machine_monitor/fault_analyser.py.
FRESHNESS_SECONDS = 5
DETECTION_WINDOW_READINGS = 10
BASELINE_LIMIT = 100
MIN_BASELINE_READINGS = 30
ROBUST_Z_THRESHOLD = 4.5


def robust_baseline(values):
    """Return the median and robust sigma (1.4826 * MAD)."""
    center = median(values)
    mad = median([abs(value - center) for value in values])
    sigma = 1.4826 * mad
    if sigma <= 1e-9:
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        sigma = variance ** 0.5
    return center, sigma


def sensor_is_anomalous(cur, sensor_id):
    """Mirror fault_analyser.py's sustained, fresh statistical detector."""
    cur.execute(
        """SELECT reading_id, recorded_at, value
           FROM sensor_readings
           WHERE sensor_id = %s
           ORDER BY recorded_at DESC, reading_id DESC
           LIMIT %s""",
        (sensor_id, BASELINE_LIMIT + DETECTION_WINDOW_READINGS),
    )
    # SQL returns newest first; reverse to chronological order.
    rows = list(reversed(cur.fetchall()))
    if len(rows) < MIN_BASELINE_READINGS + DETECTION_WINDOW_READINGS:
        return False

    baseline_rows = rows[:-DETECTION_WINDOW_READINGS]
    wave_rows = rows[-DETECTION_WINDOW_READINGS:]
    newest_at = wave_rows[-1]["recorded_at"]
    if isinstance(newest_at, str):
        newest_at = datetime.fromisoformat(newest_at)
    age_seconds = (datetime.now() - newest_at).total_seconds()
    if age_seconds < -2 or age_seconds > FRESHNESS_SECONDS:
        return False

    baseline_values = [float(row["value"]) for row in baseline_rows]
    center, sigma = robust_baseline(baseline_values)
    if sigma <= 1e-9:
        return False

    scores = [(float(row["value"]) - center) / sigma for row in wave_rows]
    high_count = sum(score >= ROBUST_Z_THRESHOLD for score in scores)
    low_count = sum(score <= -ROBUST_Z_THRESHOLD for score in scores)
    return high_count >= 7 or low_count >= 7

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME", "smart_manufacturing_erp"),
}


def db_connection():
    if not DB_CONFIG["password"]:
        raise RuntimeError(
            "DB_PASSWORD is missing. Add it to machine_monitor/.env."
        )
    return mysql.connector.connect(**DB_CONFIG)


def serialise_rows(rows):
    for row in rows:
        for key, value in row.items():
            if isinstance(value, datetime):
                row[key] = value.isoformat(sep=" ", timespec="seconds")
    return rows


@app.get("/")
def dashboard():
    return render_template("dashboard.html")


@app.get("/api/overview")
def overview():
    conn = db_connection()
    try:
        cur = conn.cursor(dictionary=True)

        cur.execute("""
            SELECT m.machine_id, m.name AS machine_name, m.criticality,
                   pl.name AS line_name,
                   COUNT(DISTINCT s.sensor_id) AS sensor_count
            FROM machines m
            LEFT JOIN production_lines pl ON pl.line_id = m.line_id
            LEFT JOIN sensors s ON s.machine_id = m.machine_id
            GROUP BY m.machine_id, m.name, m.criticality, pl.name
            ORDER BY pl.name, m.name
        """)
        machines = cur.fetchall()

        cur.execute("""
            SELECT s.sensor_id, s.sensor_type, s.unit,
                   m.machine_id, m.name AS machine_name, pl.name AS line_name,
                   sr.value, sr.recorded_at
            FROM sensors s
            JOIN machines m ON m.machine_id = s.machine_id
            LEFT JOIN production_lines pl ON pl.line_id = m.line_id
            LEFT JOIN sensor_readings sr ON sr.sensor_id = s.sensor_id
                AND sr.recorded_at = (
                    SELECT MAX(sr2.recorded_at)
                    FROM sensor_readings sr2
                    WHERE sr2.sensor_id = s.sensor_id
                )
            ORDER BY pl.name, m.name, s.sensor_id
        """)
        readings = cur.fetchall()

        # The chip colour follows the detector's current sensor readings, not
        # whether an OPEN/ASSIGNED fault record happens to exist.
        for reading in readings:
            reading["anomalous"] = (
                reading.get("recorded_at") is not None
                and sensor_is_anomalous(cur, reading["sensor_id"])
            )

        # Fault records are displayed as alarm information only. They do not
        # determine the machine's operational state.
        cur.execute("""
            SELECT f.fault_id, f.severity, f.summary, f.status,
                   f.detected_at, f.last_seen_at,
                   m.name AS machine_name,
                   ft.fault_code, ft.name AS fault_name
            FROM faults f
            JOIN machines m ON m.machine_id = f.machine_id
            JOIN fault_types ft ON ft.fault_type_id = f.fault_type_id
            WHERE UPPER(f.status) NOT IN ('RESOLVED', 'CLOSED')
            ORDER BY f.detected_at DESC
            LIMIT 20
        """)
        faults = cur.fetchall()
        cur.close()

        machines = serialise_rows(machines)
        readings = serialise_rows(readings)
        faults = serialise_rows(faults)

        for machine in machines:
            machine_readings = [
                row for row in readings
                if int(row["machine_id"]) == int(machine["machine_id"])
                and row.get("recorded_at") is not None
            ]
            classification = classify_machine(
                machine["machine_name"], machine_readings
            )
            machine["state"] = classification["state"]
            machine["state_reason"] = classification["reason"]
            machine["state_confidence"] = classification["confidence"]

        latest_times = [
            row["recorded_at"] for row in readings if row.get("recorded_at")
        ]
        states = [machine["state"] for machine in machines]

        return jsonify({
            "machines": machines,
            "readings": readings,
            "faults": faults,
            "summary": {
                "machines": len(machines),
                "sensors": len(readings),
                "sensors_reporting": sum(
                    1 for row in readings if row.get("recorded_at") is not None
                ),
                "running": states.count("RUNNING"),
                "idle": states.count("IDLE"),
                "offline": states.count("OFFLINE"),
                "unknown": states.count("UNKNOWN"),
                "active_faults": len(faults),
                "critical_faults": sum(
                    1 for fault in faults
                    if str(fault.get("severity", "")).upper() == "CRITICAL"
                ),
                "last_update": max(latest_times) if latest_times else None,
            },
        })
    finally:
        conn.close()


@app.get("/api/health")
def health():
    try:
        conn = db_connection()
        conn.close()
        return jsonify({"ok": True, "database": DB_CONFIG["database"]})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503


if __name__ == "__main__":
    app.run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "5051")),
        debug=False,
    )
