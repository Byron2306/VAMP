# 🧠 VAMP Agent — Visual AI Metadata Parser

## Overview

The **VAMP Agent** is a stealthy, browser-based deep content analysis tool that scrapes, reads, scores, and normalizes information from platforms like:

- 📧 Outlook / Office365
- ☁️ OneDrive
- 🧾 Google Drive
- 🌐 NextCloud
- 🎓 eFundi LMS

It uses **Playwright** for authenticated browser automation, **NWU Brain** for scoring extracted evidence, and a **WebSocket bridge** for frontend-extension integration.

> ⚠️ **Platform automation notice**: Use this project only where you have explicit permission to automate logins, scraping, or metadata extraction. Review each platform's terms of service and anti-automation policies (Outlook/Office365, OneDrive, Google Drive, NextCloud, eFundi) before running connectors, and add any required trademark or usage notices when demonstrating the tool.

## 🏗 System Architecture

```
Unified Agent Server (backend.app_server)
├── REST API (/api/*)
│   ├── Auth vault + audit (backend.agent_app.auth_manager)
│   ├── Connector plugins (backend.agent_app.plugin_manager)
│   ├── Evidence vault (backend.agent_app.evidence_store)
│   └── Self-update status (backend.agent_app.update_manager)
└── WebSocket bridge / automation runtimes
    ├── backend.ws_bridge ↔ frontend extension
    └── backend.vamp_agent ↔ NWU Brain (scoring)
```

## 📂 Repository Layout

```
VAMP/
├── README.md
├── backend/              # Python backend package
│   ├── agent_app/        # Agent-as-app runtime (vault, plugins, API)
│   ├── data/
│   │   ├── agent_app/    # Connector manifests + persisted config
│   │   ├── nwu_brain/    # Scoring manifest + policy knowledge base
│   │   ├── states/       # Browser storage state (created at runtime)
│   │   └── store/        # User evidence store (created at runtime)
│   ├── platform_plugins/ # Built-in connector implementations
│   ├── nwu_brain/        # NWU scorer implementation
│   ├── app_server.py
│   ├── vamp_agent.py
│   ├── vamp_master.py
│   ├── vamp_runner.py
│   ├── vamp_store.py
│   └── ws_bridge.py
├── frontend/
│   └── extension/        # Chrome extension source (incl. icons/, sounds/)
├── requirements.txt
└── scripts/
    ├── setup_backend.bat     # one-click Windows bootstrap
    ├── quick_restart_backend.bat
    ├── refresh_state.py
    └── SETUP_GUIDE.md
```

## 🚀 Features

- 🔐 Session-state auth: refreshable Playwright storage_state files captured locally (no cloud OAuth flows)
- 🧠 Full content scraping + keyword scoring
- 📜 Auto-scroll & deep content extraction
- 💾 Durable browser storage states with optional password vault entries for scripted logins
- 🔍 Works with Google, Microsoft, Sakai platforms
- 🪡 Integrated with NWU's custom scoring engine
- 🧾 Emits per-scan evidence counts to simplify "zero result" troubleshooting
- 🧱 Modular plugin design: connectors can be enabled/disabled or reconfigured live from the agent dashboard
- 🗂 Evidence vault + chain-of-custody controls surfaced via REST/CLI
- 🔄 Self-update checks and rollback orchestration managed by the agent

## ✅ Data handling and prompt safety

- Keep the NWU Brain corpus (policy text, clause packs, routing manifests) within approved NWU environments. Do **not** forward the raw corpus to third-party AI endpoints or logging providers without explicit approval and a data-sharing agreement.
- When inspecting prompts or debugging AI calls, redact policy text in logs. The backend already sends only canonical, scored fields to the assistant; avoid additional logging of full prompts.
- Refer to `backend/data/nwu_brain/PROVENANCE.md` to confirm ownership/permission for each knowledge asset before redistribution.

## 🧪 Setup Instructions

### 1. ✅ Prerequisites

- Python 3.10+
- Chrome installed (uses your live profile)
- `Playwright` + browser dependencies installed
- Optional: selective content-handling extras (OCR, archive inspection, MIME sniffing). See [`docs/connector_reliability.md`](docs/connector_reliability.md) for a minimal, install-as-needed list.

### 2. 🛠 Install Requirements

```bash
pip install -r requirements.txt
playwright install
```

If you need broader content handling (OCR, archives, Office docs) without bloating the default install, cherry-pick the packages listed in [`docs/connector_reliability.md`](docs/connector_reliability.md) rather than installing everything by default.

