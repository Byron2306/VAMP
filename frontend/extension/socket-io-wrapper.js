/**
 * Socket.IO Wrapper for VAMP Extension
 * Provides compatibility between extension and Flask-SocketIO backend
 */

// Lazily load Socket.IO from the CDN and expose a ready promise. In the
// original implementation we appended the <script> tag but immediately tried
// to use the global `io`, which races on slower machines and produced the
// "io is not defined" error seen in the activity log. By keeping an explicit
// promise we guarantee that any connection attempt waits for the library to be
// present before creating the socket instance.
let ioReadyPromise = null;

function ensureSocketIOLoaded() {
  if (typeof io !== 'undefined') {
    return Promise.resolve(io);
  }

  if (ioReadyPromise) {
    return ioReadyPromise;
  }

  ioReadyPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector('script[data-socket-io="client"]');
    if (existing) {
      const finalize = () => {
        if (typeof io !== 'undefined') {
          resolve(io);
        } else {
          reject(new Error('Socket.IO script loaded but `io` is unavailable'));
        }
      };

      if (existing.dataset.loaded === 'true') {
        finalize();
        return;
      }

      existing.addEventListener('load', finalize);
      existing.addEventListener('error', (event) => {
        reject(new Error(`Failed to load Socket.IO: ${event?.message || 'error'}`));
      });
      return;
    }

    const script = document.createElement('script');
    const socketIoUrl = (typeof chrome !== 'undefined' && chrome.runtime?.getURL)
      ? chrome.runtime.getURL('vendor/socket.io.min.js')
      : 'vendor/socket.io.min.js';
    script.src = socketIoUrl;
    script.async = true;
    script.dataset.socketIo = 'client';
    script.onload = () => {
      script.dataset.loaded = 'true';
      if (typeof io !== 'undefined') {
        resolve(io);
      } else {
        reject(new Error('Socket.IO failed to initialise correctly'));
      }
    };
    script.onerror = (event) => {
      reject(new Error(`Failed to load Socket.IO: ${event?.message || 'error'}`));
    };
    document.head.appendChild(script);
  });

  return ioReadyPromise;
}

// Create Socket.IO connection manager
const SocketIOManager = (() => {
  let socket = null;
  const listeners = {};

  return {
    connect(url) {
      return new Promise((resolve, reject) => {
        if (socket && socket.connected) {
          resolve(socket);
          return;
        }
        ensureSocketIOLoaded()
          .then(() => {
            try {
              socket = io(url, {
                reconnection: true,
                reconnectionDelay: 1000,
                reconnectionDelayMax: 5000,
                reconnectionAttempts: Infinity,
                transports: ['websocket', 'polling']
              });

              socket.on('connect', () => {
                console.log('[SocketIO] Connected to', url);
                if (listeners['connect']) {
                  listeners['connect'].forEach(cb => cb({ type: 'open' }));
                }
                resolve(socket);
              });

              socket.on('disconnect', (reason) => {
                console.log('[SocketIO] Disconnected - Reason:', reason);
                if (listeners['disconnect']) {
                  listeners['disconnect'].forEach(cb => cb({
                    type: 'close',
                    code: reason === 'io server disconnect' ? 1000 : 1006,
                    reason: reason
                  }));
                }
              });

              socket.on('error', (error) => {
                console.error('[SocketIO] Error:', error);
                if (listeners['error']) {
                  listeners['error'].forEach(cb => cb({
                    type: 'error',
                    message: error
                  }));
                }
                // Don't reject here - let the connection retry
              });

              socket.on('message', (data) => {
                if (listeners['message']) {
                  listeners['message'].forEach(cb => cb({
                    data: typeof data === 'string' ? data : JSON.stringify(data)
                  }));
                }
              });

              // Handle generic events that might be emitted as messages
              socket.onAny((event, data) => {
                console.log('[SocketIO] Event received:', event, data);
                if (event !== 'connect' && event !== 'disconnect' && event !== 'error') {
                  if (listeners['message']) {
                    listeners['message'].forEach(cb => cb({
                      data: JSON.stringify({
                        action: event,
                        ...data
                      })
                    }));
                  }
                }
              });

            } catch (error) {
              console.error('[SocketIO] Connection error:', error);
              reject(error);
            }
          })
          .catch((error) => {
            console.error('[SocketIO] Failed to load client library:', error);
            reject(error);
          });
      });
    },

    disconnect() {
      if (socket) {
        socket.disconnect();
        socket = null;
      }
    },

    send(data) {
      if (!socket || !socket.connected) {
        console.warn('[SocketIO] Not connected - cannot send data');
        return false;
      }
      try {
        // Convert to object if string
        const payload = typeof data === 'string' ? JSON.parse(data) : data;
        
        // Emit as generic message with action embedded
        const action = payload.action || 'message';
        console.log('[SocketIO] Sending action:', action);
        socket.emit('message', payload);
        return true;
      } catch (error) {
        console.error('[SocketIO] Send error:', error);
        return false;
      }
    },

    on(event, callback) {
      if (!listeners[event]) {
        listeners[event] = [];
      }
      listeners[event].push(callback);
    },

    isConnected() {
      return socket && socket.connected;
    }
  };
})();

window.SocketIOManager = SocketIOManager;
