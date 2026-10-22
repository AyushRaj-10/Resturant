const API_BASE_URL = 'http://localhost:8000';

async function checkHealth() {
  const statusEl = document.getElementById('status');
  if (!statusEl) return;

  statusEl.className = 'status-box';
  statusEl.innerHTML = `
    <div class="loading-state">
      <span class="spinner"></span>
      <span>Checking ${API_BASE_URL}/health ...</span>
    </div>
  `;

  try {
    const response = await fetch(`${API_BASE_URL}/health`, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
      },
    });

    if (!response.ok) {
      throw new Error(`HTTP error! Status: ${response.status} ${response.statusText}`);
    }

    const data = await response.json();

    statusEl.className = 'status-box ok';
    statusEl.innerHTML = `
      <div class="status-content">
        <div class="status-badge-row">
          <span class="indicator"></span>
          <span class="status-title">Backend API is Healthy</span>
        </div>
        <pre class="status-raw">${JSON.stringify(data, null, 2)}</pre>
      </div>
    `;
  } catch (error) {
    statusEl.className = 'status-box error';
    statusEl.innerHTML = `
      <div class="status-content">
        <div class="status-badge-row">
          <span class="indicator"></span>
          <span class="status-title">Backend Unreachable</span>
        </div>
        <pre class="status-raw">${error.message || 'Failed to connect to backend server. Make sure uvicorn is running on port 8000.'}</pre>
      </div>
    `;
  }
}

document.addEventListener('DOMContentLoaded', () => {
  checkHealth();

  const refreshBtn = document.getElementById('refresh-btn');
  if (refreshBtn) {
    refreshBtn.addEventListener('click', checkHealth);
  }
});
