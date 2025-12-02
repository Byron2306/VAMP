// service-worker.js — VAMP (MV3)
// Combines your existing background features (alarms, notifications, state, pings)
// with offscreen audio so sounds can play when the popup opens (no click needed).
//
// This worker also owns the Socket.IO connection so that connectivity status is
// accurate even when the popup is closed. It forwards status updates and
// messages to the UI via chrome.runtime messaging.

// ---------- Constants ----------
const ICON_128 = 'icons/icon128.png';
const DAILY_ALARM = 'vampDailyNudge';
const OFFSCREEN_URL = chrome.runtime.getURL('offscreen.html');
const DEFAULT_WS_URL = chrome.runtime.getManifest()?.vamp_defaults?.wsUrl || 'http://127.0.0.1:8080';

// ---------- WebSocket state (shared) ----------
let ws = null;
let wsUrl = DEFAULT_WS_URL;
let wsStatus = 'idle';
let reconnectTimer = null;
let heartbeatTimer = null;
let reconnectDelayMs = 1000;
let lastPongAt = Date.now();

// ---------- Install / Update ----------
chrome.runtime.onInstalled.addListener(async () => {
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

  connectWebSocket();
});

chrome.runtime.onStartup.addListener(() => {
  connectWebSocket();
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
    reasons: [chrome.offscreen.Reason.AUDIO_PLAYBACK, chrome.offscreen.Reason.IFRAME_SCRIPTING],
    justification: 'Play short UI sounds and maintain background Socket.IO connection for VAMP'
  });
}

async function playSound(type = 'done') {
  await ensureOffscreen();
  chrome.runtime.sendMessage({ action: 'OFFSCREEN_PLAY', type });
}

// ---------- WebSocket helpers ----------
function toWebSocketUrl(url) {
  if (!url) return DEFAULT_WS_URL.replace(/^http/, 'ws');
  let base = url.trim();

  if (!/^wss?:\/\//.test(base)) {
    base = base.startsWith('http') ? base.replace(/^http/, 'ws') : `ws://${base.replace(/^\//, '')}`;
  } else {
    base = base.replace(/^http/, 'ws');
  }

  const cleaned = base.endsWith('/') ? base.slice(0, -1) : base;
  if (cleaned.includes('socket.io')) return cleaned;
  return `${cleaned}/socket.io/?EIO=4&transport=websocket`;
}

async function getPersistedWsUrl() {
  try {
    const result = await chrome.storage.local.get(['vamp_settings']);
    const stored = result?.vamp_settings?.wsUrl;
    return stored || DEFAULT_WS_URL;
  } catch (_) {
    return DEFAULT_WS_URL;
  }
}

function broadcastWsEvent(event, extra = {}) {
  wsStatus = event;
  chrome.runtime.sendMessage({
    type: 'VAMP_WS_EVENT',
    event,
    url: wsUrl,
    ...extra
  }).catch?.(() => {});
}

function clearHeartbeat() {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer);
    heartbeatTimer = null;
  }
}

function startHeartbeat() {
  clearHeartbeat();
  heartbeatTimer = setInterval(() => {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      connectWebSocket(wsUrl);
      return;
    }

    try {
      ws.send('2'); // engine.io ping
    } catch (_) {
      try { ws.close(); } catch {} // force reconnect path
    }

    if (Date.now() - lastPongAt > 30000) {
      try { ws.close(); } catch {}
    }
  }, 10000);
}

function scheduleReconnect(reason = '') {
  clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(() => {
    connectWebSocket(wsUrl);
    reconnectDelayMs = Math.min(reconnectDelayMs * 1.5, 30000);
  }, reconnectDelayMs);

  if (reason) {
    console.debug('[VAMP][SW] scheduling reconnect due to', reason, 'in', reconnectDelayMs, 'ms');
  }
}

