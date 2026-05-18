/* ═══════════════════════════════════════════
   NavTools — Desktop App Logic
   Real Windows app launching + EOG signal UI
   ═══════════════════════════════════════════ */

const isElectron = window.navtools?.isElectron || false;

// ── Default Applications with real Windows commands ──
let apps = [
  { id: 'browser',    name: 'Browser',      icon: '🌐', color: '#3498db', cmd: 'browser' },
  { id: 'folder',     name: 'File Explorer', icon: '📁', color: '#f39c12', cmd: 'folder' },
  { id: 'camera',     name: 'Camera',       icon: '📷', color: '#e74c3c', cmd: 'camera' },
  { id: 'notepad',    name: 'Notepad',      icon: '📝', color: '#2ecc71', cmd: 'notepad' },
  { id: 'calculator', name: 'Calculator',   icon: '🔢', color: '#9b59b6', cmd: 'calculator' },
  { id: 'settings',   name: 'Settings',     icon: '⚙️', color: '#34495e', cmd: 'settings' },
  { id: 'music',      name: 'Music',        icon: '🎵', color: '#1abc9c', cmd: 'music' },
  { id: 'photos',     name: 'Photos',       icon: '🖼️', color: '#e84393', cmd: 'photos' },
  { id: 'terminal',   name: 'Terminal',     icon: '💻', color: '#00cec9', cmd: 'terminal' },
];

let selectedIdx = 0;
let signalData = [];
let bandData = { beta: [] };
let counts = { blink: 0, dblink: 0, winkl: 0, winkr: 0 };
const MAX_POINTS = 200;

// ── Initialize ──
document.addEventListener('DOMContentLoaded', () => {
  renderApps();
  initSignalCanvas();
  initModals();
  initCalibration();
  initDataCollection();
  initSettings();
  initKeyboard();
  initArduino();
  startSimulation();

  // Show desktop mode indicator
  if (isElectron) {
    document.querySelector('.status-text').textContent = 'Desktop Mode';
    document.querySelector('.status-dot').classList.remove('offline');
    document.querySelector('.status-dot').classList.add('online');
  }
});

// ═══════════════════════════════════════════
//  APP GRID
// ═══════════════════════════════════════════
let dragSrcIdx = null;

function renderApps() {
  const grid = document.getElementById('appGrid');
  grid.innerHTML = '';
  apps.forEach((app, i) => {
    const card = document.createElement('div');
    card.className = `app-card${i === selectedIdx ? ' selected' : ''}`;
    card.style.setProperty('--card-color', app.color + '22');
    card.dataset.index = i;
    card.draggable = true;
    card.innerHTML = `
      <button class="remove-btn" title="Remove">&times;</button>
      <div class="app-icon" style="background:${app.color}22">${app.icon}</div>
      <span class="app-name">${app.name}</span>
    `;
    card.addEventListener('click', () => selectApp(i));
    card.addEventListener('dblclick', () => { selectApp(i); launchSelected(); });
    card.querySelector('.remove-btn').addEventListener('click', (e) => {
      e.stopPropagation();
      removeApp(i);
    });

    // Drag events
    card.addEventListener('dragstart', (e) => {
      dragSrcIdx = i;
      card.classList.add('dragging');
      e.dataTransfer.effectAllowed = 'move';
    });
    card.addEventListener('dragend', () => {
      card.classList.remove('dragging');
      document.querySelectorAll('.app-card').forEach(c => c.classList.remove('drag-over'));
      dragSrcIdx = null;
    });
    card.addEventListener('dragover', (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      card.classList.add('drag-over');
    });
    card.addEventListener('dragleave', () => {
      card.classList.remove('drag-over');
    });
    card.addEventListener('drop', (e) => {
      e.preventDefault();
      card.classList.remove('drag-over');
      if (dragSrcIdx !== null && dragSrcIdx !== i) {
        const moved = apps.splice(dragSrcIdx, 1)[0];
        apps.splice(i, 0, moved);
        if (selectedIdx === dragSrcIdx) selectedIdx = i;
        else if (dragSrcIdx < selectedIdx && i >= selectedIdx) selectedIdx--;
        else if (dragSrcIdx > selectedIdx && i <= selectedIdx) selectedIdx++;
        renderApps();
        showToast(`Moved: ${moved.name}`, 'info');
      }
    });

    grid.appendChild(card);
  });
}

