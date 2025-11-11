const API_ROOT = window.localStorage.getItem('vamp-api') || 'http://localhost:8080/api';

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

async function refresh() {
  try {
    const [health, connectors, auth, evidence, updates] = await Promise.all([
      fetchJson('/health'),
      fetchJson('/connectors'),
      fetchJson('/auth/sessions'),
      fetchJson('/evidence'),
      fetchJson('/updates/status'),
    ]);

    document.getElementById('health').textContent = JSON.stringify(health, null, 2);
    document.getElementById('auth').textContent = JSON.stringify(auth, null, 2);
    document.getElementById('evidence').textContent = JSON.stringify(evidence, null, 2);
    document.getElementById('updates').textContent = JSON.stringify(updates, null, 2);

    const tbody = document.querySelector('#connectors tbody');
    tbody.innerHTML = '';
    for (const definition of connectors.connectors) {
      const row = document.createElement('tr');
      row.innerHTML = `
        <td>${definition.name}</td>
        <td>${definition.enabled ? 'enabled' : 'disabled'}</td>
        <td><input type="checkbox" ${definition.enabled ? 'checked' : ''} data-connector="${definition.name}" /></td>
        <td><button data-refresh="${definition.name}">Reload</button></td>
      `;
      tbody.appendChild(row);
    }
  } catch (err) {
    document.getElementById('health').textContent = `Error: ${err.message}`;
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
  document.getElementById('updates').textContent = JSON.stringify(result, null, 2);
}

async function applyUpdate() {
  const result = await fetchJson('/updates/apply', { method: 'POST' });
  document.getElementById('updates').textContent = JSON.stringify(result, null, 2);
}

window.addEventListener('DOMContentLoaded', () => {
  document.getElementById('refresh').addEventListener('click', refresh);
  document.getElementById('check-updates').addEventListener('click', checkUpdates);
  document.getElementById('apply-update').addEventListener('click', applyUpdate);
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
  refresh();
});
