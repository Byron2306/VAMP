// service-worker.js — VAMP (MV3)
// Combines your existing background features (alarms, notifications, state, pings)
// with offscreen audio so sounds can play when the popup opens (no click needed).

// ---------- Constants ----------
const ICON_128 = 'icons/icon128.png';
const DAILY_ALARM = 'vampDailyNudge';
const OFFSCREEN_URL = chrome.runtime.getURL('offscreen.html');

// WebSocket / status message constants
const WS_MESSAGE_TYPES = {
  status: 'WS_STATUS',
  event: 'WS_EVENT',
  ping: 'PING',
  pong: 'PONG',
  configure: 'WS_CONFIGURE',
  requestStatus: 'WS_GET_STATUS',
  refresh: 'WS_REFRESH'
};

const LEGACY_WS_URL = 'http://127.0.0.1:8080';
const PROD_DEFAULT_WS = 'https://vamp.nwu.ac.za';
const MAX_BACKOFF_MS = 30000;
const MIN_BACKOFF_MS = 1000;

let wsClient = null;
let wsReconnectTimer = null;
let wsBackoff = MIN_BACKOFF_MS;
let wsEndpoint = null;
let wsTransportUrl = null;
let wsState = {
  status: 'disconnected',
  updatedAt: Date.now(),
  attempts: 0,
  endpoint: null,
  transportUrl: null,
  lastError: null
};

// ---------- WebSocket helpers ----------
function resolveDefaultWsUrl() {
  const envDefault = typeof self !== 'undefined' && (self.VAMP_WS_URL || self.VITE_VAMP_WS_URL);
  return envDefault || PROD_DEFAULT_WS || LEGACY_WS_URL;
}

function normalizeEndpoint(urlLike) {
  if (!urlLike) return null;
  try {
    const raw = urlLike.toString().trim();
    const parsed = new URL(raw);
    if (!['http:', 'https:', 'ws:', 'wss:'].includes(parsed.protocol)) {
      return null;
    }

    const display = parsed.toString().replace(/\/$/, '');
    const wsProtocol = parsed.protocol === 'https:' ? 'wss:' : (parsed.protocol === 'http:' ? 'ws:' : parsed.protocol);
    const wsUrl = new URL(display);
    wsUrl.protocol = wsProtocol;
    return { display, transport: wsUrl.toString() };
  } catch (err) {
    console.warn('[VAMP][SW] Invalid WS endpoint provided', urlLike, err);
    return null;
  }
}

function persistWsState(patch = {}) {
  wsState = {
    ...wsState,
    ...patch,
    updatedAt: Date.now(),
    endpoint: wsEndpoint,
    transportUrl: wsTransportUrl
  };
  chrome.storage?.local?.set({ vamp_ws_state: wsState }).catch?.(() => {});
  chrome.runtime?.sendMessage?.({ type: WS_MESSAGE_TYPES.status, state: wsState }).catch?.(() => {});
}

function closeWebSocket() {
  if (wsClient) {
    try { wsClient.close(); } catch (_) {}
  }
  wsClient = null;
}

function scheduleReconnect(reason = 'reconnect') {
  clearTimeout(wsReconnectTimer);
  wsBackoff = Math.min(Math.round(wsBackoff * 1.5), MAX_BACKOFF_MS);
  wsReconnectTimer = setTimeout(() => {
    connectWebSocket(wsEndpoint, reason);
  }, wsBackoff);
  persistWsState({ status: 'reconnecting', lastError: reason, attempts: wsState.attempts + 1 });
}

