chrome.runtime.onInstalled.addListener(() => {
  chrome.offscreen.createDocument({
    url: "offscreen.html",
    reasons: [chrome.offscreen.Reason.BLOBS],
    justification: "To play UI feedback sounds like vamp.wav"
  });
});

chrome.action.onClicked.addListener(() => {
  chrome.runtime.sendMessage({ type: "PLAY_SOUND" });
});
