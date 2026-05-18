const { app, BrowserWindow, ipcMain, shell, dialog } = require('electron');
const { exec } = require('child_process');
const path = require('path');
const os   = require('os');
const http = require('http');

let mainWindow;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 900,
    minHeight: 600,
    title: 'NavTools — EOG Assistive Navigation',
    icon: path.join(__dirname, 'icon.ico'),
    backgroundColor: '#0a0e17',
    autoHideMenuBar: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js')
    }
  });

  mainWindow.loadFile('index.html');
  mainWindow.setMenuBarVisibility(false);

  if (process.argv.includes('--dev')) {
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  }
}

// ── EOG HTTP Control Server (port 7891) ──────────────────────
// Python navtools_eog_control.py sends GET /right, /left, /select
const EOG_PORT = 7891;
const eogServer = http.createServer((req, res) => {
  const action = req.url.replace('/', '').trim();   // 'right' | 'left' | 'select'
  if (['right', 'left', 'select'].includes(action) && mainWindow) {
    mainWindow.webContents.send('eog-action', action);
    res.writeHead(200, { 'Content-Type': 'text/plain' });
    res.end('ok');
    console.log(`[EOG] action received: ${action}`);
  } else {
    res.writeHead(404);
    res.end('unknown');
  }
});
eogServer.listen(EOG_PORT, '127.0.0.1', () => {
  console.log(`[EOG] Control server listening on port ${EOG_PORT}`);
});


// ── App launch commands (Windows) ──
const APP_COMMANDS = {
  browser:    { cmd: 'start https://www.google.com', label: 'Browser' },
  folder:     { cmd: `explorer "${path.join(os.homedir(), 'Documents')}"`, label: 'File Explorer' },
  camera:     { cmd: 'start microsoft.windows.camera:', label: 'Camera' },
  notepad:    { cmd: 'notepad', label: 'Notepad' },
  calculator: { cmd: 'calc', label: 'Calculator' },
  settings:   { cmd: 'start ms-settings:', label: 'Settings' },
  music:      { cmd: 'start mswindowsmusic:', label: 'Music' },
  photos:     { cmd: `explorer "${path.join(os.homedir(), 'Pictures')}"`, label: 'Photos' },
  terminal:   { cmd: 'wt', label: 'Terminal' },
  paint:      { cmd: 'mspaint', label: 'Paint' },
  wordpad:    { cmd: 'write', label: 'WordPad' },
  snip:       { cmd: 'snippingtool', label: 'Snipping Tool' },
  taskmanager:{ cmd: 'taskmgr', label: 'Task Manager' },
  mail:       { cmd: 'start outlookmail:', label: 'Mail' },
  maps:       { cmd: 'start bingmaps:', label: 'Maps' },
};

// ── IPC: Launch data collection experiment ──
ipcMain.handle('collect-data', async (event, params) => {
  const { subjectId, port } = params;
  const scriptPath = path.join(__dirname, '..', 'src', 'test_blink_wink.py');
  
  // Use 'python' or 'python3' based on environment
  // We'll try to use the current environment's python
  const cmd = `python -m src.test_blink_wink --subject ${subjectId} --port ${port}`;
  
  return new Promise((resolve) => {
    // Run in project root
    const projectRoot = path.join(__dirname, '..');
    exec(cmd, { cwd: projectRoot, shell: true }, (err, stdout, stderr) => {
      if (err) {
        console.error(`Data collection failed:`, stderr);
        resolve({ success: false, error: stderr || err.message });
      } else {
        resolve({ success: true, output: stdout });
      }
    });
  });
});

// ── IPC: Launch app ──
ipcMain.handle('launch-app', async (event, appId) => {
  const entry = APP_COMMANDS[appId];
  if (!entry) {
    // Try as a raw command
    return new Promise((resolve) => {
      exec(appId, { shell: true }, (err) => {
        resolve({ success: !err, app: appId });
      });
    });
  }

  return new Promise((resolve) => {
    exec(entry.cmd, { shell: true }, (err) => {
      if (err) {
        console.error(`Failed to launch ${entry.label}:`, err.message);
        resolve({ success: false, app: entry.label, error: err.message });
      } else {
        console.log(`Launched: ${entry.label}`);
        resolve({ success: true, app: entry.label });
      }
    });
  });
});

// ── IPC: Open folder dialog ──
ipcMain.handle('open-path', async (event, folderPath) => {
  shell.openPath(folderPath);
  return { success: true };
});

// ── IPC: Browse for application ──
ipcMain.handle('browse-app', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: 'Select Application',
    properties: ['openFile'],
    filters: [
      { name: 'Applications', extensions: ['exe', 'lnk', 'bat', 'cmd'] },
      { name: 'All Files', extensions: ['*'] }
    ],
    defaultPath: 'C:\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs'
  });

  if (result.canceled || result.filePaths.length === 0) {
    return { canceled: true };
  }

  const filePath = result.filePaths[0];
  const baseName = path.basename(filePath, path.extname(filePath));

  return {
    canceled: false,
    filePath,
    name: baseName,
    ext: path.extname(filePath),
  };
});

