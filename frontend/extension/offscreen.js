// Offscreen document used for lightweight audio playback.
// Socket handling lives in the service worker; this page only plays sounds
// when instructed via runtime messages.

const SOUND_MAP = {
  done: 'sounds/vamp.wav',
  alert: 'sounds/vamp.wav',
};

function playSound(type = 'done') {
  const file = SOUND_MAP[type] || SOUND_MAP.done;
  const audio = new Audio(chrome.runtime.getURL(file));
  audio.play().catch(() => {});
}

chrome.runtime.onMessage.addListener((msg) => {
  if (!msg || typeof msg !== 'object') return;
  if (msg.action === 'OFFSCREEN_PLAY' || msg.type === 'PLAY_SOUND') {
    playSound(msg.type || msg.action);
  }
});