### 3. ▶️ Start the unified agent server

```bash
python -m backend.app_server
```

The server exposes a REST API on `http://localhost:8080/api/*` that powers:

- `/api/health` – consolidated diagnostics
- `/api/connectors` – manage platform plugins (enable/disable/update without restarts)
- `/api/auth/*` – refresh Playwright session state, inspect audit trails, and rotate saved passwords
- `/api/evidence` – browse or purge retained evidence with chain-of-custody logs
- `/api/updates/*` – self-update checks, apply, and rollback

> `backend.ws_bridge` and the browser extension now communicate via the agent server. Existing automation entrypoints (`vamp_agent.py`) continue to function but source credentials and configuration exclusively from the agent runtime.

Hosts and ports follow the architecture defaults (`VAMP_AGENT_HOST=127.0.0.1`, `VAMP_AGENT_PORT=8080`).

If you prefer the Windows helper, run `scripts\setup_backend.bat` (see [`docs/SETUP_BACKEND.md`](docs/SETUP_BACKEND.md)). It provisions the virtual environment, installs requirements and Playwright browsers, then starts `backend.app_server`. AI dependencies are optional; the script will print that Ollama is optional and continue.

### 3b. 🔍 Inspect the agent status live

Once the server is running, hit `GET /api/ai/status` to confirm that:

- the socket bridge sees your browser session (`runtime.connected_clients`),
- the last WebSocket action routed through the backend is logged, and
- the NWU Brain corpus is loaded (`backend.brain.system_prompt_bytes` and `assets`).

Example:

```bash
curl http://127.0.0.1:8080/api/ai/status | jq
```

The response shows health metrics and includes a short preview of the compiled NWU system prompt so you can verify the correct corpus is loaded.

### 4. 🖥 Launch the built-in dashboard (optional)

Open `frontend/dashboard/index.html` in a modern browser to view health metrics, toggle connectors, inspect auth sessions, browse evidence, and trigger self-updates. The page speaks directly to the agent API—no additional build step required.

### 5. 🧬 Set Environment Variables (Optional)

Optional flags (see [`docs/SETUP_BACKEND.md`](docs/SETUP_BACKEND.md) for more):

- `VAMP_AGENT_HOST` / `VAMP_AGENT_PORT` (defaults: `127.0.0.1:8080`) — bind address for REST + Socket.IO.
- `VAMP_AGENT_ENABLED` (default: `0`/`false`) — gate the agent + SocketIO bridge. Set to `1` to allow the Playwright agent to start and enqueue evidence; leave unset/`0` to run the dashboard read-only.
- `START_WS_BRIDGE` (default: `0`) — start the legacy `backend.ws_bridge` helper (listens on `APP_HOST`/`APP_PORT`, default `127.0.0.1:8765`).

### Session-state first login and refresh

1. Perform the very first login for each platform manually in a normal, non-headless Chrome window (Playwright will prompt you if a session is missing).

2. Once authenticated, capture or refresh the storage state with either option:
   - **Dashboard**: click **"Refresh browser session state"** in the Session State section to trigger `/api/auth/session/refresh`.
   - **CLI**: `python scripts/refresh_state.py outlook --identity user@nwu.ac.za`

3. The refreshed `storage_state` JSON is recorded under `backend/data/states/<service>/<identity>/` and referenced automatically for subsequent scans. No OAuth/cloud tokens are persisted.

If you want the agent to perform a fully automated login (instead of manual capture) you can still seed a username/password in the vault:

```bash
curl -X POST http://localhost:8080/api/auth/password \\
  -H 'Content-Type: application/json' \\
  -d '{"service": "outlook", "identity": "user@nwu.ac.za", "password": "<password>", "metadata": {"username": "user@nwu.ac.za"}}'
```

Audit entries for session refreshes and password updates are written to `agent_app/auth.log` for troubleshooting.

## 🚦 Quick smoke test (end-to-end)

1. **Run the backend**
   - `python -m backend.app_server` (binds REST + Socket.IO to `http://127.0.0.1:8080`).
   - Wait for the log line announcing the Socket.IO endpoint; leave this terminal running.
2. **Load the extension in Chrome**
   - Visit `chrome://extensions`, enable **Developer mode**, and click **Load unpacked**.
   - Select `frontend/extension/`; the popup will default to `http://127.0.0.1:8080` for both API and WebSocket.
