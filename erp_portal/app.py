
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
                 WHERE review_status = 'PENDING_REVIEW') AS reports_to_review
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
                u.username AS technician_username,

                (
                    SELECT wr.report_id
                    FROM work_order_reports wr
                    WHERE wr.work_order_id = wo.work_order_id
                    ORDER BY wr.submitted_at DESC, wr.report_id DESC
                    LIMIT 1
                ) AS report_id

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


        # Repair reports awaiting Maintenance Head review
        cursor.execute("""
            SELECT
                wr.report_id,
                wr.work_order_id,
                wr.findings,
                wr.action_taken,
                wr.parts_used,
                wr.time_spent_mins,
                wr.submitted_at,
                wo.priority,
                wo.status AS work_order_status,
                f.fault_id,
                f.severity,
                m.name AS machine_name,
                pl.name AS production_line,
                ft.name AS fault_name,
                u.username AS technician_username
            FROM work_order_reports wr
            JOIN work_orders wo
                ON wo.work_order_id = wr.work_order_id
            JOIN faults f
                ON f.fault_id = wo.fault_id
            JOIN machines m
                ON m.machine_id = f.machine_id
            JOIN production_lines pl
                ON pl.line_id = m.line_id
            JOIN fault_types ft
                ON ft.fault_type_id = f.fault_type_id
            JOIN technicians t
                ON t.technician_id = wo.assigned_to
            JOIN users u
                ON u.id = t.user_id
            WHERE wr.review_status = 'PENDING_REVIEW'
            ORDER BY wr.submitted_at ASC, wr.report_id ASC
        """)
        pending_reports = cursor.fetchall()


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

        return summary, recent_work_orders, faults, pending_reports

    finally:
        if cursor is not None:
            cursor.close()
        connection.close()

