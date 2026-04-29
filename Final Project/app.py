from flask import Flask, jsonify, render_template_string
import threading
import time
import traceback
import numpy as np
import paho.mqtt.client as mqtt
import json

BROKER_IP = "128.164.137.130"
TOPIC = "wind/data"

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect(BROKER_IP,1883,60)

from final_project import IDWWindField
from as5600_read import AS5600, wrapped_angle_diff_deg

app = Flask(__name__)

# ============================================================
# Shared state for the web app
# ============================================================
latest_payload = {
    "timestamp": time.time(),
    "grid": [],
    "summary": {
        "avg_speed": 0.0,
        "avg_direction_deg": 0.0,
        "status": "Starting"
    },
    "sensors": []
}

data_lock = threading.Lock()


# ============================================================
# RPM reader built around your existing AS5600 class
# ============================================================
class AS5600RPMReader:
    def __init__(self, bus_num=1, sample_interval=0.05, alpha=0.25):
        self.sensor = AS5600(bus_num=bus_num)
        self.sample_interval = sample_interval
        self.alpha = alpha

        self.prev_angle = self.sensor.angle_degrees()
        self.prev_time = time.time()
        self.rpm_smoothed = 0.0

    def read_rpm(self):
        time.sleep(self.sample_interval)

        current_angle = self.sensor.angle_degrees()
        current_time = time.time()

        dt = current_time - self.prev_time
        if dt <= 0:
            return self.rpm_smoothed

        dtheta = wrapped_angle_diff_deg(current_angle, self.prev_angle)

        rps = (dtheta / dt) / 360.0
        rpm = rps * 60.0

        # exponential smoothing for less noisy display
        self.rpm_smoothed = self.alpha * rpm + (1.0 - self.alpha) * self.rpm_smoothed

        self.prev_angle = current_angle
        self.prev_time = current_time

        return self.rpm_smoothed

    def close(self):
        self.sensor.close()


# ============================================================
# Replace these with your calibration constants later
# wind_speed = a * (rpm / 60) + b
# ============================================================
def rpm_to_wind_speed(rpm, a=1.2, b=0.0):
    """
    Convert RPM to wind speed using a linear calibration.
    For now, a and b are placeholders.
    """
    rev_per_sec = abs(rpm) / 60.0
    return max(0.0, a * rev_per_sec + b)


# ============================================================
# Build field payload from:
# - real speed from AS5600
# - dummy direction for sensor 1
# - dummy speed + direction for sensor 2
# ============================================================
def build_field_payload(speed1, dir1_deg, speed2, dir2_deg):
    # Example 2-sensor positions in a 15 x 15 field
    sensor_x = [3.0, 12.0]
    sensor_y = [4.0, 10.5]
    sensor_speed = [speed1, speed2]
    sensor_dir_deg = [dir1_deg, dir2_deg]

    reconstructor = IDWWindField(power=2.0)

    X, Y, U, V, S, D = reconstructor.interpolate_grid(
        sensor_x=sensor_x,
        sensor_y=sensor_y,
        sensor_speed=sensor_speed,
        sensor_dir_deg=sensor_dir_deg,
        x_min=0.0,
        x_max=15.0,
        y_min=0.0,
        y_max=15.0,
        nx=21,
        ny=21
    )

    grid = []
    for j in range(X.shape[0]):
        for i in range(X.shape[1]):
            grid.append({
                "x": float(X[j, i]),
                "y": float(Y[j, i]),
                "u": float(U[j, i]),
                "v": float(V[j, i]),
                "speed": float(S[j, i]),
                "direction_deg": float(D[j, i])
            })

    avg_u = float(np.mean(U))
    avg_v = float(np.mean(V))
    avg_speed, avg_dir = IDWWindField.uv_to_speed_dir(avg_u, avg_v)

    sensors = [
        {
            "name": "Anemometer 1",
            "x": sensor_x[0],
            "y": sensor_y[0],
            "speed": float(sensor_speed[0]),
            "direction_deg": float(sensor_dir_deg[0]),
            "source": "AS5600"
        },
        {
            "name": "Anemometer 2",
            "x": sensor_x[1],
            "y": sensor_y[1],
            "speed": float(sensor_speed[1]),
            "direction_deg": float(sensor_dir_deg[1]),
            "source": "Dummy"
        }
    ]

    payload = {
        "timestamp": time.time(),
        "grid": grid,
        "summary": {
            "avg_speed": float(np.asarray(avg_speed)),
            "avg_direction_deg": float(np.asarray(avg_dir)),
            "status": "Live AS5600 + dummy second sensor"
        },
        "sensors": sensors
    }

    return payload


