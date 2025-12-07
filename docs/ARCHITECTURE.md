# VAMP architecture (Batch 0)

## Canonical runtime
The Chrome extension must use the Flask + Socket.IO server defined in `backend/app_server.py` (option **B**). Run `python -m backend.app_server` (or `python backend/app_server.py`) to expose REST at `http://127.0.0.1:8080/api` and Socket.IO on `ws://127.0.0.1:8080/socket.io`. The legacy `backend/ws_bridge.py` plain WebSocket server on port 8765 is retained only for backward compatibility and should be phased out for the extension.

## Backend components
- **app_server.py**: Flask app that serves the dashboard, registers REST routes from `backend/agent_app/api.py`, and hosts the Socket.IO endpoint that dispatches actions via `WSActionDispatcher` (`/socket.io` on port 8080).【F:backend/app_server.py†L1-L113】
- **ws_bridge.py**: Standalone plain WebSocket server (default `ws://127.0.0.1:8765/`) implementing actions such as SCAN_ACTIVE, ASK, ENROL, GET_STATE, FINALISE_MONTH, EXPORT_MONTH, and COMPILE_YEAR.【F:backend/ws_bridge.py†L1-L160】
- **vamp_master.py / vamp_runner.py**: CLI orchestrators for scanning and aggregating evidence from local folders using the NWU scoring pipeline (run directly as scripts).【F:backend/vamp_master.py†L1-L80】【F:backend/vamp_runner.py†L380-L404】
- **app_server-adjacent modules**: `agent_app/api.py` exposes REST endpoints (health, connectors, AI status). `agent_app/ws_dispatcher.py` bridges Socket.IO messages to the agent runtime and evidence store. Evidence persistence uses `vamp_store.py` under `backend/data/store` (see below).【F:backend/agent_app/api.py†L1-L63】【F:backend/agent_app/ws_dispatcher.py†L1-L124】

## Frontend components
- **Chrome extension** (`frontend/extension`):
  - `manifest.json` pins defaults to `http://127.0.0.1:8080/api` and `http://127.0.0.1:8080` for REST and Socket.IO, respectively.【F:frontend/extension/manifest.json†L8-L78】
  - `service-worker.js` is responsible for alarms, notifications, evidence storage helpers, and offscreen audio. WebSocket ownership lives exclusively in the popup so there is no duplicate background connection.【F:frontend/extension/service-worker.js†L1-L112】
  - `popup.js` renders the UI and owns the Socket.IO connection via `socket-io-wrapper.js`; it sends actions such as ENROL, GET_STATE, SCAN_ACTIVE, ASK, FINALISE_MONTH, EXPORT_MONTH, and COMPILE_YEAR over Socket.IO.【F:frontend/extension/popup.js†L930-L980】【F:frontend/extension/popup.js†L1071-L1395】
  - `socket-io-wrapper.js` lazy-loads the Socket.IO client and exposes a `SocketIOManager` used by `popup.js` for connect/disconnect/send/on/isConnected operations.【F:frontend/extension/socket-io-wrapper.js†L1-L116】
- **Dashboard** (`frontend/dashboard`): Static status UI (index.html + styles.css + app.js) served by `app_server.py` root. It defaults to `http://localhost:8080/api` for health and connector calls.【F:frontend/dashboard/app.js†L1-L44】【F:backend/app_server.py†L17-L48】

## Data and evidence storage
- `backend/__init__.py` defines `STORE_DIR = data/store` (relative to the backend folder).【F:backend/__init__.py†L1-L15】
- `vamp_store.py` writes per-user evidence under `<data/store>/<uid>/<year>/<month>/month.json` plus CSV exports under `<data/store>/<uid>/<year>/reports/`. Items include canonical fields such as `source`, `title`, `date`, `score`, and `band`.【F:backend/vamp_store.py†L13-L118】【F:backend/vamp_store.py†L225-L267】

## Network and ports
- **REST + Socket.IO**: `app_server.py` listens on host `127.0.0.1` and port `8080` by default; environment variables `VAMP_AGENT_HOST` and `VAMP_AGENT_PORT` override these.【F:backend/app_server.py†L94-L113】 The extension should connect here.
- **Legacy plain WebSocket**: `ws_bridge.py` defaults to `ws://127.0.0.1:8765/` via `APP_HOST`/`APP_PORT` env vars; recommended only for legacy dashboards or debugging.【F:backend/ws_bridge.py†L37-L40】

## Component interactions
  - The extension’s popup sends Socket.IO `message` events to `app_server.py`, which routes them to `WSActionDispatcher`. Responses flow back over the same Socket.IO channel.
- The dashboard fetches REST endpoints under `/api/*` from the same server and uses the root path `/` to load its static assets served by Flask.
- Evidence operations (ENROL/GET_STATE/SCAN_ACTIVE/etc.) ultimately read or write JSON/CSV via `VampStore` in `backend/data/store`.

## Outlook & OneDrive Connector Flow (Playwright)
- **Outlook (SCAN_ACTIVE):**
  - Uses the Playwright helpers in `backend/vamp_agent.py` to open a context backed by `STATE_DIR` storage (`get_authenticated_context`). The mailbox view is detected via selectors in `backend/outlook_selectors.py` (e.g. `OUTLOOK_SELECTORS.inbox_list`, `message_row`).
  - Message rows are read with resilient selectors (subject/sender/date) and parsed via `parse_outlook_date` in `backend/date_utils.py` to enforce month-range filtering. Rows outside the target `MonthBounds` are skipped.
  - Each row is opened via row activation, bodies are captured with `BODY_SELECTORS`, and attachments are enumerated using `ATTACHMENT_CANDIDATES`/`ATTACHMENT_NAME_SELECTORS`. Attachment deep-read uses `extract_text_from_attachment` in `backend/attachments.py`, with warnings captured on failure.
- **OneDrive/WebDAV:**
  - The OneDrive path in `scrape_onedrive` navigates to `SERVICE_URLS['onedrive']`, waits for the grid selectors defined in `backend/onedrive_selectors.py`, then iterates row/name/modified-date selectors to build evidence. Dates are parsed with the same Outlook-aware helper and filtered against month bounds.
  - WebDAV helpers remain in `backend/webdav_connector.py` for generic storage operations; the OneDrive Playwright path is preferred for SCAN_ACTIVE evidence.