function connectWebSocket(rawEndpoint, reason = 'startup') {
  clearTimeout(wsReconnectTimer);
  const normalized = normalizeEndpoint(rawEndpoint || wsEndpoint || resolveDefaultWsUrl());
  if (!normalized) {
    persistWsState({ status: 'error', lastError: 'invalid-endpoint' });
    return;
  }

  wsEndpoint = normalized.display;
  wsTransportUrl = normalized.transport;
  wsBackoff = MIN_BACKOFF_MS;
  persistWsState({ status: 'connecting', lastError: null });

  closeWebSocket();
  wsState.attempts += 1;

  try {
    wsClient = new WebSocket(wsTransportUrl);
  } catch (err) {
    persistWsState({ status: 'error', lastError: err?.message || 'connect-failed' });
    scheduleReconnect(err?.message || 'connect-failed');
    return;
  }

  wsClient.onopen = () => {
    persistWsState({ status: 'connected', lastError: null });
    chrome.runtime?.sendMessage?.({ type: WS_MESSAGE_TYPES.status, state: wsState }).catch?.(() => {});
  };

  wsClient.onmessage = (event) => {
    const payload = typeof event.data === 'string' ? event.data : JSON.stringify(event.data || {});
    chrome.runtime?.sendMessage?.({ type: WS_MESSAGE_TYPES.event, payload }).catch?.(() => {});
    if (payload === WS_MESSAGE_TYPES.ping) {
      wsClient?.send?.(WS_MESSAGE_TYPES.pong);
    }
  };

  wsClient.onerror = (err) => {
    persistWsState({ status: 'error', lastError: err?.message || 'socket-error' });
  };

  wsClient.onclose = (event) => {
    const shouldRetry = event?.code !== 1000;
    persistWsState({ status: shouldRetry ? 'disconnected' : 'closed', lastError: event?.reason || null });
    if (shouldRetry) {
      scheduleReconnect(event?.reason || 'closed');
    }
  };
}

async function loadEndpointAndConnect(trigger = 'startup') {
  try {
    const stored = await chrome.storage?.local?.get?.(['vamp_settings', 'vamp_ws_endpoint']) || {};
    const candidate = stored?.vamp_ws_endpoint?.url || stored?.vamp_settings?.wsUrl || resolveDefaultWsUrl();
    const normalized = normalizeEndpoint(candidate) || normalizeEndpoint(LEGACY_WS_URL);
    if (normalized) {
      wsEndpoint = normalized.display;
      wsTransportUrl = normalized.transport;
      chrome.storage?.local?.set({ vamp_ws_endpoint: { url: wsEndpoint, transport: wsTransportUrl, source: trigger } }).catch?.(() => {});
      connectWebSocket(wsEndpoint, trigger);
    }
  } catch (err) {
    persistWsState({ status: 'error', lastError: err?.message || 'init-failed' });
  }
}

// ---------- Install / Update ----------
chrome.runtime.onInstalled.addListener(() => {
  // Daily reminder alarm (idempotent)
  chrome.alarms.create(DAILY_ALARM, { periodInMinutes: 60 * 24 });

  // Init tiny state record
  chrome.storage.local.set({
    vamp_state: {
      lastScanAt: null,
      lastScanCount: 0,
      lastStatus: 'idle'
    },
    vamp_evidence: []
  }).catch?.(() => {});

  loadEndpointAndConnect('installed');
});

chrome.runtime.onStartup.addListener(() => {
  loadEndpointAndConnect('startup');
});

// ---------- Alarms ----------
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm && alarm.name === DAILY_ALARM) {
    chrome.notifications.create({
      type: 'basic',
      iconUrl: ICON_128,
      title: 'VAMP Reminder',
      message: 'It\'s time to scan this month\'s teaching & learning evidence.',
      priority: 0
    });
  }
});

// ---------- Offscreen Audio Helpers ----------
async function ensureOffscreen() {
  try {
    if (chrome.offscreen && (await chrome.offscreen.hasDocument?.())) return;
  } catch (_) {
    // Some Chrome versions didn't expose hasDocument; ignore and try create
  }
  await chrome.offscreen.createDocument({
    url: OFFSCREEN_URL,
    reasons: [chrome.offscreen.Reason.AUDIO_PLAYBACK],
    justification: 'Play short UI sounds for VAMP without user gesture'
  });
}

async function playSound(type = 'done') {
  await ensureOffscreen();
  chrome.runtime.sendMessage({ action: 'OFFSCREEN_PLAY', type });
}

// ---------- Enhanced evidence state management ----------
chrome.storage.onChanged.addListener((changes, namespace) => {
  if (namespace === 'local' && changes.vamp_evidence) {
    // Evidence was updated, notify UI if needed
    chrome.tabs.query({active: true, currentWindow: true}, (tabs) => {
      if (tabs[0]) {
        chrome.tabs.sendMessage(tabs[0].id, {
          type: 'EVIDENCE_UPDATED',
          evidence: changes.vamp_evidence.newValue
        }).catch(() => {}); // Ignore errors if content script isn't ready
      }
    });
  }
});

