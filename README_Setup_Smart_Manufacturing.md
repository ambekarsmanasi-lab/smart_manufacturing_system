# Smart Manufacturing Maintenance System with Real Time Fault Detection

## Requirements
- MySQL 8.0+
- Python 3.10+ recommended
- The project source files, including `app.py`, `simulator.py`, `fault_analyser.py`, and the HTML templates used by the Flask app.

## 1. Create and seed the database
1. Open MySQL Workbench and connect to your local MySQL server.
2. Open `sql/setup_database.sql`.
3. Execute the entire script.
4. The script creates `smart_manufacturing_erp`, all 16 application tables, and demo records. It is intended for a fresh local demo database; it does not drop the database.

If the project files expect `machine_monitor/simulator.py` and `machine_monitor/fault_analyser.py`, keep them in that folder. Run commands below from the project root and adjust paths only if your final folder structure differs.

## 2. Configure environment variables
Create a `.env` file in the project root (do not commit it):

```env
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=PUT_YOUR_LOCAL_MYSQL_PASSWORD_HERE
DB_NAME=smart_manufacturing_erp
SECRET_KEY=replace-this-with-a-long-random-secret
```

The Flask app uses `SECRET_KEY`; the simulator and fault analyser use the `DB_*` values. Make sure the database password is your own local MySQL password.

## 3. Install Python dependencies
In a terminal opened at the project root:

```bash
python -m venv .venv
```

Windows:
```bat
.venv\Scripts\activate
```

macOS/Linux:
```bash
source .venv/bin/activate
```

Then install:
```bash
pip install Flask mysql-connector-python python-dotenv
```

If your application imports any additional packages, install those too.

## 4. Start the project
Open separate terminals in the project root.

**Terminal 1 — maintenance web app**
```bash
python app.py
```
Open `http://127.0.0.1:5000/`.

**Terminal 2 — telemetry simulator**
```bash
python machine_monitor/simulator.py
```

**Terminal 3 — fault analyser**
```bash
python machine_monitor/fault_analyser.py
```

If the final repository keeps `simulator.py` and `fault_analyser.py` in the root instead, use `python simulator.py` and `python fault_analyser.py`.

Start the simulator before the analyser. The analyser needs historical baseline readings and a fresh stream of new readings. To demonstrate a controlled anomaly, run the simulator with one of the supported options, for example:

```bash
python machine_monitor/simulator.py --demo-fault vibration
```

Use the option spelling supported by your current `simulator.py`; if unsure, run `python machine_monitor/simulator.py --help`.

## Demo login accounts
All four accounts use the password **`Demo@123`**.

| Role | Username |
|---|---|
| Maintenance Head | `head_demo` |
| Technician | `tech01` |
| Technician | `tech02` |
| Technician | `tech03` |

These are local classroom-demo credentials only. Change them before deploying anywhere outside your own machine.

## What the seed data contains
- 2 production lines, 6 machines and 13 sensors.
- 40 historical baseline readings per sensor so the analyser can begin after fresh telemetry arrives.
- Three fault categories and their sensor/skill mappings.
- One Maintenance Head and three technician accounts with skill profiles.
- Example faults, one in-progress work order, activity history and a report record.

Some fault/work-order records are explicitly marked as demo data. The live simulator adds new readings; the fault analyser can then create or update fault records when its detection conditions are met.

## Troubleshooting
- **`Access denied`**: check `DB_USER` and `DB_PASSWORD` in `.env`.
- **`Unknown database`**: rerun `sql/setup_database.sql` in MySQL Workbench.
- **`Table doesn't exist`**: make sure the full setup script completed without an error.
- **Login fails**: confirm that the Flask app connects to `smart_manufacturing_erp` and uses Werkzeug's `check_password_hash` for the `users.password_hash` column.
- **No new faults appear**: start the simulator first; allow enough readings to arrive; then check that the latest readings are fresh and the fault analyser is running.
- **Do not commit** `.env`, `.venv/`, or `__pycache__/` to Git.

## Important implementation note
This setup matches the `smart_manufacturing_erp` schema represented by the project's detailed schema export: `production_lines`, `machines`, `sensors`, `sensor_readings`, `fault_types`, `sensor_fault_type_map`, `faults`, `fault_evidence`, `users`, `technicians`, `skills`, `technician_skills`, `fault_type_skills`, `work_orders`, `work_order_activity`, and `work_order_reports`.

Before using this on an existing database, back it up first. The SQL uses `CREATE TABLE IF NOT EXISTS` and inserts predictable demo records; it does not delete existing tables.
