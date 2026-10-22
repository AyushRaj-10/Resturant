/**
 * Trace rendering component for Restaurant Order Management System.
 * Visualizes the agent execution plan, tool invocations, and guardrail decisions safely.
 */

import { createEl } from './ui.js';

const STOPPED_REASON_EXPLANATIONS = {
  completed: 'Execution completed normally.',
  max_tool_calls: 'The assistant stopped because it reached its tool call limit.',
  max_steps: 'The assistant stopped because it reached its reasoning step limit.',
  timeout: 'The assistant stopped because processing took too long.',
  llm_unavailable: 'The AI assistant is currently operating in offline fallback mode.',
  error: 'The assistant stopped due to an execution error.',
};

/**
 * Render a readable argument summary (key: value pairs, truncated safely).
 */
function renderArgumentsList(args) {
  if (!args || typeof args !== 'object' || Object.keys(args).length === 0) {
    return null;
  }

  const container = createEl('div', { className: 'trace-args' });
  const label = createEl('div', { className: 'trace-args-label', textContent: 'Arguments:' });
  container.appendChild(label);

  const list = createEl('ul', { className: 'trace-args-list' });
  for (const [key, val] of Object.entries(args)) {
    if (key.startsWith('_')) continue; // Skip internal metadata like _meta

    let valStr;
    if (typeof val === 'object') {
      valStr = JSON.stringify(val);
    } else {
      valStr = String(val);
    }

    if (valStr.length > 80) {
      valStr = valStr.substring(0, 80) + '...';
    }

    const li = createEl('li', { className: 'trace-args-item' });
    li.appendChild(createEl('span', { className: 'trace-arg-key', textContent: `${key}: ` }));
    li.appendChild(createEl('span', { className: 'trace-arg-val', textContent: valStr }));
    list.appendChild(li);
  }

  container.appendChild(list);
  return container;
}

/**
 * Determine icon and status text based on step kind and attributes.
 */
function getStepStatus(step) {
  if (step.kind === 'blocked') {
    return {
      icon: '⛔',
      badgeClass: 'badge-blocked',
      text: 'BLOCKED',
    };
  }
  if (step.kind === 'tool_result') {
    if (step.summary && step.summary.toLowerCase().includes('confirmation')) {
      return {
        icon: '⏳',
        badgeClass: 'badge-pending',
        text: 'WAITING CONFIRMATION',
      };
    }
    if (step.ok === false) {
      return {
        icon: '✗',
        badgeClass: 'badge-failed',
        text: 'FAILED',
      };
    }
    return {
      icon: '✓',
      badgeClass: 'badge-ok',
      text: 'OK',
    };
  }
  if (step.kind === 'tool_call') {
    return {
      icon: '⚡',
      badgeClass: 'badge-invoked',
      text: 'INVOKED',
    };
  }
  if (step.agent === 'router_agent') {
    return {
      icon: '🧭',
      badgeClass: 'badge-routing',
      text: 'ROUTED',
    };
  }
  return {
    icon: 'ℹ',
    badgeClass: 'badge-info',
    text: 'INFO',
  };
}

/**
 * Create a collapsible trace timeline container.
 *
 * @param {Array} trace - Array of trace step objects from AgentRunResult.
 * @param {Object} meta - Metadata containing steps_used, tool_calls_used, stopped_reason.
 * @returns {HTMLElement} Collapsible details element with timeline.
 */