function selectApp(idx) {
  selectedIdx = idx;
  document.querySelectorAll('.app-card').forEach((c, i) => {
    c.classList.toggle('selected', i === idx);
  });
}

function removeApp(idx) {
  if (apps.length <= 1) { showToast('Cannot remove last app', 'info'); return; }
  const name = apps[idx].name;
  apps.splice(idx, 1);
  if (selectedIdx >= apps.length) selectedIdx = apps.length - 1;
  renderApps();
  showToast(`Removed: ${name}`, 'info');
}

function moveNext() {
  selectedIdx = (selectedIdx + 1) % apps.length;
  renderApps();
  showToast('▶ Next: ' + apps[selectedIdx].name, 'info');
  counts.winkr++;
  updateCounts();
  triggerSignalSpike('wink');
}

function movePrev() {
  selectedIdx = (selectedIdx - 1 + apps.length) % apps.length;
  renderApps();
  showToast('◀ Previous: ' + apps[selectedIdx].name, 'info');
  counts.winkl++;
  updateCounts();
  triggerSignalSpike('wink');
}

async function launchSelected() {
  const app = apps[selectedIdx];
  counts.blink++;
  updateCounts();
  triggerSignalSpike('blink');

  // Flash the card
  const cards = document.querySelectorAll('.app-card');
  if (cards[selectedIdx]) {
    cards[selectedIdx].style.boxShadow = `0 0 30px ${app.color}80`;
    setTimeout(() => { cards[selectedIdx].style.boxShadow = ''; }, 800);
  }

  // Actually launch the app
  if (isElectron && window.navtools) {
    const result = await window.navtools.launchApp(app.cmd || app.id);
    if (result.success) {
      showToast(`✅ Opened: ${app.name}`, 'success');
    } else {
      showToast(`❌ Failed: ${app.name}`, 'info');
    }
  } else {
    showToast(`✅ ${app.name} (demo — run as desktop app for real launch)`, 'success');
  }
}

function goBack() {
  showToast('↩ Back', 'info');
  counts.dblink++;
  updateCounts();
  triggerSignalSpike('double');
}

function updateCounts() {
  document.getElementById('blinkCount').textContent = counts.blink;
  document.getElementById('dblinkCount').textContent = counts.dblink;
  document.getElementById('winklCount').textContent = counts.winkl;
  document.getElementById('winkrCount').textContent = counts.winkr;
}

// ═══════════════════════════════════════════
//  SIGNAL CANVAS
// ═══════════════════════════════════════════
let sigCtx, sigCanvas;
function initSignalCanvas() {
  sigCanvas = document.getElementById('signalCanvas');
  sigCtx = sigCanvas.getContext('2d');
  sigCanvas.width = sigCanvas.clientWidth * 2;
  sigCanvas.height = sigCanvas.clientHeight * 2;
  for (let i = 0; i < MAX_POINTS; i++) signalData.push(0);
}

function drawSignal() {
  const w = sigCanvas.width, h = sigCanvas.height;
  sigCtx.clearRect(0, 0, w, h);

  // Grid
  sigCtx.strokeStyle = 'rgba(255,255,255,0.04)';
  sigCtx.lineWidth = 1;
  for (let y = 0; y < h; y += h / 5) {
    sigCtx.beginPath(); sigCtx.moveTo(0, y); sigCtx.lineTo(w, y); sigCtx.stroke();
  }

  // Gradient line
  const grad = sigCtx.createLinearGradient(0, 0, w, 0);
  grad.addColorStop(0, '#00D4FF');
  grad.addColorStop(0.5, '#7B61FF');
  grad.addColorStop(1, '#FF6B9D');
  sigCtx.strokeStyle = grad;
  sigCtx.lineWidth = 2.5;
  sigCtx.lineJoin = 'round';
  sigCtx.beginPath();
  const step = w / (MAX_POINTS - 1), mid = h / 2, scale = h / 4;
  for (let i = 0; i < signalData.length; i++) {
    const x = i * step, y = mid - signalData[i] * scale;
    if (i === 0) sigCtx.moveTo(x, y); else sigCtx.lineTo(x, y);
  }
  sigCtx.stroke();

  // Glow fill
  sigCtx.lineTo(w, mid); sigCtx.lineTo(0, mid); sigCtx.closePath();
  const fg = sigCtx.createLinearGradient(0, 0, 0, h);
  fg.addColorStop(0, 'rgba(0,212,255,0.08)');
  fg.addColorStop(1, 'rgba(0,212,255,0)');
  sigCtx.fillStyle = fg;
  sigCtx.fill();

  document.getElementById('statAmplitude').textContent =
    (Math.abs(signalData[signalData.length - 1]) * 150).toFixed(0) + ' µV';
}

