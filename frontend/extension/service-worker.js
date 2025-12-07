// service-worker.js — VAMP (MV3)
// Background responsibilities: alarms/reminders, notifications, evidence storage plumbing,
// and offscreen audio for UI feedback. WebSocket connectivity is handled exclusively by the
// popup via Socket.IO.

const ICON_128 = 'icons/icon128.png';
const DAILY_ALARM = 'vampDailyNudge';
const OFFSCREEN_URL = chrome.runtime.getURL('offscreen.html');

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
