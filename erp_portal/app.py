
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
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                wo.work_order_id,
                wo.priority,
                wo.status,
                wo.instructions,
                wo.assigned_at,
                wo.due_at,
                wo.started_at,
                f.fault_id,
                f.severity,
                f.summary,
                f.confidence,
                f.est_ttf_hrs,
                m.name AS machine_name,
                m.machine_type,
                m.criticality,
                pl.name AS production_line,
                ft.name AS fault_name,
                ft.fault_code
            FROM technicians t
            JOIN work_orders wo
                ON wo.assigned_to = t.technician_id
            JOIN faults f
                ON f.fault_id = wo.fault_id
            JOIN machines m
                ON m.machine_id = f.machine_id
            JOIN production_lines pl
                ON pl.line_id = m.line_id
            JOIN fault_types ft
                ON ft.fault_type_id = f.fault_type_id
            WHERE t.user_id = %s
            ORDER BY
                CASE wo.status
                    WHEN 'ASSIGNED' THEN 1
                    WHEN 'IN_PROGRESS' THEN 2
                    WHEN 'REWORK' THEN 3
                    WHEN 'SUBMITTED' THEN 4
                    ELSE 5
                END,
                wo.assigned_at DESC,
                wo.work_order_id DESC
        """, (session["user_id"],))

        work_orders = cursor.fetchall()

        return render_template(
            "technician.html",
            username=session["username"],
            work_orders=work_orders,
        )

    except mysql.connector.Error:
        app.logger.exception(
            "Failed to load work orders for technician %s",
            session.get("username"),
        )
        return (
            "Unable to load your work orders. "
            "Check the Flask terminal for details.",
            500,
        )

    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


def get_technician_recommendations(fault_id):
    connection = get_db_connection()
    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                t.technician_id,
                u.username,
                t.availability,
                t.max_active_orders,
                COALESCE(orders.active_orders, 0) AS active_orders,
                AVG(ts.proficiency) AS avg_proficiency
            FROM faults f
            JOIN fault_type_skills fts
                ON fts.fault_type_id = f.fault_type_id
            JOIN technician_skills ts
                ON ts.skill_id = fts.skill_id
               AND ts.proficiency >= fts.min_proficiency
            JOIN technicians t
                ON t.technician_id = ts.technician_id
            JOIN users u
                ON u.id = t.user_id
            LEFT JOIN (
                SELECT
                    assigned_to,
                    COUNT(*) AS active_orders
                FROM work_orders
                WHERE status IN ('ASSIGNED', 'IN_PROGRESS', 'REWORK')
                GROUP BY assigned_to
            ) orders
                ON orders.assigned_to = t.technician_id
            WHERE f.fault_id = %s
              AND u.role = 'technician'
              AND t.availability = 'AVAILABLE'
            GROUP BY
                t.technician_id,
                u.username,
                t.availability,
                t.max_active_orders,
                orders.active_orders
            HAVING COUNT(DISTINCT fts.skill_id) = (
                SELECT COUNT(*)
                FROM fault_type_skills required_skills
                JOIN faults target_fault
                    ON target_fault.fault_type_id = required_skills.fault_type_id
                WHERE target_fault.fault_id = %s
            )
            AND COALESCE(orders.active_orders, 0) < t.max_active_orders
            ORDER BY
                active_orders ASC,
                avg_proficiency DESC,
                u.username ASC
        """, (fault_id, fault_id))

        return cursor.fetchall()

    finally:
        if cursor is not None:
            cursor.close()
        connection.close()