let spikeQueue = [];
function triggerSignalSpike(type) {
  spikeQueue.push({ type, t: 0 });
  const badge = document.getElementById('signalBadge');
  const labels = { blink: 'BLINK', double: 'DOUBLE', wink: 'WINK' };
  badge.textContent = labels[type] || 'EVENT';
  badge.className = 'signal-badge blink-ev';
  setTimeout(() => { badge.textContent = 'IDLE'; badge.className = 'signal-badge'; }, 1200);
}

// Band Power removed as requested

// ═══════════════════════════════════════════
//  SIMULATION LOOP
// ═══════════════════════════════════════════
function startSimulation() {
  let t = 0;
  setInterval(() => {
    t += 0.05;
    let val = Math.sin(t * 2.1) * 0.1 + Math.sin(t * 5.7) * 0.05
            + Math.sin(t * 13.3) * 0.03 + (Math.random() - 0.5) * 0.08;

    spikeQueue = spikeQueue.filter(s => {
      s.t++;
      if (s.t < 15) {
        const env = Math.sin(s.t / 15 * Math.PI);
        const mag = s.type === 'double' ? 1.4 : s.type === 'wink' ? 0.7 : 1.0;
        val += env * mag * (s.t < 8 ? 1 : -0.6);
        return true;
      }
      return false;
    });

    signalData.push(val);
    if (signalData.length > MAX_POINTS) signalData.shift();

    drawSignal();
    updateSignalHealth();

    const baseline = 120 + Math.sin(t * 0.3) * 15;
    document.getElementById('statBaseline').textContent = baseline.toFixed(0) + ' µV';
    const snr = 2.5 + Math.sin(t * 0.5) * 1.2;
    document.getElementById('statSNR').textContent = snr.toFixed(1) + 'x';
  }, 50);
}

function updateSignalHealth() {
  const bar = document.getElementById('healthBar');
  const label = document.getElementById('healthLabel');
  if (!bar || !label) return;

  // Calculate noise (standard deviation of the tail of signalData)
  const tail = signalData.slice(-30);
  const avg = tail.reduce((a, b) => a + b, 0) / tail.length;
  const variance = tail.reduce((a, b) => a + Math.pow(b - avg, 2), 0) / tail.length;
  const stdDev = Math.sqrt(variance);

  // Quality mapping (higher stdDev = lower quality)
  // Normal simulation noise is ~0.08 stdDev. Spikes go much higher.
  // We want to penalize high constant noise.
  let quality = Math.max(0, 100 - (stdDev * 500));
  if (spikeQueue.length > 0) quality = Math.max(quality, 70); // Don't drop quality just for blinks

  bar.style.width = quality + '%';

  if (quality > 80) {
    bar.style.background = '#2ECC71'; label.textContent = 'EXCELLENT'; label.style.color = '#2ECC71';
  } else if (quality > 50) {
    bar.style.background = '#F1C40F'; label.textContent = 'GOOD'; label.style.color = '#F1C40F';
  } else {
    bar.style.background = '#E74C3C'; label.textContent = 'POOR'; label.style.color = '#E74C3C';
  }
}

// ═══════════════════════════════════════════
//  ADD APP (File Browser)
// ═══════════════════════════════════════════
const APP_COLORS = ['#3498db','#e74c3c','#2ecc71','#f39c12','#9b59b6','#1abc9c','#e84393','#00cec9'];
let colorIdx = 0;

function initModals() {
  // Add App button opens native file browser directly
  document.getElementById('btnAddApp').onclick = async () => {
    if (isElectron && window.navtools) {
      const result = await window.navtools.browseApp();
      if (result.canceled) return;

      const color = APP_COLORS[colorIdx % APP_COLORS.length];
      colorIdx++;

      apps.push({
        id: result.name.toLowerCase().replace(/\s+/g, '_'),
        name: result.name,
        icon: '📂',
        color,
        cmd: `"${result.filePath}"`,
      });
      renderApps();
      showToast(`✅ Added: ${result.name}`, 'success');
    } else {
      showToast('Run as desktop app to browse files', 'info');
    }
  };
}

