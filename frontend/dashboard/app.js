const DEFAULT_API_ROOT = 'http://localhost:8080/api';

function sanitizeApiRoot(value) {
  if (!value || typeof value !== 'string') return DEFAULT_API_ROOT;
  const trimmed = value.trim();
  if (!trimmed) return DEFAULT_API_ROOT;
  const normalized = trimmed.replace(/\/+$/, '');
  return normalized || DEFAULT_API_ROOT;
}

function resolveEnvApiRoot() {
  const importMeta = typeof import.meta !== 'undefined' ? import.meta : null;
  const globalCandidates = [
    globalThis?.VAMP_API_ROOT,
    globalThis?.API_BASE_URL,
    importMeta?.env?.VAMP_API_ROOT,
    importMeta?.env?.VITE_VAMP_API_ROOT,
    typeof process !== 'undefined' ? process?.env?.VAMP_API_ROOT : undefined,
    typeof process !== 'undefined' ? process?.env?.VITE_VAMP_API_ROOT : undefined,
  ];
  return globalCandidates.find((value) => typeof value === 'string' && value.trim())?.trim();
}

function resolveMetaApiRoot() {
  const meta = document.querySelector('meta[name="vamp-api-root"]');
  const content = meta?.getAttribute('content');
  return content?.trim();
}

function resolveApiRoot() {
  const stored = window.localStorage.getItem('vamp-api');
  const meta = resolveMetaApiRoot();
  const env = resolveEnvApiRoot();
  return sanitizeApiRoot(stored || meta || env || DEFAULT_API_ROOT);
}

let API_ROOT = resolveApiRoot();

