const $ = (id) => document.getElementById(id);

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  })[char]);
}

function formatTime(value) {
  if (!value) return "NO DATA";

  const date = new Date(String(value).replace(" ", "T"));

  return Number.isNaN(date.getTime())
    ? String(value)
    : date.toLocaleTimeString([], {
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

function makeCard(machine, readings) {
  const machineReadings = readings.filter(
    (reading) =>
      Number(reading.machine_id) === Number(machine.machine_id)
  );

  const state = machine.state || "UNKNOWN";

  // Display each sensor on its own full-width row.
  const sensorRows = machineReadings.map((reading) => {
    const value = reading.value == null
      ? "—"
      : Number(reading.value).toFixed(2);

    return `
      <div class="sensor-chip">
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

function updateSummary(data, machines, readings, faults) {
  const summary = data.summary || {};

  const running = machines.filter(
    (machine) => machine.state === "RUNNING"
  ).length;

  const reporting = readings.filter(
    (reading) => reading.recorded_at
  ).length;

  $("avgOee").textContent = "N/A";
  $("runningCount").textContent = `${running} / ${machines.length}`;
  $("alarmCount").textContent = String(
    summary.active_faults ?? faults.length
  );
  $("onlineCount").textContent = `${reporting} / ${readings.length}`;
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
      ? lineA.map((machine) => makeCard(machine, readings)).join("")
      : '<div class="empty">No machines assigned to Line A.</div>';

    $("lineB").innerHTML = lineB.length
      ? lineB.map((machine) => makeCard(machine, readings)).join("")
      : '<div class="empty">No machines assigned to Line B.</div>';

    updateSummary(data, machines, readings, faults);

    $("lineACount").textContent = `${lineA.length} MACHINES`;
    $("lineBCount").textContent = `${lineB.length} MACHINES`;
    $("updated").textContent =
      `UPDATED ${new Date().toLocaleTimeString()}`;

    $("error").textContent = "";
  } catch (error) {
    $("error").textContent =
      `UPLINK FAILURE :: ${error.message} — check MySQL, .env, and machine_monitor/app.py`;
  }
}

function tick() {
  $("clock").textContent = new Date().toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
    hour12: true
  });
}

tick();
setInterval(tick, 1000);

refresh();
setInterval(refresh, 2500);