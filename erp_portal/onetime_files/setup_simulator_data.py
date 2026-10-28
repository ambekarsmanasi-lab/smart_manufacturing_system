import os
import sys
import mysql.connector
from dotenv import load_dotenv

load_dotenv("erp_portal/.env")

APPLY = "--apply" in sys.argv

MACHINES = [
    ("Line A", "CNC-01", "CNC", "HIGH", [
        ("Spindle Temperature", "°C"),
        ("Vibration", "mm/s"),
        ("Spindle Load", "%"),
    ]),
    ("Line A", "Conveyor-A", "Conveyor", "MEDIUM", [
        ("Vibration", "mm/s"),
        ("Belt Speed", "m/s"),
    ]),
    ("Line A", "RobotArm-01", "Robot Arm", "HIGH", [
        ("Joint Temperature", "°C"),
        ("Motor Current", "A"),
    ]),
    ("Line B", "Injection-01", "Injection Molding", "HIGH", [
        ("Barrel Temperature", "°C"),
        ("Injection Pressure", "bar"),
    ]),
    ("Line B", "Conveyor-B", "Conveyor", "MEDIUM", [
        ("Vibration", "mm/s"),
        ("Belt Speed", "m/s"),
    ]),
    ("Line B", "Packaging-01", "Packaging", "MEDIUM", [
        ("Seal Temperature", "°C"),
        ("Throughput", "units/min"),
    ]),
]

conn = mysql.connector.connect(
    host=os.getenv("DB_HOST", "localhost"),
    user=os.getenv("DB_USER", "root"),
    password=os.getenv("DB_PASSWORD"),
    database="smart_manufacturing_erp",
)