// ═══════════════════════════════════════════
//  SETTINGS
// ═══════════════════════════════════════════
function initSettings() {
  const panel = document.getElementById('settingsPanel');
  document.getElementById('btnSettings').onclick = () => panel.classList.add('show');
  document.getElementById('settingsClose').onclick = () => panel.classList.remove('show');
  panel.addEventListener('click', (e) => { if (e.target === panel) panel.classList.remove('show'); });

  ['blinkSens', 'winkSens', 'cooldownMs', 'scanSpeed'].forEach(id => {
    const el = document.getElementById(id);
    const valEl = document.getElementById(id.replace('Ms', '') + 'Val') ||
                  document.getElementById(id + 'Val');
    if (el && valEl) el.addEventListener('input', () => { valEl.textContent = el.value; });
  });

  document.getElementById('btnConnect').onclick = () => {
    const dot = document.querySelector('.status-dot');
    const txt = document.querySelector('.status-text');
    dot.classList.toggle('online'); dot.classList.toggle('offline');
    txt.textContent = dot.classList.contains('online') ? 'Connected' : 'Disconnected';
    showToast(dot.classList.contains('online') ? '✅ Connected' : 'Disconnected', 'success');
  };
}

// ═══════════════════════════════════════════
//  KEYBOARD
// ═══════════════════════════════════════════
function initKeyboard() {
  document.addEventListener('keydown', (e) => {
    if (document.querySelector('.modal-overlay.show') ||
        document.querySelector('.settings-overlay.show')) return;

    switch (e.key.toLowerCase()) {
      case 'b': case 'enter': launchSelected(); break;
      case 'd': goBack(); break;
      case 'w': case 'arrowright': moveNext(); break;
      case 'q': case 'arrowleft':  movePrev(); break;
    }
  });

  // ── Direct EOG Control (Python → HTTP → IPC → here) ──────────
  if (window.navtools?.onEogAction) {
    window.navtools.onEogAction((action) => {
      switch (action) {
        case 'right':  moveNext();      break;
        case 'left':   movePrev();      break;
        case 'select': launchSelected(); break;
      }
    });
    console.log('[EOG] Direct control listener registered on port 7891');
  }
}


// ═══════════════════════════════════════════
//  ARDUINO AUTO-CONNECT
// ═══════════════════════════════════════════
function initArduino() {
  const btn = document.getElementById('btnArduino');
  if (!btn) return;

  // Auto-detect on startup
  autoDetectArduino();

  // Header button opens the details modal (if it exists) or re-scans
  btn.onclick = () => {
    const modal = document.getElementById('arduinoDetailsModal');
    if (modal) {
      modal.classList.add('show');
      refreshArduinoModal();
    } else {
      // No modal — just re-scan and show a toast
      autoDetectArduino(true);
    }
  };

  // Modal controls (only wire up if modal exists in HTML)
  const modal = document.getElementById('arduinoDetailsModal');
  if (!modal) return;

  document.getElementById('arduinoModalClose')?.addEventListener('click', () => modal.classList.remove('show'));
  document.getElementById('arduinoModalCancel')?.addEventListener('click', () => modal.classList.remove('show'));
  document.getElementById('btnCopyCode')?.addEventListener('click', () => {
    const code = document.getElementById('arduinoCodeDisplay')?.textContent || '';
    navigator.clipboard.writeText(code);
    showToast('📋 Code copied to clipboard!', 'success');
  });

  document.getElementById('arduinoModalFlash')?.addEventListener('click', async () => {
    const portEl = document.getElementById('arduinoPortName');
    const port = portEl?.textContent;
    if (!port || port === 'N/A' || port === 'Not Detected') {
      showToast('❌ No device detected to flash.', 'info');
      return;
    }

    const flashBtn = document.getElementById('arduinoModalFlash');
    const code = document.getElementById('arduinoCodeDisplay')?.value || '';

    flashBtn.disabled = true;
    flashBtn.textContent = '⚡ Flashing...';
    showToast('⚡ Starting firmware upload...', 'info');

    try {
      const result = await window.navtools.flashArduino({ port, code });
      if (result.success) {
        showToast('✅ Firmware flashed successfully!', 'success');
        updateConnectionStatus(true, port);
      } else {
        showToast(`❌ Flash failed: ${result.error}`, 'info');
        console.error('Flash error:', result.details);
      }
    } catch (err) {
      showToast('❌ Critical error during flash', 'info');
    } finally {
      flashBtn.disabled = false;
      flashBtn.textContent = '⚡ Flash to Device';
    }
  });
}

