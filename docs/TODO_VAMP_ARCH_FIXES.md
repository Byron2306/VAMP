# TODO – VAMP architecture fixes

## Port/protocol inconsistencies
- Legacy plain WebSocket bridge (`ws_bridge.py`) still listens on 8765 for backwards compatibility, but the extension and docs now standardise on the Socket.IO endpoint at `http://127.0.0.1:8080`/`/socket.io`. Retire the bridge once dependent dashboards are migrated.【F:frontend/extension/manifest.json†L8-L78】【F:backend/ws_bridge.py†L1-L160】
- Keep REST and dashboard defaults aligned to the canonical 8080 host/port; call out the legacy bridge explicitly anywhere it appears to avoid regression to the old port.【F:README.md†L100-L182】【F:frontend/dashboard/app.js†L1-L44】

## Message-type mismatches / duplication
- Background Socket.IO ownership has been removed; the popup now owns the single Socket.IO client path. Keep backend → extension replies in the `WS_STATUS`/`WS_MESSAGE` shape and prune any legacy event names that resurface.【F:frontend/extension/popup.js†L820-L990】【F:backend/app_server.py†L62-L113】

## AI / external LLM hooks
- Both `ws_bridge.py` and `agent_app/ws_dispatcher.py` carry stubs for `ask_ollama` and `analyze_feedback_with_ollama`. The stubs still cause runtime errors (e.g., NameError in `_supports_structured_feedback`) and should be removed or fully guarded so deterministic mode works without any AI backend.【F:backend/ws_bridge.py†L51-L74】【F:backend/agent_app/ws_dispatcher.py†L20-L70】

## Test failures to address
- Keep the AI stubs guarded so the test suite continues to collect cleanly even when optional dependencies are absent; pytest now passes end-to-end after the recent guards.【d29fca†L1-L19】
