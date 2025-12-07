/**
 * Socket.IO Wrapper for VAMP Extension
 * Provides a small class that wraps the bundled Socket.IO client and exposes
 * a consistent interface for popup.js.
 */

let socketIoPromise = null;

function loadSocketIo() {
  if (typeof io !== 'undefined') {
    return Promise.resolve(io);
  }

  if (!socketIoPromise) {
    socketIoPromise = new Promise((resolve, reject) => {
      const existing = document.querySelector('script[data-socket-io="client"]');
      if (existing) {
        existing.addEventListener('load', () => resolve(typeof io !== 'undefined' ? io : null));
        existing.addEventListener('error', (event) => reject(new Error(`Failed to load Socket.IO: ${event?.message || 'error'}`)));
        if (existing.dataset.loaded === 'true' && typeof io !== 'undefined') {
          resolve(io);
        }
        return;
      }

      const script = document.createElement('script');
      script.dataset.socketIo = 'client';
      script.async = true;
      script.src = chrome.runtime?.getURL ? chrome.runtime.getURL('vendor/socket.io.min.js') : 'vendor/socket.io.min.js';
      script.onload = () => {
        script.dataset.loaded = 'true';
        if (typeof io !== 'undefined') {
          resolve(io);
        } else {
          reject(new Error('Socket.IO failed to initialise correctly'));
        }
      };
      script.onerror = (event) => reject(new Error(`Failed to load Socket.IO: ${event?.message || 'error'}`));
      document.head.appendChild(script);
    });
  }

  return socketIoPromise.then((client) => {
    if (!client) throw new Error('Socket.IO client unavailable');
    return client;
  });
}

class SocketIOManager {
  constructor() {
    this.socket = null;
    this.listeners = new Map();
  }

  async connect(baseUrl) {
    const ioClient = await loadSocketIo();

    if (this.socket?.connected && this.socket.io?.uri?.startsWith(baseUrl)) {
      return this.socket;
    }

    this.disconnect();
    this.socket = ioClient(baseUrl, {
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
      reconnectionAttempts: Infinity,
      transports: ['websocket', 'polling']
    });

    this.socket.on('connect', () => this.emitLocal('connect'));
    this.socket.on('disconnect', (reason) => this.emitLocal('disconnect', { reason }));
    this.socket.on('error', (error) => this.emitLocal('error', { message: error?.message || error }));
    this.socket.onAny((event, data) => {
      if (event === 'connect' || event === 'disconnect' || event === 'error') return;
      this.emitLocal('message', { data: typeof data === 'string' ? data : JSON.stringify({ action: event, ...data }) });
    });

    return this.socket;
  }

  disconnect() {
    try {
      this.socket?.removeAllListeners?.();
      this.socket?.disconnect?.();
    } catch (_) {
      // ignore
    }
    this.socket = null;
  }

  send(obj) {
    if (!this.socket || !this.socket.connected) {
      return false;
    }
    try {
      const payload = typeof obj === 'string' ? JSON.parse(obj) : obj;
      const action = payload?.action || 'message';
      this.socket.emit('message', payload);
      this.emitLocal('message', { data: JSON.stringify({ action, ...payload }) });
      return true;
    } catch (err) {
      console.error('[SocketIO] Send error:', err);
      return false;
    }
  }

  on(event, callback) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    this.listeners.get(event).add(callback);
  }

  emitLocal(event, payload = {}) {
    const callbacks = this.listeners.get(event);
    if (!callbacks) return;
    callbacks.forEach((cb) => {
      try { cb(payload); } catch (err) { console.warn('[SocketIO] Listener error', err); }
    });
  }

  isConnected() {
    return Boolean(this.socket?.connected);
  }
}

window.SocketIOManager = new SocketIOManager();
