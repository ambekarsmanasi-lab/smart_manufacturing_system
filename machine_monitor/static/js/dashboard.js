const $ = (id) => document.getElementById(id);

const FRESHNESS_WINDOW_MS = 10_000;

let lastOnlineTimestamp = null;
let lastTelemetryWasLive = false;

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  })[char]);
}

function parseTimestamp(value) {
  if (!value) return null;

  // MySQL timestamps are commonly returned as "YYYY-MM-DD HH:mm:ss".
  const date = new Date(String(value).replace(" ", "T"));

  return Number.isNaN(date.getTime()) ? null : date;
}

function formatTime(value) {
  const date = value instanceof Date ? value : parseTimestamp(value);

  if (!date) return "NO DATA";

  return date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: true
  });
}

function stateClass(state) {
  const normalized = String(state || "UNKNOWN").toLowerCase();

  return ["running", "idle", "down", "offline", "unknown"].includes(normalized)
    ? normalized
    : "unknown";
}

function isFresh(timestamp, now = Date.now()) {
  const date = parseTimestamp(timestamp);

  return date !== null &&
    now - date.getTime() >= 0 &&
    now - date.getTime() <= FRESHNESS_WINDOW_MS;
}

/*
 * Extract useful text from a fault record.
 * API field names can differ between versions.
 */