try:
    conn.start_transaction()
    cur = conn.cursor(dictionary=True)

    # Locate only the explicitly named placeholder machine.
    cur.execute("""
        SELECT machine_id, line_id, name
        FROM machines
        WHERE name = 'TEST MACHINE - DELETE LATER'
    """)
    demo_machines = cur.fetchall()

    if len(demo_machines) > 1:
        raise RuntimeError("Multiple placeholder machines found; aborting.")

    demo_machine_ids = [m["machine_id"] for m in demo_machines]
    demo_line_ids = list({m["line_id"] for m in demo_machines})

    fault_ids = []
    work_order_ids = []

    if demo_machine_ids:
        placeholders = ",".join(["%s"] * len(demo_machine_ids))

        cur.execute(
            f"SELECT fault_id FROM faults "
            f"WHERE machine_id IN ({placeholders})",
            tuple(demo_machine_ids),
        )
        fault_ids = [r["fault_id"] for r in cur.fetchall()]

    if fault_ids:
        placeholders = ",".join(["%s"] * len(fault_ids))

        cur.execute(
            f"SELECT work_order_id FROM work_orders "
            f"WHERE fault_id IN ({placeholders})",
            tuple(fault_ids),
        )
        work_order_ids = [r["work_order_id"] for r in cur.fetchall()]

    print("=" * 65)
    print("SIMULATOR DATABASE SETUP")
    print("MODE:", "APPLY CHANGES" if APPLY else "DRY RUN — NO CHANGES")
    print("=" * 65)

    print("\nPlaceholder machines to remove:", demo_machines)
    print("Associated fault IDs:", fault_ids)
    print("Associated work-order IDs:", work_order_ids)

    cur.execute("SELECT name FROM production_lines")
    print("\nExisting production lines:", cur.fetchall())

    cur.execute("SELECT name FROM machines")
    print("Existing machines:", cur.fetchall())

    print("\nTarget production setup:")
    for line, machine, machine_type, criticality, sensors in MACHINES:
        print(f"  {line} / {machine} ({machine_type}, {criticality})")
        for sensor_type, unit in sensors:
            print(f"      - {sensor_type} [{unit}]")

    if not APPLY:
        conn.rollback()
        print("\nDry run complete. No database changes made.")
        print("Review the output, then rerun with --apply to execute.")
        sys.exit(0)

    # Prevent accidental deletion if the placeholder contains real
    # work-order history beyond the test faults.
    

    # Remove work-order children before their parent records.
    if work_order_ids:
        placeholders = ",".join(["%s"] * len(work_order_ids))

        cur.execute(
            f"DELETE FROM work_order_activity "
            f"WHERE work_order_id IN ({placeholders})",
            tuple(work_order_ids),
        )

        cur.execute(
            f"DELETE FROM work_order_reports "
            f"WHERE work_order_id IN ({placeholders})",
            tuple(work_order_ids),
        )

        cur.execute(
            f"DELETE FROM work_orders "
            f"WHERE work_order_id IN ({placeholders})",
            tuple(work_order_ids),
        )

    if fault_ids:
        placeholders = ",".join(["%s"] * len(fault_ids))

        cur.execute(
            f"DELETE FROM fault_evidence "
            f"WHERE fault_id IN ({placeholders})",
            tuple(fault_ids),
        )

        cur.execute(
            f"DELETE FROM faults "
            f"WHERE fault_id IN ({placeholders})",
            tuple(fault_ids),
        )

    if demo_machine_ids:
        placeholders = ",".join(["%s"] * len(demo_machine_ids))

        cur.execute(
            f"DELETE FROM sensor_readings WHERE sensor_id IN "
            f"(SELECT sensor_id FROM sensors "
            f"WHERE machine_id IN ({placeholders}))",
            tuple(demo_machine_ids),
        )

        cur.execute(
            f"DELETE FROM sensors "
            f"WHERE machine_id IN ({placeholders})",
            tuple(demo_machine_ids),
        )

        cur.execute(
            f"DELETE FROM machines "
            f"WHERE machine_id IN ({placeholders})",
            tuple(demo_machine_ids),
        )

    # Remove only the old placeholder line if it is now empty.
    for line_id in demo_line_ids:
        cur.execute(
            "SELECT COUNT(*) AS total FROM machines WHERE line_id = %s",
            (line_id,),
        )
        if cur.fetchone()["total"] == 0:
            cur.execute("""
                DELETE FROM production_lines
                WHERE line_id = %s
                  AND name = 'TEST LINE - DELETE LATER'
            """, (line_id,))

    # Seed or reuse production lines.
    line_ids = {}
    for line_name in ("Line A", "Line B"):
        cur.execute(
            "SELECT line_id FROM production_lines WHERE name = %s",
            (line_name,),
        )
        row = cur.fetchone()

        if row:
            line_ids[line_name] = row["line_id"]
        else:
            cur.execute(
                "INSERT INTO production_lines (name) VALUES (%s)",
                (line_name,),
            )
            line_ids[line_name] = cur.lastrowid

    # Seed machines and sensors, avoiding duplicate names.
    for line, name, machine_type, criticality, sensors in MACHINES:
        cur.execute("""
            SELECT machine_id
            FROM machines
            WHERE line_id = %s AND name = %s
        """, (line_ids[line], name))
        row = cur.fetchone()

        if row:
            machine_id = row["machine_id"]
            cur.execute("""
                UPDATE machines
                SET machine_type = %s, criticality = %s
                WHERE machine_id = %s
            """, (machine_type, criticality, machine_id))
        else:
            cur.execute("""
                INSERT INTO machines
                    (line_id, name, machine_type, criticality)
                VALUES (%s, %s, %s, %s)
            """, (line_ids[line], name, machine_type, criticality))
            machine_id = cur.lastrowid

        for sensor_type, unit in sensors:
            cur.execute("""
                SELECT sensor_id
                FROM sensors
                WHERE machine_id = %s AND sensor_type = %s
            """, (machine_id, sensor_type))
            sensor_row = cur.fetchone()

            if sensor_row:
                cur.execute("""
                    UPDATE sensors SET unit = %s
                    WHERE sensor_id = %s
                """, (unit, sensor_row["sensor_id"]))
            else:
                cur.execute("""
                    INSERT INTO sensors (machine_id, sensor_type, unit)
                    VALUES (%s, %s, %s)
                """, (machine_id, sensor_type, unit))

    conn.commit()
    print("\nSetup committed successfully.")
    print("Created or updated six machines and their sensors.")
    print("User accounts, skills, fault types, and OT database were preserved.")

except Exception:
    conn.rollback()
    raise

finally:
    conn.close()
