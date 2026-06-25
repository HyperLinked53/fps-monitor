const WS_URL = 'ws://localhost:8765';
const HISTORY_SIZE = 120;
const MAX_FRAMETIME_MS = 50;
const HOLD_MS = 2000;     // hold last valid reading for 2s during static scenes
const MIN_VALID_FPS = 20; // below this is considered a static/menu scene

const fpsEl = document.getElementById('fps');
const canvas = document.getElementById('graph');
const ctx = canvas.getContext('2d');

const history = new Array(HISTORY_SIZE).fill(0);
let displayFps = 0;
let lastValidFps = 0;
let lastValidTime = 0;
let connected = false;

function barColor(ms) {
  if (ms <= 20) return '#00e676';
  if (ms <= 33) return '#ffcc00';
  return '#ff4444';
}

function render() {
  const w = canvas.width;
  const h = canvas.height;
  const barW = w / HISTORY_SIZE;

  ctx.clearRect(0, 0, w, h);

  // Subtle grid lines at 60fps (16.7ms) and 30fps (33.3ms)
  ctx.strokeStyle = 'rgba(255,255,255,0.15)';
  ctx.lineWidth = 1;
  [16.7, 33.3].forEach(target => {
    const y = h - (target / MAX_FRAMETIME_MS) * h;
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
  });

  history.forEach((ft, i) => {
    if (ft <= 0) return;
    const barH = Math.min(ft / MAX_FRAMETIME_MS, 1) * h;
    ctx.fillStyle = barColor(ft);
    ctx.fillRect(i * barW, h - barH, Math.max(barW - 1, 1), barH);
  });

  // FPS color and text
  fpsEl.style.color = displayFps >= 50 ? '#ffffff' : displayFps >= 30 ? '#ffcc00' : '#ff4444';
  fpsEl.textContent = connected ? `${displayFps} FPS` : '-- FPS';

  requestAnimationFrame(render);
}

function connect() {
  const ws = new WebSocket(WS_URL);

  ws.onopen = () => { connected = true; };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      const now = Date.now();

      if (data.fps >= MIN_VALID_FPS) {
        // Good reading — update everything
        lastValidFps = data.fps;
        lastValidTime = now;
        displayFps = data.fps;
      } else if (lastValidTime && (now - lastValidTime) < HOLD_MS) {
        // Scene went static (menu/cutscene) — hold last valid reading
        displayFps = lastValidFps;
      } else {
        // Held too long — accept the low reading as real
        displayFps = data.fps;
      }

      if (data.is_new_frame && data.frametime_ms > 0) {
        history.shift();
        history.push(data.frametime_ms);
      }
    } catch (e) {
      // ignore malformed message
    }
  };

  ws.onclose = () => {
    connected = false;
    setTimeout(connect, 1000); // auto-reconnect after 1s
  };

  ws.onerror = () => ws.close();
}

connect();
render();