# ============================================================
# Background data update loop
# ============================================================
def data_loop():
    global latest_payload
    reader = None
    
    
    try:
        reader = AS5600RPMReader(bus_num=1, sample_interval=0.05, alpha=0.25)

        # Dummy placeholders for now
        dummy_dir_1 = 270.0
        dummy_dir_2 = 250.0
        dummy_speed_2 = 1

        while True:
            rpm1 = reader.read_rpm()
            speed1 = rpm_to_wind_speed(rpm1, a=1.2, b=0.0)

            payload = build_field_payload(
                speed1=speed1,
                dir1_deg=dummy_dir_1,
                speed2=dummy_speed_2,
                dir2_deg=dummy_dir_2
            )

            payload["summary"]["rpm_1"] = float(rpm1)
            payload["summary"]["speed_1"] = float(speed1)

            with data_lock:
                latest_payload = payload
            wind_data = {
                "sensor_id": "wind_sensor_1",
                "x": 2,
                "y": 2,
                "speed": float(speed1),
                "direction_deg": float(dummy_dir_1),
                "source": "AS5600"
            }
            message = json.dumps(wind_data)
            client.publish(TOPIC, message)
            print("Published:",message)

    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        traceback.print_exc()

        with data_lock:
            latest_payload = {
                "timestamp": time.time(),
                "grid": [],
                "summary": {
                    "avg_speed": 0.0,
                    "avg_direction_deg": 0.0,
                    "status": f"Error: {err}"
                },
                "sensors": []
            }

    finally:
        if reader is not None:
            try:
                reader.close()
            except Exception:
                pass


