// Offscreen document used for audio playback and background Socket.IO connection
const DEFAULT_WS_URL = 'http://127.0.0.1:8080';

let socketState = {
  status: 'disconnected',
  url: DEFAULT_WS_URL,
  lastError: null,
  lastChanged: new Date().toISOString()
};

const socketListenersReady = (() => {
  let ready = false;
  return () => {
    if (ready || typeof SocketIOManager === 'undefined') return ready;

    SocketIOManager.on('connect', () => {
      socketState = {
        ...socketState,
        status: 'connected',
        lastError: null,
        lastChanged: new Date().toISOString()
      };
      chrome.runtime.sendMessage({
        source: 'offscreen-socket',
        event: 'status',
        state: socketState
      }).catch?.(() => {});
    });

    SocketIOManager.on('disconnect', (event) => {
      socketState = {
        ...socketState,
        status: 'disconnected',
        lastError: event?.reason || null,
        lastChanged: new Date().toISOString()
      };
      chrome.runtime.sendMessage({
        source: 'offscreen-socket',
        event: 'status',
        state: socketState
      }).catch?.(() => {});
    });

    SocketIOManager.on('error', (event) => {
      socketState = {
        ...socketState,
        status: 'error',
        lastError: event?.message || event?.toString?.() || 'Socket error',
        lastChanged: new Date().toISOString()
      };
      chrome.runtime.sendMessage({
        source: 'offscreen-socket',
        event: 'status',
        state: socketState
      }).catch?.(() => {});
    });

    SocketIOManager.on('message', (event) => {
      chrome.runtime.sendMessage({
        source: 'offscreen-socket',
        event: 'message',
        payload: event?.data
      }).catch?.(() => {});
    });

    ready = true;
    return ready;
  };
})();

async function connectSocket(url) {
  socketState = {
    ...socketState,
    url: url || socketState.url || DEFAULT_WS_URL,
    status: 'connecting',
    lastChanged: new Date().toISOString()
  };
  chrome.runtime.sendMessage({ source: 'offscreen-socket', event: 'status', state: socketState }).catch?.(() => {});

  try {
    if (typeof SocketIOManager === 'undefined') {
      throw new Error('Socket manager unavailable');
    }
    socketListenersReady();
    await SocketIOManager.connect(socketState.url);
    return { ok: true, state: socketState };
  } catch (error) {
    socketState = {
      ...socketState,
      status: 'error',
      lastError: error?.message || String(error),
      lastChanged: new Date().toISOString()
    };
    chrome.runtime.sendMessage({ source: 'offscreen-socket', event: 'status', state: socketState }).catch?.(() => {});
    return { ok: false, state: socketState, error: socketState.lastError };
  }
}

function disconnectSocket() {
  try {
    SocketIOManager.disconnect();
  } catch {}
  socketState = {
    ...socketState,
    status: 'disconnected',
    lastChanged: new Date().toISOString()
  };
  chrome.runtime.sendMessage({ source: 'offscreen-socket', event: 'status', state: socketState }).catch?.(() => {});
  return { ok: true, state: socketState };
}

function sendSocketPayload(payload) {
  try {
    const sent = SocketIOManager.send(payload);
    return { ok: sent };
  } catch (error) {
    return { ok: false, error: error?.message || String(error) };
  }
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (!msg || typeof msg !== 'object') return;

  if (msg.type === 'PLAY_SOUND' || msg.action === 'OFFSCREEN_PLAY') {
    const audio = new Audio(chrome.runtime.getURL('sounds/vamp.wav'));
    audio.play();
    return;
  }

  if (msg.action === 'OFFSCREEN_SOCKET_CONNECT') {
    connectSocket(msg.url).then(sendResponse);
    return true;
  }

  if (msg.action === 'OFFSCREEN_SOCKET_DISCONNECT') {
    sendResponse(disconnectSocket());
    return true;
  }

  if (msg.action === 'OFFSCREEN_SOCKET_SEND') {
    sendResponse(sendSocketPayload(msg.payload));
    return true;
  }

  if (msg.action === 'OFFSCREEN_SOCKET_STATUS') {
    sendResponse({ ok: true, state: socketState });
    return true;
  }
});
