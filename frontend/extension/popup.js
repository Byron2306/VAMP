// popup.js - Professional VAMP UI with Enhanced Evidence Display
(() => {
  const $ = (id) => document.getElementById(id);

  const els = {
    wsUrl:        $('wsUrl'),
    wsStatus:     $('wsStatus'),
    email:        $('email'),
    name:         $('name'),
    org:          $('org'),
    year:         $('year'),
    month:        $('month'),
    scanUrl:      $('scanUrl'),
    askText:      $('askText'),

    btnEnrol:     $('btnEnrol'),
    btnState:     $('btnState'),
    btnScan:      $('btnScan'),
    btnFinalise:  $('btnFinalise'),
    btnExport:    $('btnExport'),
    btnCompile:   $('btnCompile'),
    btnAsk:       $('btnAsk'),
    btnAskFb:     $('btnAskFeedback'),

    // Evidence display elements
    btnRefreshEvidence: $('btnRefreshEvidence'),
    btnViewDetails:     $('btnViewDetails'),
    btnClearEvidence:   $('btnClearEvidence'),
    evidenceTableBody:  $('evidenceTableBody'),
    evidenceCount:      $('evidenceCount'),
    evidenceScore:      $('evidenceScore'),
    evidenceLastScan:   $('evidenceLastScan'),
    evidenceModal:      $('evidenceModal'),
    btnCloseModal:      $('btnCloseModal'),
    btnCloseDetails:    $('btnCloseDetails'),

    progressBar:  $('progressBar'),
    scanNote:     $('scanNote'),
    answerBox:    $('answerBox'),
    openSound:    $('openSound'),
    brandIcon:    $('brandIcon'),
  };

  // ---------- State Management ----------
  let ws = null;
  let wsUrlCurrent = 'ws://127.0.0.1:8765';
  let reconnectTimer = null;
  let reconnectDelayMs = 1000;
  let isBusy = false;
  let lastPhase = 'idle';
  let lastPct = 0;
  let heartbeatTimer = null;
  let scanTimeout = null;
  
  // Evidence state
  let currentEvidence = [];
  let selectedEvidenceItem = null;
  let currentSort = { column: 'title', direction: 'asc' };

  // ---------- Enhanced UI Helpers ----------
  function setStatus(text, type = 'disconnected') {
    if (els.wsStatus) {
      els.wsStatus.textContent = text;
      els.wsStatus.setAttribute('data-status', type);
    }
  }

  function setProgressPct(pct, immediate = false) {
    const v = Math.max(0, Math.min(100, Number(pct) || 0));
    if (els.progressBar) {
      if (immediate) {
        els.progressBar.style.transition = 'none';
        els.progressBar.style.width = `${v}%`;
      } else {
        els.progressBar.style.transition = 'width 0.5s cubic-bezier(0.4, 0, 0.2, 1)';
        els.progressBar.style.width = `${v}%`;
      }
      els.progressBar.setAttribute('aria-valuenow', String(v));
    }
  }

  function setScanNote(note) {
    if (els.scanNote) {
      els.scanNote.textContent = note || '';
      // Add loading animation for active scanning
      if (note && (note.includes('...') || isBusy)) {
        els.scanNote.classList.add('loading-dots');
      } else {
        els.scanNote.classList.remove('loading-dots');
      }
    }
  }

  function logAnswer(text, type = 'info') {
    if (!els.answerBox) return;
    const line = document.createElement('div');
    line.className = 'log-line';
    
    // Add timestamp and type indicator
    const timestamp = new Date().toLocaleTimeString();
    const prefix = type === 'error' ? '❌' : type === 'success' ? '✅' : 'ℹ️';
    
    line.innerHTML = `<span style=\"color: var(--muted); font-size: 11px;\">[${timestamp}]</span> ${prefix} ${text}`;
    
    // Auto-scroll to bottom
    els.answerBox.prepend(line);
    els.answerBox.scrollTop = 0;
  }

  function enableControls(on) {
    const controls = [
      els.btnEnrol, els.btnState, els.btnScan,
      els.btnFinalise, els.btnExport, els.btnCompile,
      els.btnAsk, els.btnAskFb, els.btnRefreshEvidence,
      els.btnViewDetails, els.btnClearEvidence,
      els.wsUrl, els.scanUrl, els.email, els.name, els.org, els.year, els.month, els.askText
    ];
    
    controls.forEach(el => { 
      if (el) {
        el.disabled = !on;
        // Add visual feedback for disabled state
        if (!on) {
          el.style.opacity = '0.6';
          el.style.cursor = 'not-allowed';
        } else {
          el.style.opacity = '1';
          el.style.cursor = 'pointer';
        }
      }
    });
  }

  function playOpenSound() {
    if (!els.openSound) return;
    try { 
      els.openSound.currentTime = 0; 
      els.openSound.volume = 0.7;
      els.openSound.play().catch(()=>{}); 
    } catch {} 
  }

  // ---------- Evidence Display Functions ----------
  function updateEvidenceDisplay(evidenceItems) {
    if (!els.evidenceTableBody) return;
    
    currentEvidence = evidenceItems || [];
    
    if (!currentEvidence || currentEvidence.length === 0) {
      els.evidenceTableBody.innerHTML = `
        <tr>
          <td colspan="6" class="no-evidence">
            <div class="no-evidence-content">
              <div class="no-evidence-icon">📧</div>
              <div class="no-evidence-text">Scan Outlook Office365 to see evidence</div>
              <div class="no-evidence-hint">Click "Scan Active" while on your Outlook mailbox</div>
            </div>
          </td>
        </tr>
      `;
      updateEvidenceStats(0, 'N/A');
      return;
    }

    // Sort evidence
    const sortedEvidence = sortEvidence(currentEvidence, currentSort.column, currentSort.direction);
    
    // Update table
    els.evidenceTableBody.innerHTML = sortedEvidence.map((item, index) => {
      const typeIcon = getEvidenceTypeIcon(item.source);
      const kpaDisplay = getKPADisplay(item.kpa);
      const scoreClass = getScoreClass(item.score);
      const dateDisplay = formatDate(item.date || item.modified);
      const sourceDisplay = getSourceDisplay(item.platform || item.source);
      
      return `
        <tr data-index="${index}" class="${selectedEvidenceItem === index ? 'selected' : ''}">
          <td title="${escapeHtml(item.source)}">${typeIcon}</td>
          <td title="${escapeHtml(item.title || 'No title')}">${truncateText(escapeHtml(item.title || 'No title'), 25)}</td>
          <td>${dateDisplay}</td>
          <td>${kpaDisplay}</td>
          <td class="${scoreClass}">${item.score ? item.score.toFixed(1) : 'N/A'}</td>
          <td title="${escapeHtml(sourceDisplay)}">${truncateText(sourceDisplay, 8)}</td>
        </tr>
      `;
    }).join('');

    // Add click handlers
    const rows = els.evidenceTableBody.querySelectorAll('tr[data-index]');
    rows.forEach(row => {
      row.addEventListener('click', () => {
        const index = parseInt(row.getAttribute('data-index'));
        selectEvidenceItem(index);
      });
    });

    // Update statistics
    updateEvidenceStats(sortedEvidence.length, calculateAverageScore(sortedEvidence));
  }

  function updateEvidenceStats(count, averageScore) {
    if (els.evidenceCount) {
      els.evidenceCount.textContent = `${count} Office365 items`;
    }
    if (els.evidenceScore) {
      els.evidenceScore.textContent = `Avg: ${averageScore}`;
    }
    if (els.evidenceLastScan) {
      els.evidenceLastScan.textContent = `Last: ${new Date().toLocaleTimeString()}`;
    }
  }

  function calculateAverageScore(evidence) {
    const scores = evidence.filter(item => item.score).map(item => item.score);
    if (scores.length === 0) return 'N/A';
    const avg = scores.reduce((a, b) => a + b, 0) / scores.length;
    return avg.toFixed(1);
  }

  function sortEvidence(evidence, column, direction) {
    return [...evidence].sort((a, b) => {
      let aVal = a[column];
      let bVal = b[column];
      
      // Handle special cases
      switch (column) {
        case 'title':
          aVal = a.title || '';
          bVal = b.title || '';
          break;
        case 'date':
          aVal = new Date(a.date || a.modified || 0);
          bVal = new Date(b.date || b.modified || 0);
          break;
        case 'kpa':
          aVal = getKPADisplay(a.kpa);
          bVal = getKPADisplay(b.kpa);
          break;
        case 'score':
          aVal = a.score || 0;
          bVal = b.score || 0;
          break;
        case 'source':
          aVal = a.source || '';
          bVal = b.source || '';
          break;
        case 'type':
          aVal = getEvidenceTypeIcon(a.source);
          bVal = getEvidenceTypeIcon(b.source);
          break;
      }
      
      if (direction === 'asc') {
        return aVal < bVal ? -1 : aVal > bVal ? 1 : 0;
      } else {
        return aVal > bVal ? -1 : aVal < bVal ? 1 : 0;
      }
    });
  }

  function getEvidenceTypeIcon(source) {
    const icons = {
      'outlook': '📧',
      'onedrive': '📁',
      'gdrive': '☁️',
      'efundi': '🎓',
      'web': '🌐'
    };
    return icons[source] || '📄';
  }

  function getKPADisplay(kpa) {
    if (!kpa) return '-';
    if (Array.isArray(kpa)) {
      return kpa.map(k => k.replace('KPA', '')).join(',');
    }
    return String(kpa).replace('KPA', '');
  }

  function getScoreClass(score) {
    if (!score) return '';
    if (score >= 4) return 'score-high';
    if (score >= 2.5) return 'score-medium';
    return 'score-low';
  }

  function getSourceDisplay(platform) {
    if (platform.includes('Office365')) return 'Office365';
    if (platform.includes('OneDrive')) return 'OneDrive';
    if (platform.includes('Google')) return 'Google Drive';
    if (platform.includes('eFundi')) return 'eFundi';
    return platform || 'Unknown';
  }

  function selectEvidenceItem(index) {
    selectedEvidenceItem = index;
    const item = currentEvidence[index];
    
    // Update row selection
    const rows = els.evidenceTableBody.querySelectorAll('tr[data-index]');
    rows.forEach(row => row.classList.remove('selected'));
    rows[index]?.classList.add('selected');
    
    // Show details in modal
    showEvidenceDetails(item);
  }

  function showEvidenceDetails(item) {
    if (!els.evidenceModal) return;
    
    // Update modal content
    if ($('detailTitle')) $('detailTitle').textContent = item.title || 'No title';
    if ($('detailSource')) $('detailSource').textContent = item.platform || item.source || 'Unknown';
    if ($('detailDate')) $('detailDate').textContent = formatDate(item.date || item.modified);
    if ($('detailKPA')) $('detailKPA').textContent = getKPADisplay(item.kpa);
    if ($('detailScore')) $('detailScore').textContent = item.score ? item.score.toFixed(1) : 'N/A';
    if ($('detailSnippet')) $('detailSnippet').textContent = item.snippet || 'No snippet available';
    if ($('detailRationale')) $('detailRationale').textContent = item.rationale || 'No rationale available';
    
    // Show modal
    els.evidenceModal.style.display = 'block';
  }

  function hideEvidenceDetails() {
    if (els.evidenceModal) {
      els.evidenceModal.style.display = 'none';
    }
  }

  function clearEvidenceDisplay() {
    currentEvidence = [];
    selectedEvidenceItem = null;
    updateEvidenceDisplay([]);
    logAnswer('Evidence display cleared', 'info');
  }

  // Utility functions
  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  function truncateText(text, length) {
    return text.length > length ? text.substring(0, length) + '...' : text;
  }

  function formatDate(dateString) {
    if (!dateString) return 'N/A';
    try {
      const date = new Date(dateString);
      return date.toLocaleDateString();
    } catch {
      return 'N/A';
    }
  }

  // ---------- Persistence ----------
  function saveSettings() {
    const obj = {
      wsUrl: els.wsUrl?.value?.trim() || wsUrlCurrent,
      scanUrl: els.scanUrl?.value?.trim() || '',
      email: els.email?.value?.trim() || '',
      name:  els.name?.value?.trim()  || '',
      org:   els.org?.value?.trim()   || 'NWU',
      year:  Number(els.year?.value || new Date().getFullYear()),
      month: Number(els.month?.value || (new Date().getMonth()+1)),
      ask:   els.askText?.value || ''
    };
    try { chrome.storage?.local?.set({ vamp_settings: obj }); } catch {}
    return obj;
  }

  function restoreSettings() {
    try {
      chrome.storage?.local?.get(['vamp_settings'], (res) => {
        const s = res?.vamp_settings || {};
        if (els.wsUrl && s.wsUrl)  els.wsUrl.value = s.wsUrl;
        if (els.scanUrl && s.scanUrl) els.scanUrl.value = s.scanUrl;
        if (els.email && s.email)  els.email.value = s.email;
        if (els.name  && s.name)   els.name.value  = s.name;
        if (els.org   && s.org)    els.org.value   = s.org;
        if (els.year  && s.year)   els.year.value  = String(s.year);
        if (els.month && s.month)  els.month.value = String(s.month);
        if (els.askText && typeof s.ask === 'string') els.askText.value = s.ask;
        if (els.wsUrl && !els.wsUrl.value) els.wsUrl.value = wsUrlCurrent;
      });
    } catch {
      if (els.wsUrl && !els.wsUrl.value) els.wsUrl.value = wsUrlCurrent;
    }
  }

  // ---------- Month/Year Setup ----------
  function ensureYearMonth() {
    const now = new Date(), yNow = now.getFullYear(), mNow = now.getMonth()+1;

    if (els.year) {
      if (!els.year.value) els.year.value = String(yNow);
      els.year.disabled = false;
    }

    if (els.month) {
      els.month.disabled = false;
      if (!els.month.options || els.month.options.length === 0) {
        els.month.innerHTML = '';
        for (let m = 1; m <= 12; m++) {
          const o = document.createElement('option');
          o.value = String(m);
          o.textContent = String(m).padStart(2, '0');
          if (m === mNow) o.selected = true;
          els.month.appendChild(o);
        }
      }
    }
  }

  // ---------- Enhanced Progress Tracking ----------
  function heartbeatNote(phase) {
    const notes = {
      'auth':     'Authenticating Office365 session...',
      'collect':  'Collecting artefacts from Outlook...',
      'deepread': 'Deep reading email content...',
      'score':    'Scoring against NWU policies...',
      'store':    'Storing evidence in database...',
      'default':  'Processing evidence...'
    };
    return notes[phase] || notes.default;
  }

  function startHeartbeat() {
    stopHeartbeat();
    heartbeatTimer = setInterval(() => {
      if (!isBusy) return;
      setScanNote(heartbeatNote(lastPhase));
      setProgressPct(lastPct);
    }, 800);
  }

  function stopHeartbeat() {
    if (heartbeatTimer) { clearInterval(heartbeatTimer); heartbeatTimer = null; }
  }

  // ---------- WebSocket Management ----------
  function scheduleReconnect() {
    clearTimeout(reconnectTimer);
    reconnectTimer = setTimeout(() => {
      logAnswer('Attempting to reconnect...', 'info');
      connectWS(els.wsUrl?.value?.trim() || wsUrlCurrent);
      reconnectDelayMs = Math.min(reconnectDelayMs * 1.5, 10000);
    }, reconnectDelayMs);
  }

  function connectWS(url) {
    if (ws) {
      try { ws.onopen = ws.onclose = ws.onmessage = ws.onerror = null; ws.close(); } catch {}
      ws = null;
    }
    clearTimeout(reconnectTimer);

    wsUrlCurrent = url || wsUrlCurrent;
    setStatus('Connecting...', 'scanning');

    try {
      ws = new WebSocket(wsUrlCurrent);
    } catch (e) {
      setStatus('Connection Failed', 'error');
      logAnswer(`Connection error: ${e.message}`, 'error');
      scheduleReconnect();
      return;
    }

    ws.onopen = () => {
      setStatus('Connected', 'connected');
      reconnectDelayMs = 1000;
      enableControls(true);
      logAnswer('WebSocket connected successfully', 'success');
      
      try {
        chrome.storage?.local?.get(['vamp_settings'], (res) => {
          const s = res?.vamp_settings || {};
          s.wsUrl = els.wsUrl?.value?.trim() || wsUrlCurrent;
          chrome.storage?.local?.set({ vamp_settings: s });
        });
      } catch {}
    };

    ws.onmessage = (ev) => handleMessage(ev.data);

    ws.onerror = (error) => {
      setStatus('Connection Error', 'error');
      logAnswer('WebSocket connection error', 'error');
    };

    ws.onclose = (event) => {
      setStatus('Disconnected', 'disconnected');
      if (event.code !== 1000) {
        logAnswer(`Connection closed: ${event.reason || 'Unknown reason'}`, 'error');
      }
      if (!document.hidden) scheduleReconnect();
    };
  }

  function sendWS(obj) {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      logAnswer('Not connected - reconnecting...', 'warning');
      connectWS(els.wsUrl?.value?.trim() || wsUrlCurrent);
      setTimeout(() => {
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify(obj));
          logAnswer('Command sent after reconnect', 'success');
        } else {
          logAnswer('Failed to reconnect for command', 'error');
        }
      }, 500);
      return;
    }
    
    try {
      ws.send(JSON.stringify(obj));
    } catch (e) {
      logAnswer(`Failed to send command: ${e.message}`, 'error');
    }
  }

  // ---------- Enhanced Message Handling ----------
  function handleMessage(raw) {
    let msg = null;
    try {
      msg = JSON.parse(raw);
    } catch {
      logAnswer('Invalid message received', 'error');
      return;
    }

    const action = msg.action || '';
    const data = (msg.data && typeof msg.data === 'object') ? msg.data : {};

    if (msg.ok === false) {
      setScanNote(`Error: ${msg.error || 'Unknown error'}`);
      logAnswer(`❌ ${action} failed: ${msg.error || 'Unknown error'}`, 'error');
      isBusy = false; 
      enableControls(true);
      setStatus('Error', 'error');
      stopHeartbeat();
      clearTimeout(scanTimeout);
      return;
    }

    switch (action) {
      case 'SCAN_ACTIVE/STARTED': {
        isBusy = true;
        enableControls(false);
        lastPhase = 'auth';
        lastPct = 5;
        setProgressPct(5, true);
        setScanNote('Initializing Office365 scan...');
        setStatus('Scanning...', 'scanning');
        startHeartbeat();
        
        // Set scan timeout (5 minutes)
        clearTimeout(scanTimeout);
        scanTimeout = setTimeout(() => {
          if (isBusy) {
            logAnswer('⚠️ Scan timeout - process may be stuck', 'warning');
            setScanNote('Scan timeout - check backend');
          }
        }, 300000);
        
        logAnswer('Office365 scan started successfully', 'success');
        break;
      }
      
      case 'SCAN_ACTIVE/PROGRESS': {
        const pct = typeof data.pct === 'number' ? data.pct : (Number(data.progress || 0) * 100);
        const note = data.note || data.status || data.phase || '';
        lastPct = Math.max(5, Math.min(95, Number(pct) || 0));
        lastPhase = String(data.phase || 'progress');
        setProgressPct(lastPct);
        setScanNote(note);
        break;
      }

      case 'PROGRESS': {
        const pctRaw = (typeof data.percent === 'number') ? data.percent : msg.percent;
        const pct = Math.max(5, Math.min(95, (Number(pctRaw || 0) || 0) * 100));
        lastPct = pct;
        setProgressPct(pct);
        setScanNote(data.note || msg.note || 'Processing...');
        break;
      }

      case 'BATCH': {
        const c = Number(data.count || msg.count || 0);
        setScanNote(`Processed ${c} Office365 items...`);
        logAnswer(`📦 Batch processed: ${c} Office365 items`, 'info');
        break;
      }

      case 'SCAN_ACTIVE/COMPLETE': {
        isBusy = false;
        lastPhase = 'store';
        lastPct = 100;
        setProgressPct(100);
        const added = data.added || msg.added || 0;
        const total = data.total_evidence || data.total || msg.total_evidence || 0;
        setScanNote(`Complete - ${added} new items, ${total} total`);
        logAnswer(`✅ Office365 scan complete! ${added} new items, ${total} total evidence`, 'success');
        const brainSummary = data.brain_summary || msg.brain_summary || data.summary || msg.summary || '';
        if (brainSummary) {
          logAnswer(`🧠 ${brainSummary}`, 'info');
        }
        enableControls(true);
        setStatus('Connected', 'connected');
        stopHeartbeat();
        clearTimeout(scanTimeout);
        playOpenSound();
        
        // Refresh evidence display
        refreshEvidenceDisplay();
        break;
      }
      
      case 'SCAN_ACTIVE/DONE': {
        isBusy = false;
        lastPhase = 'store';
        lastPct = 100;
        setProgressPct(100);
        setScanNote(data.note || 'Office365 scan completed');
        logAnswer('✅ Office365 scan finished', 'success');
        enableControls(true);
        setStatus('Connected', 'connected');
        stopHeartbeat();
        clearTimeout(scanTimeout);
        
        // Refresh evidence display
        refreshEvidenceDisplay();
        break;
      }

      case 'GET_STATE': {
        const yearDoc = data.year_doc || msg.year_doc;
        if (yearDoc && yearDoc.months) {
          const evidenceItems = extractEvidenceFromYearDoc(yearDoc);
          updateEvidenceDisplay(evidenceItems);
          logAnswer(`📊 Loaded ${evidenceItems.length} evidence items from storage`, 'success');
        }
        break;
      }

      // Chat responses
      case 'ASK': {
        const answer = (data.answer || msg.answer || '').toString();
        if (answer) logAnswer(`🧠 ${answer}`, 'info');
        enableControls(true);
        setStatus('Connected', 'connected');
        break;
      }

      case 'ASK_FEEDBACK': {
        const answer = (data.answer || msg.answer || '').toString();
        if (answer) logAnswer(`📋 ${answer}`, 'info');
        enableControls(true);
        setStatus('Connected', 'connected');
        break;
      }

      // Other actions
      case 'ENROL':
        logAnswer('👤 Profile enrolled successfully', 'success');
        break;
      case 'FINALISE_MONTH':
        logAnswer('🔒 Month finalized and locked', 'success');
        break;
      case 'EXPORT_MONTH':
        logAnswer(`📁 CSV exported: ${data.path || msg.path || 'Unknown location'}`, 'success');
        break;
      case 'COMPILE_YEAR':
        logAnswer(`📊 Year CSV compiled: ${data.path || msg.path || 'Unknown location'}`, 'success');
        break;

      default:
        if (action) {
          const detail = data.message || data.status || msg.message || '';
          const suffix = detail ? ` — ${detail}` : '';
          logAnswer(`ℹ️ ${action}${suffix}`, 'info');
        }
        break;
    }
  }

  function extractEvidenceFromYearDoc(yearDoc) {
    const evidence = [];
    if (!yearDoc.months) return evidence;
    
    Object.values(yearDoc.months).forEach(month => {
      if (month.items && Array.isArray(month.items)) {
        evidence.push(...month.items);
      }
    });
    
    return evidence;
  }

  function refreshEvidenceDisplay() {
    logAnswer('Refreshing evidence display...', 'info');
    onGetState(); // This will trigger GET_STATE and update the display
  }

  // ---------- Enhanced Action Handlers ----------
  function currentSettings() {
    return saveSettings();
  }

  async function withActiveTabUrl() {
    return new Promise((resolve) => {
      try {
        chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
          const u = tabs && tabs[0] && tabs[0].url ? tabs[0].url : '';
          resolve(u);
        });
      } catch {
        resolve('');
      }
    });
  }

  async function resolveScanUrl() {
    const manual = els.scanUrl?.value?.trim();
    if (manual) {
      logAnswer('Using manual scan URL from popup.', 'info');
      return manual;
    }

    const active = await withActiveTabUrl();
    if (active) {
      logAnswer('Using URL from the active browser tab.', 'info');
    }
    if (!active) {
      logAnswer('Active tab URL unavailable. Provide a Scan URL manually if needed.', 'warning');
    }
    return active;
  }

  function getYearMonth() {
    const y = Number(els.year?.value || new Date().getFullYear());
    const m = Number(els.month?.value || (new Date().getMonth() + 1));
    return { year: y, month: m };
  }

  function coerceMessages(text) {
    const t = (text || '').trim();
    if (!t) return [];
    return [{ role: 'user', content: t }];
  }

  function onEnrol() {
    const s = currentSettings();
    if (!s.email) {
      logAnswer('Please enter an email address', 'error');
      els.email?.focus();
      return;
    }
    
    sendWS({
      action: 'ENROL',
      email: s.email,
      name:  s.name || (s.email ? s.email.split('@')[0] : ''),
      org:   s.org || 'NWU',
    });
    logAnswer('Enrolling profile...', 'info');
  }

  function onGetState() {
    const { year } = getYearMonth();
    sendWS({ action: 'GET_STATE', year });
    logAnswer('Fetching current state and evidence...', 'info');
  }

  async function onScanActive() {
    const s = currentSettings();
    const { year, month } = getYearMonth();
    const scanUrl = await resolveScanUrl();

    if (!s.email) {
      logAnswer('Please enter your email before scanning', 'error');
      els.email?.focus();
      return;
    }

    if (!scanUrl) {
      logAnswer('No scan URL detected. Enter a Scan URL or open the target tab before scanning.', 'error');
      setScanNote('Waiting for scan URL');
      return;
    }

    isBusy = true;
    enableControls(false);
    lastPhase = 'auth';
    lastPct = 5;
    setProgressPct(5, true);
    setScanNote('Starting Office365 scan...');
    setStatus('Scanning...', 'scanning');
    startHeartbeat();

    sendWS({
      action: 'SCAN_ACTIVE',
      url: scanUrl,
      deep_read: true,
      email: s.email,
      name:  s.name,
      org:   s.org || 'NWU',
      year,
      month
    });
  }

  function onFinaliseMonth() {
    const { year, month } = getYearMonth();
    sendWS({ action: 'FINALISE_MONTH', year, month });
    logAnswer('Finalizing month...', 'info');
  }

  function onExportMonth() {
    const { year, month } = getYearMonth();
    sendWS({ action: 'EXPORT_MONTH', year, month });
    logAnswer('Exporting month CSV...', 'info');
  }

  function onCompileYear() {
    const { year } = getYearMonth();
    sendWS({ action: 'COMPILE_YEAR', year });
    logAnswer('Compiling year report...', 'info');
  }

  function onAsk() {
    const { year, month } = getYearMonth();
    const q = (els.askText?.value || '').trim();
    if (!q) { 
      logAnswer('Please type a question', 'error');
      els.askText?.focus();
      return; 
    }
    
    enableControls(false);
    setStatus('Processing...', 'scanning');
    sendWS({
      action: 'ASK',
      year, month,
      messages: coerceMessages(q),
      mode: 'ask'
    });
    logAnswer('Asking VAMP...', 'info');
  }

  function onAskFeedback() {
    const { year, month } = getYearMonth();
    const q = (els.askText?.value || '').trim();
    if (!q) { 
      logAnswer('Please type a request', 'error');
      els.askText?.focus();
      return; 
    }
    
    enableControls(false);
    setStatus('Processing...', 'scanning');
    sendWS({
      action: 'ASK_FEEDBACK',
      year, month,
      messages: coerceMessages(q),
      mode: 'assessor_strict'
    });
    logAnswer('Requesting strict assessment...', 'info');
  }

  // Evidence display handlers
  function onRefreshEvidence() {
    refreshEvidenceDisplay();
  }

  function onViewDetails() {
    if (selectedEvidenceItem !== null) {
      const item = currentEvidence[selectedEvidenceItem];
      showEvidenceDetails(item);
    } else {
      logAnswer('Please select an evidence item first', 'warning');
    }
  }

  function onClearEvidence() {
    clearEvidenceDisplay();
  }

  // ---------- Enhanced Initialization ----------
  document.addEventListener('DOMContentLoaded', () => {
    playOpenSound();
    ensureYearMonth();
    restoreSettings();

    // Enhanced input handling
    els.askText?.addEventListener('focus', () => {
      els.askText.style.borderColor = 'var(--red)';
      els.askText.style.boxShadow = 'var(--red-glow)';
    });
    
    els.askText?.addEventListener('blur', () => {
      els.askText.style.borderColor = '';
      els.askText.style.boxShadow = '';
    });

    // Auto-resize textarea
    els.askText?.addEventListener('input', function() {
      this.style.height = 'auto';
      this.style.height = Math.min(this.scrollHeight, 200) + 'px';
    });

    // Initialize connection
    if (els.wsUrl && !els.wsUrl.value) {
      els.wsUrl.value = wsUrlCurrent;
    } else if (els.wsUrl) {
      wsUrlCurrent = els.wsUrl.value.trim() || wsUrlCurrent;
    }

    connectWS(els.wsUrl?.value?.trim() || wsUrlCurrent);

    // Event listeners
    els.btnEnrol?.addEventListener('click', (e) => { e.preventDefault(); onEnrol(); });
    els.btnState?.addEventListener('click', (e) => { e.preventDefault(); onGetState(); });
    els.btnScan?.addEventListener('click', (e) => { e.preventDefault(); onScanActive(); });
    els.btnFinalise?.addEventListener('click', (e) => { e.preventDefault(); onFinaliseMonth(); });
    els.btnExport?.addEventListener('click', (e) => { e.preventDefault(); onExportMonth(); });
    els.btnCompile?.addEventListener('click', (e) => { e.preventDefault(); onCompileYear(); });
    els.btnAsk?.addEventListener('click', (e) => { e.preventDefault(); onAsk(); });
    els.btnAskFb?.addEventListener('click', (e) => { e.preventDefault(); onAskFeedback(); });

    // Evidence display listeners
    els.btnRefreshEvidence?.addEventListener('click', (e) => { e.preventDefault(); onRefreshEvidence(); });
    els.btnViewDetails?.addEventListener('click', (e) => { e.preventDefault(); onViewDetails(); });
    els.btnClearEvidence?.addEventListener('click', (e) => { e.preventDefault(); onClearEvidence(); });
    els.btnCloseModal?.addEventListener('click', (e) => { e.preventDefault(); hideEvidenceDetails(); });
    els.btnCloseDetails?.addEventListener('click', (e) => { e.preventDefault(); hideEvidenceDetails(); });

    // Close modal when clicking outside
    els.evidenceModal?.addEventListener('click', (e) => {
      if (e.target === els.evidenceModal) {
        hideEvidenceDetails();
      }
    });

    // Table sorting
    const tableHeaders = document.querySelectorAll('.evidence-table th[data-sort]');
    tableHeaders.forEach(header => {
      header.addEventListener('click', () => {
        const column = header.getAttribute('data-sort');
        const currentDirection = header.classList.contains('sort-asc') ? 'asc' : 'desc';
        const newDirection = currentDirection === 'asc' ? 'desc' : 'asc';
        
        // Update header classes
        tableHeaders.forEach(h => {
          h.classList.remove('sort-asc', 'sort-desc');
        });
        header.classList.add(`sort-${newDirection}`);
        
        // Update sort state
        currentSort = { column, direction: newDirection };
        
        // Re-sort and update display
        updateEvidenceDisplay(currentEvidence);
      });
    });

    // Settings persistence
    [els.wsUrl, els.scanUrl, els.email, els.name, els.org, els.year, els.month, els.askText].forEach(el => {
      if (!el) return;
      const evt = (el.tagName === 'SELECT' || el.type === 'checkbox' || el.type === 'number') ? 'change' : 'input';
      el.addEventListener(evt, saveSettings);
    });

    // Manual reconnect when URL changes
    els.wsUrl?.addEventListener('blur', () => {
      const val = els.wsUrl.value.trim();
      if (val && val !== wsUrlCurrent) {
        wsUrlCurrent = val;
        logAnswer('WebSocket URL updated, reconnecting...', 'info');
        connectWS(wsUrlCurrent);
        saveSettings();
      }
    });

    // Enhanced brand icon interaction
    els.brandIcon?.addEventListener('click', () => {
      playOpenSound();
      logAnswer('VAMP system activated', 'success');
    });

    // Initial evidence load
    setTimeout(() => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        refreshEvidenceDisplay();
      }
    }, 1000);
  });

  window.addEventListener('unload', () => {
    stopHeartbeat();
    clearTimeout(reconnectTimer);
    clearTimeout(scanTimeout);
    if (ws) { 
      try { 
        ws.close(1000, 'Popup closing'); 
      } catch {} 
      ws = null; 
    }
  });
})();
