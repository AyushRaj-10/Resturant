/**
 * Audit Log Viewer component for Restaurant Order Management System.
 * Displays immutable audit trails of all tool calls, deterministic guard approvals, and blocked requests.
 */

import * as api from './api.js';
import { createEl, formatDate, showToast } from './ui.js';

let auditState = {
  logs: [],
  filters: {
    decision: '',
    agent_name: '',
    tool_name: '',
    skip: 0,
    limit: 20,
  },
  loading: false,
};

/**
 * Format and pretty-print JSON payload safely without innerHTML.
 */
function createJsonPreBlock(title, data) {
  const box = createEl('div', { className: 'audit-json-box' });
  box.appendChild(createEl('span', { className: 'audit-json-title', textContent: title }));

  const pre = createEl('pre', {
    className: 'audit-json-pre',
    textContent: data !== null && data !== undefined ? JSON.stringify(data, null, 2) : 'null',
  });
  box.appendChild(pre);
  return box;
}

/**
 * Create a decision badge with color coding and text.
 */
function createDecisionBadge(decision) {
  let badgeClass = 'badge-secondary';
  let icon = 'ℹ';

  if (decision === 'ALLOWED') {
    badgeClass = 'badge-allowed';
    icon = '✓';
  } else if (decision === 'BLOCKED') {
    badgeClass = 'badge-blocked';
    icon = '⛔';
  } else if (decision === 'PENDING_CONFIRMATION') {
    badgeClass = 'badge-pending';
    icon = '⏳';
  }

  const badge = createEl('span', { className: `badge audit-decision-badge ${badgeClass}` });
  badge.appendChild(createEl('span', { className: 'badge-icon', textContent: icon }));
  badge.appendChild(createEl('span', { textContent: ` ${decision}` }));
  return badge;
}

/**
 * Initialize and render the Audit Log viewer into a target DOM element.
 *
 * @param {HTMLElement} containerEl - Target element to mount the audit viewer.
 */
export function initAuditViewer(containerEl) {
  containerEl.innerHTML = '';

  const root = createEl('div', { className: 'audit-viewer-root' });

  // 1. Header & Controls Bar
  const header = createEl('div', { className: 'audit-header' });
  const titleGroup = createEl('div', { className: 'audit-title-group' });
  titleGroup.appendChild(createEl('h2', { textContent: 'Agent Audit & Security Log' }));
  titleGroup.appendChild(createEl('p', {
    className: 'card-sub',
    textContent: 'Immutable, fail-closed activity record for all agent tool invocations and guardrail decisions.',
  }));
  header.appendChild(titleGroup);

  const controlsBar = createEl('div', { className: 'audit-controls-bar' });

  // Decision filter
  const filterDecision = createEl('select', {
    className: 'form-select audit-select',
    ariaLabel: 'Filter by decision',
    onChange: (e) => {
      auditState.filters.decision = e.target.value;
      auditState.filters.skip = 0;
      fetchAuditLogs(tbody, paginationEl);
    },
  });
  filterDecision.appendChild(createEl('option', { value: '', textContent: 'All Decisions' }));
  filterDecision.appendChild(createEl('option', { value: 'ALLOWED', textContent: 'ALLOWED Only' }));
  filterDecision.appendChild(createEl('option', { value: 'BLOCKED', textContent: 'BLOCKED Only' }));
  filterDecision.appendChild(createEl('option', { value: 'PENDING_CONFIRMATION', textContent: 'PENDING_CONFIRMATION' }));
  controlsBar.appendChild(filterDecision);

  // Tool name filter
  const filterTool = createEl('input', {
    type: 'text',
    className: 'form-control audit-input-filter',
    placeholder: 'Filter by tool...',
    ariaLabel: 'Filter by tool name',
    onInput: (e) => {
      auditState.filters.tool_name = e.target.value.trim();
      auditState.filters.skip = 0;
      fetchAuditLogs(tbody, paginationEl);
    },
  });
  controlsBar.appendChild(filterTool);

  // Refresh button
  const btnRefresh = createEl('button', {
    type: 'button',
    className: 'btn btn-outline btn-sm',
    textContent: '⟳ Refresh Log',
    onClick: () => {
      fetchAuditLogs(tbody, paginationEl);
      showToast('Audit log refreshed.', 'info');
    },
  });
  controlsBar.appendChild(btnRefresh);

  header.appendChild(controlsBar);
  root.appendChild(header);

  // 2. Table Component
  const tableContainer = createEl('div', { className: 'table-responsive audit-table-wrapper' });
  const table = createEl('table', { className: 'data-table audit-table' });

  const thead = createEl('thead');
  const headerRow = createEl('tr');
  headerRow.appendChild(createEl('th', { textContent: 'Timestamp' }));
  headerRow.appendChild(createEl('th', { textContent: 'Agent' }));
  headerRow.appendChild(createEl('th', { textContent: 'Tool' }));
  headerRow.appendChild(createEl('th', { textContent: 'Decision' }));
  headerRow.appendChild(createEl('th', { textContent: 'Reason / Explanation' }));
  headerRow.appendChild(createEl('th', { textContent: 'Details' }));
  thead.appendChild(headerRow);
  table.appendChild(thead);

  const tbody = createEl('tbody', { className: 'audit-tbody' });
  table.appendChild(tbody);
  tableContainer.appendChild(table);

  // Empty state placeholder
  const emptyState = createEl('div', { className: 'empty-state hidden', id: 'audit-empty-state' });
  emptyState.appendChild(createEl('span', { className: 'empty-icon', textContent: '🛡️' }));
  emptyState.appendChild(createEl('p', { className: 'empty-title', textContent: 'No agent activity recorded yet' }));
  emptyState.appendChild(createEl('p', { className: 'empty-sub', textContent: 'Invocations will appear here as the AI assistant is used.' }));
  tableContainer.appendChild(emptyState);

  root.appendChild(tableContainer);

  // 3. Pagination Controls
  const paginationEl = createEl('div', { className: 'pagination-bar audit-pagination' });
  root.appendChild(paginationEl);

  containerEl.appendChild(root);

  // Initial fetch
  fetchAuditLogs(tbody, paginationEl);
}

