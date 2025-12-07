# Backend setup and launch

This guide describes the single-command startup flow for the canonical backend (`backend/app_server.py`) defined in [`docs/ARCHITECTURE.md`](./ARCHITECTURE.md). The defaults expose REST + Socket.IO on `http://127.0.0.1:8080` and keep legacy `ws_bridge.py` optional.

## Quick start (Windows)

1. Open a Command Prompt in the repository root (the folder containing `scripts/`).
2. Run:
   ```bat
   scripts\setup_backend.bat
   ```
3. The script will:
   - create or reuse `.venv`,
   - install `requirements.txt`,
   - install Playwright browsers, and
   - start `backend.app_server` on the configured host/port.

The script prints **“Ollama optional: AI insights disabled if not running.”** and continues even if no local AI runtime or Tesseract installation is present. Keep the two spawned Command Prompt windows open while you use VAMP.

## Environment variables

The backend and helper scripts share the same defaults:

| Variable | Default | Purpose |
| --- | --- | --- |
| `VAMP_AGENT_HOST` | `127.0.0.1` | Host for `backend.app_server` (REST + Socket.IO). Set to `0.0.0.0` to listen on all interfaces. |
| `VAMP_AGENT_PORT` | `8080` | Port for `backend.app_server`. |
| `VAMP_AGENT_ENABLED` | `0` | Enable Playwright-driven scans. `0` keeps the dashboard read-only. |
| `START_WS_BRIDGE` | `0` | Set to `1` to also start the legacy `backend.ws_bridge` helper. |
| `APP_HOST` / `APP_PORT` | `127.0.0.1` / `8765` | Host/port for the optional legacy WebSocket bridge. |

Non-critical variables fall back to these defaults if unset so the scripts never crash when values are missing.

## Manual start (non-Windows)

Activate your virtual environment and launch the canonical backend directly:

```bash
python -m backend.app_server
```

Use the same `VAMP_AGENT_HOST` / `VAMP_AGENT_PORT` values if you need to override the defaults.

## Optional dependencies

- **AI / Ollama:** Not required. If no local AI endpoint is running, the backend simply skips AI-assisted insights.
- **Tesseract OCR:** Optional. When missing, the backend logs `"OCR fallback disabled: ..."` once at startup and continues without OCR support. Install Tesseract to enable OCR-based scraping.

## Testing Outlook/OneDrive selectors

After signing in once (so storage_state JSON files exist under `backend/state`), you can sanity-check the Playwright selectors with:

```bash
python tools/selector_smoke_test.py --service outlook
python tools/selector_smoke_test.py --service onedrive
```

The script opens a page using the cached session, verifies that list/grid selectors resolve, and logs whether a sample row and attachment area are visible. Use this to quickly debug UI changes without running a full scan.
