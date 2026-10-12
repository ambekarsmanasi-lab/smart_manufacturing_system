"""
backend_app.py
----------------
A small Flask API that queries the live MySQL database and returns
current OEE (Availability, Performance, Quality) per machine as JSON.

Requires: pip install flask mysql-connector-python flask-cors

Run with: python backend_app.py
Then visit: http://localhost:5000/api/oee
"""

from flask import Flask, jsonify
from flask_cors import CORS
import mysql.connector

app = Flask(__name__)
CORS(app)  # allows the frontend HTML file to fetch this API directly

DB_CONFIG = {
    "host": "localhost",
    "user": "root",          # <-- change to your MySQL username
    "password": "YOUR_PASSWORD",  # <-- change to your MySQL password
    "database": "smart_manufacturing_ot",
}

OEE_QUERY = """
WITH availability_cte AS (
    SELECT
        machine_id,
        SUM(CASE WHEN status = 'running'
                 THEN TIMESTAMPDIFF(SECOND, start_time, IFNULL(end_time, NOW()))
                 ELSE 0 END) AS actual_op_sec,
        SUM(TIMESTAMPDIFF(SECOND, start_time, IFNULL(end_time, NOW()))) AS planned_sec
    FROM MachineStatusLog
    GROUP BY machine_id
),
performance_quality_cte AS (
    SELECT
        machine_id,
        SUM(units_produced) AS total_units,
        SUM(good_units) AS good_units
    FROM CycleEvent
    GROUP BY machine_id
)
SELECT
    m.machine_id,
    m.machine_name,
    m.machine_type,
    l.line_name,
    IFNULL(ROUND(a.actual_op_sec / NULLIF(a.planned_sec, 0), 4), 0) AS availability,
    IFNULL(ROUND(
        LEAST(1, (m.ideal_cycle_time_sec * pq.total_units) / NULLIF(a.actual_op_sec, 0))
    , 4), 0) AS performance,
    IFNULL(ROUND(pq.good_units / NULLIF(pq.total_units, 0), 4), 0) AS quality,
    IFNULL(ROUND(
        LEAST(1, a.actual_op_sec / NULLIF(a.planned_sec, 0))
        * LEAST(1, (m.ideal_cycle_time_sec * pq.total_units) / NULLIF(a.actual_op_sec, 0))
        * LEAST(1, pq.good_units / NULLIF(pq.total_units, 0))
    , 4), 0) AS oee
FROM Machine m
JOIN ProductionLine l ON l.line_id = m.line_id
LEFT JOIN availability_cte a ON a.machine_id = m.machine_id
LEFT JOIN performance_quality_cte pq ON pq.machine_id = m.machine_id
ORDER BY m.machine_id;
"""

LATEST_STATUS_QUERY = """
SELECT s.machine_id, m.machine_name, s.status, s.start_time, s.reason_code
FROM MachineStatusLog s
JOIN Machine m ON m.machine_id = s.machine_id
WHERE s.end_time IS NULL
ORDER BY s.machine_id;
"""

LATEST_SENSORS_QUERY = """
SELECT sr.machine_id, sr.sensor_type, sr.value, sr.reading_time
FROM SensorReading sr
INNER JOIN (
    SELECT machine_id, sensor_type, MAX(reading_time) AS max_time
    FROM SensorReading
    GROUP BY machine_id, sensor_type
) latest ON sr.machine_id = latest.machine_id
         AND sr.sensor_type = latest.sensor_type
         AND sr.reading_time = latest.max_time
ORDER BY sr.machine_id, sr.sensor_type;
"""


MAINTENANCE_QUERY = """
SELECT
    mc.check_id, mc.machine_id, m.machine_name, mc.check_type,
    mc.scheduled_date, mc.completed_date, mc.status, mc.technician, mc.notes
FROM MaintenanceCheck mc
JOIN Machine m ON m.machine_id = mc.machine_id
WHERE mc.status IN ('scheduled', 'in_progress', 'overdue')
ORDER BY
    CASE mc.status WHEN 'overdue' THEN 0 WHEN 'in_progress' THEN 1 ELSE 2 END,
    mc.scheduled_date ASC;
"""


def get_connection():
    return mysql.connector.connect(**DB_CONFIG)


@app.route("/api/oee")
def get_oee():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(OEE_QUERY)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    # mysql-connector returns DECIMAL/ROUND() results as Decimal objects, which
    # Flask's jsonify serializes as JSON *strings* (e.g. "0.983") rather than
    # numbers. That breaks any JS arithmetic done on them (string concatenation
    # instead of addition), so convert explicitly to float here.
    for row in rows:
        for key in ("availability", "performance", "quality", "oee"):
            if row.get(key) is not None:
                row[key] = float(row[key])
    return jsonify(rows)


@app.route("/api/status")
def get_status():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(LATEST_STATUS_QUERY)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(rows)


@app.route("/api/sensors")
def get_sensors():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(LATEST_SENSORS_QUERY)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(rows)


@app.route("/api/maintenance")
def get_maintenance():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(MAINTENANCE_QUERY)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    # dates come back as date objects; convert to strings for JSON
    for row in rows:
        if row.get("scheduled_date"):
            row["scheduled_date"] = str(row["scheduled_date"])
        if row.get("completed_date"):
            row["completed_date"] = str(row["completed_date"])
    return jsonify(rows)


@app.route("/")
def health_check():
    return jsonify({"status": "ok", "message": "Smart Manufacturing OT API is running"})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