def get_technician_directory():
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

                COUNT(DISTINCT CASE
                    WHEN wo.status IN ('ASSIGNED', 'IN_PROGRESS', 'REWORK')
                    THEN wo.work_order_id
                END) AS active_orders,

                COUNT(DISTINCT CASE
                    WHEN wo.status = 'COMPLETED'
                    THEN wo.work_order_id
                END) AS completed_orders

            FROM technicians t
            JOIN users u ON u.id = t.user_id

            LEFT JOIN work_orders wo
                ON wo.assigned_to = t.technician_id

            WHERE u.role = 'technician'

            GROUP BY
                t.technician_id,
                u.username,
                t.availability,
                t.max_active_orders

            ORDER BY u.username
        """)

        technicians = cursor.fetchall()

        # Retrieve skills for the technicians in the directory.
        cursor.execute("""
            SELECT
                ts.technician_id,
                s.name AS skill_name,
                ts.proficiency
            FROM technician_skills ts
            JOIN skills s ON s.skill_id = ts.skill_id
            JOIN technicians t
                ON t.technician_id = ts.technician_id
            JOIN users u ON u.id = t.user_id
            WHERE u.role = 'technician'
            ORDER BY s.name
        """)

        skill_rows = cursor.fetchall()

        skills_by_technician = {}

        for row in skill_rows:
            technician_id = row["technician_id"]

            skills_by_technician.setdefault(
                technician_id, []
            ).append({
                "name": row["skill_name"],
                "proficiency": row["proficiency"]
            })

        for technician in technicians:
            technician["skills"] = skills_by_technician.get(
                technician["technician_id"], []
            )

        return technicians

    finally:
        if cursor is not None:
            cursor.close()

        connection.close()

@app.route("/maintenance-head")
@role_required("maintenance_head")
def maintenance_head():
    try:
        summary, recent_work_orders, faults, pending_reports = get_maintenance_overview()

        technicians = get_technician_directory()

        return render_template(
            "maintenance_head.html",
            username=session["username"],
            summary=summary,
            recent_work_orders=recent_work_orders,
            faults=faults,
            pending_reports=pending_reports,
            technicians=technicians,
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

                    (
                        SELECT wa.activity_type
                        FROM work_order_activity wa
                        WHERE wa.work_order_id = wo.work_order_id
                        ORDER BY wa.activity_id DESC
                        LIMIT 1
                    ) AS latest_activity,

                    (
                        SELECT wa.recorded_at
                        FROM work_order_activity wa
                        WHERE wa.work_order_id = wo.work_order_id
                        ORDER BY wa.activity_id DESC
                        LIMIT 1
                    ) AS latest_activity_at,

                    (
                        SELECT wr.review_comment
                        FROM work_order_reports wr
                        WHERE wr.work_order_id = wo.work_order_id
                          AND wr.review_status = 'REJECTED'
                        ORDER BY wr.reviewed_at DESC, wr.report_id DESC
                        LIMIT 1
                    ) AS latest_rejection_comment,

                    (
                        SELECT wr.report_id
                        FROM work_order_reports wr
                        WHERE wr.work_order_id = wo.work_order_id
                          AND wr.review_status = 'REJECTED'
                        ORDER BY wr.reviewed_at DESC, wr.report_id DESC
                        LIMIT 1
                    ) AS latest_rejected_report_id,

                    (
                        SELECT wr.report_id
                        FROM work_order_reports wr
                        WHERE wr.work_order_id = wo.work_order_id
                        ORDER BY wr.submitted_at DESC, wr.report_id DESC
                        LIMIT 1
                    ) AS latest_report_id,

                    (
                        SELECT COUNT(*)
                        FROM work_order_reports wr
                        WHERE wr.work_order_id = wo.work_order_id
                          AND wr.review_status = 'REJECTED'
                    ) AS rejected_report_count,

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

@app.route("/work-orders/<int:work_order_id>/start", methods=["POST"])
@role_required("technician")
def start_work(work_order_id):
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        connection.start_transaction()
        cursor = connection.cursor(dictionary=True)

        # Lock the work order while checking and updating its status.
        cursor.execute("""
            SELECT
                wo.work_order_id,
                wo.status,
                t.technician_id
            FROM work_orders wo
            JOIN technicians t
                ON t.technician_id = wo.assigned_to
            WHERE wo.work_order_id = %s
              AND t.user_id = %s
            FOR UPDATE
        """, (work_order_id, session["user_id"]))

        work_order = cursor.fetchone()

        if work_order is None:
            connection.rollback()
            flash("Work order not found or not assigned to you.")
            return redirect(url_for("technician"))

        if work_order["status"] not in ("ASSIGNED", "REWORK"):
            connection.rollback()
            flash("Only assigned work orders or work orders requiring rework can be started.")
            return redirect(url_for("technician"))

        previous_status = work_order["status"]

        # Rework returns the existing work order to IN_PROGRESS. Previous
        # rejected reports are retained; submitting again creates a new report.
        cursor.execute("""
            UPDATE work_orders
            SET status = 'IN_PROGRESS',
                started_at = CURRENT_TIMESTAMP
            WHERE work_order_id = %s
              AND status = %s
        """, (work_order_id, previous_status))

        if cursor.rowcount != 1:
            connection.rollback()
            flash("The work order could not be started. Please refresh and try again.")
            return redirect(url_for("technician"))

        # Record the event in the activity history.
        cursor.execute("""
            INSERT INTO work_order_activity (
                work_order_id,
                activity_type,
                reason,
                recorded_by
            )
            VALUES (%s, 'STARTED', %s, %s)
        """, (
            work_order_id,
            "Technician started rework after report rejection."
            if previous_status == "REWORK" else None,
            session["user_id"],
        ))

        connection.commit()

        flash(
            f"Work order #{work_order_id} rework started successfully."
            if previous_status == "REWORK"
            else f"Work order #{work_order_id} started successfully."
        )

    except mysql.connector.Error:
        if connection is not None and connection.is_connected():
            connection.rollback()

        app.logger.exception(
            "Failed to start work order %s for technician %s",
            work_order_id,
            session.get("username"),
        )
        flash("Unable to start the work order due to a database error.")

    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()

    return redirect(url_for("technician"))

@app.route("/work-orders/<int:work_order_id>/pause", methods=["POST"])
@role_required("technician")
def pause_work(work_order_id):
    reason = request.form.get("reason", "").strip()

    if not reason:
        flash("Please provide a reason for pausing the work.")
        return redirect(url_for("technician"))

    if len(reason) > 255:
        flash("The pause reason must be 255 characters or fewer.")
        return redirect(url_for("technician"))

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        connection.start_transaction()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT wo.status
            FROM work_orders wo
            JOIN technicians t
                ON t.technician_id = wo.assigned_to
            WHERE wo.work_order_id = %s
              AND t.user_id = %s
            FOR UPDATE
        """, (work_order_id, session["user_id"]))

        work_order = cursor.fetchone()

        if work_order is None:
            connection.rollback()
            flash("Work order not found or not assigned to you.")
            return redirect(url_for("technician"))

        if work_order["status"] != "IN_PROGRESS":
            connection.rollback()
            flash("Only work orders in progress can be paused.")
            return redirect(url_for("technician"))

        cursor.execute("""
            SELECT activity_type
            FROM work_order_activity
            WHERE work_order_id = %s
            ORDER BY activity_id DESC
            LIMIT 1
        """, (work_order_id,))

        latest_activity = cursor.fetchone()

        if (
            latest_activity is None
            or latest_activity["activity_type"] == "PAUSED"
            or latest_activity["activity_type"] in (
                "REPORT_SUBMITTED",
                "REPORT_APPROVED",
                "REPORT_REJECTED",
                "COMPLETED",
            )
        ):
            connection.rollback()
            flash("This work order cannot be paused in its current state.")
            return redirect(url_for("technician"))

        cursor.execute("""
            INSERT INTO work_order_activity (
                work_order_id,
                activity_type,
                reason,
                recorded_by
            )
            VALUES (%s, 'PAUSED', %s, %s)
        """, (work_order_id, reason, session["user_id"]))

        connection.commit()
        flash(f"Work order #{work_order_id} paused.")

    except mysql.connector.Error:
        if connection is not None and connection.is_connected():
            connection.rollback()

        app.logger.exception(
            "Failed to pause work order %s for technician %s",
            work_order_id,
            session.get("username"),
        )
        flash("Unable to pause the work order due to a database error.")

    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()

    return redirect(url_for("technician"))