// Auto-detect Arduino and update header status indicator
async function autoDetectArduino(showToastMsg = false) {
  if (!window.navtools?.detectArduino) return;

  try {
    const detect = await window.navtools.detectArduino();
    if (detect.found && detect.ports.length > 0) {
      const port = detect.ports[0];
      updateConnectionStatus(true, port.port);
      if (showToastMsg) showToast(`✅ Arduino found on ${port.port}`, 'success');
      console.log(`[Arduino] Detected: ${port.description} on ${port.port}`);
    } else {
      updateConnectionStatus(false);
      if (showToastMsg) showToast('⚠ No Arduino detected', 'info');
    }
  } catch (err) {
    updateConnectionStatus(false);
    console.warn('[Arduino] Detection failed:', err);
  }
}

async function refreshArduinoModal() {
  // Guard: modal elements may not exist in current HTML
  const statusBadge = document.getElementById('arduinoModalStatus');
  const deviceName  = document.getElementById('arduinoDeviceName');
  const portName    = document.getElementById('arduinoPortName');
  const codeDisplay = document.getElementById('arduinoCodeDisplay');

  if (statusBadge) { statusBadge.textContent = 'Scanning...'; statusBadge.className = 'status-badge'; }
  if (deviceName)  deviceName.textContent = 'Scanning...';
  if (portName)    portName.textContent = 'Scanning...';

  // Load firmware code
  if (codeDisplay && window.navtools?.readFirmwareCode) {
    const codeResult = await window.navtools.readFirmwareCode();
    codeDisplay.textContent = codeResult.success
      ? codeResult.code
      : '// Error loading code: ' + codeResult.error;
  }

  // Detect hardware
  try {
    const detect = await window.navtools.detectArduino();
    if (detect.found && detect.ports.length > 0) {
      const port = detect.ports[0];
      if (statusBadge) { statusBadge.textContent = 'Detected'; statusBadge.classList.add('online'); }
      if (deviceName)  deviceName.textContent = port.description;
      if (portName)    portName.textContent = port.port;
      updateConnectionStatus(true, port.port);
    } else {
      if (statusBadge) statusBadge.textContent = 'Not Found';
      if (deviceName)  deviceName.textContent = 'No Arduino detected';
      if (portName)    portName.textContent = 'N/A';
      updateConnectionStatus(false);
    }
  } catch (err) {
    if (statusBadge) statusBadge.textContent = 'Error';
    if (deviceName)  deviceName.textContent = 'Detection failed';
    updateConnectionStatus(false);
  }
}


function updateConnectionStatus(online, port = '') {
  const dot = document.querySelector('.status-dot');
  const txt = document.querySelector('.status-text');
  if (online) {
    dot.classList.add('online');
    dot.classList.remove('offline');
    txt.textContent = `Arduino minima r4 (${port})`;
  } else {
    dot.classList.remove('online');
    dot.classList.add('offline');
    txt.textContent = 'Disconnected';
  }
}


// ═══════════════════════════════════════════
//  TOAST
// ═══════════════════════════════════════════
function showToast(msg, type = 'info') {
  const container = document.getElementById('toastContainer');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = msg;
  container.appendChild(toast);
  setTimeout(() => { toast.style.opacity = '0'; toast.style.transform = 'translateY(10px)'; }, 2500);
  setTimeout(() => toast.remove(), 3000);
}

