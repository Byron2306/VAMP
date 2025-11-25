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

✅ **AI Server (Ollama)**
- Check if Ollama is running at `http://127.0.0.1:11434`
- Verify Gemma3:4b-b model is installed
- Offer to download the model if missing (5-10 minutes)
- Continue in offline mode if Ollama isn't available

✅ **Backend Services**
- Launch REST API server (port 8000)
- Launch WebSocket bridge (port 8000)
- Both run in separate Command Prompt windows
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

### Phase 6: Ollama AI Server (~5-10 minutes if downloading model)
```
[6/7] Checking Ollama AI server...
[INFO] Testing connection to http://127.0.0.1:11434...

[OK] Ollama server is running and reachable.
[INFO] Checking Ollama models...
[INFO] Downloading Gemma3:4b-b model (this may take 5-10 minutes)...
[OK] Gemma model is available.
```

### Phase 7: Services Launch (~30 seconds)
```
[7/7] Launching VAMP backend services...
[INFO] Starting REST API server (port 8000)...
[OK] REST API server launched in new window.

[INFO] Starting WebSocket bridge (port 8000)...
[OK] WebSocket bridge launched in new window.

[INFO] Performing health checks...
[OK] REST API is responding.

========================================================================
SUCCESS! VAMP Backend is Ready
========================================================================

[OK] All services are running:
  - REST API: http://localhost:8000/api/*
  - WebSocket Bridge: ws://localhost:8000
  - Ollama AI: http://127.0.0.1:11434 (if available)

[INFO] Next steps:
  1. Open your browser and navigate to: http://localhost:8000/dashboard
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

**Solution B - Start Ollama:**
- If already installed, open Command Prompt/Terminal
- Run: `ollama serve`
- This starts the local API at `http://127.0.0.1:11434`
- Keep this terminal open while using VAMP

**Solution C - Continue without AI:**
- The setup script can continue in offline mode
- AI-powered features will be disabled
- Basic scanning and session management will still work

### "REST API failed to start"
**Solution:**
- Port 8000 may be in use by another application
- Find and close the other application
- Or modify the backend code to use a different port
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
- Open browser: `http://localhost:8000/dashboard`
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
- **Disk Space**: ~2GB minimum (for Playwright + Ollama models)
- **RAM**: 4GB minimum (8GB+ recommended for AI features)
- **Network**: Internet access for downloads and API calls
- **Ports**: 8000 (REST API), 11434 (Ollama)

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
