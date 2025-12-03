# TODO – VAMP architecture fixes

## Port/protocol inconsistencies
- Extension defaults to Socket.IO on port 8080 (`manifest.json`, popup defaults, service worker/offscreen config), while `ws_bridge.py` still advertises plain WebSocket on 8765; only 8080 should be used for the extension.【F:frontend/extension/manifest.json†L8-L95】【F:backend/ws_bridge.py†L37-L40】【F:frontend/extension/service-worker.js†L13-L207】【F:frontend/extension/popup.js†L930-L980】
- README and dashboard both point to REST at `http://localhost:8080/api`, but legacy WebSocket host/port (8765) is not documented alongside; clarify or remove to avoid confusion.【F:README.md†L102-L153】【F:frontend/dashboard/app.js†L1-L44】
- Service worker converts base URLs into Engine.IO `/socket.io/?EIO=4&transport=websocket`, whereas `ws_bridge.py` expects raw JSON frames; mixing these protocols will fail handshakes, reinforcing the need to retire `ws_bridge.py`.【F:frontend/extension/service-worker.js†L78-L207】【F:backend/ws_bridge.py†L1-L160】

## Message-type mismatches / duplication
- The extension maintains two Socket.IO clients: the background service worker (broadcasting `VAMP_WS_EVENT` → popup) and the popup itself (directly connecting via `SocketIOManager` and listening for `WS_STATUS`/`WS_MESSAGE`). This duplication risks competing connections and inconsistent status handling; consolidate to a single shared client path.【F:frontend/extension/service-worker.js†L104-L207】【F:frontend/extension/popup.js†L140-L207】【F:frontend/extension/popup.js†L930-L980】
- Background messaging types (`VAMP_WS_EVENT`, `WS_STATUS`, `WS_MESSAGE`, `PONG`) are extension-internal and do not map to backend responses, which use action names (e.g., `GET_STATE`, `SCAN_ACTIVE/STARTED`). Document or align the event schema so UI listeners are consistent.【F:frontend/extension/service-worker.js†L104-L207】【F:frontend/extension/popup.js†L140-L207】【F:backend/app_server.py†L62-L91】

## AI / external LLM hooks
- Both `ws_bridge.py` and `agent_app/ws_dispatcher.py` carry stubs for `ask_ollama` and `analyze_feedback_with_ollama`. The stubs still cause runtime errors (e.g., NameError in `_supports_structured_feedback`) and should be removed or fully guarded so deterministic mode works without any AI backend.【F:backend/ws_bridge.py†L51-L74】【F:backend/agent_app/ws_dispatcher.py†L20-L70】

## Test failures to address
- `pytest` currently fails during collection because `analyze_feedback_with_ollama` is undefined in `agent_app/ws_dispatcher.py`; fixing the stub or removing the AI hook is required before tests can pass.【d29fca†L1-L19】
