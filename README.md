# Smart Manufacturing OT Dashboard (smart_manufacturing_ot)

MySQL + Flask API + HTML/JS dashboard that tracks OEE (Availability x Performance x Quality).

## Where everything is

| File | What it does | When you use it |
|---|---|---|
| sql/create_schema_and_seed.sql | Drops and recreates the 6 tables, seeds 2 lines and 6 machines | Once (re-run any time for a clean start) |
| sql/ot_sample_data.sql | 3 days of generated history (status, cycles, sensors, maintenance) | Once, after the schema |
| generate_ot_data.py | Regenerates sql/ot_sample_data.sql (optional, file already included) | Only if you want new data |
| backend_app.py | Flask API on port 5000: /api/oee, /api/status, /api/sensors, /api/maintenance | Keep running |
| live_data_simulator.py | Inserts new random data every 5 s so the dashboard moves | Keep running (ONE copy only) |
| dashboard.html | The dashboard UI, polls the API every 2 s | Open in a browser |
| diagrams/ | ER diagram and system architecture (PNG + SVG) | For your report |

## Setup
    pip install flask flask-cors mysql-connector-python

Edit the MySQL password in BOTH backend_app.py and live_data_simulator.py (DB_CONFIG, currently "password123").
generate_ot_data.py does not connect to MySQL, so it needs no password.

## Run order
1. MySQL Workbench: run sql/create_schema_and_seed.sql
2. MySQL Workbench: run sql/ot_sample_data.sql
3. Terminal 1: python backend_app.py
4. Terminal 2: python live_data_simulator.py
5. Open dashboard.html in your browser

## Troubleshooting
- Machines Running shows something like 7 / 8: the simulator was started twice. Stop all copies and start one. On startup it closes leftover duplicate open rows by itself.
- Dashboard shows "UPLINK FAILURE": backend_app.py is not running.
- Table doesn't exist errors: re-run step 1 and 2 in order.
- Tuning: TICK_SECONDS in live_data_simulator.py (data rate), REFRESH_MS in dashboard.html (page refresh).

