// service-worker.js — VAMP (MV3)
// Background responsibilities: alarms/reminders, notifications, evidence storage plumbing,
// offscreen audio for UI feedback, and a single shared Socket.IO connection to the backend.

const ICON_128 = 'icons/icon128.png';
const DAILY_ALARM = 'vampDailyNudge';
const OFFSCREEN_URL = chrome.runtime.getURL('offscreen.html');
const DEFAULT_WS_URL = 'http://127.0.0.1:8080';

let socket = null;
let wsBaseUrl = DEFAULT_WS_URL;
let wsStatus = 'disconnected';
let socketIoLoader = null;

async function getDefaultWsUrl() {
  const manifest = chrome.runtime?.getManifest?.() || {};
  const cfg = manifest.vampConfig || {};
  const defaults = manifest.vamp_defaults || {};
  return cfg.wsBaseUrl || cfg.ws_base_url || defaults.wsUrl || DEFAULT_WS_URL;
}

function broadcastWsStatus(status, extra = {}) {
  wsStatus = status;
  chrome.runtime.sendMessage({ type: 'VAMP_WS_STATUS', status, wsUrl: wsBaseUrl, ...extra }).catch?.(() => {});
}

function broadcastWsEvent(payload) {
  chrome.runtime.sendMessage({ type: 'VAMP_WS_EVENT', payload }).catch?.(() => {});
}

async function ensureSocketIo() {
  if (socketIoLoader) return socketIoLoader;
  socketIoLoader = new Promise((resolve, reject) => {
    try {
      const url = chrome.runtime.getURL('vendor/socket.io.min.js');
      importScripts(url);
      if (typeof self.io === 'undefined') {
        reject(new Error('Socket.IO client failed to load'));
        return;
      }
      resolve(self.io);
    } catch (err) {
      console.warn('[VAMP][SW] Socket.IO load error', err);
      reject(err);
    }
  });
  return socketIoLoader;
}

function disconnectSocket() {
  try {
    socket?.removeAllListeners?.();
    socket?.disconnect?.();
  } catch (_) {}
  socket = null;
  wsStatus = 'disconnected';
}

async function connectSocket(targetUrl) {
  wsBaseUrl = targetUrl || wsBaseUrl || (await getDefaultWsUrl());
  await ensureSocketIo();

  disconnectSocket();
  broadcastWsStatus('connecting');

  socket = self.io(wsBaseUrl, {
    reconnection: true,
    reconnectionDelay: 1000,
    reconnectionDelayMax: 5000,
    transports: ['websocket', 'polling']
  });

  socket.on('connect', () => broadcastWsStatus('connected'));
  socket.on('disconnect', (reason) => broadcastWsStatus('disconnected', { reason }));
  socket.on('error', (error) => broadcastWsStatus('error', { error: error?.message || String(error) }));
  socket.onAny((event, data) => {
    if (event === 'connect' || event === 'disconnect' || event === 'error') return;
    const payload = typeof data === 'string' ? data : JSON.stringify({ action: event, ...(typeof data === 'object' ? data : {}) });
    broadcastWsEvent(payload);
  });

  return socket;
}

function sendSocketMessage(payload) {
  if (!socket || socket.disconnected) {
    broadcastWsStatus('disconnected');
    return false;
  }
  try {
    socket.emit('message', payload);
    return true;
  } catch (err) {
    console.warn('[VAMP][SW] Failed to emit message', err);
    return false;
  }
}

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
});

// ---------- Alarms ----------
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm && alarm.name === DAILY_ALARM) {
    chrome.notifications.create({
      type: 'basic',
      iconUrl: ICON_128,
      title: 'VAMP Reminder',
      message: "It's time to scan this month's teaching & learning evidence.",
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
    justification: 'Play short UI sounds for VAMP'
  });
}

async function playSound(type = 'done') {
  await ensureOffscreen();
  chrome.runtime.sendMessage({ action: 'OFFSCREEN_PLAY', type });
}

// ---------- Evidence change fan-out ----------
chrome.storage.onChanged.addListener((changes, namespace) => {
  if (namespace === 'local' && changes.vamp_evidence) {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs = []) => {
      const tabId = tabs?.[0]?.id;
      if (!tabId) return;
      chrome.tabs.sendMessage(tabId, {
        type: 'EVIDENCE_UPDATED',
        evidence: changes.vamp_evidence.newValue
      }).catch?.(() => {});
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

    if (msg.action === 'PLAY_SOUND') {
      await playSound(msg.type || 'done');
      sendResponse?.({ ok: true });
      return;
    }

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

    if (msg.type === 'VAMP_GET_EVIDENCE') {
      chrome.storage.local.get(['vamp_evidence'], (result) => {
        sendResponse({ evidence: result.vamp_evidence || [] });
      });
      return true;
    }

    if (msg.type === 'VAMP_CLEAR_EVIDENCE') {
      chrome.storage.local.set({ vamp_evidence: [] }, () => {
        sendResponse({ ok: true });
      });
      return true;
    }

    if (msg.type === 'VAMP_WS_CONNECT') {
      const target = typeof msg.wsUrl === 'string' && msg.wsUrl.trim() ? msg.wsUrl.trim() : await getDefaultWsUrl();
      await connectSocket(target);
      sendResponse?.({ ok: true, status: wsStatus, wsUrl: wsBaseUrl });
      return;
    }

    if (msg.type === 'VAMP_WS_DISCONNECT') {
      disconnectSocket();
      sendResponse?.({ ok: true, status: wsStatus });
      return;
    }

    if (msg.type === 'VAMP_WS_SEND') {
      const sent = sendSocketMessage(msg.payload);
      sendResponse?.({ ok: sent, status: wsStatus });
      return;
    }

    if (msg.type === 'VAMP_WS_STATUS_REQ') {
      if (wsStatus === 'disconnected' && !socket) {
        wsBaseUrl = msg.wsUrl || wsBaseUrl || (await getDefaultWsUrl());
      }
      sendResponse?.({ ok: true, status: wsStatus, wsUrl: wsBaseUrl });
      return;
    }

    if (msg.type === 'VAMP_SW_PING') {
      sendResponse?.({ ok: true, pong: true });
      return;
    }

    sendResponse?.({ ok: false, error: 'Unknown message' });
  })();
  return true; // keep sendResponse alive for async
});

// ---------- Notification click ----------
chrome.notifications.onClicked.addListener(() => {
  chrome.windows.getCurrent((w) => {
    if (w && w.focused === false) {
      chrome.windows.update(w.id, { focused: true });
    }
  });
});

// ---------- Unhandled rejections guard ----------
self.addEventListener('unhandledrejection', (ev) => {
  console.warn('Unhandled promise rejection in service-worker:', ev.reason);
});
