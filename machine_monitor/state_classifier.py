from datetime import datetime, timezone
from typing import Optional

# Readings older than this are considered stale.
TELEMETRY_TIMEOUT_SECONDS = 10

# Demonstration thresholds, not certified industrial limits.
RULES = {
    "CNC-01": {"operating_sensor": "spindle load", "running_above": 5.0, "unit": "%"},
    "Conveyor-A": {"operating_sensor": "belt speed", "running_above": 0.1, "unit": "m/s"},
    "Conveyor-B": {"operating_sensor": "belt speed", "running_above": 0.1, "unit": "m/s"},
    "RobotArm-01": {"operating_sensor": "motor current", "running_above": 1.0, "unit": "A"},
    "Packaging-01": {"operating_sensor": "throughput", "running_above": 0.5, "unit": "units/min"},
    "Injection-01": {"operating_sensor": "injection pressure", "running_above": 1.0, "unit": "bar"},
}


def parse_timestamp(value):
    """Return a datetime from a datetime object or ISO timestamp string."""
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


def _comparable_datetimes(left, right):
    """Normalize naive/aware timestamps to UTC before comparing."""
    if left.tzinfo is None:
        left = left.replace(tzinfo=timezone.utc)
    else:
        left = left.astimezone(timezone.utc)
    if right.tzinfo is None:
        right = right.replace(tzinfo=timezone.utc)
    else:
        right = right.astimezone(timezone.utc)
    return left, right


def classify_machine(machine_name: str, readings: list,
                     explicit_state: Optional[str] = None,
                     now: Optional[datetime] = None) -> dict:
    """
    Infer a conservative machine state from telemetry.

    RUNNING: latest configured operating signal is above threshold.
    IDLE: latest configured operating signal is at/below threshold.
    DOWN: only an explicit trusted state source confirms DOWN.
    OFFLINE: telemetry is missing or stale.
    UNKNOWN: available telemetry cannot determine operational state.

    Fault records are deliberately not used to classify state.
    """
    if explicit_state and explicit_state.strip().upper() == "DOWN":
        return {
            "state": "DOWN",
            "reason": "Confirmed by an operational state source",
            "confidence": "high",
        }

    if not readings:
        return {"state": "OFFLINE", "reason": "No sensor readings available", "confidence": "low"}

    parsed = [
        (row, parse_timestamp(row.get("recorded_at")))
        for row in readings
    ]
    parsed = [(row, stamp) for row, stamp in parsed if stamp is not None]
    if not parsed:
        return {
            "state": "UNKNOWN",
            "reason": "Sensor timestamps are missing or invalid",
            "confidence": "low",
        }

    now = now or datetime.now()
    latest_time = max(stamp for _, stamp in parsed)
    latest_time, now_utc = _comparable_datetimes(latest_time, now)
    age_seconds = max(0.0, (now_utc - latest_time).total_seconds())

    if age_seconds > TELEMETRY_TIMEOUT_SECONDS:
        return {
            "state": "OFFLINE",
            "reason": f"No recent telemetry ({age_seconds:.0f}s old)",
            "confidence": "high",
        }

    rule = RULES.get(machine_name)
    if not rule:
        return {
            "state": "UNKNOWN",
            "reason": "No validated operating sensor configured for this machine",
            "confidence": "low",
        }

    expected_sensor = rule["operating_sensor"].lower()
    matching = [
        (row, stamp) for row, stamp in parsed
        if expected_sensor in str(row.get("sensor_type", "")).lower()
        and row.get("value") is not None
    ]
    if not matching:
        return {
            "state": "UNKNOWN",
            "reason": f"Missing operating sensor: {rule['operating_sensor']}",
            "confidence": "low",
        }

    row, _ = max(matching, key=lambda item: item[1])
    try:
        value = float(row["value"])
    except (ValueError, TypeError):
        return {
            "state": "UNKNOWN",
            "reason": "Operating sensor value is invalid",
            "confidence": "low",
        }

    threshold = rule["running_above"]
    if value > threshold:
        return {
            "state": "RUNNING",
            "reason": f"{rule['operating_sensor']} is {value:g} {rule['unit']}, above the {threshold:g} {rule['unit']} threshold",
            "confidence": "medium",
        }
    return {
        "state": "IDLE",
        "reason": f"{rule['operating_sensor']} is {value:g} {rule['unit']}, at/below the {threshold:g} {rule['unit']} threshold",
        "confidence": "medium",
    }
