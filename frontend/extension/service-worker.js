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

// ---------- Socket.IO background management ----------
let socket = null;
let socketIoReady = null;
let wsStatus = { status: 'disconnected', url: null, detail: {} };
let reconnectDelayMs = 1000;
let reconnectTimer = null;
let heartbeatTimer = null;

function ensureSocketIOLoaded() {
  if (typeof io !== 'undefined') {
    return Promise.resolve(io);
  }

  if (socketIoReady) return socketIoReady;

  socketIoReady = new Promise((resolve, reject) => {
    try {
      importScripts('vendor/socket.io.min.js');
      if (typeof io !== 'undefined') {
        resolve(io);
        return;
      }
      reject(new Error('Socket.IO library unavailable'));
    } catch (err) {
      reject(err);
    }
  });

  return socketIoReady;
}

function emitWsStatus(status, detail = {}) {
  wsStatus = { status, url: wsStatus.url, detail };
  chrome.runtime.sendMessage({ type: 'WS_STATUS', status, detail, url: wsStatus.url }).catch?.(() => {});
}

function stopReconnect() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
}

function scheduleReconnect(reason = '') {
  stopReconnect();
  reconnectTimer = setTimeout(() => {
    emitWsStatus('reconnecting', { reason, delay: reconnectDelayMs });
    reconnectDelayMs = Math.min(reconnectDelayMs * 1.5, 10000);
    if (wsStatus.url) {
      connectSocket(wsStatus.url);
    }
  }, reconnectDelayMs);
}

function stopHeartbeatBroadcast() {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer);
    heartbeatTimer = null;
  }
}

function startHeartbeatBroadcast() {
  stopHeartbeatBroadcast();
  heartbeatTimer = setInterval(() => {
    if (socket && socket.connected) {
      emitWsStatus('connected', { heartbeat: Date.now() });
    }
  }, 15000);
}

function disconnectSocket(manual = false) {
  stopReconnect();
  stopHeartbeatBroadcast();
  if (socket) {
    try { socket.disconnect(); } catch (_) {}
    socket = null;
  }
  emitWsStatus('disconnected', { manual });
}

async function connectSocket(url) {
  stopReconnect();
  stopHeartbeatBroadcast();
  wsStatus.url = url;

  emitWsStatus('connecting', {});

  try {
    await ensureSocketIOLoaded();
  } catch (err) {
    emitWsStatus('error', { message: err?.message || String(err) });
    scheduleReconnect('load_failed');
    return;
  }

  if (socket) {
    try { socket.disconnect(); } catch (_) {}
    socket = null;
  }

  try {
    socket = io(url, {
      reconnection: false,
      transports: ['websocket', 'polling']
    });
  } catch (err) {
    emitWsStatus('error', { message: err?.message || String(err) });
    scheduleReconnect('create_failed');
    return;
  }

  socket.on('connect', () => {
    reconnectDelayMs = 1000;
    emitWsStatus('connected', {});
    startHeartbeatBroadcast();
  });

  socket.on('disconnect', (reason) => {
    emitWsStatus('disconnected', { reason });
    stopHeartbeatBroadcast();
    scheduleReconnect(reason || 'disconnect');
  });

  socket.on('connect_error', (error) => {
    emitWsStatus('error', { message: error?.message || String(error) });
    scheduleReconnect('connect_error');
  });

  socket.io?.on?.('reconnect_attempt', (attempt) => {
    emitWsStatus('reconnecting', { attempt });
  });

  socket.on('error', (error) => {
    emitWsStatus('error', { message: error?.message || String(error) });
  });

  socket.on('message', (data) => {
    const payload = typeof data === 'string' ? data : JSON.stringify(data);
    chrome.runtime.sendMessage({ type: 'WS_MESSAGE', data: payload }).catch?.(() => {});
  });
}

function sendViaSocket(payload) {
  if (!socket || !socket.connected) {
    return false;
  }
  try {
    socket.emit('message', payload);
    return true;
  } catch (err) {
    emitWsStatus('error', { message: err?.message || String(err) });
    return false;
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

// ---------- Optional keep-alive (disabled) ----------
// chrome.alarms.create('vamp-keepalive', { periodInMinutes: 4 });
// chrome.alarms.onAlarm.addListener(a => {
//   if (a.name === 'vamp-keepalive') { /* heartbeat */ }
// });