@app.route("/work-orders/<int:work_order_id>/resume", methods=["POST"])
@role_required("technician")
def resume_work(work_order_id):
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        connection.start_transaction()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT wo.status
            FROM work_orders wo
            JOIN technicians t
                ON t.technician_id = wo.assigned_to
            WHERE wo.work_order_id = %s
              AND t.user_id = %s
            FOR UPDATE
        """, (work_order_id, session["user_id"]))

        work_order = cursor.fetchone()

        if work_order is None:
            connection.rollback()
            flash("Work order not found or not assigned to you.")
            return redirect(url_for("technician"))

        if work_order["status"] != "IN_PROGRESS":
            connection.rollback()
            flash("Only work orders in progress can be resumed.")
            return redirect(url_for("technician"))

        cursor.execute("""
            SELECT activity_type
            FROM work_order_activity
            WHERE work_order_id = %s
            ORDER BY activity_id DESC
            LIMIT 1
        """, (work_order_id,))

        latest_activity = cursor.fetchone()

        if (
            latest_activity is None
            or latest_activity["activity_type"] != "PAUSED"
        ):
            connection.rollback()
            flash("This work order is not currently paused.")
            return redirect(url_for("technician"))

        cursor.execute("""
            INSERT INTO work_order_activity (
                work_order_id,
                activity_type,
                recorded_by
            )
            VALUES (%s, 'RESUMED', %s)
        """, (work_order_id, session["user_id"]))

        connection.commit()
        flash(f"Work order #{work_order_id} resumed.")

    except mysql.connector.Error:
        if connection is not None and connection.is_connected():
            connection.rollback()

        app.logger.exception(
            "Failed to resume work order %s for technician %s",
            work_order_id,
            session.get("username"),
        )
        flash("Unable to resume the work order due to a database error.")

    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()

    return redirect(url_for("technician"))

@app.route("/work-orders/<int:work_order_id>/submit-report", methods=["POST"])
@role_required("technician")
def submit_repair_report(work_order_id):
    findings = request.form.get("findings", "").strip()
    action_taken = request.form.get("action_taken", "").strip()
    parts_used = request.form.get("parts_used", "").strip()
    time_spent_raw = request.form.get("time_spent_mins", "").strip()

    # Validate required fields.
    if not findings or not action_taken:
        flash("Findings and action taken are required.")
        return redirect(url_for("technician"))

    # Validate the optional time-spent field.
    time_spent_mins = None

    if time_spent_raw:
        try:
            time_spent_mins = int(time_spent_raw)
        except ValueError:
            flash("Time spent must be a whole number of minutes.")
            return redirect(url_for("technician"))

        if time_spent_mins <= 0:
            flash("Time spent must be greater than zero.")
            return redirect(url_for("technician"))

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        connection.start_transaction()
        cursor = connection.cursor(dictionary=True)

        # Verify ownership and lock the work order.
        cursor.execute("""
            SELECT
                wo.work_order_id,
                wo.status
            FROM work_orders wo
            JOIN technicians t
                ON t.technician_id = wo.assigned_to
            WHERE wo.work_order_id = %s
              AND t.user_id = %s
            FOR UPDATE
        """, (work_order_id, session["user_id"]))

        work_order = cursor.fetchone()

        if work_order is None:
            connection.rollback()
            flash("Work order not found or not assigned to you.")
            return redirect(url_for("technician"))

        if work_order["status"] != "IN_PROGRESS":
            connection.rollback()
            flash("Only work orders in progress can be submitted.")
            return redirect(url_for("technician"))

        # A paused work order cannot be submitted.
        cursor.execute("""
            SELECT activity_type
            FROM work_order_activity
            WHERE work_order_id = %s
            ORDER BY activity_id DESC
            LIMIT 1
        """, (work_order_id,))

        latest_activity = cursor.fetchone()

        if (
            latest_activity is None
            or latest_activity["activity_type"] not in (
                "STARTED",
                "RESUMED",
            )
        ):
            connection.rollback()
            flash(
                "Resume the work order before submitting its repair report."
            )
            return redirect(url_for("technician"))

        # Create the report. review_status defaults to PENDING.
        cursor.execute("""
            INSERT INTO work_order_reports (
                work_order_id,
                findings,
                action_taken,
                parts_used,
                time_spent_mins
            )
            VALUES (%s, %s, %s, %s, %s)
        """, (
            work_order_id,
            findings,
            action_taken,
            parts_used or None,
            time_spent_mins,
        ))

        # Move the work order into the review queue.
        cursor.execute("""
            UPDATE work_orders
            SET status = 'SUBMITTED',
                completed_at = NULL
            WHERE work_order_id = %s
              AND status = 'IN_PROGRESS'
        """, (work_order_id,))

        if cursor.rowcount != 1:
            connection.rollback()
            flash(
                "The work order could not be submitted. Please refresh and try again."
            )
            return redirect(url_for("technician"))

        # Record the submission in the activity history.
        cursor.execute("""
            INSERT INTO work_order_activity (
                work_order_id,
                activity_type,
                recorded_by
            )
            VALUES (%s, 'REPORT_SUBMITTED', %s)
        """, (work_order_id, session["user_id"]))

        connection.commit()

        flash(
            f"Repair report for work order #{work_order_id} "
            "submitted successfully."
        )

    except mysql.connector.Error:
        if connection is not None and connection.is_connected():
            connection.rollback()

        app.logger.exception(
            "Failed to submit repair report for work order %s "
            "by technician %s",
            work_order_id,
            session.get("username"),
        )

        flash("Unable to submit the repair report due to a database error.")

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None:
            connection.close()

    return redirect(url_for("technician"))

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

    confirm_override = request.form.get("confirm_override") == "1"
    submitted_override_reason = (
        request.form.get("override_reason") or ""
    ).strip()

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

        skill_mismatch = (
            skills["required_skills"] != skills["matched_skills"]
        )

        if skill_mismatch and not confirm_override:
            connection.rollback()
            flash(
                "This technician does not meet all required skill levels. "
                "Use Manual Technician Assignment to confirm an override."
            )
            return redirect(url_for("fault_detail", fault_id=fault_id))

        if confirm_override and not submitted_override_reason:
            connection.rollback()
            flash("An override reason is required.")
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

        workload_exceeded = (
            workload >= technician["max_active_orders"]
        )

        if workload_exceeded and not confirm_override:
            connection.rollback()
            flash(
                "This technician has reached their active-work-order limit. "
                "Use Manual Technician Assignment to confirm an override."
            )
            return redirect(url_for("fault_detail", fault_id=fault_id))

        # Determine the current top recommendation for audit metadata.
        # The recommendation query uses its own connection.
        recommendations = get_technician_recommendations(fault_id)

        cursor.execute("""
            SELECT
                t.technician_id,
                u.username,
                t.availability,
                t.max_active_orders,
                (
                    SELECT COUNT(*)
                    FROM work_orders wo
                    WHERE wo.assigned_to = t.technician_id
                      AND wo.status IN (
                          'ASSIGNED', 'IN_PROGRESS', 'SUBMITTED', 'REWORK'
                      )
                ) AS active_orders
            FROM technicians t
            JOIN users u ON u.id = t.user_id
            WHERE u.role = 'technician'
            ORDER BY u.username
        """)

        all_technicians = cursor.fetchall()

        suggested_id = (
            recommendations[0]["technician_id"]
            if recommendations else None
        )

        is_top_recommendation = (
            suggested_id is not None
            and suggested_id == technician_id
        )

        manual_override_used = (
            confirm_override
            or not is_top_recommendation
        )

        assignment_method = (
            "MANUAL_OVERRIDE"
            if manual_override_used
            else "SYSTEM_SUGGESTED"
        )

        if confirm_override:
            override_reason = submitted_override_reason
        elif not is_top_recommendation:
            override_reason = (
                "Maintenance Head selected a different qualified technician."
            )
        else:
            override_reason = None

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


@app.route(
    "/work-orders/<int:work_order_id>/reports/<int:report_id>"
)
def work_order_report_detail(work_order_id, report_id):
    if session.get("role") not in ("maintenance_head", "technician"):
        return redirect(url_for("login"))

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                wr.report_id,
                wr.work_order_id,
                wr.findings,
                wr.action_taken,
                wr.parts_used,
                wr.time_spent_mins,
                wr.submitted_at,
                wr.review_status,
                wr.review_comment,
                wr.reviewed_at,

                wo.status AS work_order_status,
                wo.priority,
                wo.instructions,
                wo.assigned_at,

                f.fault_id,
                f.severity,
                f.summary AS fault_summary,

                m.name AS machine_name,
                m.machine_type,
                m.criticality,

                pl.name AS production_line,

                ft.name AS fault_name,
                ft.fault_code,

                u.username AS technician_username,
                t.user_id AS technician_user_id

            FROM work_order_reports wr

            JOIN work_orders wo
                ON wo.work_order_id = wr.work_order_id

            JOIN faults f
                ON f.fault_id = wo.fault_id

            JOIN machines m
                ON m.machine_id = f.machine_id

            JOIN production_lines pl
                ON pl.line_id = m.line_id

            JOIN fault_types ft
                ON ft.fault_type_id = f.fault_type_id

            JOIN technicians t
                ON t.technician_id = wo.assigned_to

            JOIN users u
                ON u.id = t.user_id

            WHERE wr.report_id = %s
              AND wr.work_order_id = %s

        """, (report_id, work_order_id))

        report = cursor.fetchone()

        if report is None:
            flash("The requested repair report was not found.")
            destination = (
                url_for("technician")
                if session.get("role") == "technician"
                else url_for("maintenance_head") + "#work-orders"
            )
            return redirect(destination)

        if (
            session.get("role") == "technician"
            and report["technician_user_id"] != session.get("user_id")
        ):
            flash("You can only view reports for your assigned work orders.")
            return redirect(url_for("technician"))

        # Show the complete report history for this work order to both roles.
        cursor.execute("""
            SELECT
                wr.report_id,
                wr.review_status,
                wr.submitted_at,
                wr.reviewed_at,
                wr.review_comment,
                (
                    SELECT COUNT(*)
                    FROM work_order_reports earlier_wr
                    JOIN work_orders earlier_wo
                        ON earlier_wo.work_order_id = earlier_wr.work_order_id
                    WHERE earlier_wo.assigned_to = wo.assigned_to
                      AND (
                            earlier_wr.submitted_at < wr.submitted_at
                            OR (
                                earlier_wr.submitted_at = wr.submitted_at
                                AND earlier_wr.report_id <= wr.report_id
                            )
                      )
                ) AS technician_report_number
            FROM work_order_reports wr
            JOIN work_orders wo
                ON wo.work_order_id = wr.work_order_id
            WHERE wr.work_order_id = %s
            ORDER BY wr.submitted_at DESC, wr.report_id DESC
        """, (work_order_id,))
        report_history = cursor.fetchall()

        return render_template(
            "work_order_report_detail.html",
            report=report,
            report_history=report_history,
            viewer_role=session.get("role"),
            can_review=(session.get("role") == "maintenance_head")
        )

    except mysql.connector.Error:
        app.logger.exception(
            "Failed to load report %s for work order %s",
            report_id,
            work_order_id
        )

        return (
            "Unable to load repair report details. "
            "Check the Flask terminal for details.",
            500
        )

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None:
            connection.close()

