chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === "PLAY_SOUND") {
    const audio = new Audio(chrome.runtime.getURL("sounds/vamp.wav"));
    audio.play();
  }
});
