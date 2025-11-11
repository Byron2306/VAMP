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
