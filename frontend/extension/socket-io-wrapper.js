/**
 * Socket.IO Wrapper for VAMP Extension
 * Provides compatibility between extension and Flask-SocketIO backend
 */

// Load Socket.IO client library from CDN
if (typeof io === 'undefined') {
  const script = document.createElement('script');
  script.src = 'https://cdn.socket.io/4.5.4/socket.io.min.js';
  script.async = true;
  document.head.appendChild(script);
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

          socket.on('disconnect', () => {
            console.log('[SocketIO] Disconnected');
            if (listeners['disconnect']) {
              listeners['disconnect'].forEach(cb => cb({ type: 'close' }));
            }
          });

          socket.on('error', (error) => {
            console.error('[SocketIO] Error:', error);
            if (listeners['error']) {
              listeners['error'].forEach(cb => cb({ type: 'error', message: error }));
            }
            reject(new Error(error));
          });

          socket.on('message', (data) => {
            if (listeners['message']) {
              listeners['message'].forEach(cb => cb({ data: JSON.stringify(data) }));
            }
          });
        } catch (error) {
          console.error('[SocketIO] Connection error:', error);
          reject(error);
        }
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
        return false;
      }
      try {
        socket.emit('message', typeof data === 'string' ? JSON.parse(data) : data);
        return true;
      } catch (error) {
        console.error('[SocketIO] Send error:', error);
        return false;
      }
    },

    on(event, callback) {
      if (!listeners[event]) listeners[event] = [];
      listeners[event].push(callback);
    },

    isConnected() {
      return socket && socket.connected;
    }
  };
})();

window.SocketIOManager = SocketIOManager;
