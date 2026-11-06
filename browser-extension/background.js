chrome.runtime.onMessage.addListener((msg) => {
  if (msg && msg.type === 'OVERLAY_UPDATE' && msg.payload) {
    fetch('http://127.0.0.1:8765/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(msg.payload)
    }).catch(() => {});
  }
});
