# VAMP Scripts - Backend Setup & Management Tools

> **Complete automated backend setup for non-technical users**

This directory contains all the scripts needed to set up, manage, and troubleshoot the VAMP backend services. No manual PowerShell or Command Prompt experience required!

## 🚀 Quick Start

### For New Users (First Time Setup)

1. **Double-click `setup_backend.bat` in this folder**
   - Creates `.venv`, installs requirements + Playwright browsers, and starts the canonical `backend.app_server` on `127.0.0.1:8080`.
   - Nothing else is required. Let the two spawned Command Prompt windows stay open while you use VAMP.
   - Takes 5–15 minutes depending on your system and Playwright download speed.

### For Existing Users (Restart Services)

- **Double-click `quick_restart_backend.bat`**
  - Quickly restarts the running services using the existing `.venv`.
  - Use if services crash or you need a clean restart.
  - Takes ~30 seconds.

---

## 📋 Available Scripts

### 1. **setup_backend.bat** ⭐ START HERE

**Purpose**: Complete first-time backend setup and launch

**What it does**:
- ✅ Verifies Python is available
- ✅ Creates Python virtual environment (`.venv`)
- ✅ Installs all pip dependencies from `requirements.txt`
- ✅ Installs Playwright browser binaries (one-time download)
- ✅ Launches REST + Socket.IO server (`backend.app_server`) on `127.0.0.1:8080`
- ✅ Optionally launches the legacy plain WebSocket bridge (`backend.ws_bridge`) if `START_WS_BRIDGE=1`
- ✅ Performs a quick health check against `/api/health`
- ✅ Shows clear status messages and next steps

**How to run**:
```batch
Double-click setup_backend.bat
```
Or from Command Prompt:
```batch
cd scripts
setup_backend.bat
```

**Output**: Two Command Prompt windows open by default:
1. Main setup window (closes after completion)
2. REST + Socket.IO server window (keep open)

If `START_WS_BRIDGE=1` is set, a third window hosts the optional legacy bridge on port `8765`.

**Time to completion**: ~5–15 minutes on first run
- Python setup: 1–2 minutes
- Playwright install: 2–5 minutes (first time only)
- Services launch: ~30 seconds

**What to do after**: See SETUP_GUIDE.md "Next Steps After Setup"

---

### 2. **quick_restart_backend.bat** 🔄 QUICK RESTART

**Purpose**: Fast restart of backend services without full setup

**What it does**:
- ✅ Checks virtual environment exists
- ✅ Activates venv quickly
- ✅ Restarts REST API and WebSocket bridge
- ✅ Performs quick health check
- ✅ Shows service status

**When to use**:
- Services crashed or hung
- You need to restart without full re-setup
- Development/testing workflows
- Quick service recovery

**How to run**:
```batch
Double-click quick_restart_backend.bat
```

**Time to completion**: ~30 seconds

**Prerequisites**: 
- `setup_backend.bat` must have been run successfully at least once
- Virtual environment must exist at `..\.venv`

---

### 3. **check_ollama.py** 🤖 AI SERVER CHECK

**Purpose**: Verify Ollama AI server is running and accessible

**What it does**:
- Checks if Ollama is running at `http://127.0.0.1:11434`
- Lists available models
- Verifies connection health

**How to run**:
```batch
python check_ollama.py
```

**Output example**:
```
Ollama API Health Check
=======================
API URL: http://127.0.0.1:11434
Status: ✓ Reachable
Available Models:
  - gemma3:4b-b (4.5 GB)
  - mistral:latest (4.1 GB)
```

---

### 4. **refresh_state.py** 🔄 SESSION STATE REFRESH

**Purpose**: Refresh browser session state for platform connectors

**What it does**:
- Updates stored session credentials
- Re-captures browser authentication state
- Useful after password changes or session expiry

**How to run**:
```batch
python refresh_state.py outlook --identity your.email@company.com
```

**Supported platforms**:
- `outlook` - Microsoft Outlook/Microsoft 365
- `onedrive` - OneDrive
- `google` - Google Drive
- `nextcloud` - Nextcloud
- `efundi` - Efundi

---

## 📚 Complete Guide

For detailed setup instructions, troubleshooting, and post-setup steps:

👉 **Read: [SETUP_GUIDE.md](SETUP_GUIDE.md)**

Includes:
- Step-by-step instructions
- What to expect at each phase
- Troubleshooting for common errors
- Next steps after setup
- System requirements
- Advanced manual setup

---