3. **Do the first Outlook scan**
   - Open Outlook in a tab and click the VAMP toolbar icon.
   - Verify the popup shows **Connected**; if not, click **Reconnect**.
   - Enter your email, year, and month (and optionally a custom sign-in URL), then press **Scan Active**.
   - Watch the progress bar and evidence list populate; the status should reach **Complete**.
4. **Export CSV**
   - From the same popup, pick the year/month and click **Export Month CSV** to write a CSV under `backend/data/store/<uid>/<year>/reports/`.
   - Use **Compile Year CSV** if you want the full academic year in one file.

## 🧠 Usage

### Start the backend WebSocket bridge (optional for extension workflows):

```bash
python -m backend.ws_bridge
```

The bridge now relies on the agent server for configuration and authentication. Runtime data (Chrome storage states, vault metadata, evidence, audit logs) is surfaced through the dashboard API instead of ad-hoc file inspection.

## 💡 Example Scan Flow

1. Frontend triggers `"scanActive"` with:
```json
{
  "action": "scanActive",
  "email": "user@nwu.ac.za",
  "url": "https://outlook.office365.com/mail/",
  "year": 2025,
  "month": 11
}
```

2. Backend invokes `run_scan_active(...)`
3. Browser is launched and logs into Outlook using session state
4. Emails are parsed, filtered, scored and returned to the frontend

## 🧪 Supported Platforms

| Platform | Status | Notes |
|----------|--------|-------|
| Outlook | ✅ | MFA/login handled manually first |
| OneDrive | ✅ | Uses state restore for auth |
| GoogleDrive | ✅ | Uses persistent context |
| eFundi | ✅ | No auth needed |

## 🛠️ Troubleshooting

- **WebSocket connection failed**: Ensure `python -m backend.app_server` is running and reachable at `http://127.0.0.1:8080`. If you changed ports, update `frontend/extension/config.json` or `manifest.json` accordingly, then reload the unpacked extension.
- **`chrome-extension://…` is not an accepted origin**: Set `VAMP_CORS_ALLOWED_ORIGINS=*` (or add your extension ID explicitly) before starting `backend.app_server` so Socket.IO accepts the extension origin. Restart the backend after changing the env var.
- **Automated login crashed / Playwright not installed**: Install the browsers with `python -m playwright install chromium` (from your virtualenv) and retry. If headless automation still fails, fall back to manual session capture via `/api/auth/session/refresh` as described above.
| NextCloud | ⚠️ | Placeholder - manual add required |

## 📁 Key Files

| File / Folder | Description |
|---------------|-------------|
| `backend/vamp_agent.py` | Core scraping + Playwright automation |
| `backend/ws_bridge.py` | WebSocket bridge to frontend |
| `backend/nwu_brain/scoring.py` | Loads NWU brain manifest + scoring logic |
| `backend/data/nwu_brain/*.json` | Manifest, policy registry, routing rules |
| `backend/data/states/` | Chrome storage states (generated at runtime) |
| `backend/data/store/` | Evidence store per user (generated) |

## 🧠 NWU Brain Scoring

All extracted items are passed to the `NWUScorer` which assigns:

- `kpa`: Key Performance Area
- `tier`: Risk/priority tier
- `score`: Numerical score
- `band`: Banding (e.g. "Developing")
- `policy_hits`: Keyword/policy matches

## 🛡 Authentication

The system **does not use OAuth**.

- Instead, it authenticates via **live Chrome profile**.
- First-time use requires manual login in browser.
- Persistent state is saved for reuse:
  - `outlook_state.json`
  - `onedrive_state.json`
  - `drive_state.json`

## 🪡 Debugging Tips

- ✅ Ensure `playwright install` is complete
- ✅ Always launch with `python -m backend.ws_bridge`
- 🔒 Check for blocked browser login prompts
- 🧪 Use `--headless=False` in `BROWSER_CONFIG` to see browser
- 🧪 Logs appear in terminal: scan status, scoring feedback

## 🔧 Developer Tips

- Modify `backend/vamp_agent.py` to add new platforms
- Adjust selectors in `scrape_*` functions
- Use `logger.info()` to trace progress
- Patch in `backend/data/nwu_brain/` for updated policies or scoring

## 🧾 License

Internal use only – NWU Research and Policy Development.

## 🧠 Credits

Built with ❤️ using:

- Microsoft Playwright
- Python 3.10
- NWU's brain.json and scoring logic
