# Machine Monitor (corrected)

## What this version does
- `simulator.py` inserts generated telemetry only into `smart_manufacturing_erp.sensor_readings`.
- It does not write to `faults`, `fault_evidence`, or the separate `smart_manufacturing_ot` database.
- `state_classifier.py` estimates RUNNING / IDLE / OFFLINE / UNKNOWN from recent telemetry. Fault records do not determine state.
- `app.py` serves the dashboard on port 5051 and exposes `/api/overview` and `/api/health`.
- OEE is displayed as N/A because no real OEE calculation/model is connected. No fake OEE, availability, performance, or quality percentages are generated.

## Install
Run these commands from this `machine_monitor` directory:
```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```
Edit `.env` and set your local MySQL password. Do not upload `.env` to GitHub or share it.

## Run
Open two terminals in this directory and activate the environment in each.

Terminal 1:
```powershell
python simulator.py
```

Terminal 2:
```powershell
python app.py
```

Open `http://127.0.0.1:5051`.

## Notes
- The app and simulator read the `machine_monitor/.env` file; they do not rely on `erp_portal/.env`.
- `DB_NAME` defaults to `smart_manufacturing_erp`. Do not change it to `smart_manufacturing_ot`.
- `Injection-01` is `UNKNOWN` until a validated operational signal/rule is provided.
- The simulator does not clean up or alter existing fault rows.
