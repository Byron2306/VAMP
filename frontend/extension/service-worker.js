// service-worker.js — VAMP (MV3)
// Combines your existing background features (alarms, notifications, state, pings)
// with offscreen audio so sounds can play when the popup opens (no click needed).

// ---------- Constants ----------
const ICON_128 = 'icons/icon128.png';
const DAILY_ALARM = 'vampDailyNudge';
const OFFSCREEN_URL = chrome.runtime.getURL('offscreen.html');
const CONNECTION_KEY = 'vamp_connection';
const DEFAULT_WS_URL = 'http://127.0.0.1:8080';

let connectionState = {
  status: 'disconnected',
  url: DEFAULT_WS_URL,
  lastError: null,
  lastChanged: new Date().toISOString()
};

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

  await persistConnectionState({ status: 'disconnected', url: DEFAULT_WS_URL });
  await bootstrapConnectionManager('installed');
});

chrome.runtime.onStartup.addListener(() => {
  bootstrapConnectionManager('startup');
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

// ---------- Background Socket.IO Manager ----------
function broadcastConnection(state) {
  try {
    chrome.runtime.sendMessage({ type: 'VAMP_CONNECTION_STATUS', state });
  } catch {}

  try {
    chrome.tabs.query({}, (tabs) => {
      tabs.forEach((tab) => {
        chrome.tabs.sendMessage(tab.id, { type: 'VAMP_CONNECTION_STATUS', state }).catch?.(() => {});
      });
    });
  } catch {}
}

async function persistConnectionState(patch = {}, broadcast = true) {
  const next = {
    ...connectionState,
    ...patch,
    lastChanged: patch.lastChanged || new Date().toISOString()
  };
  connectionState = next;
  try { await chrome.storage.local.set({ [CONNECTION_KEY]: next }); } catch {}
  if (broadcast) broadcastConnection(next);
  return next;
}

async function loadConnectionDefaults() {
  try {
    const res = await chrome.storage.local.get([CONNECTION_KEY, 'vamp_settings']);
    const saved = res?.[CONNECTION_KEY] || {};
    const savedUrl = res?.vamp_settings?.wsUrl || saved.url || DEFAULT_WS_URL;
    connectionState = {
      ...connectionState,
      ...saved,
      url: savedUrl
    };
  } catch {}
  return connectionState;
}

async function sendToOffscreen(payload) {
  await ensureOffscreen();
  return chrome.runtime.sendMessage(payload);
}

async function startBackgroundSocket(urlOverride) {
  const url = urlOverride || connectionState.url || DEFAULT_WS_URL;
  await persistConnectionState({ status: 'connecting', url });

  try {
    const res = await sendToOffscreen({ action: 'OFFSCREEN_SOCKET_CONNECT', url });
    if (!res?.ok) {
      await persistConnectionState({ status: 'error', lastError: res?.error || 'Unable to connect' });
    }
    return res;
  } catch (error) {
    await persistConnectionState({ status: 'error', lastError: error?.message || String(error) });
    return { ok: false, error };
  }
}

async function relaySocketSend(payload) {
  try {
    const res = await sendToOffscreen({ action: 'OFFSCREEN_SOCKET_SEND', payload });
    if (!res?.ok) {
      await persistConnectionState({ status: 'error', lastError: res?.error || 'Send failed' }, true);
    }
    return res;
  } catch (error) {
    await persistConnectionState({ status: 'error', lastError: error?.message || String(error) }, true);
    return { ok: false, error };
  }
}

async function bootstrapConnectionManager(trigger = 'startup') {
  await loadConnectionDefaults();
  await persistConnectionState({ status: 'connecting' });
  if (trigger === 'installed') {
    await persistConnectionState({ status: 'disconnected' });
  }
  await startBackgroundSocket(connectionState.url);
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

// ---------- Optional keep-alive (disabled) ----------
// chrome.alarms.create('vamp-keepalive', { periodInMinutes: 4 });
// chrome.alarms.onAlarm.addListener(a => {
//   if (a.name === 'vamp-keepalive') { /* heartbeat */ }
// });