# ============================================================
# HTML frontend
# ============================================================
HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Wind Field Dashboard</title>
    <style>
        :root {
            --bg: #08111f;
            --panel: rgba(14, 25, 43, 0.78);
            --border: rgba(255,255,255,0.08);
            --text: #eaf2ff;
            --muted: #9db2d1;
            --good: #63e6be;
            --shadow: 0 12px 40px rgba(0,0,0,0.35);
        }

        * { box-sizing: border-box; }

        body {
            margin: 0;
            font-family: Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
            color: var(--text);
            background:
                radial-gradient(circle at top left, rgba(68, 136, 255, 0.16), transparent 32%),
                radial-gradient(circle at top right, rgba(90, 255, 200, 0.10), transparent 28%),
                linear-gradient(180deg, #06101c 0%, #091625 100%);
            min-height: 100vh;
        }

        .shell {
            max-width: 1450px;
            margin: 0 auto;
            padding: 24px;
        }

        .topbar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 16px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }

        h1 {
            margin: 0;
            font-size: 2rem;
        }

        .subtitle {
            margin-top: 6px;
            color: var(--muted);
        }

        .pill {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 10px 14px;
            border-radius: 999px;
            background: var(--panel);
            border: 1px solid var(--border);
            box-shadow: var(--shadow);
            color: var(--muted);
            font-size: 0.9rem;
        }

        .dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: var(--good);
            box-shadow: 0 0 12px var(--good);
        }

        .layout {
            display: grid;
            grid-template-columns: 320px 1fr;
            gap: 20px;
        }

        .card {
            background: var(--panel);
            border: 1px solid var(--border);
            border-radius: 24px;
            box-shadow: var(--shadow);
            backdrop-filter: blur(12px);
        }

        .sidebar {
            padding: 18px;
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        .metric-card {
            padding: 16px;
            border-radius: 20px;
            background: linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0.01));
            border: 1px solid rgba(255,255,255,0.05);
        }

        .metric-label {
            color: var(--muted);
            font-size: 0.88rem;
            margin-bottom: 8px;
        }

        .metric-value {
            font-size: 1.9rem;
            font-weight: 700;
        }

        .metric-sub {
            margin-top: 6px;
            color: var(--muted);
            font-size: 0.9rem;
        }

        .sensor-block {
            margin-top: 10px;
            padding-top: 10px;
            border-top: 1px solid rgba(255,255,255,0.06);
            color: var(--muted);
            font-size: 0.92rem;
            line-height: 1.5;
        }

        .plot-panel {
            padding: 16px;
        }

        .plot-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 12px;
            flex-wrap: wrap;
            margin-bottom: 12px;
        }

        .plot-title {
            font-size: 1.1rem;
            font-weight: 600;
        }

        .plot-subtitle {
            color: var(--muted);
            font-size: 0.92rem;
        }

        .canvas-wrap {
            position: relative;
            width: 100%;
            aspect-ratio: 16 / 10;
            border-radius: 22px;
            overflow: hidden;
            background:
                linear-gradient(180deg, rgba(18, 32, 54, 0.95), rgba(11, 22, 38, 0.95));
            border: 1px solid rgba(255,255,255,0.05);
        }

        canvas {
            width: 100%;
            height: 100%;
            display: block;
        }

        @media (max-width: 980px) {
            .layout {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="shell">
        <div class="topbar">
            <div>
                <h1>Wind Vector Field Dashboard</h1>
                <div class="subtitle">AS5600 live input → IDW field reconstruction → local Pi website</div>
            </div>
            <div class="pill">
                <span class="dot"></span>
                <span id="status-text">Connecting...</span>
            </div>
        </div>

        <div class="layout">
            <div class="card sidebar">
                <div class="metric-card">
                    <div class="metric-label">Average wind speed</div>
                    <div class="metric-value" id="avg-speed">--</div>
                    <div class="metric-sub">m/s</div>
                </div>

                <div class="metric-card">
                    <div class="metric-label">Average direction</div>
                    <div class="metric-value" id="avg-dir">--</div>
                    <div class="metric-sub">meteorological FROM direction</div>
                </div>

                <div class="metric-card">
                    <div class="metric-label">Live anemometer 1 RPM</div>
                    <div class="metric-value" id="rpm-1">--</div>
                    <div class="metric-sub">from AS5600</div>
                </div>

                <div class="metric-card">
                    <div class="metric-label">Anemometer inputs</div>
                    <div id="sensor-list" class="sensor-block">No sensor data yet.</div>
                </div>
            </div>

            <div class="card plot-panel">
                <div class="plot-header">
                    <div>
                        <div class="plot-title">Interpolated wind field</div>
                        <div class="plot-subtitle">Arrows show reconstructed local flow vectors</div>
                    </div>
                    <div class="plot-subtitle" id="last-update">Last update: --</div>
                </div>

                <div class="canvas-wrap">
                    <canvas id="windCanvas"></canvas>
                </div>
            </div>
        </div>
    </div>

<script>
const canvas = document.getElementById("windCanvas");
const ctx = canvas.getContext("2d");
let latestData = null;

function resizeCanvas() {
    const ratio = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * ratio;
    canvas.height = rect.height * ratio;
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    draw();
}

window.addEventListener("resize", resizeCanvas);

function formatTime(ts) {
    const d = new Date(ts * 1000);
    return d.toLocaleTimeString();
}

function speedColor(speed, maxSpeed) {
    const s = maxSpeed > 0 ? speed / maxSpeed : 0;
    if (s < 0.25) return "#7dd3fc";
    if (s < 0.50) return "#86efac";
    if (s < 0.75) return "#fcd34d";
    return "#fb7185";
}

function drawGridBackground(w, h, margin, nx=10, ny=8) {
    ctx.save();
    ctx.strokeStyle = "rgba(255,255,255,0.06)";
    ctx.lineWidth = 1;

    for (let i = 0; i <= nx; i++) {
        const x = margin + (w - 2 * margin) * i / nx;
        ctx.beginPath();
        ctx.moveTo(x, margin);
        ctx.lineTo(x, h - margin);
        ctx.stroke();
    }

    for (let j = 0; j <= ny; j++) {
        const y = margin + (h - 2 * margin) * j / ny;
        ctx.beginPath();
        ctx.moveTo(margin, y);
        ctx.lineTo(w - margin, y);
        ctx.stroke();
    }
    ctx.restore();
}

function drawArrow(x, y, u, v, color, scale) {
    const dx = u * scale;
    const dy = -v * scale;

    const x2 = x + dx;
    const y2 = y + dy;

    ctx.save();
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.lineWidth = 2.0;
    ctx.lineCap = "round";

    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineTo(x2, y2);
    ctx.stroke();

    const angle = Math.atan2(dy, dx);
    const headLen = 8;

    ctx.beginPath();
    ctx.moveTo(x2, y2);
    ctx.lineTo(
        x2 - headLen * Math.cos(angle - Math.PI / 6),
        y2 - headLen * Math.sin(angle - Math.PI / 6)
    );
    ctx.lineTo(
        x2 - headLen * Math.cos(angle + Math.PI / 6),
        y2 - headLen * Math.sin(angle + Math.PI / 6)
    );
    ctx.closePath();
    ctx.fill();
    ctx.restore();
}

function drawSensorMarker(x, y, label, color) {
    ctx.save();
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(x, y, 6, 0, 2 * Math.PI);
    ctx.fill();

    ctx.font = "12px sans-serif";
    ctx.fillStyle = "rgba(255,255,255,0.92)";
    ctx.fillText(label, x + 10, y - 10);
    ctx.restore();
}

function draw() {
    const rect = canvas.getBoundingClientRect();
    const w = rect.width;
    const h = rect.height;

    ctx.clearRect(0, 0, w, h);

    const margin = 32;
    drawGridBackground(w, h, margin);

    if (!latestData || !latestData.grid || latestData.grid.length === 0) {
        ctx.save();
        ctx.fillStyle = "rgba(255,255,255,0.8)";
        ctx.font = "16px sans-serif";
        ctx.fillText("Waiting for field data...", 40, 50);
        ctx.restore();
        return;
    }

    const grid = latestData.grid;
    const sensors = latestData.sensors || [];

    const xs = grid.map(p => p.x);
    const ys = grid.map(p => p.y);
    const speeds = grid.map(p => p.speed ?? Math.sqrt(p.u*p.u + p.v*p.v));

    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    const maxSpeed = Math.max(...speeds, 0.001);

    const plotW = w - 2 * margin;
    const plotH = h - 2 * margin;

    const toScreenX = x => margin + (x - minX) / Math.max(maxX - minX, 1e-6) * plotW;
    const toScreenY = y => h - margin - (y - minY) / Math.max(maxY - minY, 1e-6) * plotH;

    const scale = 16 / Math.max(maxSpeed, 0.5);

    for (const p of grid) {
        const x = toScreenX(p.x);
        const y = toScreenY(p.y);
        const speed = p.speed ?? Math.sqrt(p.u*p.u + p.v*p.v);
        const color = speedColor(speed, maxSpeed);
        drawArrow(x, y, p.u, p.v, color, scale);
    }

    sensors.forEach((s, idx) => {
        const sx = toScreenX(s.x);
        const sy = toScreenY(s.y);
        drawSensorMarker(sx, sy, s.name || `S${idx+1}`, idx === 0 ? "#63e6be" : "#fcd34d");
    });
}

function updateCards(data) {
    document.getElementById("avg-speed").textContent =
        (data.summary?.avg_speed ?? 0).toFixed(2);

    document.getElementById("avg-dir").textContent =
        (data.summary?.avg_direction_deg ?? 0).toFixed(1) + "°";

    document.getElementById("rpm-1").textContent =
        ((data.summary?.rpm_1 ?? 0)).toFixed(2);

    document.getElementById("status-text").textContent =
        data.summary?.status ?? "Live";

    document.getElementById("last-update").textContent =
        "Last update: " + formatTime(data.timestamp ?? Date.now()/1000);

    const sensors = data.sensors || [];
    const sensorList = document.getElementById("sensor-list");

    if (sensors.length === 0) {
        sensorList.innerHTML = "No sensor data yet.";
    } else {
        sensorList.innerHTML = sensors.map(s => `
            <div style="margin-bottom:10px;">
                <strong>${s.name}</strong><br>
                source: ${s.source}<br>
                speed: ${Number(s.speed).toFixed(2)}<br>
                direction: ${Number(s.direction_deg).toFixed(1)}°<br>
                position: (${Number(s.x).toFixed(1)}, ${Number(s.y).toFixed(1)})
            </div>
        `).join("");
    }
}

async function fetchWindData() {
    try {
        const response = await fetch("/api/wind");
        const data = await response.json();
        latestData = data;
        updateCards(data);
        draw();
    } catch (err) {
        document.getElementById("status-text").textContent = "Disconnected";
        console.error(err);
    }
}

resizeCanvas();
fetchWindData();
setInterval(fetchWindData, 1000);
</script>
</body>
</html>
"""


# ============================================================
# Routes
# ============================================================
@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/api/wind", methods=["GET"])
def api_wind():
    with data_lock:
        return jsonify(latest_payload)


# ============================================================
# Main
# ============================================================
if __name__ == "__main__":
    threading.Thread(target=data_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, debug=False)
