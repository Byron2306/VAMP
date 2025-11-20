# 🧠 VAMP Agent — Visual AI Metadata Parser

## Overview

The **VAMP Agent** is a stealthy, browser-based deep content analysis tool that scrapes, reads, scores, and normalizes information from platforms like:
- 📧 Outlook / Office365
- ☁️ OneDrive
- 🧾 Google Drive
- 🌐 NextCloud
- 🎓 eFundi LMS

It uses **Playwright** for authenticated browser automation, **NWU Brain** for scoring extracted evidence, and a **WebSocket bridge** for frontend-extension integration.

---

## 🏗 System Architecture

```txt
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

---

## 📂 Repository Layout

```
VAMP/
├── README.md
├── backend/                   # Python backend package
│   ├── agent_app/             # Agent-as-app runtime (vault, plugins, API)
│   ├── data/
│   │   ├── agent_app/         # Connector manifests + persisted config
│   │   ├── nwu_brain/         # Scoring manifest + policy knowledge base
│   │   ├── states/            # Browser storage state (created at runtime)
│   │   └── store/             # User evidence store (created at runtime)
│   ├── platform_plugins/      # Built-in connector implementations
│   ├── nwu_brain/             # NWU scorer implementation
│   ├── app_server.py
│   ├── ollama_client.py
│   ├── vamp_agent.py
│   ├── vamp_master.py
│   ├── vamp_runner.py
│   ├── vamp_store.py
│   └── ws_bridge.py
├── frontend/
│   └── extension/             # Chrome extension source (incl. icons/, sounds/)
├── requirements.txt
└── scripts/
    ├── setup_backend.ps1
    └── setup_backend.bat
```

---

## 🚀 Features

- 🔐 Agent-managed auth: OAuth/device-code flows captured, encrypted, audited, and rotated entirely in-app
- 🧠 Full content scraping + keyword scoring
- 📜 Auto-scroll & deep content extraction
- 💾 Secrets vaulted at rest, plus durable browser storage states (no leaked env vars)
- 🔍 Works with Google, Microsoft, Sakai platforms
- 🧰 Integrated with NWU's custom scoring engine
- 🧩 Injects the full NWU brain corpus (charter, routing, policies, scoring, values) into every Ollama gpt-oss:120-b prompt
- 🧾 Emits per-scan evidence counts to simplify "zero result" troubleshooting
- 🧱 Modular plugin design: connectors can be enabled/disabled or reconfigured live from the agent dashboard
- 🗂 Evidence vault + chain-of-custody controls surfaced via REST/CLI
- 🔄 Self-update checks and rollback orchestration managed by the agent
- 🤖 Ollama-driven orchestration can trigger live VAMP scans directly from chat questions

---

## 🧪 Setup Instructions

### 1. ✅ Prerequisites

- Python 3.10+
- Chrome installed (uses your live profile)
- `Playwright` + browser dependencies installed

### 2. 🛠 Install Requirements

```bash
pip install -r requirements.txt
playwright install
```

### 3. ▶️ Start the unified agent server

```bash
python -m backend.app_server
```

The server exposes a REST API on `http://localhost:8080/api/*` that powers:

- `/api/health` – consolidated diagnostics
- `/api/connectors` – manage platform plugins (enable/disable/update without restarts)
- `/api/auth/*` – rotate credentials, inspect login history, manage OAuth tokens
- `/api/evidence` – browse or purge retained evidence with chain-of-custody logs
- `/api/updates/*` – self-update checks, apply, and rollback

> `backend.ws_bridge` and the browser extension now communicate via the agent server. Existing automation entrypoints (`vamp_agent.py`) continue to function but source credentials and configuration exclusively from the agent runtime.

If you prefer the Windows helper, run `scripts\setup_backend.bat`. The script now performs a lightweight health check using `scripts/check_ollama.py` before launching the REST API and WebSocket bridge, so you'll immediately see whether the local Ollama runtime (127.0.0.1:11434) is reachable. No API keys or cloud endpoints are required—the helper exports the detected loopback URL to every backend component automatically.

### 3b. 🔍 Inspect the AI stack live

Once the server is running, hit `GET /api/ai/status` to confirm that:

- the socket bridge sees your browser session (`runtime.connected_clients`),
- the last WebSocket action routed through the backend is logged, and
- the NWU Brain corpus is actually injected into every Ollama prompt (`backend.brain.system_prompt_bytes` and `assets`).

Example:

```bash
curl http://127.0.0.1:8080/api/ai/status | jq
```

The response shows the resolved Ollama URL/model, whether a reasoning directive is being sent, and includes a short preview of the compiled NWU system prompt so you can verify the correct corpus is loaded.