// ═══════════════════════════════════════════
//  CALIBRATION WIZARD LOGIC
// ═══════════════════════════════════════════
let isCalibrating = false;
let calStep = 1;
function initCalibration() {
  const modal = document.getElementById('calibrationModal');
  const btnOpen = document.getElementById('btnCalibrate');
  const btnStart = document.getElementById('btnStartCal');
  const btnFinish = document.getElementById('btnFinishCal');

  if (!btnOpen) return;

  btnOpen.onclick = () => {
    modal.classList.add('show');
    resetCalibration();
  };

  document.getElementById('calClose').onclick = () => {
    modal.classList.remove('show');
    isCalibrating = false;
  };

  btnStart.onclick = startCalibration;
  btnFinish.onclick = () => {
    modal.classList.remove('show');
    showToast('🚀 Calibration Applied!', 'success');
  };
}

function resetCalibration() {
  calStep = 1;
  isCalibrating = false;
  updateCalUI();
}

function updateCalUI() {
  document.querySelectorAll('.cal-step-content').forEach(c => c.classList.add('hidden'));
  document.getElementById(`calStep${calStep}`).classList.remove('hidden');
  document.querySelectorAll('.step').forEach((s, i) => {
    s.classList.toggle('active', i + 1 === calStep);
  });
}

async function startCalibration() {
  isCalibrating = true;
  calStep = 2;
  updateCalUI();

  const timer = document.getElementById('calTimer');
  const ring = document.getElementById('calProgressCircle');
  
  let timeLeft = 5;
  const interval = setInterval(() => {
    timeLeft--;
    timer.textContent = timeLeft;
    const progress = (5 - timeLeft) / 5 * 100;
    ring.style.strokeDasharray = `${progress}, 100`;

    if (timeLeft <= 0) {
      clearInterval(interval);
      finishCalibration();
    }
  }, 1000);
}

function finishCalibration() {
  calStep = 3;
  updateCalUI();
  isCalibrating = false;
  
  // Simulated results based on current signal
  const noise = (0.05 + Math.random() * 0.02).toFixed(2);
  const threshold = (0.7 + Math.random() * 0.2).toFixed(1);
  
  document.getElementById('calBlinkVal').textContent = threshold + 'V';
  document.getElementById('calNoiseVal').textContent = noise + 'V';
  
  // Update actual settings
  const sens = document.getElementById('blinkSens');
  if (sens) sens.value = Math.round(threshold * 5);
}

// ── Ripple effect on blink ──
function triggerRipple() {
  const selected = document.querySelector('.app-card.selected');
  if (selected) {
    selected.classList.remove('blink-hit');
    void selected.offsetWidth; // trigger reflow
    selected.classList.add('blink-hit');
    setTimeout(() => selected.classList.remove('blink-hit'), 800);
  }
}

// Update simulation loop to trigger ripple
const originalTriggerSpike = triggerSignalSpike;
triggerSignalSpike = function(type) {
  originalTriggerSpike(type);
  if (type === 'blink' || type === 'double') triggerRipple();
};

// ═══════════════════════════════════════════
//  DATA COLLECTION LOGIC
// ═══════════════════════════════════════════
function initDataCollection() {
  const modal = document.getElementById('collectionModal');
  const btnOpen = document.getElementById('btnOpenCollection');
  const btnLaunch = document.getElementById('btnLaunchExp');
  const subIdInput = document.getElementById('subjectIdInput');
  const subIdDisplay = document.getElementById('subIdDisplay');

  if (!btnOpen) return;

  btnOpen.onclick = () => {
    modal.classList.add('show');
    const id = subIdInput.value.toString().padStart(3, '0');
    subIdDisplay.textContent = id;
  };

  document.getElementById('colClose').onclick = () => modal.classList.remove('show');

  subIdInput.oninput = () => {
    const id = subIdInput.value.toString().padStart(3, '0');
    subIdDisplay.textContent = id;
  };

  btnLaunch.onclick = async () => {
    const subjectId = subIdInput.value;
    const port = 'COM7'; 

    btnLaunch.disabled = true;
    btnLaunch.textContent = '🚀 Launching Experiment...';
    showToast('🚀 Launching Pygame Experiment...', 'info');

    try {
      const result = await window.navtools.collectData({ subjectId, port });
      if (result.success) {
        showToast('✅ Collection session completed!', 'success');
      } else {
        showToast('❌ Failed to launch experiment', 'info');
        console.error('Collection error:', result.error);
      }
    } catch (err) {
      showToast('❌ Error starting collection', 'info');
    } finally {
      btnLaunch.disabled = false;
      btnLaunch.textContent = 'Launch Experiment Window';
      modal.classList.remove('show');
    }
  };
}