@app.route("/technicians/<int:technician_id>")
@role_required("maintenance_head")
def technician_detail(technician_id):
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Technician profile and workload.
        cursor.execute("""
            SELECT
                t.technician_id,
                u.username,
                t.availability,
                t.max_active_orders,

                (
                    SELECT COUNT(*)
                    FROM work_orders wo
                    WHERE wo.assigned_to = t.technician_id
                      AND wo.status IN (
                          'ASSIGNED', 'IN_PROGRESS', 'REWORK'
                      )
                ) AS active_orders,

                (
                    SELECT COUNT(*)
                    FROM work_orders wo
                    WHERE wo.assigned_to = t.technician_id
                      AND wo.status = 'COMPLETED'
                ) AS completed_orders

            FROM technicians t
            JOIN users u ON u.id = t.user_id

            WHERE t.technician_id = %s
              AND u.role = 'technician'
        """, (technician_id,))

        technician = cursor.fetchone()

        if technician is None:
            return "Technician not found.", 404

        # Technician skills.
        cursor.execute("""
            SELECT
                s.name AS skill_name,
                ts.proficiency
            FROM technician_skills ts
            JOIN skills s ON s.skill_id = ts.skill_id
            WHERE ts.technician_id = %s
            ORDER BY s.name
        """, (technician_id,))

        skills = cursor.fetchall()

        # Work-order history.
        cursor.execute("""
            SELECT
                wo.work_order_id,
                wo.priority,
                wo.status,
                wo.assigned_at,
                wo.completed_at,
                m.name AS machine_name,
                ft.name AS fault_name,
                f.severity
            FROM work_orders wo
            JOIN faults f ON f.fault_id = wo.fault_id
            JOIN machines m ON m.machine_id = f.machine_id
            JOIN fault_types ft
                ON ft.fault_type_id = f.fault_type_id
            WHERE wo.assigned_to = %s
            ORDER BY wo.assigned_at DESC, wo.work_order_id DESC
        """, (technician_id,))

        work_orders = cursor.fetchall()

        return render_template(
            "technician_detail.html",
            username=session["username"],
            technician=technician,
            skills=skills,
            work_orders=work_orders
        )

    except mysql.connector.Error:
        app.logger.exception(
            "Failed to load technician details for ID %s",
            technician_id
        )

        return (
            "Unable to load technician details. "
            "Check the Flask terminal for details.",
            500
        )

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None:
            connection.close()

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

        cursor.execute("""
            SELECT
                t.technician_id,
                u.username,
                t.availability,
                t.max_active_orders,
                (
                    SELECT COUNT(*)
                    FROM work_orders wo
                    WHERE wo.assigned_to = t.technician_id
                      AND wo.status IN (
                          'ASSIGNED', 'IN_PROGRESS', 'SUBMITTED', 'REWORK'
                      )
                ) AS active_orders
            FROM technicians t
            JOIN users u ON u.id = t.user_id
            WHERE u.role = 'technician'
            ORDER BY u.username
        """)

        all_technicians = cursor.fetchall()

        return render_template(
            "fault_detail.html",
            fault=fault,
            evidence=evidence,
            recommendations=recommendations,
            all_technicians=all_technicians
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

@app.route(
    "/work-orders/<int:work_order_id>/reports/<int:report_id>/review",
    methods=["POST"]
)
@role_required("maintenance_head")
def review_repair_report(work_order_id, report_id):
    decision = request.form.get("decision", "").strip().lower()
    review_comment = request.form.get("review_comment", "").strip()

    if decision not in ("approve", "reject"):
        flash("Invalid review decision.")
        return redirect(url_for(
            "work_order_report_detail",
            work_order_id=work_order_id,
            report_id=report_id
        ))

    if decision == "reject" and not review_comment:
        flash("A review comment is required when rejecting a report.")
        return redirect(url_for(
            "work_order_report_detail",
            work_order_id=work_order_id,
            report_id=report_id
        ))

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        connection.start_transaction()
        cursor = connection.cursor(dictionary=True)

        # Lock the work order and report to prevent conflicting reviews.
        cursor.execute("""
            SELECT
                wo.work_order_id,
                wo.fault_id,
                wo.status AS work_order_status,
                wr.report_id,
                wr.review_status
            FROM work_orders wo
            JOIN work_order_reports wr
                ON wr.work_order_id = wo.work_order_id
            WHERE wo.work_order_id = %s
              AND wr.report_id = %s
            FOR UPDATE
        """, (work_order_id, report_id))

        record = cursor.fetchone()

        if record is None:
            connection.rollback()
            flash("Work order or repair report not found.")
            return redirect(url_for("maintenance_head"))

        if (
            record["review_status"] != "PENDING_REVIEW"
            or record["work_order_status"] != "SUBMITTED"
        ):
            connection.rollback()
            flash("This report has already been reviewed or is no longer awaiting review.")
            return redirect(url_for(
                "work_order_report_detail",
                work_order_id=work_order_id,
                report_id=report_id
            ))

        if decision == "approve":
            cursor.execute("""
                UPDATE work_order_reports
                SET review_status = 'APPROVED',
                    review_comment = %s,
                    reviewed_by = %s,
                    reviewed_at = CURRENT_TIMESTAMP
                WHERE report_id = %s
                  AND review_status = 'PENDING_REVIEW'
            """, (
                review_comment or None,
                session["user_id"],
                report_id
            ))

            cursor.execute("""
                UPDATE work_orders
                SET status = 'COMPLETED',
                    completed_at = CURRENT_TIMESTAMP
                WHERE work_order_id = %s
                  AND status = 'SUBMITTED'
            """, (work_order_id,))

            cursor.execute("""
                UPDATE faults
                SET status = 'RESOLVED',
                    resolved_at = CURRENT_TIMESTAMP
                WHERE fault_id = %s
            """, (record["fault_id"],))

            cursor.execute("""
                INSERT INTO work_order_activity
                    (work_order_id, activity_type, reason, recorded_by)
                VALUES (%s, 'REPORT_APPROVED', %s, %s)
            """, (
                work_order_id,
                review_comment or None,
                session["user_id"]
            ))

            flash(f"Report #{report_id} approved. Work order completed.")

        else:
            cursor.execute("""
                UPDATE work_order_reports
                SET review_status = 'REJECTED',
                    review_comment = %s,
                    reviewed_by = %s,
                    reviewed_at = CURRENT_TIMESTAMP
                WHERE report_id = %s
                  AND review_status = 'PENDING_REVIEW'
            """, (
                review_comment,
                session["user_id"],
                report_id
            ))

            cursor.execute("""
                UPDATE work_orders
                SET status = 'REWORK',
                    completed_at = NULL
                WHERE work_order_id = %s
                  AND status = 'SUBMITTED'
            """, (work_order_id,))

            cursor.execute("""
                INSERT INTO work_order_activity
                    (work_order_id, activity_type, reason, recorded_by)
                VALUES (%s, 'REPORT_REJECTED', %s, %s)
            """, (
                work_order_id,
                review_comment,
                session["user_id"]
            ))

            flash(f"Report #{report_id} rejected. The technician must rework the repair.")

        connection.commit()

    except mysql.connector.Error:
        if connection is not None and connection.is_connected():
            connection.rollback()

        app.logger.exception(
            "Failed to review report %s for work order %s",
            report_id,
            work_order_id
        )
        flash("Unable to review the report because of a database error.")

    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()

    return redirect(url_for(
        "work_order_report_detail",
        work_order_id=work_order_id,
        report_id=report_id
    ))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)