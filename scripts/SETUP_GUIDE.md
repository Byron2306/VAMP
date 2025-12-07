# VAMP Backend - Complete Auto-Setup Guide

## Quick Start (One-Click Setup)

For **Windows users**, this is all you need to do:

### Step 1: Run the Setup Script
1. Open **File Explorer** and navigate to your VAMP repository root
2. Go to the `scripts` folder
3. **Double-click** `setup_backend.bat`
   - This single script handles everything automatically!

### What the Script Does Automatically
The `setup_backend.bat` script will:

✅ **Python Setup**
- Verify Python 3.10+ is installed
- Create a virtual environment (`.venv`)
- Activate the virtual environment
- Upgrade pip to the latest version

✅ **Dependencies Installation**
- Install all pip packages from `requirements.txt`
- Install Playwright browser binaries (2-5 minutes first time)
- Detect Chrome browser installation
- Skip AI setup entirely (Ollama/Tesseract are optional; AI insights are disabled if not running)

✅ **Backend Services**
- Launch REST API + Socket.IO server (default `127.0.0.1:8080`)
- Optionally start the legacy WebSocket bridge when `START_WS_BRIDGE=1` (default disabled)
- Services run in separate Command Prompt windows
- Perform health checks

✅ **Status Reporting**
- Clear color-coded progress messages
- Detailed error messages with troubleshooting hints
- Final summary showing all running services

---

## What You See During Setup

### Phase 1-5: Initial Checks & Setup (~2-3 minutes)
```
[1/7] Verifying Python 3.10+ installation...
[OK] Python found: 3.11.7

[2/7] Setting up Python virtual environment...
[OK] Virtual environment activated.

[3/7] Installing Python dependencies...
[OK] All dependencies installed successfully.

[4/7] Installing Playwright browsers...
[INFO] This may take 2-5 minutes on first run (one-time only)
[OK] Playwright browsers installed successfully.

[5/7] Verifying Chrome browser...
[OK] Chrome found in PATH.
```

### Phase 6: Services Launch (~30 seconds)
```
[6/6] Launching VAMP backend services...
[INFO] Starting REST API server (port 8080)...
[OK] REST API server launched in new window.

[INFO] Starting WebSocket bridge (port 8765)... (only when START_WS_BRIDGE=1)
[OK] WebSocket bridge launched in new window.

[INFO] Performing health checks...
[OK] REST API is responding.

========================================================================
SUCCESS! VAMP Backend is Ready
========================================================================

[OK] All services are running:
  - REST API + Socket.IO: http://localhost:8080/api/*
  - WebSocket Bridge: ws://localhost:8765 (if enabled)

[INFO] Next steps:
  1. Open your browser and navigate to: http://localhost:8080/dashboard
  2. Load the VAMP extension in Chrome (chrome://extensions)
  3. Log into your email/cloud accounts in Chrome
  4. Enroll in the extension using your email
  5. Start scanning!
```

---

## Troubleshooting

### "Python not found in PATH"
**Solution:**
- Download Python 3.10+ from https://www.python.org/downloads/
- **IMPORTANT**: During installation, check the box "Add Python to PATH"
- Restart your computer after installation
- Run the setup script again

### "Failed to install dependencies"
**Solution:**
- Open a Command Prompt in the repo root
- Run: `python -m pip install --upgrade pip`
- Run: `python -m pip install -r requirements.txt`
- Then run the setup script again

### "Playwright install failed"
**Solution:**
- Open Command Prompt in the repo root
- Activate venv: `.venv\Scripts\activate`
- Run: `python -m playwright install --with-deps`
- This requires ~2GB disk space and 5-10 minutes

### "Ollama not running"
**Solution A - Install Ollama:**
- Download from https://ollama.ai
- Run the installer
- After install, Ollama auto-starts as a background service

AI runtimes are optional. If you do not have a local AI endpoint running, the backend simply disables AI-assisted insights and continues.

### "REST API failed to start"
**Solution:**
- Port 8080 may be in use by another application
- Find and close the other application
- Or modify `VAMP_AGENT_PORT` to use a different port
- Then run the setup script again

### "Chrome not found"
**Solution:**
- Download Chrome from https://www.google.com/chrome/
- Install normally
- The setup script will auto-detect it
- Extension features require Chrome to be installed

---

## Next Steps After Setup

### 1. Access the Dashboard
- Open browser: `http://localhost:8080/dashboard`
- View connector status, sessions, and evidence
- Monitor health metrics

### 2. Load the Extension
- Go to `chrome://extensions`
- Enable "Developer mode" (top right)
- Click "Load unpacked"
- Select the `frontend/extension/` folder

### 3. First-Time Login
- Go to https://outlook.office.com (or your email platform)
- Log in normally in Chrome
- This saves your session for the extension to use
- Repeat for OneDrive, Google Drive, etc.

### 4. Enroll in Extension
- Open the VAMP extension (puzzle icon in Chrome)
- Click "Enroll"
- Enter your email and name
- Click "Enroll Now"

### 5. Start Scanning
- Use the extension UI to trigger scans
- View results on the dashboard
- Export reports as needed

---

## Keep It Running

The backend services run in separate Command Prompt windows. **Keep these windows open** while using VAMP:

- **REST API Window**: Shows server logs and API requests
- **WebSocket Bridge Window**: Shows real-time event updates
- **Main Setup Window**: Shows status messages

### To Stop Services
Press **CTRL+C** in any Command Prompt window to stop that service.

---

## System Requirements

- **OS**: Windows 10 or later (with Admin access for first-time setup)
- **Disk Space**: ~2GB minimum (for Playwright browsers)
- **RAM**: 4GB minimum (8GB+ recommended when running Playwright + OCR)
- **Network**: Internet access for downloads and API calls
- **Ports**: 8080 (REST + Socket.IO), 8765 (legacy WebSocket bridge if enabled)

---

## Support

If you encounter issues:
1. Check the troubleshooting section above
2. Review the script console output for specific error messages
3. Check GitHub Issues: https://github.com/Byron2306/VAMP/issues
4. Consult the main README for detailed architecture info

---

## Advanced: Manual Setup (Not Recommended)

If the automated script fails, you can do this manually:

```batch
REM Activate venv
.venv\Scripts\activate

REM Install dependencies
pip install -r requirements.txt
python -m playwright install

REM Start services (in separate terminals)
python -m backend.app_server
python -m backend.ws_bridge
```

But this is much more error-prone. **Stick with the automated script!**

---

**Last Updated**: November 25, 2025
**Script Version**: setup_backend.bat v2.0 (Fully Automated)