// ── IPC: Detect Arduino on COM ports ──
ipcMain.handle('detect-arduino', async () => {
  return new Promise((resolve) => {
    // [System.IO.Ports.SerialPort]::GetPortNames() is the most reliable way
    // to list ALL available COM ports on Windows — same API Python uses internally.
    const psCmd = `[System.IO.Ports.SerialPort]::GetPortNames() | ConvertTo-Json`;

    exec(
      `powershell -NoProfile -NonInteractive -Command "${psCmd}"`,
      { shell: true, timeout: 5000 },
      (err, stdout) => {
        let ports = [];

        if (!err && stdout && stdout.trim()) {
          try {
            let raw = stdout.trim();
            // GetPortNames returns a string or array
            let parsed = JSON.parse(raw);
            if (!Array.isArray(parsed)) parsed = [parsed];
            ports = parsed
              .filter(p => typeof p === 'string' && p.match(/^COM\d+$/i))
              .map(p => ({ port: p.toUpperCase(), description: `Arduino minima r4 (${p})` }));
          } catch (e) {
            // Plain text fallback (no JSON, single port)
            const matches = stdout.match(/COM\d+/gi) || [];
            ports = [...new Set(matches)].map(p => ({
              port: p.toUpperCase(),
              description: `Arduino minima r4 (${p})`
            }));
          }
        }

        // Secondary fallback: `mode` command
        if (ports.length === 0) {
          exec('mode', { shell: true, timeout: 3000 }, (_e, out) => {
            const matches = out?.match(/COM\d+/gi) || [];
            const unique = [...new Set(matches)];
            resolve({
              found: unique.length > 0,
              ports: unique.map(p => ({ port: p.toUpperCase(), description: `Arduino minima r4 (${p})` }))
            });
          });

        } else {
          // Prefer the port that matches known Arduino names by trying a quick
          // PnP lookup, but don't block on it — return what we have immediately.
          resolve({ found: true, ports });
        }
      }
    );
  });
});



// ── IPC: Flash firmware to Arduino ──
ipcMain.handle('flash-arduino', async (event, { port, code }) => {
  const sketchPath = path.resolve(__dirname, '..', 'firmware', 'eeg_stream.ino');
  const sketchDir = path.dirname(sketchPath);

  // Save the (potentially edited) code first
  try {
    const fs = require('fs').promises;
    await fs.writeFile(sketchPath, code, 'utf8');
  } catch (err) {
    return { success: false, error: 'Failed to save code before flash', details: err.message };
  }

  const possiblePaths = [
    'arduino-cli',
    path.join(os.homedir(), 'AppData', 'Local', 'Arduino15', 'arduino-cli.exe'),
    'C:\\Program Files\\Arduino IDE\\resources\\app\\lib\\backend\\resources\\arduino-cli.exe',
  ];

  // Helper to check CLI sequentially
  const findCli = async () => {
    for (const cli of possiblePaths) {
      try {
        const result = await new Promise((resolve, reject) => {
          exec(`"${cli}" version`, { shell: true, timeout: 3000 }, (err, stdout) => {
            if (!err && stdout) resolve(cli);
            else reject();
          });
        });
        if (result) return result;
      } catch (e) { /* continue */ }
    }
    return null;
  };

  const cli = await findCli();

  if (!cli) {
    return new Promise((resolve) => {
      // Fallback to 'arduino' command (Arduino IDE 1.x)
      const ideCmd = `arduino --upload --port ${port} --board arduino:renesas_uno:unor4wifi "${sketchPath}"`;
      exec(ideCmd, { shell: true, timeout: 120000 }, (err, stdout, stderr) => {
        if (err) {
          resolve({
            success: false,
            error: 'arduino-cli not found and IDE fallback failed.',
            details: stderr || err.message,
          });
        } else {
          resolve({ success: true, output: stdout });
        }
      });
    });
  }

  return new Promise((resolve) => {
    // For Arduino R4 Minima/WiFi
    const fqbn = 'arduino:renesas_uno:unor4wifi';
    const uploadCmd = `"${cli}" compile --upload -b ${fqbn} -p ${port} "${sketchDir}"`;

    exec(uploadCmd, { shell: true, timeout: 120000 }, (err, stdout, stderr) => {
      if (err) {
        resolve({
          success: false,
          error: 'Upload failed',
          details: stderr || err.message,
          output: stdout,
        });
      } else {
        resolve({ success: true, output: stdout });
      }
    });
  });
});

// ── IPC: Read firmware code ──
ipcMain.handle('read-firmware-code', async () => {
  const sketchPath = path.resolve(__dirname, '..', 'firmware', 'eeg_stream.ino');
  try {
    const fs = require('fs').promises;
    const code = await fs.readFile(sketchPath, 'utf8');
    return { success: true, code };
  } catch (err) {
    return { success: false, error: err.message };
  }
});

// ── IPC: Window controls ──
ipcMain.on('window-minimize', () => mainWindow?.minimize());
ipcMain.on('window-maximize', () => {
  if (mainWindow?.isMaximized()) mainWindow.unmaximize();
  else mainWindow?.maximize();
});
ipcMain.on('window-close', () => mainWindow?.close());

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});