async function fetchJson(path, options = {}) {
  const res = await fetch(`${API_ROOT}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json();
}

function setChipStatus(element, status) {
  const normalized = (status || 'unknown').toLowerCase();
  element.textContent = status || 'unknown';
  element.classList.remove('success', 'warning', 'danger');
  if (normalized.includes('ok') || normalized.includes('ready')) {
    element.classList.add('success');
  } else if (normalized.includes('warn')) {
    element.classList.add('warning');
  } else if (normalized.includes('fail') || normalized.includes('error') || normalized.includes('down')) {
    element.classList.add('danger');
  }
}

function setStatusTone(element, tone = 'muted') {
  if (!element) return;
  element.classList.remove('success', 'warning', 'danger');
  if (tone) {
    element.classList.add(tone);
  }
}

function updateApiStatus(message, tone = 'muted') {
  const statusEl = document.getElementById('api-status');
  if (!statusEl) return;
  statusEl.textContent = message;
  setStatusTone(statusEl, tone);
}

async function probeApiRoot() {
  updateApiStatus(`Checking ${API_ROOT}/health…`);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 4000);
  try {
    const response = await fetch(`${API_ROOT}/health`, { signal: controller.signal });
    const payload = await response.json().catch(() => ({}));
    const status = payload?.status || payload?.state || response.status || 'ok';
    const message = payload?.message || 'API reachable';
    if (!response.ok) {
      throw new Error(`${status} ${message}`.trim());
    }
    updateApiStatus(`${message} (${status})`, 'success');
    return true;
  } catch (err) {
    const reason = err.name === 'AbortError' ? 'timeout' : err.message;
    updateApiStatus(`Cannot reach API. Update the base URL above or ensure the service is running. (${reason})`, 'danger');
    return false;
  } finally {
    clearTimeout(timeout);
  }
}

function formatDate(input) {
  if (!input) return '—';
  try {
    return new Intl.DateTimeFormat(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(input));
  } catch (err) {
    return String(input);
  }
}

function reportConfigurationError(message) {
  document.getElementById('health-summary').textContent = message;
  document.getElementById('health-raw').textContent = message;
  setChipStatus(document.getElementById('health-status'), 'error');
}

function updateConnectorsTable(connectors) {
  const tbody = document.querySelector('#connectors tbody');
  tbody.innerHTML = '';
  if (!connectors?.length) {
    const row = document.createElement('tr');
    row.innerHTML = '<td colspan="4">No connectors reported</td>';
    tbody.appendChild(row);
    return;
  }

  for (const definition of connectors) {
    const row = document.createElement('tr');
    const enabled = Boolean(definition.enabled);
    row.innerHTML = `
      <td>${definition.name || 'unknown'}</td>
      <td>${definition.status || (enabled ? 'enabled' : 'disabled')}</td>
      <td><input type="checkbox" ${enabled ? 'checked' : ''} data-connector="${definition.name}" aria-label="Toggle ${definition.name}" /></td>
      <td><button data-refresh="${definition.name}">Reload</button></td>
    `;
    tbody.appendChild(row);
  }
}

function renderEvidenceSummary(evidence) {
  const items = evidence?.items || evidence || [];
  const total = Array.isArray(items) ? items.length : evidence?.total || 0;
  document.getElementById('evidence-count').textContent = total;
  if (Array.isArray(items) && items.length) {
    const latest = items[0]?.timestamp || items[0]?.created || items[0]?.date;
    document.getElementById('evidence-latest').textContent = formatDate(latest);
  } else {
    document.getElementById('evidence-latest').textContent = '—';
  }
}

function renderUpdateSummary(updates) {
  const summary = document.getElementById('updates-summary');
  if (!updates) {
    summary.textContent = 'Updates unavailable';
    return;
  }
  const status = updates.status || updates.state || 'unknown';
  const detail = updates.detail || updates.message || '';
  summary.textContent = detail ? `${status}: ${detail}` : status;
  setChipStatus(document.getElementById('connectors-enabled'), status);
}

function renderHealth(health) {
  const status = health?.status || health?.state || 'unknown';
  document.getElementById('health-summary').textContent = health?.message || 'No health details provided.';
  document.getElementById('health-updated').textContent = health?.timestamp ? `Updated ${formatDate(health.timestamp)}` : '';
  setChipStatus(document.getElementById('health-status'), status);
}

async function refresh(preloadedHealth = null) {
  const healthEl = document.getElementById('health-raw');
  healthEl.textContent = 'Refreshing…';
  try {
    const [health, connectors, auth, evidence, updates] = await Promise.all([
      preloadedHealth ? Promise.resolve(preloadedHealth) : fetchJson('/health'),
      fetchJson('/connectors'),
      fetchJson('/auth/sessions'),
      fetchJson('/evidence'),
      fetchJson('/updates/status'),
    ]);

    renderHealth(health);
    document.getElementById('health-raw').textContent = JSON.stringify(health, null, 2);

    const connectorList = connectors?.connectors || [];
    const enabledCount = connectorList.filter((c) => c.enabled).length;
    document.getElementById('connectors-summary').textContent = `${enabledCount}/${connectorList.length || 0} enabled`;
    document.getElementById('connectors-enabled').textContent = `${enabledCount} enabled`;
    updateConnectorsTable(connectorList);

    const sessions = auth?.sessions || [];
    document.getElementById('sessions-count').textContent = sessions.length;
    document.getElementById('auth-raw').textContent = JSON.stringify(auth, null, 2);

    renderEvidenceSummary(evidence);
    document.getElementById('evidence-raw').textContent = JSON.stringify(evidence, null, 2);

    renderUpdateSummary(updates);
    document.getElementById('updates-raw').textContent = JSON.stringify(updates, null, 2);
  } catch (err) {
    const message = `Error: ${err.message}`;
    healthEl.textContent = message;
    document.getElementById('health-summary').textContent = message;
    setChipStatus(document.getElementById('health-status'), 'error');
  }
}

async function refreshSessionState() {
  const service = document.getElementById('session-service').value;
  const identity = document.getElementById('session-identity').value.trim();
  const payload = { service, identity, notes: 'Dashboard refresh' };
  await fetchJson('/auth/session/refresh', { method: 'POST', body: JSON.stringify(payload) });
  await refresh();
}

async function testAi() {
  const statusEl = document.getElementById('ai-status');
  const rawEl = document.getElementById('ai-raw');
  statusEl.textContent = 'Pinging Ollama…';
  try {
    const status = await fetchJson('/ai/status');
    const message = status?.status || status?.message || 'See diagnostics';
    statusEl.textContent = message;
    rawEl.textContent = JSON.stringify(status, null, 2);
  } catch (err) {
    statusEl.textContent = `Error: ${err.message}`;
    rawEl.textContent = `Error: ${err.message}`;
  }
}

async function updateConnector(name, enabled) {
  await fetchJson(`/connectors/${name}`, {
    method: 'POST',
    body: JSON.stringify({ enabled }),
  });
  await refresh();
}

async function checkUpdates() {
  const result = await fetchJson('/updates/check', { method: 'POST' });
  document.getElementById('updates-raw').textContent = JSON.stringify(result, null, 2);
  renderUpdateSummary(result);
}

async function applyUpdate() {
  const result = await fetchJson('/updates/apply', { method: 'POST' });
  document.getElementById('updates-raw').textContent = JSON.stringify(result, null, 2);
  renderUpdateSummary(result);
}

function validateAndPersistApiRoot(value) {
  const trimmed = (value || '').trim();
  if (!trimmed) return null;
  try {
    const normalized = normalizeApiRoot(trimmed);
    window.localStorage.setItem('vamp-api', normalized);
    setApiRoot(normalized);
    document.getElementById('api-root').setCustomValidity('');
    return normalized;
  } catch (err) {
    document.getElementById('api-root').setCustomValidity(err.message);
    document.getElementById('api-root').reportValidity();
    reportConfigurationError(`Configuration error: ${err.message}`);
    return null;
  }
}

async function preflightHealthCheck() {
  const summaryEl = document.getElementById('health-summary');
  summaryEl.textContent = `Checking ${API_ROOT}…`;
  try {
    const health = await fetchJson('/health');
    renderHealth(health);
    document.getElementById('health-raw').textContent = JSON.stringify(health, null, 2);
    return health;
  } catch (err) {
    reportConfigurationError(`Configuration error: ${err.message}`);
    return null;
  }
}

function persistApiRoot() {
  const input = document.getElementById('api-root');
  const value = sanitizeApiRoot(input.value);
  window.localStorage.setItem('vamp-api', value);
  API_ROOT = value;
  input.value = API_ROOT;
  updateApiStatus('Saved API base URL to local storage.', 'success');
}

window.addEventListener('DOMContentLoaded', () => {
  const apiField = document.getElementById('api-root');
  apiField.value = API_ROOT;
  updateApiStatus(`Using API base: ${API_ROOT}`);

  document.getElementById('save-api').addEventListener('click', () => {
    persistApiRoot();
    probeApiRoot().then((reachable) => {
      if (reachable) refresh();
    });
  });
  document.getElementById('refresh').addEventListener('click', refresh);
  document.getElementById('refresh-session').addEventListener('click', refreshSessionState);
  document.getElementById('check-updates').addEventListener('click', checkUpdates);
  document.getElementById('apply-update').addEventListener('click', applyUpdate);
  document.getElementById('test-ai').addEventListener('click', testAi);
  document.querySelector('#connectors tbody').addEventListener('change', (event) => {
    const checkbox = event.target.closest('input[type="checkbox"]');
    if (!checkbox) return;
    updateConnector(checkbox.dataset.connector, checkbox.checked);
  });
  document.querySelector('#connectors tbody').addEventListener('click', (event) => {
    const button = event.target.closest('button[data-refresh]');
    if (!button) return;
    fetchJson(`/connectors/${button.dataset.refresh}`, { method: 'POST', body: JSON.stringify({}) })
      .then(refresh)
      .catch((err) => alert(err.message));
  });

  probeApiRoot().then((reachable) => {
    if (reachable) {
      refresh();
    }
  });
});
