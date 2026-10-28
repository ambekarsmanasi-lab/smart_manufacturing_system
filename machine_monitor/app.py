import os
from datetime import datetime
from flask import Flask, jsonify, render_template
import mysql.connector
from dotenv import load_dotenv

from state_classifier import classify_machine

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

app = Flask(__name__)

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