function faultText(fault) {
  return [
    fault.fault_code,
    fault.fault_type,
    fault.fault_name,
    fault.name,
    fault.summary,
    fault.sensor_type
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

/*
 * Determine whether a sensor is associated with an active fault.
 *
 * Supports faults that identify:
 * - a sensor directly, or
 * - a machine and a fault type/category.
 *
 * If the API doesn't return enough information to identify the
 * affected sensor, the function deliberately avoids guessing.
 */
function isSensorAnomalous(reading, faults) {
  const sensorId = Number(reading.sensor_id);
  const machineId = Number(reading.machine_id);

  const sensorName = String(reading.sensor_type || "").toLowerCase();

  return faults.some((fault) => {
    const status = String(fault.status || "").toUpperCase();

    if (!["OPEN", "ASSIGNED"].includes(status)) {
      return false;
    }

    const faultMachineId = Number(fault.machine_id);

    if (
      Number.isFinite(machineId) &&
      Number.isFinite(faultMachineId) &&
      machineId !== faultMachineId
    ) {
      return false;
    }

    // If the fault identifies a sensor explicitly, match that sensor.
    const directSensorId = Number(fault.sensor_id);

    if (
      Number.isFinite(sensorId) &&
      Number.isFinite(directSensorId) &&
      directSensorId > 0
    ) {
      return sensorId === directSensorId;
    }

    // Some APIs return fault evidence with sensor IDs.
    const evidence = Array.isArray(fault.evidence)
      ? fault.evidence
      : Array.isArray(fault.fault_evidence)
        ? fault.fault_evidence
        : [];

    if (evidence.length > 0) {
      return evidence.some((item) => {
        const evidenceSensorId = Number(item.sensor_id);

        return Number.isFinite(sensorId) &&
          Number.isFinite(evidenceSensorId) &&
          sensorId === evidenceSensorId;
      });
    }

    // Otherwise, try to infer the sensor from the fault category.
    const text = faultText(fault);

    const sensorKeywords = {
      "spindle temperature": ["spindle_temp", "spindle temperature"],
      "vibration": ["vibration"],
      "joint temperature": ["joint temperature", "motor overheating"],
      "barrel temperature": ["barrel temperature"],
      "injection pressure": ["injection pressure"],
      "motor current": ["motor current"],
      "spindle load": ["spindle load"],
      "belt speed": ["belt speed"],
      "seal temperature": ["seal temperature"],
      "throughput": ["throughput"]
    };

    const keywords = sensorKeywords[sensorName] || [];

    return keywords.some((keyword) => text.includes(keyword));
  });
}

function makeCard(machine, readings, faults) {
  const machineReadings = readings.filter(
    (reading) =>
      Number(reading.machine_id) === Number(machine.machine_id)
  );

  const state = machine.state || "UNKNOWN";

  const sensorRows = machineReadings.map((reading) => {
    const value = reading.value == null
      ? "—"
      : Number(reading.value).toFixed(2);

    const anomalous = Boolean(reading.anomalous);
    const freshness = isFresh(reading.recorded_at);

    const classes = [
      "sensor-chip",
      anomalous ? "sensor-anomalous" : "",
      freshness ? "sensor-fresh" : "sensor-stale"
    ].filter(Boolean).join(" ");

    return `
      <div class="${classes}"
           data-sensor-id="${esc(reading.sensor_id)}"
           title="${anomalous ? "Sustained sensor anomaly detected" : ""}">
        <span class="sensor-reading-name">
          ${esc(reading.sensor_type)}
        </span>

        <b>${value}${reading.unit ? ` ${esc(reading.unit)}` : ""}</b>

        <span class="sensor-time">
          ${esc(formatTime(reading.recorded_at))}
        </span>
      </div>
    `;
  }).join("");

  return `
    <article class="machine-card">
      <div class="machine-top">
        <div class="machine-name">
          ${esc(machine.machine_name)}
        </div>

        <span class="state ${stateClass(state)}">
          ${esc(state)}
        </span>
      </div>

      <div class="telemetry-title">
        LATEST SENSOR READINGS
      </div>

      <div class="sensor-list">
        ${sensorRows || '<div class="no-sensors">No sensor readings available</div>'}
      </div>
    </article>
  `;
}

/*
 * Keep the existing summary layout, minus Active Alarms.
 * Only count distinct sensors with fresh readings.
 */
function updateSummary(machines, readings) {
  const running = machines.filter(
    (machine) => machine.state === "RUNNING"
  ).length;

  const now = Date.now();

  const freshSensorIds = new Set(
    readings
      .filter((reading) => isFresh(reading.recorded_at, now))
      .map((reading) => reading.sensor_id)
      .filter((id) => id !== undefined && id !== null)
      .map(String)
  );

  const configuredSensorCount = new Set(
    readings
      .map((reading) => reading.sensor_id)
      .filter((id) => id !== undefined && id !== null)
      .map(String)
  ).size;

  if ($("avgOee")) {
    $("avgOee").textContent = "N/A";
  }

  if ($("runningCount")) {
    $("runningCount").textContent =
      `${running} / ${machines.length}`;
  }

  if ($("onlineCount")) {
    $("onlineCount").textContent =
      `${freshSensorIds.size} / ${configuredSensorCount}`;
  }
}

/*
 * Update the header indicator and its time display.
 *
 * Expected HTML IDs:
 *   liveStatus - LIVE / LAST ONLINE label
 *   clock      - timestamp below the label
 *
 * If your HTML uses a different status ID, update liveStatus below.
 */
function updateLiveIndicator(readings) {
  const now = Date.now();

  const freshReadings = readings.filter((reading) => {
    const date = parseTimestamp(reading.recorded_at);

    return date &&
      now - date.getTime() >= 0 &&
      now - date.getTime() <= FRESHNESS_WINDOW_MS;
  });

  const live = freshReadings.length > 0;

  const timestamps = readings
    .map((reading) => parseTimestamp(reading.recorded_at))
    .filter(Boolean);

  if (timestamps.length > 0) {
    const newest = new Date(
      Math.max(...timestamps.map((date) => date.getTime()))
    );

    lastOnlineTimestamp = newest;
  }

  const container = $("liveClock");
  const label = $("connectionLabel");
  const dot = $("connectionDot");
  const clock = $("clock");

  if (container) {
    container.classList.toggle("connection-offline", !live);
  }

  if (label) {
    label.textContent = live ? "LIVE" : "LAST ONLINE";
  }

  if (dot) {
    dot.classList.toggle("offline", !live);
  }

  if (clock) {
    clock.textContent = live
      ? new Date().toLocaleTimeString([], {
          hour: "numeric",
          minute: "2-digit",
          second: "2-digit",
          hour12: true
        })
      : lastOnlineTimestamp
        ? formatTime(lastOnlineTimestamp)
        : "NO DATA RECEIVED";
  }
}

async function refresh() {
  try {
    const response = await fetch("/api/overview", {
      cache: "no-store"
    });

    if (!response.ok) {
      throw new Error(`API ${response.status}`);
    }

    const data = await response.json();

    const machines = data.machines || [];
    const readings = data.readings || [];
    const faults = data.faults || [];

    const lineA = machines.filter((machine) =>
      String(machine.line_name || "").toUpperCase().includes("LINE A")
    );

    const lineB = machines.filter((machine) =>
      String(machine.line_name || "").toUpperCase().includes("LINE B")
    );

    $("lineA").innerHTML = lineA.length
      ? lineA.map((machine) => makeCard(machine, readings, faults)).join("")
      : '<div class="empty">No machines assigned to Line A.</div>';

    $("lineB").innerHTML = lineB.length
      ? lineB.map((machine) => makeCard(machine, readings, faults)).join("")
      : '<div class="empty">No machines assigned to Line B.</div>';

    updateSummary(machines, readings);
    updateLiveIndicator(readings);

    if ($("lineACount")) {
      $("lineACount").textContent = `${lineA.length} MACHINES`;
    }

    if ($("lineBCount")) {
      $("lineBCount").textContent = `${lineB.length} MACHINES`;
    }

    if ($("updated")) {
      $("updated").textContent =
        `UPDATED ${new Date().toLocaleTimeString()}`;
    }

    if ($("error")) {
      $("error").textContent = "";
    }
  } catch (error) {
    if ($("error")) {
      $("error").textContent =
        `UPLINK FAILURE :: ${error.message} — check MySQL, .env, and machine_monitor/app.py`;
    }

    // Do not pretend telemetry is live if the API is unreachable.
    updateLiveIndicator([]);
  }
}

refresh();
setInterval(refresh, 2500);