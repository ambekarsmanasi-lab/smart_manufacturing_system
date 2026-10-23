
import os
from functools import wraps

import mysql.connector
from dotenv import load_dotenv
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash
)
from werkzeug.security import check_password_hash

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ["SECRET_KEY"]


def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD"),
        database="smart_manufacturing_erp",
    )


def role_required(required_role):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))

            if session.get("role") != required_role:
                flash("You do not have permission to access that page.")
                return redirect(url_for("dashboard"))

            return view(*args, **kwargs)
        return wrapped
    return decorator


@app.route("/", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        connection = get_db_connection()
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT id, username, password_hash, role
                FROM users
                WHERE username = %s
                """,
                (username,),
            )
            user = cursor.fetchone()
        finally:
            cursor.close()
            connection.close()

        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            return redirect(url_for("dashboard"))

        flash("Invalid username or password.")

    return render_template("login.html")


@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if session["role"] == "maintenance_head":
        return redirect(url_for("maintenance_head"))

    if session["role"] == "technician":
        return redirect(url_for("technician"))

    session.clear()
    return redirect(url_for("login"))



def get_maintenance_overview():
    connection = get_db_connection()
    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)

        # Summary cards
        cursor.execute("""
            SELECT
                (SELECT COUNT(*)
                 FROM faults
                 WHERE status IN ('OPEN', 'ASSIGNED')) AS open_faults,

                (SELECT COUNT(*)
                 FROM faults
                 WHERE status = 'OPEN') AS pending_assignment,

                (SELECT COUNT(*)
                 FROM work_orders
                 WHERE status = 'IN_PROGRESS') AS in_progress,

                (SELECT COUNT(*)
                 FROM work_order_reports
                 WHERE review_status = 'PENDING') AS reports_to_review
        """)
        summary = cursor.fetchone()

        # Most recent work orders
        cursor.execute("""
            SELECT
                wo.work_order_id,
                wo.priority,
                wo.status,
                wo.assigned_at,
                m.name AS machine_name,
                ft.name AS fault_name,
                u.username AS technician_username
            FROM work_orders wo
            JOIN faults f ON f.fault_id = wo.fault_id
            JOIN machines m ON m.machine_id = f.machine_id
            JOIN fault_types ft ON ft.fault_type_id = f.fault_type_id
            JOIN technicians t ON t.technician_id = wo.assigned_to
            JOIN users u ON u.id = t.user_id
            ORDER BY wo.assigned_at DESC, wo.work_order_id DESC
            LIMIT 10
        """)
        recent_work_orders = cursor.fetchall()

        # Latest fault records
        cursor.execute("""
            SELECT
                f.fault_id,
                m.name AS machine_name,
                pl.name AS production_line,
                ft.name AS fault_name,
                ft.fault_code,
                ft.category,
                f.severity,
                f.confidence,
                f.summary,
                f.status,
                f.detected_at,
                f.last_seen_at,
                f.occurrence_count
            FROM faults f
            JOIN machines m ON m.machine_id = f.machine_id
            JOIN production_lines pl ON pl.line_id = m.line_id
            JOIN fault_types ft ON ft.fault_type_id = f.fault_type_id
            ORDER BY
                CASE f.severity
                    WHEN 'CRITICAL' THEN 1
                    WHEN 'HIGH' THEN 2
                    WHEN 'MEDIUM' THEN 3
                    WHEN 'LOW' THEN 4
                END,
                f.detected_at DESC
            LIMIT 100
        """)
        faults = cursor.fetchall()

        return summary, recent_work_orders, faults

    finally:
        if cursor is not None:
            cursor.close()
        connection.close()


@app.route("/maintenance-head")
@role_required("maintenance_head")
def maintenance_head():
    try:
        summary, recent_work_orders, faults = get_maintenance_overview()

        return render_template(
            "maintenance_head.html",
            username=session["username"],
            summary=summary,
            recent_work_orders=recent_work_orders,
            faults=faults,
        )

    except mysql.connector.Error:
        app.logger.exception(
            "Failed to load Maintenance Head dashboard"
        )
        return (
            "Unable to load maintenance data. "
            "Check the Flask terminal for details.",
            500,
        )



@app.route("/technician")
@role_required("technician")
def technician():
    return render_template(
        "technician.html",
        username=session["username"],
    )


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/faults/<int:fault_id>")
@role_required("maintenance_head")
def fault_detail(fault_id):
    connection = get_db_connection()
    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                f.fault_id,
                f.severity,
                f.confidence,
                f.summary,
                f.est_ttf_hrs,
                f.model_version,
                f.status,
                f.detected_at,
                f.last_seen_at,
                f.occurrence_count,
                f.resolved_at,
                m.machine_id,
                m.name AS machine_name,
                m.machine_type,
                m.criticality,
                pl.name AS production_line,
                ft.fault_code,
                ft.name AS fault_name,
                ft.category,
                ft.recommended_action
            FROM faults f
            JOIN machines m ON m.machine_id = f.machine_id
            JOIN production_lines pl ON pl.line_id = m.line_id
            JOIN fault_types ft ON ft.fault_type_id = f.fault_type_id
            WHERE f.fault_id = %s
        """, (fault_id,))

        fault = cursor.fetchone()

        if fault is None:
            return render_template(
                "fault_detail.html",
                fault=None,
                evidence=[]
            ), 404

        cursor.execute("""
            SELECT
                fe.sensor_id,
                s.sensor_type,
                fe.observed_value,
                fe.expected_value,
                COALESCE(fe.unit, s.unit) AS unit
            FROM fault_evidence fe
            JOIN sensors s ON s.sensor_id = fe.sensor_id
            WHERE fe.fault_id = %s
            ORDER BY fe.sensor_id
        """, (fault_id,))

        evidence = cursor.fetchall()

        return render_template(
            "fault_detail.html",
            fault=fault,
            evidence=evidence
        )

    except mysql.connector.Error:
        app.logger.exception(
            "Failed to load fault details for fault %s", fault_id
        )
        return (
            "Unable to load fault details. Check the Flask terminal.",
            500
        )

    finally:
        if cursor is not None:
            cursor.close()
        connection.close()



if __name__ == "__main__":
    app.run(debug=True)