### 4. 🖥 Launch the built-in dashboard (optional)

Open `frontend/dashboard/index.html` in a modern browser to view health metrics, toggle connectors, inspect auth sessions, browse evidence, and trigger self-updates. The page speaks directly to the agent API—no additional build step required.

### 3. 🧬 Set Environment Variables

```powershell
$env:OLLAMA_API_URL = "http://127.0.0.1:11434/api/chat"
$env:OLLAMA_MODEL   = "gpt-oss:120-b"
```

> `ollama_client.py` automatically detects Ollama-style endpoints (`/api/chat` or `/api/generate`) and applies the correct payload, headers, and system prompt. The default configuration assumes the local Ollama runtime, so no API keys are required.

### Agent-managed login and credential rotation

Use the REST API (or call helpers from Python) to seed OAuth/device-code sessions and password vault entries. Examples:

```bash
curl -X POST http://localhost:8080/api/auth/password \
  -H 'Content-Type: application/json' \
  -d '{"service": "outlook", "identity": "user@nwu.ac.za", "password": "<secret>"}'

curl -X POST http://localhost:8080/api/auth/session \
  -H 'Content-Type: application/json' \
  -d '{"service": "outlook", "identity": "user@nwu.ac.za", "access_token": "<token>", "refresh_token": "<refresh>", "expires_in": 3600}'
```

The agent encrypts and stores credentials in its internal vault (`backend/data/states/agent_app`), rotates keys on demand, and maintains an append-only audit log (`auth.log`). The Playwright automation consumes credentials through the agent runtime—no environment variables or shell history leaks required.

---

## 🧠 Usage

### Start the backend WebSocket bridge (optional for extension workflows):

```bash
python -m backend.ws_bridge
```

The bridge now relies on the agent server for configuration and authentication. Runtime data (Chrome storage states, vault metadata, evidence, audit logs) is surfaced through the dashboard API instead of ad-hoc file inspection.

---

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

---

## 🧪 Supported Platforms

| Platform   | Status | Notes                             |
|------------|--------|-----------------------------------|
| Outlook    | ✅     | MFA/login handled manually first  |
| OneDrive   | ✅     | Uses state restore for auth       |
| GoogleDrive| ✅     | Uses persistent context           |
| eFundi     | ✅     | No auth needed                    |
| NextCloud  | ⚠️     | Placeholder - manual add required |

---

## 📁 Key Files

| File / Folder                        | Description                                 |
|--------------------------------------|---------------------------------------------|
| `backend/vamp_agent.py`              | Core scraping + Playwright automation       |
| `backend/ws_bridge.py`               | WebSocket bridge to frontend                |
| `backend/ollama_client.py`           | Client to Ollama gpt-oss:120-b API          |
| `backend/nwu_brain/scoring.py`       | Loads NWU brain manifest + scoring logic    |
| `backend/data/nwu_brain/*.json`      | Manifest, policy registry, routing rules    |
| `backend/data/states/`               | Chrome storage states (generated at runtime)|
| `backend/data/store/`                | Evidence store per user (generated)         |

---

## 🧠 NWU Brain Scoring

All extracted items are passed to the `NWUScorer` which assigns:

- `kpa`: Key Performance Area
- `tier`: Risk/priority tier
- `score`: Numerical score
- `band`: Banding (e.g. "Developing")
- `policy_hits`: Keyword/policy matches

---

## 🛡 Authentication

The system **does not use OAuth**.
- Instead, it authenticates via **live Chrome profile**.
- First-time use requires manual login in browser.
- Persistent state is saved for reuse:
  - `outlook_state.json`
  - `onedrive_state.json`
  - `drive_state.json`

---

## 🧰 Debugging Tips

- ✅ Ensure `playwright install` is complete
- ✅ Always launch with `python -m backend.ws_bridge`
- 🔒 Check for blocked browser login prompts
- 🧪 Use `--headless=False` in `BROWSER_CONFIG` to see browser
- 🧪 Logs appear in terminal: scan status, scoring feedback

---

## 🔧 Developer Tips

- Modify `backend/vamp_agent.py` to add new platforms
- Adjust selectors in `scrape_*` functions
- Use `logger.info()` to trace progress
- Patch in `backend/data/nwu_brain/` for updated policies or scoring

---

## 🧾 License

Internal use only – NWU Research and Policy Development.

---

## 🧠 Credits

Built with ❤️ using:
- Microsoft Playwright
- Python 3.10
- Ollama LLM (gpt-oss:120-b cloud)
- NWU’s brain.json and scoring logic
