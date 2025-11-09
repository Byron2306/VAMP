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
Browser Extension ↔ backend.ws_bridge ↔ backend.vamp_agent ↔ NWU Brain (scoring)
                          ↑
                 backend.deepseek_client (Ollama)
```

---

## 📂 Repository Layout

```
VAMP/
├── README.md
├── backend/                   # Python backend package
│   ├── data/
│   │   ├── nwu_brain/         # Scoring manifest + policy knowledge base
│   │   ├── states/            # Browser storage state (created at runtime)
│   │   └── store/             # User evidence store (created at runtime)
│   ├── nwu_brain/             # NWU scorer implementation
│   ├── deepseek_client.py
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

- 🔐 Uses live authenticated sessions (via persistent browser contexts)
- 🧠 Full content scraping + keyword scoring
- 📜 Auto-scroll & deep content extraction
- 💾 Saves storage states (no repeated login)
- 🔍 Works with Google, Microsoft, Sakai platforms
- 🧰 Integrated with NWU's custom scoring engine
- 🧩 Injects the full NWU brain corpus (charter, routing, policies, scoring, values) into every DeepSeek/Ollama prompt
- 🧾 Emits per-scan evidence counts to simplify "zero result" troubleshooting
- 🧱 Modular design: easy to extend per platform

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

### 3. 🧬 Set Environment Variables

```powershell
$env:DEEPSEEK_API_URL = "http://127.0.0.1:11434/v1/chat/completions"
$env:DEEPSEEK_MODEL   = "gpt-oss:120b-cloud"

# Optional Ollama cloud overrides
$env:OLLAMA_API_URL   = "https://api.ollama.cloud/api/chat"
$env:OLLAMA_MODEL     = "gpt-oss:120b"
$env:OLLAMA_API_KEY   = "<token>"
```

> `deepseek_client.py` will automatically detect Ollama-style endpoints (`/api/chat` or `/api/generate`) and adjust the payload/headers. If you only set the Ollama variables, the DeepSeek defaults are ignored.

### Headless Outlook / OneDrive / Google Drive login

To keep Chromium hidden while still authenticating, provide service credentials via environment variables before starting the backend:

```bash
export VAMP_OUTLOOK_USERNAME="user@nwu.ac.za"
export VAMP_OUTLOOK_PASSWORD="<app-password-or-sso-secret>"
export VAMP_ONEDRIVE_USERNAME="user@nwu.ac.za"   # optional, defaults to email argument
export VAMP_ONEDRIVE_PASSWORD="<password>"
export VAMP_GOOGLE_USERNAME="user@nwu.ac.za"
export VAMP_GOOGLE_PASSWORD="<password>"
```

When these are present the Playwright agent attempts a full headless login, captures a persistent storage state, and skips the manual Chromium window entirely. If the automated login fails or credentials are omitted the previous interactive flow is used as a fallback.

---

## 🧠 Usage

### Start the backend WebSocket bridge:

```bash
python -m backend.ws_bridge
```

It will:
- Listen for frontend requests
- Trigger scans via `run_scan_active`
- Return scored, deduped results

> Runtime data (Chrome storage states and evidence store) is written to `backend/data/states/<service>/<user>.json` and `backend/data/store/`.

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
| `backend/deepseek_client.py`         | Client to LLM API via Ollama                |
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
- Ollama LLM (DeepSeek-V2)
- NWU’s brain.json and scoring logic