## 🆘 Quick Troubleshooting

| Problem | Solution |
|---------|----------|
| "Python not found" | Install Python 3.10+ from python.org, check "Add to PATH" |
| "Failed to install dependencies" | Run `python -m pip install --upgrade pip` first |
| "Playwright failed" | Run `python -m playwright install --with-deps` manually |
| "REST API failed to start" | Port 8080 is in use, close other applications or set `VAMP_AGENT_PORT` |
| "Services crash immediately" | Check error in Command Prompt window, see SETUP_GUIDE.md |

**For detailed troubleshooting**: See SETUP_GUIDE.md "Troubleshooting" section

---

## 📁 Workflow Examples

### First-Time Setup
```
1. Navigate to scripts folder
2. Double-click setup_backend.bat
3. Wait for completion (10-30 minutes)
4. Backend services are now running!
5. Read next steps in SETUP_GUIDE.md
```

### Daily Usage
```
1. Double-click setup_backend.bat (or quick_restart_backend.bat if restarting)
2. Wait for services to launch
3. Open browser to http://127.0.0.1:8080/
4. Load VAMP extension in Chrome
5. Use the extension to trigger scans
```

### Service Recovery After Crash
```
1. Double-click quick_restart_backend.bat
2. Services restart in ~30 seconds
3. Back to normal operation
```

### Development & Testing
```
1. Use quick_restart_backend.bat for frequent restarts
2. Modify backend code as needed
3. Each restart picks up code changes
4. Use Command Prompt windows to see live logs
```

---

## 🔧 Advanced Usage

### Running Scripts from Command Prompt

```batch
REM Navigate to scripts folder
cd path\to\VAMP\scripts

REM Run setup
setup_backend.bat

REM Or run quick restart
quick_restart_backend.bat
```

### Running Python Scripts Directly

```batch
REM Activate virtual environment
..\.\ venv\Scripts\activate

REM Check Ollama
python check_ollama.py

REM Refresh session state
python refresh_state.py outlook --identity user@example.com
```

### Customizing Port Numbers

If port 8080 is in use, set an alternate host/port using environment variables before launching:

```batch
set VAMP_AGENT_HOST=0.0.0.0
set VAMP_AGENT_PORT=9090
set START_WS_BRIDGE=0
setup_backend.bat
```

---

## 📊 System Requirements

- **OS**: Windows 10 or later
- **Python**: 3.10 or later
- **RAM**: 4GB minimum (8GB+ recommended)
- **Disk**: 2GB minimum (for Playwright downloads)
- **Ports**: 8080 (REST + Socket.IO), 8765 (optional legacy WebSocket bridge if enabled)
- **Browser**: Chrome (for extension features)

---

## 📝 Log Files & Debugging

When services run in Command Prompt windows, all logs appear in real-time:

**REST API Window**:
- Shows incoming API requests
- Backend errors and exceptions
- Database queries

**Optional WebSocket Bridge Window** (only when `START_WS_BRIDGE=1`):
- Shows connected clients
- Real-time event broadcasts
- Connection/disconnection logs

**Main Setup Window**:
- Setup progress
- Error messages
- Next steps instructions

---

## ❓ FAQ

**Q: Can I move these scripts?**
A: No, they're designed to work from the `scripts` folder. They reference `..` for the repo root.

**Q: What if I already have Python installed?**
A: The script will detect it automatically. If it's not in PATH, reinstall with "Add to PATH" checked.

**Q: Do I need to keep Command Prompt windows open?**
A: Yes! The backend runs in those windows. Closing them stops the services.

**Q: Can I customize the setup?**
A: Edit the script files (advanced users) or modify environment variables before running.

**Q: What if I want to uninstall everything?**
A: Delete the `.venv` folder and reinstall from scratch by running `setup_backend.bat` again.

---

## 🔗 Related Documentation

- [SETUP_GUIDE.md](SETUP_GUIDE.md) - Detailed setup walkthrough
- [Main README](../README.md) - Project overview
- [Backend Architecture](../docs/backend.md) - Technical details

---

## 🚨 Support

If you encounter issues:

1. **Check SETUP_GUIDE.md** troubleshooting section
2. **Review Command Prompt output** for error messages
3. **Check GitHub Issues**: https://github.com/Byron2306/VAMP/issues
4. **Review logs** in the main repo logs folder

---

**Last Updated**: November 25, 2025  
**VAMP Version**: 8.0+  
**Script Version**: v2.0 (Fully Automated)