@app.route("/faults/<int:fault_id>/assign", methods=["POST"])
@role_required("maintenance_head")
def assign_technician(fault_id):
    technician_id = request.form.get("technician_id", type=int)

    if not technician_id:
        flash("Please select a valid technician.")
        return redirect(url_for("fault_detail", fault_id=fault_id))

    connection = get_db_connection()
    cursor = None

    try:
        connection.start_transaction()
        cursor = connection.cursor(dictionary=True)

        # Lock the fault row to serialize assignments for this fault.
        cursor.execute("""
            SELECT fault_id, fault_type_id, severity, status
            FROM faults
            WHERE fault_id = %s
            FOR UPDATE
        """, (fault_id,))
        fault = cursor.fetchone()

        if fault is None:
            connection.rollback()
            flash("Fault not found.")
            return redirect(url_for("maintenance_head") + "#faults")

        if fault["status"] != "OPEN":
            connection.rollback()
            flash("This fault is no longer open for assignment.")
            return redirect(url_for("fault_detail", fault_id=fault_id))

        # Protect against duplicate active work orders.
        cursor.execute("""
            SELECT work_order_id
            FROM work_orders
            WHERE fault_id = %s
              AND status IN (
                  'ASSIGNED', 'IN_PROGRESS', 'SUBMITTED', 'REWORK'
              )
            LIMIT 1
            FOR UPDATE
        """, (fault_id,))

        if cursor.fetchone():
            connection.rollback()
            flash("An active work order already exists for this fault.")
            return redirect(url_for("fault_detail", fault_id=fault_id))

        # Lock and validate the selected technician.
        cursor.execute("""
            SELECT
                t.technician_id,
                t.availability,
                t.max_active_orders,
                u.username
            FROM technicians t
            JOIN users u ON u.id = t.user_id
            WHERE t.technician_id = %s
              AND u.role = 'technician'
            FOR UPDATE
        """, (technician_id,))
        technician = cursor.fetchone()

        if technician is None:
            connection.rollback()
            flash("The selected technician does not exist.")
            return redirect(url_for("fault_detail", fault_id=fault_id))

        if technician["availability"] != "AVAILABLE":
            connection.rollback()
            flash("This technician is not currently available.")
            return redirect(url_for("fault_detail", fault_id=fault_id))

        # Verify that the technician meets every required skill.
        cursor.execute("""
            SELECT
                COUNT(DISTINCT fts.skill_id) AS required_skills,
                COUNT(DISTINCT CASE
                    WHEN ts.proficiency >= fts.min_proficiency
                    THEN fts.skill_id
                END) AS matched_skills
            FROM fault_type_skills fts
            LEFT JOIN technician_skills ts
              ON ts.skill_id = fts.skill_id
             AND ts.technician_id = %s
            WHERE fts.fault_type_id = %s
        """, (technician_id, fault["fault_type_id"]))
        skills = cursor.fetchone()

        if skills["required_skills"] != skills["matched_skills"]:
            connection.rollback()
            flash("The technician does not meet all required skill levels.")
            return redirect(url_for("fault_detail", fault_id=fault_id))

        # Count all active orders, including submitted reports awaiting review.
        cursor.execute("""
            SELECT COUNT(*) AS active_orders
            FROM work_orders
            WHERE assigned_to = %s
              AND status IN (
                  'ASSIGNED', 'IN_PROGRESS', 'SUBMITTED', 'REWORK'
              )
        """, (technician_id,))
        workload = cursor.fetchone()["active_orders"]

        if workload >= technician["max_active_orders"]:
            connection.rollback()
            flash("The technician has reached their active-work-order limit.")
            return redirect(url_for("fault_detail", fault_id=fault_id))

        # Determine the current top recommendation for audit metadata.
        # The recommendation query uses its own connection.
        recommendations = get_technician_recommendations(fault_id)
        suggested_id = (
            recommendations[0]["technician_id"]
            if recommendations else None
        )

        is_top_recommendation = (
            suggested_id is not None
            and suggested_id == technician_id
        )

        assignment_method = (
            "SYSTEM_SUGGESTED"
            if is_top_recommendation
            else "MANUAL_OVERRIDE"
        )

        override_reason = (
            None if is_top_recommendation
            else "Maintenance Head selected a different qualified technician."
        )

        priority_map = {
            "CRITICAL": "URGENT",
            "HIGH": "HIGH",
            "MEDIUM": "MEDIUM",
            "LOW": "LOW",
        }
        priority = priority_map.get(fault["severity"], "MEDIUM")

        cursor.execute("""
            SELECT recommended_action
            FROM fault_types
            WHERE fault_type_id = %s
        """, (fault["fault_type_id"],))
        fault_type = cursor.fetchone()

        cursor.execute("""
            INSERT INTO work_orders (
                fault_id,
                assigned_to,
                assigned_by,
                suggested_technician_id,
                assignment_method,
                override_reason,
                priority,
                status,
                instructions
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'ASSIGNED', %s)
        """, (
            fault_id,
            technician_id,
            session["user_id"],
            suggested_id,
            assignment_method,
            override_reason,
            priority,
            fault_type["recommended_action"] if fault_type else None,
        ))

        work_order_id = cursor.lastrowid

        cursor.execute("""
            UPDATE faults
            SET status = 'ASSIGNED'
            WHERE fault_id = %s
              AND status = 'OPEN'
        """, (fault_id,))

        if cursor.rowcount != 1:
            raise RuntimeError("Fault status changed during assignment.")

        connection.commit()
        flash(
            f"Work order #{work_order_id} assigned to "
            f"{technician['username']}."
        )

    except (mysql.connector.Error, RuntimeError):
        connection.rollback()
        app.logger.exception("Failed to assign fault %s", fault_id)
        flash("Assignment failed. Check the Flask terminal for details.")

    finally:
        if cursor is not None:
            cursor.close()
        connection.close()

    return redirect(url_for("fault_detail", fault_id=fault_id))

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

        recommendations = get_technician_recommendations(fault_id)

        return render_template(
            "fault_detail.html",
            fault=fault,
            evidence=evidence,
            recommendations=recommendations
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