/**
 * Fetch and populate audit log rows.
 */
async function fetchAuditLogs(tbody, paginationEl) {
  if (auditState.loading) return;
  auditState.loading = true;

  try {
    const logs = await api.getAuditLog(auditState.filters);
    auditState.logs = logs || [];
    renderAuditRows(tbody, paginationEl);
  } catch (err) {
    showToast(err.detail || err.message || 'Could not load audit log.', 'error');
  } finally {
    auditState.loading = false;
  }
}

/**
 * Render table rows and pagination indicators.
 */
function renderAuditRows(tbody, paginationEl) {
  tbody.innerHTML = '';
  const { logs, filters } = auditState;
  const emptyEl = document.getElementById('audit-empty-state');

  if (logs.length === 0) {
    if (emptyEl) emptyEl.classList.remove('hidden');
  } else {
    if (emptyEl) emptyEl.classList.add('hidden');

    logs.forEach((row) => {
      const isBlocked = row.decision === 'BLOCKED';
      const tr = createEl('tr', { className: isBlocked ? 'audit-row-blocked' : '' });

      // Timestamp
      tr.appendChild(createEl('td', {
        className: 'text-dim text-xs font-mono',
        textContent: formatDate(row.created_at),
      }));

      // Agent
      tr.appendChild(createEl('td', {
        className: 'font-semibold text-xs',
        textContent: row.agent_name || 'system',
      }));

      // Tool
      tr.appendChild(createEl('td', {
        className: 'font-mono text-xs',
        textContent: row.tool_name || '—',
      }));

      // Decision Badge
      const decisionTd = createEl('td');
      decisionTd.appendChild(createDecisionBadge(row.decision));
      tr.appendChild(decisionTd);

      // Reason (plain words, safe textContent)
      const reasonTd = createEl('td', {
        className: `audit-reason-cell ${isBlocked ? 'text-blocked-bold' : ''}`,
        textContent: row.reason || '—',
      });
      tr.appendChild(reasonTd);

      // Expandable payload toggle
      const actionTd = createEl('td');
      const toggleBtn = createEl('button', {
        type: 'button',
        className: 'btn btn-outline btn-sm font-mono',
        textContent: '{ } Payload',
        onClick: () => {
          const isExpanded = detailsRow.classList.toggle('hidden');
          toggleBtn.textContent = isExpanded ? '{ } Payload' : '▲ Hide';
        },
      });
      actionTd.appendChild(toggleBtn);
      tr.appendChild(actionTd);

      tbody.appendChild(tr);

      // Details Drawer Row (hidden by default)
      const detailsRow = createEl('tr', { className: 'audit-details-row hidden' });
      const detailsTd = createEl('td', { colSpan: '6', className: 'audit-details-cell' });

      const payloadGrid = createEl('div', { className: 'audit-payload-grid' });
      payloadGrid.appendChild(createJsonPreBlock('Invocation Arguments', row.arguments));
      payloadGrid.appendChild(createJsonPreBlock('Execution Result', row.result));

      detailsTd.appendChild(payloadGrid);
      detailsRow.appendChild(detailsTd);
      tbody.appendChild(detailsRow);
    });
  }

  // Update Pagination Controls
  paginationEl.innerHTML = '';
  const currentOffset = filters.skip;
  const count = logs.length;
  const currentPage = Math.floor(currentOffset / filters.limit) + 1;

  const info = createEl('span', {
    className: 'pagination-info',
    textContent: `Showing ${currentOffset + 1} - ${currentOffset + count} entries`,
  });
  paginationEl.appendChild(info);

  const btnGroup = createEl('div', { className: 'pagination-buttons' });

  const btnPrev = createEl('button', {
    type: 'button',
    className: 'btn btn-outline btn-sm',
    textContent: '← Prev',
    disabled: currentOffset <= 0,
    onClick: () => {
      filters.skip = Math.max(0, filters.skip - filters.limit);
      fetchAuditLogs(tbody, paginationEl);
    },
  });
  btnGroup.appendChild(btnPrev);

  const indicator = createEl('span', {
    className: 'page-indicator',
    textContent: `Page ${currentPage}`,
  });
  btnGroup.appendChild(indicator);

  const btnNext = createEl('button', {
    type: 'button',
    className: 'btn btn-outline btn-sm',
    textContent: 'Next →',
    disabled: count < filters.limit,
    onClick: () => {
      filters.skip = filters.skip + filters.limit;
      fetchAuditLogs(tbody, paginationEl);
    },
  });
  btnGroup.appendChild(btnNext);

  paginationEl.appendChild(btnGroup);
}