// ---------- Messages (popup/content -> SW) ----------
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  (async () => {
    if (!msg || typeof msg !== 'object') {
      sendResponse?.({ ok: false, error: 'Bad message' });
      return;
    }

    if (msg.type === WS_MESSAGE_TYPES.ping) {
      sendResponse?.({ type: WS_MESSAGE_TYPES.pong, state: wsState });
      return;
    }

    if (msg.type === WS_MESSAGE_TYPES.requestStatus) {
      sendResponse?.({ ok: true, state: wsState });
      return;
    }

    if (msg.type === WS_MESSAGE_TYPES.configure && msg.endpoint) {
      const normalized = normalizeEndpoint(msg.endpoint);
      if (!normalized) {
        sendResponse?.({ ok: false, error: 'Invalid endpoint' });
        return;
      }

      wsEndpoint = normalized.display;
      wsTransportUrl = normalized.transport;
      chrome.storage?.local?.set({ vamp_ws_endpoint: { url: wsEndpoint, transport: wsTransportUrl, source: 'popup' } }).catch?.(() => {});
      connectWebSocket(wsEndpoint, 'configure');
      sendResponse?.({ ok: true, state: wsState });
      return;
    }

    if (msg.type === WS_MESSAGE_TYPES.refresh) {
      loadEndpointAndConnect('refresh');
      sendResponse?.({ ok: true });
      return;
    }

    // 1) Request to play a sound immediately (popup open / scan complete / etc.)
    //    In popup.js, call: chrome.runtime.sendMessage({ action: 'PLAY_SOUND', type: 'open'|'done'|'warn' });
    if (msg.action === 'PLAY_SOUND') {
      await playSound(msg.type || 'done');
      sendResponse?.({ ok: true });
      return;
    }

    // 2) Generic notifier (kept from your previous SW)
    //    { type: 'VAMP_NOTIFY', title, body }
    if (msg.type === 'VAMP_NOTIFY') {
      const title = typeof msg.title === 'string' ? msg.title : 'VAMP';
      const body  = typeof msg.body  === 'string' ? msg.body  : 'Event';
      chrome.notifications.create({
        type: 'basic',
        iconUrl: ICON_128,
        title,
        message: body,
        priority: 0
      });
      sendResponse?.({ ok: true });
      return;
    }

    // 3) Scan lifecycle breadcrumb (kept)
    //    { type: 'VAMP_SCAN_STATE', status: 'starting'|'progress'|'done'|'error', count?: number }
    if (msg.type === 'VAMP_SCAN_STATE') {
      chrome.storage.local.get(['vamp_state'], (res) => {
        const prev = res?.vamp_state || {};
        const now = new Date().toISOString();
        const next = {
          ...prev,
          lastScanAt: (msg.status === 'done' || msg.status === 'error') ? now : (prev.lastScanAt || null),
          lastScanCount: (typeof msg.count === 'number') ? msg.count : (prev.lastScanCount || 0),
          lastStatus: msg.status || prev.lastStatus || 'idle'
        };
        chrome.storage.local.set({ vamp_state: next }).catch?.(() => {});
      });
      sendResponse?.({ ok: true });
      return;
    }

    // 4) Health ping (kept)
    if (msg.type === 'VAMP_SW_PING') {
      sendResponse?.({ ok: true, pong: true });
      return;
    }

    // 5) Evidence-related messages (NEW)
    if (msg.type === 'VAMP_GET_EVIDENCE') {
      chrome.storage.local.get(['vamp_evidence'], (result) => {
        sendResponse({evidence: result.vamp_evidence || []});
      });
      return true;
    }
    
    if (msg.type === 'VAMP_CLEAR_EVIDENCE') {
      chrome.storage.local.set({vamp_evidence: []}, () => {
        sendResponse({ok: true});
      });
      return true;
    }

    // Unknown message
    sendResponse?.({ ok: false, error: 'Unknown message' });
  })();
  return true; // keep sendResponse alive for async
});

// ---------- Notification click (kept) ----------
chrome.notifications.onClicked.addListener(() => {
  // Focus current window (MV3 cannot programmatically open the action popup)
  chrome.windows.getCurrent((w) => {
    if (w && w.focused === false) {
      chrome.windows.update(w.id, { focused: true });
    }
  });
});

// ---------- Unhandled rejections guard (kept) ----------
self.addEventListener('unhandledrejection', (ev) => {
  console.warn('Unhandled promise rejection in service-worker:', ev.reason);
});

// Kick off background connection eagerly when the worker spins up
loadEndpointAndConnect('hot-start');

// ---------- Optional keep-alive (disabled) ----------
// chrome.alarms.create('vamp-keepalive', { periodInMinutes: 4 });
// chrome.alarms.onAlarm.addListener(a => {
//   if (a.name === 'vamp-keepalive') { /* heartbeat */ }
// });