async function connectWebSocket(providedUrl) {
  clearTimeout(reconnectTimer);
  const targetUrl = providedUrl || await getPersistedWsUrl();
  wsUrl = targetUrl || DEFAULT_WS_URL;
  const endpoint = toWebSocketUrl(wsUrl);

  try {
    if (ws) {
      ws.onopen = ws.onclose = ws.onerror = ws.onmessage = null;
      ws.close();
    }

    ws = new WebSocket(endpoint);
  } catch (err) {
    broadcastWsEvent('error', { message: err?.message || 'Failed to create WebSocket' });
    scheduleReconnect('construct-error');
    return;
  }

  broadcastWsEvent('connecting');

  ws.onopen = () => {
    reconnectDelayMs = 1000;
    lastPongAt = Date.now();
    broadcastWsEvent('connect');
    startHeartbeat();
    try { ws.send('40'); } catch (_) {}
  };

  ws.onclose = (event) => {
    clearHeartbeat();
    broadcastWsEvent('disconnect', { code: event?.code, reason: event?.reason });
    scheduleReconnect('close');
  };

  ws.onerror = (event) => {
    broadcastWsEvent('error', { message: event?.message || 'WebSocket error' });
  };

  ws.onmessage = (messageEvent) => {
    const data = messageEvent?.data;
    if (data === '3' || data === '3probe') {
      lastPongAt = Date.now();
      return;
    }

    if (typeof data === 'string' && data.startsWith('0')) {
      try { ws?.send('40'); } catch (_) {}
      return;
    }

    if (data === '40') {
      broadcastWsEvent('connect');
    }
  };
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

    if (msg.source === 'offscreen-socket') {
      if (msg.event === 'status' && msg.state) {
        connectionState = msg.state;
        await persistConnectionState(msg.state, true);
        sendResponse?.({ ok: true });
        return;
      }
      if (msg.event === 'message' && msg.payload) {
        try { chrome.runtime.sendMessage({ type: 'VAMP_SOCKET_MESSAGE', payload: msg.payload }); } catch {}
        try {
          chrome.tabs.query({}, (tabs) => {
            tabs.forEach((tab) => {
              chrome.tabs.sendMessage(tab.id, { type: 'VAMP_SOCKET_MESSAGE', payload: msg.payload }).catch?.(() => {});
            });
          });
        } catch {}
        sendResponse?.({ ok: true });
        return;
      }
    }

    if (msg.type === 'VAMP_SOCKET_STATUS_REQUEST') {
      sendResponse?.({ ok: true, state: connectionState });
      return;
    }

    if (msg.type === 'VAMP_SOCKET_CONNECT') {
      const res = await startBackgroundSocket(msg.url);
      sendResponse?.({ ok: !!res?.ok, state: connectionState, error: res?.error });
      return;
    }

    if (msg.type === 'VAMP_SOCKET_SEND') {
      const res = await relaySocketSend(msg.payload);
      sendResponse?.({ ok: !!res?.ok, error: res?.error });
      return;
    }

    // 0) WebSocket status / ensure connected
    if (msg.type === 'VAMP_WS_STATUS') {
      connectWebSocket(msg.url || wsUrl);
      sendResponse?.({
        ok: true,
        status: wsStatus,
        readyState: ws?.readyState ?? WebSocket.CLOSED,
        url: wsUrl
      });
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

    // 4b) Socket lifecycle routed through the background
    if (msg.type === 'WS_CONNECT') {
      connectSocket(msg.url || '');
      sendResponse?.({ ok: true });
      return;
    }

    if (msg.type === 'WS_DISCONNECT') {
      disconnectSocket(true);
      sendResponse?.({ ok: true });
      return;
    }

    if (msg.type === 'WS_SEND') {
      const sent = sendViaSocket(msg.payload);
      sendResponse?.({ ok: sent });
      return;
    }

    if (msg.type === 'WS_GET_STATUS') {
      sendResponse?.({ ok: true, status: wsStatus });
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

// ---------- Socket.IO connectivity (NEW) ----------
let socket = null;
let socketIoPromise = null;
let reconnectTimer = null;
let heartbeatTimer = null;
let reconnectDelayMs = 1000;
let lastWsUrl = DEFAULT_WS_URL;

async function resolveWsUrl() {
  try {
    const { vamp_settings: settings } = await chrome.storage.local.get(['vamp_settings']);
    const stored = settings?.wsUrl;
    if (typeof stored === 'string' && stored.trim()) {
      return stored.trim();
    }
  } catch (err) {
    console.warn('Unable to read wsUrl from storage', err);
  }
  return DEFAULT_WS_URL;
}

async function loadSocketIOLibrary() {
  if (socketIoPromise) return socketIoPromise;

  socketIoPromise = (async () => {
    const src = chrome.runtime.getURL('vendor/socket.io.min.js');
    const res = await fetch(src);
    const code = await res.text();
    const factory = new Function('self', `${code}; return self.io;`);
    const ioClient = factory(self);
    if (!ioClient) {
      throw new Error('Socket.IO client failed to initialise');
    }
    return ioClient;
  })();

  return socketIoPromise;
}

function emitWsStatus(status, details = {}) {
  chrome.runtime.sendMessage({
    type: 'WS_STATUS',
    status,
    ...details
  }).catch?.(() => {});
}

function emitWsEvent(event, payload = {}) {
  chrome.runtime.sendMessage({
    type: 'WS_EVENT',
    event,
    payload
  }).catch?.(() => {});
}

function stopHeartbeatLoop() {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer);
    heartbeatTimer = null;
  }
}

function startHeartbeatLoop() {
  stopHeartbeatLoop();
  heartbeatTimer = setInterval(() => {
    emitWsStatus('heartbeat', {
      url: lastWsUrl,
      connected: Boolean(socket?.connected),
      ts: Date.now()
    });
  }, HEARTBEAT_INTERVAL_MS);
}

function scheduleReconnect(reason = 'retry') {
  clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(() => {
    initialiseSocket(reason).catch(() => {});
    reconnectDelayMs = Math.min(Math.round(reconnectDelayMs * 1.5), RECONNECT_MAX_DELAY_MS);
  }, reconnectDelayMs);

  emitWsStatus('reconnecting', {
    delayMs: reconnectDelayMs,
    reason
  });
}

async function initialiseSocket(reason = 'manual') {
  clearTimeout(reconnectTimer);
  const url = await resolveWsUrl();
  lastWsUrl = url;
  emitWsStatus('connecting', { url, reason });

  const ioClient = await loadSocketIOLibrary();

  try {
    socket?.removeAllListeners?.();
    socket?.disconnect?.();
  } catch (err) {
    console.warn('Error cleaning previous socket', err);
  }

  socket = ioClient(url, {
    reconnection: false,
    transports: ['websocket', 'polling']
  });

  socket.on('connect', () => {
    reconnectDelayMs = 1000;
    emitWsStatus('connected', { url });
    startHeartbeatLoop();
  });

  socket.on('connect_error', (error) => {
    emitWsStatus('error', { message: error?.message || 'connect_error' });
    scheduleReconnect('connect_error');
  });

  socket.on('disconnect', (why) => {
    emitWsStatus('disconnected', { reason: why });
    stopHeartbeatLoop();
    scheduleReconnect('disconnect');
  });

  socket.onAny((event, data) => {
    emitWsEvent(event, data);
  });
}

function teardownSocket() {
  clearTimeout(reconnectTimer);
  stopHeartbeatLoop();
  try {
    socket?.removeAllListeners?.();
    socket?.disconnect?.();
  } catch (err) {
    console.warn('Error tearing down socket', err);
  }
  socket = null;
}

// ---------- Optional keep-alive (disabled) ----------
// chrome.alarms.create('vamp-keepalive', { periodInMinutes: 4 });
// chrome.alarms.onAlarm.addListener(a => {
//   if (a.name === 'vamp-keepalive') { /* heartbeat */ }
// });