export function renderTrace(trace, meta = {}) {
  if (!Array.isArray(trace) || trace.length === 0) {
    return null;
  }

  const details = createEl('details', { className: 'trace-collapsible' });

  // Summary header acting as collapsible toggle
  const summary = createEl('summary', { className: 'trace-toggle' });
  const summaryLeft = createEl('span', { className: 'trace-toggle-text' });
  summaryLeft.appendChild(createEl('span', { className: 'trace-toggle-icon', textContent: '⚙' }));
  summaryLeft.appendChild(createEl('span', { textContent: ` Show what the assistant did (${trace.length} steps)` }));
  summary.appendChild(summaryLeft);

  // Quick chips in summary
  const summaryChips = createEl('div', { className: 'trace-summary-chips' });
  if (meta.tool_calls_used !== undefined) {
    summaryChips.appendChild(createEl('span', {
      className: 'trace-chip',
      textContent: `${meta.tool_calls_used} tool call${meta.tool_calls_used === 1 ? '' : 's'}`,
    }));
  }
  summary.appendChild(summaryChips);
  details.appendChild(summary);

  // Body container
  const body = createEl('div', { className: 'trace-body' });

  // Ordered timeline list
  const timeline = createEl('ol', { className: 'trace-timeline' });

  trace.forEach((step, index) => {
    const isBlocked = step.kind === 'blocked';
    const statusInfo = getStepStatus(step);

    const li = createEl('li', {
      className: `trace-step ${isBlocked ? 'trace-step-blocked' : ''}`,
    });

    // Step Header: Sequence number, Icon, Title/Agent, Status Badge
    const header = createEl('div', { className: 'trace-step-header' });

    const stepIndex = createEl('span', { className: 'trace-step-num', textContent: `#${index + 1}` });
    const stepIcon = createEl('span', { className: 'trace-step-icon', textContent: statusInfo.icon });

    const titleGroup = createEl('div', { className: 'trace-step-title-group' });
    const agentLabel = createEl('span', {
      className: 'trace-step-agent',
      textContent: step.agent ? step.agent.replace('_', ' ').toUpperCase() : 'AGENT',
    });

    let actionLabelText = '';
    if (step.tool) {
      actionLabelText = ` • ${step.tool}`;
    }
    const actionLabel = createEl('span', { className: 'trace-step-action', textContent: actionLabelText });
    titleGroup.appendChild(agentLabel);
    titleGroup.appendChild(actionLabel);

    const badge = createEl('span', {
      className: `trace-status-badge ${statusInfo.badgeClass}`,
      textContent: statusInfo.text,
    });

    header.appendChild(stepIndex);
    header.appendChild(stepIcon);
    header.appendChild(titleGroup);
    header.appendChild(badge);
    li.appendChild(header);

    // Summary / Explanation line safely via textContent
    if (step.summary) {
      const summaryEl = createEl('div', {
        className: `trace-step-summary ${isBlocked ? 'text-blocked-reason' : ''}`,
        textContent: isBlocked ? `⛔ Guard: ${step.summary}` : step.summary,
      });
      li.appendChild(summaryEl);
    }

    // Arguments breakdown (if any)
    if (step.arguments) {
      const argsEl = renderArgumentsList(step.arguments);
      if (argsEl) li.appendChild(argsEl);
    }

    timeline.appendChild(li);
  });

  body.appendChild(timeline);

  // Footer: Counters & Stopped Reason
  const footer = createEl('div', { className: 'trace-footer' });

  const statsGroup = createEl('div', { className: 'trace-stats-group' });
  if (meta.steps_used !== undefined) {
    statsGroup.appendChild(createEl('span', {
      className: 'trace-stat',
      textContent: `Reasoning steps: ${meta.steps_used}`,
    }));
  }
  if (meta.tool_calls_used !== undefined) {
    statsGroup.appendChild(createEl('span', {
      className: 'trace-stat',
      textContent: `Tool calls: ${meta.tool_calls_used}`,
    }));
  }
  footer.appendChild(statsGroup);

  if (meta.stopped_reason && meta.stopped_reason !== 'completed') {
    const reasonText = STOPPED_REASON_EXPLANATIONS[meta.stopped_reason] || `Stopped: ${meta.stopped_reason}`;
    const reasonEl = createEl('div', {
      className: 'trace-stopped-notice',
      textContent: `ℹ ${reasonText}`,
    });
    footer.appendChild(reasonEl);
  }

  body.appendChild(footer);
  details.appendChild(body);

  return details;
}
