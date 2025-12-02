// popup.js - Professional VAMP UI with Enhanced Evidence Display
(() => {
  const $ = (id) => document.getElementById(id);

  const els = {
    wsUrl:        $('wsUrl'),
    wsUrlResolved: $('wsUrlResolved'),
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
    btnScanBrain: $('btnScanBrain'),
    btnFinalise:  $('btnFinalise'),
    btnExport:    $('btnExport'),
    btnCompile:   $('btnCompile'),
    btnAsk:       $('btnAsk'),
    btnAskFb:     $('btnAskFeedback'),
    btnClearChat: $('btnClearChat'),

    chatHistory:  $('chatHistory'),

    // Evidence display elements
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
    brainSummary: $('brainSummary'),
    toolFeedback: $('toolFeedback'),

    detailDateConfidence: $('detailDateConfidence'),
    detailRawTimestamp:   $('detailRawTimestamp'),
  };

  // ---------- State Management ----------
  const PROD_WS_FALLBACK = 'https://vamp.nwu.ac.za';
  const LOCAL_WS_PORT = 8080;
  let wsUrlCurrent = PROD_WS_FALLBACK;
  let reconnectTimer = null;
  let reconnectDelayMs = 1000;
  let isBusy = false;
  let lastPhase = 'idle';
  let lastPct = 0;
  let heartbeatTimer = null;
  let scanTimeout = null;
  let socketHandlersRegistered = false;
  
  // Evidence state
  let currentEvidence = [];
  let selectedEvidenceItem = null;
  let currentSort = { column: 'title', direction: 'asc' };
  const chatState = { entries: [], maxEntries: 40 };
  let askConversation = [];
  const toolEvents = [];
  const TOOL_EVENT_LIMIT = 30;

  // ---------- Configuration ----------
  async function loadExtensionConfig() {
    const manifestConfig = chrome?.runtime?.getManifest?.()?.vampConfig || {};
    const configUrl = chrome?.runtime?.getURL ? chrome.runtime.getURL('config.json') : null;
    let fileConfig = {};

    if (configUrl) {
      try {
        const res = await fetch(configUrl);
        if (res.ok) {
          fileConfig = await res.json();
        }
      } catch (err) {
        console.warn('[VAMP] Unable to load extension config.json', err);
      }
    }

    const apiBaseUrl = manifestConfig.apiBaseUrl || manifestConfig.api_base_url || fileConfig.apiBaseUrl || fileConfig.api_base_url || '';
    const wsBaseUrl = manifestConfig.wsBaseUrl || manifestConfig.ws_base_url || fileConfig.wsBaseUrl || fileConfig.ws_base_url || '';

    return { apiBaseUrl, wsBaseUrl };
  }

  function deriveWsUrlFromApi(apiBaseUrl) {
    if (!apiBaseUrl) return '';
    try {
      const u = new URL(apiBaseUrl);
      return u.origin;
    } catch (err) {
      console.warn('[VAMP] Could not derive WS URL from apiBaseUrl', err);
      return '';
    }
  }

  async function resolveDefaultWsUrl() {
    if (wsUrlDefault) return wsUrlDefault;

    const cfg = await loadExtensionConfig();
    wsUrlDefault = cfg.wsBaseUrl || deriveWsUrlFromApi(cfg.apiBaseUrl) || 'http://localhost:8080';
    wsUrlCurrent = wsUrlDefault;

    return wsUrlDefault;
  }

  // ---------- Enhanced UI Helpers ----------
  function setStatus(text, type = 'disconnected') {
    if (els.wsStatus) {
      els.wsStatus.textContent = text;
      els.wsStatus.setAttribute('data-status', type);
    }
  }

  function handleWsStatusMessage(message = {}) {
    const status = message.status || 'disconnected';
    const detail = message.detail || {};
    wsStatusCache = { status, detail, url: message.url };

    if (detail.heartbeat) {
      return; // avoid chatty logs for keep-alives
    }

    switch (status) {
      case 'connecting':
        setStatus('Connecting...', 'scanning');
        enableControls(false);
        break;
      case 'reconnecting':
        setStatus('Reconnecting...', 'scanning');
        enableControls(false);
        logAnswer('Attempting to reconnect...', 'info');
        break;
      case 'connected':
        setStatus('Connected', 'connected');
        enableControls(true);
        logAnswer('WebSocket connected (background)', 'success');
        refreshEvidenceDisplay();
        break;
      case 'error':
        setStatus('Connection Error', 'error');
        enableControls(false);
        if (detail.message) {
          logAnswer(`WebSocket error: ${detail.message}`, 'error');
        }
        break;
      default:
        setStatus('Disconnected', 'disconnected');
        enableControls(false);
        if (detail?.reason && !detail.manual) {
          logAnswer(`Connection lost: ${detail.reason}`, 'error');
        }
        break;
    }
  }

  function requestWsStatus() {
    try {
      chrome.runtime?.sendMessage({ type: 'WS_GET_STATUS' }, (res) => {
        if (chrome.runtime?.lastError) return;
        if (res?.status) handleWsStatusMessage(res.status);
      });
    } catch {}
  }

  chrome.runtime?.onMessage?.addListener((msg) => {
    if (!msg || typeof msg !== 'object') return;
    if (msg.type === 'WS_STATUS') {
      handleWsStatusMessage(msg);
    }
    if (msg.type === 'WS_MESSAGE') {
      handleMessage(msg.data);
    }
  });

  function formatEndpoint(url) {
    if (!url) return '';
    try {
      const parsed = new URL(url);
      return parsed.host || url;
    } catch (err) {
      return url.replace(/^https?:\/\//, '');
    }
  }

  function setConnectionStatus(text, type = 'disconnected') {
    const endpoint = formatEndpoint(wsUrlCurrent || wsUrlDefault);
    const label = endpoint ? `${text} • ${endpoint}` : text;
    setStatus(label, type);
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
      els.btnEnrol, els.btnState, els.btnScan, els.btnScanBrain,
      els.btnFinalise, els.btnExport, els.btnCompile,
      els.btnAsk, els.btnAskFb, els.btnClearChat,
      els.btnClearEvidence,
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

  // ---------- Conversational & AI helpers ----------
  function addChatMessage(role, content, context = 'ask') {
    if (!content) return;
    const entry = {
      role,
      content: content.toString(),
      context,
      ts: new Date(),
    };
    const labelMap = { user: 'You', assistant: 'VAMP', system: 'System' };
    entry.label = labelMap[role] || role;
    entry.contextLabel = context === 'brain' ? 'Brain Scan' : context === 'ask' ? 'Ask VAMP' : context;

    chatState.entries.push(entry);
    if (chatState.entries.length > chatState.maxEntries) {
      chatState.entries.splice(0, chatState.entries.length - chatState.maxEntries);
    }

    renderChatHistory();
  }

  function renderChatHistory() {
    if (!els.chatHistory) return;
    const target = els.chatHistory;
    target.innerHTML = '';

    if (!chatState.entries.length) {
      const empty = document.createElement('div');
      empty.className = 'chat-line empty';
      empty.textContent = 'No conversation yet — ask VAMP to begin.';
      target.appendChild(empty);
      return;
    }

    chatState.entries.slice(-chatState.maxEntries).forEach((entry) => {
      const line = document.createElement('div');
      line.className = `chat-line ${entry.role}`;

      const meta = document.createElement('div');
      meta.className = 'chat-meta';
      const who = document.createElement('span');
      who.textContent = entry.label;
      const ctx = document.createElement('span');
      ctx.className = 'chat-context';
      ctx.textContent = `${entry.contextLabel} • ${entry.ts.toLocaleTimeString()}`;
      meta.appendChild(who);
      meta.appendChild(ctx);

      const content = document.createElement('div');
      content.className = 'chat-content';
      content.innerHTML = escapeHtml(entry.content).replace(/\n/g, '<br>');

      line.appendChild(meta);
      line.appendChild(content);
      target.appendChild(line);
    });
  }

  function recordAskMessage(role, content) {
    if (!content) return;
    if (!['user', 'assistant'].includes(role)) return;
    askConversation.push({ role, content: content.toString() });
    if (askConversation.length > 20) {
      askConversation.splice(0, askConversation.length - 20);
    }
  }

  function clearAskConversation() {
    askConversation = [];
    chatState.entries = chatState.entries.filter(entry => entry.context !== 'ask');
    renderChatHistory();
  }

  function describeTimestamp(item) {
    const iso = item.date || item.modified || item.timestamp || '';
    const raw = item.raw_timestamp || item.timestamp_relative || '';
    const estimated = Boolean(item.timestamp_estimated);
    let confidence = Number(item.timestamp_confidence);
    if (!Number.isFinite(confidence)) {
      confidence = estimated ? 0.5 : 0.92;
    }
    confidence = Math.max(0, Math.min(1, confidence));
    const confidencePercent = Math.round(confidence * 100);
    const displayText = iso ? formatDate(iso) : (raw || 'N/A');
    const chipClass = estimated ? 'estimated' : 'exact';
    const badge = estimated ? '≈' : '✔';
    const tooltipParts = [];
    if (raw) tooltipParts.push(`Original: ${raw}`);
    tooltipParts.push(estimated ? 'Confidence estimated from AI synthesis' : 'Captured directly from Outlook');
    const tooltip = tooltipParts.join(' • ');
    const chip = `<span class="confidence-chip ${chipClass}" title="${escapeHtml(confidencePercent + '% confidence')}">${badge} ${confidencePercent}%</span>`;
    return {
      displayText,
      confidencePercent,
      chipClass,
      badge,
      tooltip,
      rawText: raw,
      estimated,
      html: `${escapeHtml(displayText)} ${chip}`,
    };
  }

  function updateBrainSummary(summary, meta = {}) {
    if (!els.brainSummary) return;
    const text = (summary || '').toString().trim();
    if (!text) {
      els.brainSummary.textContent = 'No AI synthesis yet. Run a scan via Brain to populate this panel.';
      return;
    }

    const extras = [];
    const added = Number(meta.added);
    const total = Number(meta.total);
    if (Number.isFinite(added)) {
      extras.push(`${added} new item${added === 1 ? '' : 's'}`);
    }
    if (Number.isFinite(total)) {
      extras.push(`${total} total stored`);
    }

    const metaLine = extras.length ? `<div class="brain-summary-meta">${escapeHtml(extras.join(' • '))}</div>` : '';
    els.brainSummary.innerHTML = `${escapeHtml(text)}${metaLine}`;
  }

  function recordToolFeedback(tools, origin = 'ASK') {
    if (!Array.isArray(tools) || !tools.length) {
      renderToolFeedback();
      return;
    }

    const now = new Date();
    tools.forEach((tool) => {
      if (!tool || typeof tool !== 'object') return;
      const entry = {
        tool: (tool.tool || tool.action || 'unknown').toString(),
        status: (tool.status || 'info').toString().toLowerCase(),
        items: Number(tool.items_found ?? tool.count ?? 0) || 0,
        total: Number(tool.total_month_items ?? tool.total ?? 0) || 0,
        note: (tool.error || tool.reason || tool.summary || '').toString(),
        origin,
        ts: now,
      };
      toolEvents.push(entry);
    });

    if (toolEvents.length > TOOL_EVENT_LIMIT) {
      toolEvents.splice(0, toolEvents.length - TOOL_EVENT_LIMIT);
    }

    renderToolFeedback();
  }

  function renderToolFeedback() {
    if (!els.toolFeedback) return;
    const target = els.toolFeedback;
    target.innerHTML = '';

    if (!toolEvents.length) {
      const empty = document.createElement('li');
      empty.className = 'tool-empty';
      empty.textContent = 'No tool activity yet.';
      target.appendChild(empty);
      return;
    }

    toolEvents.slice(-TOOL_EVENT_LIMIT).reverse().forEach((entry) => {
      const li = document.createElement('li');
      const meta = document.createElement('div');
      meta.className = 'tool-meta';
      meta.innerHTML = `<span>${escapeHtml(entry.tool)}</span><span>${escapeHtml(entry.origin)} • ${entry.ts.toLocaleTimeString()}</span>`;

      const body = document.createElement('div');
      body.className = 'tool-body';
      const statusClass = entry.status === 'success' ? 'status-success' : entry.status === 'error' ? 'status-error' : 'status-warning';
      const counts = entry.items ? `Δ ${entry.items}` : 'Δ 0';
      const total = entry.total ? `Total ${entry.total}` : '';
      const noteParts = [counts];
      if (total) noteParts.push(total);
      if (entry.note) noteParts.push(entry.note);
      body.innerHTML = `<span class="${statusClass}">${escapeHtml(entry.status)}</span> — ${escapeHtml(noteParts.join(' • '))}`;

      li.appendChild(meta);
      li.appendChild(body);
      target.appendChild(li);
    });
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
      const tsMeta = describeTimestamp(item);
      const sourceDisplay = getSourceDisplay(item.platform || item.source);

      return `
        <tr data-index="${index}" class="${selectedEvidenceItem === index ? 'selected' : ''}">
          <td title="${escapeHtml(item.source)}">${typeIcon}</td>
          <td title="${escapeHtml(item.title || 'No title')}">${truncateText(escapeHtml(item.title || 'No title'), 25)}</td>
          <td class="timestamp-cell" title="${escapeHtml(tsMeta.tooltip)}">${tsMeta.html}</td>
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
          aVal = new Date(a.date || a.modified || a.timestamp || 0);
          bVal = new Date(b.date || b.modified || b.timestamp || 0);
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
    const tsMeta = describeTimestamp(item);
    if ($('detailDate')) $('detailDate').textContent = tsMeta.displayText;
    if (els.detailDateConfidence) {
      const modeLabel = tsMeta.estimated ? 'Estimated' : 'Exact';
      els.detailDateConfidence.textContent = `${tsMeta.confidencePercent}% • ${modeLabel}`;
    }
    if (els.detailRawTimestamp) {
      els.detailRawTimestamp.textContent = tsMeta.rawText || 'Not provided';
    }
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
      const datePart = date.toLocaleDateString();
      const timePart = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      return `${datePart} ${timePart}`;
    } catch {
      return 'N/A';
    }
  }

  function readMeta(name) {
    try {
      return document.querySelector(`meta[name="${name}"]`)?.content;
    } catch {
      return undefined;
    }
  }

  function normalizeWsUrl(input) {
    if (!input) return null;
    try {
      const parsed = new URL(input.toString().trim());
      if (['ws:', 'wss:'].includes(parsed.protocol)) {
        parsed.protocol = parsed.protocol === 'wss:' ? 'https:' : 'http:';
      }
      if (!['http:', 'https:'].includes(parsed.protocol)) return null;
      return parsed.toString().replace(/\/$/, '');
    } catch {
      return null;
    }
  }

  function resolveDefaultWsUrl() {
    const candidates = [
      window.VAMP_WS_URL,
      window.VITE_VAMP_WS_URL,
      readMeta('vamp-ws-default'),
      WS_DEFAULT_PROD,
      WS_DEFAULT_FALLBACK,
    ];

    for (const candidate of candidates) {
      const normalized = normalizeWsUrl(candidate);
      if (normalized) return normalized;
    }
    return WS_DEFAULT_FALLBACK;
  }

  function getBuildWsUrl() {
    try {
      if (globalThis?.VAMP_WS_URL) return globalThis.VAMP_WS_URL;
      if (globalThis?.__VAMP_WS_URL__) return globalThis.__VAMP_WS_URL__;
      if (typeof process !== 'undefined' && process?.env?.VAMP_WS_URL) return process.env.VAMP_WS_URL;
    } catch {}
    return '';
  }

  function deriveActiveTabWsUrl() {
    return new Promise((resolve) => {
      const fallback = () => resolve('');
      try {
        if (!chrome?.tabs?.query) return fallback();
        chrome.tabs.query({ active: true, currentWindow: true }, (tabs = []) => {
          const activeUrl = tabs?.[0]?.url;
          if (!activeUrl) return fallback();
          try {
            const parsed = new URL(activeUrl);
            const isLocal = ['localhost', '127.0.0.1'].includes(parsed.hostname);
            const port = parsed.port || (isLocal ? String(LOCAL_WS_PORT) : '');
            const portPart = port ? `:${port}` : '';
            resolve(`${parsed.protocol}//${parsed.hostname}${portPart}`);
          } catch {
            fallback();
          }
        });
      } catch {
        fallback();
      }
    });
  }

  function restoreSettings() {
    return new Promise((resolve) => {
      const applySettings = (s = {}) => {
        if (els.wsUrl && s.wsUrl)  els.wsUrl.value = s.wsUrl;
        if (els.scanUrl && s.scanUrl) els.scanUrl.value = s.scanUrl;
        if (els.email && s.email)  els.email.value = s.email;
        if (els.name  && s.name)   els.name.value  = s.name;
        if (els.org   && s.org)    els.org.value   = s.org;
        if (els.year  && s.year)   els.year.value  = String(s.year);
        if (els.month && s.month)  els.month.value = String(s.month);
        if (els.askText && typeof s.ask === 'string') els.askText.value = s.ask;
        resolve(s);
      };

      try {
        chrome.storage?.local?.get(['vamp_settings'], (res) => {
          applySettings(res?.vamp_settings || {});
        });
      } catch {
        applySettings();
      }
    });
  }

  async function resolveInitialWsUrl(stored = {}) {
    if (stored.wsUrl) return stored.wsUrl;

    const buildUrl = getBuildWsUrl();
    if (buildUrl) return buildUrl;

    const tabUrl = await deriveActiveTabWsUrl();
    if (tabUrl) return tabUrl;

    return PROD_WS_FALLBACK;
  }

  function applyResolvedWsUrl(url) {
    wsUrlCurrent = url || PROD_WS_FALLBACK;
    if (els.wsUrl) {
      els.wsUrl.value = wsUrlCurrent;
    }
    if (els.wsUrlResolved) {
      els.wsUrlResolved.textContent = wsUrlCurrent;
      els.wsUrlResolved.title = wsUrlCurrent;
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
  function resolveActiveWsUrl() {
    const manual = els.wsUrl?.value?.trim();
    if (manual) return manual;
    if (wsUrlCurrent) return wsUrlCurrent;
    return wsUrlDefault;
  }

  function scheduleReconnect() {
    clearTimeout(reconnectTimer);
    reconnectTimer = setTimeout(() => {
      logAnswer('Attempting to reconnect...', 'info');
      connectWS(resolveActiveWsUrl());
      reconnectDelayMs = Math.min(reconnectDelayMs * 1.5, 10000);
    }, reconnectDelayMs);
  }

  function ensureSocketHandlers() {
    if (socketHandlersRegistered) return;
    socketHandlersRegistered = true;

    SocketIOManager.on('connect', () => {
      setConnectionStatus('Connected', 'connected');
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
    });

    SocketIOManager.on('message', (ev) => handleMessage(ev.data));

    SocketIOManager.on('error', () => {
      setConnectionStatus('Connection Error', 'error');
      logAnswer('WebSocket connection error', 'error');
    });

    SocketIOManager.on('disconnect', (event) => {
      setConnectionStatus('Disconnected', 'disconnected');
      if (event?.code !== 1000) {
        logAnswer(`Connection closed: ${event?.reason || 'Unknown reason'}`, 'error');
      }
      if (!document.hidden) scheduleReconnect();
    });
  }

  function connectWS(url) {
    clearTimeout(reconnectTimer);
    wsUrlCurrent = url || wsUrlCurrent || wsUrlDefault;
    setConnectionStatus('Connecting...', 'scanning');
    ensureSocketHandlers();

    try {
      SocketIOManager.disconnect();
    } catch (err) {
      console.warn('[SocketIO] Disconnect failed', err);
    }

    SocketIOManager.connect(wsUrlCurrent).catch((e) => {
      setStatus('Connection Failed', 'error');
      logAnswer(`Connection error: ${e?.message || e}`, 'error');
      scheduleReconnect();
    });
  }

  function sendWS(obj) {
    if (!SocketIOManager.isConnected()) {
      logAnswer('Not connected - reconnecting...', 'warning');
      connectWS(resolveActiveWsUrl());
      setTimeout(() => {
        if (SocketIOManager.isConnected()) {
          SocketIOManager.send(obj);
          logAnswer('Command sent after reconnect', 'success');
        } else {
          logAnswer('Failed to reconnect for command', 'error');
        }
      }, 500);
      return;
    }

    try {
      SocketIOManager.send(obj);
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
        const summaryText = brainSummary || `Scan complete. ${added} new items recorded.`;
        updateBrainSummary(summaryText, { added, total });
        if (summaryText) {
          logAnswer(`🧠 ${summaryText}`, 'info');
        }
        const toolList = Array.isArray(data.tools) ? data.tools : (Array.isArray(msg.tools) ? msg.tools : []);
        recordToolFeedback(toolList, 'Brain Scan');
        enableControls(true);
        setConnectionStatus('Connected', 'connected');
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
        setConnectionStatus('Connected', 'connected');
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
        const modeRaw = data.mode || msg.mode || 'ask';
        const mode = typeof modeRaw === 'string' ? modeRaw : 'ask';
        const tools = Array.isArray(data.tools) ? data.tools : (Array.isArray(msg.tools) ? msg.tools : []);
        const context = mode === 'brain_scan' ? 'brain' : (mode === 'assessor_strict' ? 'assessor' : 'ask');

        if (mode !== 'brain_scan') {
          if (tools.length) {
            recordToolFeedback(tools, 'Ask');
          } else {
            recordToolFeedback([], 'Ask');
          }
        }

        if (answer) {
          addChatMessage('assistant', answer, context);
          if (context === 'ask') {
            recordAskMessage('assistant', answer);
          }
          if (mode !== 'brain_scan') {
            logAnswer(`🧠 ${answer}`, 'info');
          }
        }

        if (mode !== 'brain_scan' || !isBusy) {
          enableControls(true);
          setConnectionStatus('Connected', 'connected');
        }
        break;
      }

      case 'ASK_FEEDBACK': {
        const answer = (data.answer || msg.answer || '').toString();
        if (answer) {
          addChatMessage('assistant', answer, 'assessor');
          logAnswer(`📋 ${answer}`, 'info');
        }
        enableControls(true);
        setConnectionStatus('Connected', 'connected');
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

  chrome.runtime?.onMessage.addListener((msg) => {
    if (msg?.type === 'WS_STATUS') {
      applyWorkerStatus(msg.state);
    }
    if (msg?.type === 'WS_EVENT' && msg.payload) {
      logAnswer(`Background event: ${msg.payload}`, 'info');
    }
    if (msg?.type === 'PONG') {
      logAnswer('Service worker responded to ping', 'success');
    }
  });

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

  async function onScanBrain() {
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
    setScanNote('Requesting NWU Brain orchestrator...');
    setStatus('Scanning...', 'scanning');
    startHeartbeat();

    addChatMessage('user', 'Scan via Brain orchestrator initiated.', 'brain');

    sendWS({
      action: 'ASK',
      mode: 'brain_scan',
      email: s.email,
      name: s.name,
      org: s.org || 'NWU',
      year,
      month,
      url: scanUrl,
      deep_read: true,
      messages: [
        {
          role: 'user',
          content: `Run the scan_active connector immediately for ${s.email || 'this user'} using ${scanUrl}. After the connector completes, report how many artefacts were added and the new monthly total.`,
        }
      ]
    });

    logAnswer('Delegating scan to NWU Brain orchestrator...', 'info');
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
    addChatMessage('user', q, 'ask');
    recordAskMessage('user', q);
    const messages = askConversation.map(entry => ({ role: entry.role, content: entry.content }));
    sendWS({
      action: 'ASK',
      year, month,
      messages,
      mode: 'ask'
    });
    logAnswer('Asking VAMP...', 'info');
  }

  function onClearChat() {
    clearAskConversation();
    logAnswer('Chat history cleared.', 'info');
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
    addChatMessage('user', q, 'assessor');
    sendWS({
      action: 'ASK_FEEDBACK',
      year, month,
      messages: coerceMessages(q),
      mode: 'assessor_strict'
    });
    logAnswer('Requesting strict assessment...', 'info');
  }

  // Evidence display handlers
  function onClearEvidence() {
    clearEvidenceDisplay();
  }

  // ---------- Enhanced Initialization ----------
  document.addEventListener('DOMContentLoaded', () => {
    (async () => {
      playOpenSound();
      ensureYearMonth();
      const storedSettings = await restoreSettings();
      renderChatHistory();
      renderToolFeedback();
      updateBrainSummary('', {});

      const resolvedUrl = await resolveInitialWsUrl(storedSettings);
      applyResolvedWsUrl(resolvedUrl);
      logAnswer(`Resolved WebSocket URL: ${wsUrlCurrent}`, 'info');

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

      connectWS(wsUrlCurrent);

      // Event listeners
      els.btnEnrol?.addEventListener('click', (e) => { e.preventDefault(); onEnrol(); });
      els.btnState?.addEventListener('click', (e) => { e.preventDefault(); onGetState(); });
      els.btnScan?.addEventListener('click', (e) => { e.preventDefault(); onScanActive(); });
      els.btnScanBrain?.addEventListener('click', (e) => { e.preventDefault(); onScanBrain(); });
      els.btnFinalise?.addEventListener('click', (e) => { e.preventDefault(); onFinaliseMonth(); });
      els.btnExport?.addEventListener('click', (e) => { e.preventDefault(); onExportMonth(); });
      els.btnCompile?.addEventListener('click', (e) => { e.preventDefault(); onCompileYear(); });
      els.btnAsk?.addEventListener('click', (e) => { e.preventDefault(); onAsk(); });
      els.btnAskFb?.addEventListener('click', (e) => { e.preventDefault(); onAskFeedback(); });
      els.btnClearChat?.addEventListener('click', (e) => { e.preventDefault(); onClearChat(); });

      // Evidence display listeners
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
          applyResolvedWsUrl(wsUrlCurrent);
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
        if (SocketIOManager.isConnected()) {
          refreshEvidenceDisplay();
        }
      }, 1000);
    })();
  });

  window.addEventListener('unload', () => {
    stopHeartbeat();
    clearTimeout(reconnectTimer);
    clearTimeout(scanTimeout);
    SocketIOManager.disconnect();
  });
})();


