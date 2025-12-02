const DEFAULT_API_ROOT = 'http://localhost:8080/api';

function normalizeApiRoot(value) {
  if (!value) throw new Error('API root is required.');
  let url;
  try {
    url = new URL(value, window.location.origin);
  } catch (err) {
    throw new Error('API root must be a valid URL.');
  }
  if (!['http:', 'https:'].includes(url.protocol)) {
    throw new Error('API root must use http or https.');
  }
  const sanitizedPath = url.pathname.replace(/\/+$/, '');
  url.pathname = sanitizedPath.endsWith('/api') ? sanitizedPath : `${sanitizedPath || ''}/api`;
  url.hash = '';
  return url.toString().replace(/\/$/, '');
}

function resolveApiRoot() {
  const candidates = [
    {
      value:
        window.__VAMP_API_ROOT__ ||
        window.VAMP_API_ROOT ||
        window.__ENV__?.VAMP_API_ROOT ||
        document.querySelector('meta[name="vamp-api-root"]')?.content,
      source: 'build configuration',
    },
    { value: window.localStorage.getItem('vamp-api'), source: 'local storage' },
    {
      value:
        window.location?.origin && window.location.origin !== 'null'
          ? `${window.location.origin}/api`
          : null,
      source: 'current origin',
    },
    { value: DEFAULT_API_ROOT, source: 'default' },
  ];

  for (const candidate of candidates) {
    if (!candidate.value) continue;
    try {
      const normalized = normalizeApiRoot(candidate.value);
      if (candidate.source === 'local storage' && normalized !== candidate.value) {
        window.localStorage.setItem('vamp-api', normalized);
      }
      return { apiRoot: normalized, source: candidate.source };
    } catch (err) {
      if (candidate.source === 'local storage') {
        window.localStorage.removeItem('vamp-api');
      }
    }
  }

  return { apiRoot: DEFAULT_API_ROOT, source: 'default' };
}

function setApiRoot(apiRoot) {
  API_ROOT = apiRoot;
  document.getElementById('api-root').value = apiRoot;
}

let API_ROOT = resolveApiRoot().apiRoot;

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
  return validateAndPersistApiRoot(input.value);
}

window.addEventListener('DOMContentLoaded', () => {
  setApiRoot(API_ROOT);

  document.getElementById('save-api').addEventListener('click', async () => {
    const normalized = persistApiRoot();
    if (!normalized) return;
    const health = await preflightHealthCheck();
    if (health) refresh(health);
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

  preflightHealthCheck().then((health) => {
    if (health) refresh(health);
  });
});
