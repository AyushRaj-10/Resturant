/**
 * Assistant Chat component for Restaurant Order Management System.
 * Manages conversational turns, streaming status, session memory,
 * human confirmation prompts, and live page synchronization.
 */

import * as api from './api.js';
import { renderTrace } from './trace.js';
import { createEl, showToast } from './ui.js';

const SESSION_STORAGE_KEY = 'restaurant_assistant_session_id';

const STARTER_SUGGESTIONS = [
  'Show vegetarian starters',
  'Create an order for Priya, table 3: 2 butter naan',
  'Explain the bill for order 1',
];

const WRITE_DESTRUCTIVE_TOOLS = new Set([
  'create_order',
  'update_quantity',
  'update_bill',
  'cancel_order',
  'delete_order',
]);

let chatState = {
  sessionId: null,
  aiStatus: null,
  sending: false,
  activeCountdowns: new Map(), // confirmation_id -> intervalId
  openOrderDetailFn: null,
  refreshOrdersFn: null,
  refreshCurrentOrderDetailFn: null,
};

/**
 * Format remaining seconds into mm:ss.
 */
function formatCountdown(seconds) {
  if (seconds <= 0) return '0:00';
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s < 10 ? '0' : ''}${s}`;
}

/**
 * Parse an order ID from trace data if any tool touched an order.
 */
function extractOrderIdFromTrace(trace) {
  if (!Array.isArray(trace)) return null;
  for (const step of trace) {
    if (step.arguments && step.arguments.order_id) {
      return parseInt(step.arguments.order_id, 10);
    }
    // Check if create_order returned an id in summary or ok step
    if (step.tool === 'create_order' && step.ok && step.summary) {
      const match = step.summary.match(/#?(\d+)/);
      if (match) return parseInt(match[1], 10);
    }
  }
  return null;
}

/**
 * Check if trace contained a successful write or destructive action.
 */
function hasSuccessfulMutations(trace) {
  if (!Array.isArray(trace)) return false;
  return trace.some((step) => {
    return WRITE_DESTRUCTIVE_TOOLS.has(step.tool) && step.ok === true;
  });
}

/**
 * Initialize the Assistant Chat module and bind to DOM elements.
 */
export function initChat({ openOrderDetail, fetchOrders, refreshCurrentOrderDetail }) {
  chatState.openOrderDetailFn = openOrderDetail;
  chatState.refreshOrdersFn = fetchOrders;
  chatState.refreshCurrentOrderDetailFn = refreshCurrentOrderDetail;

  // Retrieve or initialize session ID
  chatState.sessionId = sessionStorage.getItem(SESSION_STORAGE_KEY);
  if (!chatState.sessionId) {
    chatState.sessionId = `sess-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
    sessionStorage.setItem(SESSION_STORAGE_KEY, chatState.sessionId);
  }

  const elements = {
    btnOpen: document.getElementById('btn-open-assistant'),
    panel: document.getElementById('assistant-panel'),
    btnClose: document.getElementById('btn-close-assistant'),
    btnNewChat: document.getElementById('btn-new-chat'),
    aiModeBadge: document.getElementById('chat-ai-mode-badge'),
    aiUnavailableNotice: document.getElementById('chat-ai-unavailable-notice'),
    messagesList: document.getElementById('chat-messages-list'),
    chatForm: document.getElementById('chat-input-form'),
    textarea: document.getElementById('chat-input-textarea'),
    btnSend: document.getElementById('btn-send-message'),
    charCounter: document.getElementById('chat-char-counter'),
  };

  if (!elements.panel) return;

  // 1. Fetch AI Provider Status
  fetchAiStatus(elements.aiModeBadge, elements.aiUnavailableNotice);

  // 2. Event Listeners for Panel Toggle
  elements.btnOpen.addEventListener('click', () => {
    elements.panel.classList.remove('hidden');
    elements.panel.setAttribute('aria-hidden', 'false');
    elements.btnOpen.setAttribute('aria-expanded', 'true');
    elements.textarea.focus();

    // Check for any live pending confirmation actions for this session
    syncPendingActions(elements.messagesList);
  });

  elements.btnClose.addEventListener('click', () => {
    closeChatPanel(elements);
  });

  // Global Escape key support
  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !elements.panel.classList.contains('hidden')) {
      closeChatPanel(elements);
    }
  });

  // New Chat Button
  elements.btnNewChat.addEventListener('click', () => {
    handleNewChat(elements);
  });

  // Textarea input and character counting
  elements.textarea.addEventListener('input', () => {
    const len = elements.textarea.value.length;
    elements.charCounter.textContent = `${len} / 500`;
  });

  // Enter sends, Shift+Enter new line
  elements.textarea.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      elements.chatForm.dispatchEvent(new Event('submit', { cancelable: true }));
    }
  });

  // Form Submission
  elements.chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const message = elements.textarea.value.trim();
    if (!message || chatState.sending) return;

    await sendMessage(message, elements);
  });

  // Render starter chips if messages are empty
  renderEmptyStateIfClean(elements.messagesList, elements.textarea, elements.charCounter);

  // Sync existing pending actions on load
  syncPendingActions(elements.messagesList);
}

function closeChatPanel(elements) {
  elements.panel.classList.add('hidden');
  elements.panel.setAttribute('aria-hidden', 'true');
  elements.btnOpen.setAttribute('aria-expanded', 'false');
  elements.btnOpen.focus();
}

/**
 * Reset session and start fresh conversation.
 */
function handleNewChat(elements) {
  // Clear any running countdown timers
  for (const intervalId of chatState.activeCountdowns.values()) {
    clearInterval(intervalId);
  }
  chatState.activeCountdowns.clear();

  // Generate new session ID
  chatState.sessionId = `sess-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
  sessionStorage.setItem(SESSION_STORAGE_KEY, chatState.sessionId);

  elements.messagesList.innerHTML = '';
  elements.textarea.value = '';
  elements.charCounter.textContent = '0 / 500';
  renderEmptyStateIfClean(elements.messagesList, elements.textarea, elements.charCounter);
  showToast('Started a new conversation.', 'info');
}

/**
 * Fetch and render AI availability badge.
 */
async function fetchAiStatus(badgeEl, noticeEl) {
  try {
    const status = await api.getAiStatus();
    chatState.aiStatus = status;

    if (status.available) {
      const modelName = status.model ? status.model.split('/').pop() : 'Groq';
      badgeEl.textContent = `AI: ${modelName}`;
      badgeEl.className = 'badge badge-ai-online';
      if (noticeEl) noticeEl.classList.add('hidden');
    } else {
      badgeEl.textContent = 'AI unavailable (fallback)';
      badgeEl.className = 'badge badge-ai-offline';
      if (noticeEl) noticeEl.classList.remove('hidden');
    }
  } catch {
    badgeEl.textContent = 'AI offline';
    badgeEl.className = 'badge badge-ai-offline';
    if (noticeEl) noticeEl.classList.remove('hidden');
  }
}

/**
 * Render empty state with suggestion chips.
 */
function renderEmptyStateIfClean(listEl, textareaEl, counterEl) {
  if (listEl.children.length > 0) return;

  const emptyWrapper = createEl('div', { className: 'chat-empty-state', id: 'chat-starter-empty' });
  emptyWrapper.appendChild(createEl('div', { className: 'chat-empty-icon', textContent: '👋' }));
  emptyWrapper.appendChild(createEl('h3', { className: 'chat-empty-title', textContent: 'How can I help you today?' }));
  emptyWrapper.appendChild(createEl('p', {
    className: 'chat-empty-desc',
    textContent: 'Ask about menu items, place table orders, check order statuses, or request bill adjustments.',
  }));

  const chipsContainer = createEl('div', { className: 'chat-chips-container' });
  chipsContainer.appendChild(createEl('div', { className: 'chat-chips-label', textContent: 'Quick suggestions:' }));

  STARTER_SUGGESTIONS.forEach((text) => {
    const chipBtn = createEl('button', {
      type: 'button',
      className: 'btn-chip',
      textContent: text,
      onClick: () => {
        textareaEl.value = text;
        counterEl.textContent = `${text.length} / 500`;
        textareaEl.focus();
      },
    });
    chipsContainer.appendChild(chipBtn);
  });

  emptyWrapper.appendChild(chipsContainer);
  listEl.appendChild(emptyWrapper);
}

/**
 * Core send routine with streaming indicators, disable state, and error handling.
 */
async function sendMessage(message, elements) {
  chatState.sending = true;

  // Clear starter empty state
  const starter = document.getElementById('chat-starter-empty');
  if (starter) starter.remove();

  // 1. Append User Message
  appendUserMessage(message, elements.messagesList);

  // Clear input
  elements.textarea.value = '';
  elements.charCounter.textContent = '0 / 500';
  elements.textarea.disabled = true;
  elements.btnSend.disabled = true;

  // 2. Append Typing Indicator
  const typingBubble = appendTypingIndicator(elements.messagesList);
  scrollToBottom(elements.messagesList);

  try {
    const response = await api.agentChat(message, chatState.sessionId);
    if (response.session_id) {
      chatState.sessionId = response.session_id;
      sessionStorage.setItem(SESSION_STORAGE_KEY, chatState.sessionId);
    }

    typingBubble.remove();

    // 3. Append Assistant Message
    appendAssistantMessage(response, elements.messagesList);

    // 4. Handle Pending Confirmation Card
    if (response.pending_confirmation) {
      appendConfirmationCard(response.pending_confirmation, elements.messagesList);
    }

    // 5. Check if live orders on main page need refreshing
    if (hasSuccessfulMutations(response.trace)) {
      if (typeof chatState.refreshOrdersFn === 'function') {
        chatState.refreshOrdersFn();
      }
      if (typeof chatState.refreshCurrentOrderDetailFn === 'function') {
        chatState.refreshCurrentOrderDetailFn();
      }
    }
  } catch (err) {
    typingBubble.remove();
    appendErrorMessage(err, elements.messagesList, elements.btnSend, elements.textarea);
  } finally {
    chatState.sending = false;
    // If not locked by rate limiter countdown, re-enable textarea & send
    if (!elements.btnSend.hasAttribute('data-rate-locked')) {
      elements.textarea.disabled = false;
      elements.btnSend.disabled = false;
      elements.textarea.focus();
    }
    scrollToBottom(elements.messagesList);
  }
}

/**
 * Safely append user message bubble using textContent.
 */
function appendUserMessage(text, listEl) {
  const row = createEl('div', { className: 'chat-row chat-row-user' });
  const bubble = createEl('div', { className: 'chat-bubble chat-bubble-user' });

  const content = createEl('div', {
    className: 'chat-text',
    textContent: text,
  });

  bubble.appendChild(content);
  row.appendChild(bubble);
  listEl.appendChild(row);
}

/**
 * Safely append assistant message bubble with agent badges, safe text, trace, and order links.
 */
function appendAssistantMessage(data, listEl) {
  const row = createEl('div', { className: 'chat-row chat-row-assistant' });
  const bubble = createEl('div', { className: 'chat-bubble chat-bubble-assistant' });

  // Meta header: Agent name badge & Source badge
  const metaHeader = createEl('div', { className: 'chat-msg-meta' });

  let agentDisplay = 'Restaurant Assistant';
  if (data.agent === 'order_agent') agentDisplay = 'Order Specialist';
  else if (data.agent === 'billing_agent') agentDisplay = 'Billing Specialist';
  else if (data.agent === 'router_agent') agentDisplay = 'Router';

  const agentBadge = createEl('span', {
    className: 'badge badge-agent-name',
    textContent: agentDisplay,
  });

  const sourceBadge = createEl('span', {
    className: `badge ${data.source === 'llm' ? 'badge-source-ai' : 'badge-source-template'}`,
    textContent: data.source === 'llm' ? '✨ AI' : '📋 Template',
  });

  metaHeader.appendChild(agentBadge);
  metaHeader.appendChild(sourceBadge);
  bubble.appendChild(metaHeader);

  // Message content safely rendered with pre-wrap
  const content = createEl('div', {
    className: 'chat-text',
    textContent: data.reply || '',
  });
  bubble.appendChild(content);

  // Quick Action Link: Open Order (if trace mentions a relevant order)
  const orderId = extractOrderIdFromTrace(data.trace);
  if (orderId && typeof chatState.openOrderDetailFn === 'function') {
    const orderLinkBox = createEl('div', { className: 'chat-order-link-box' });
    const orderBtn = createEl('button', {
      type: 'button',
      className: 'btn-order-link',
      textContent: `🔍 Open Order #${orderId}`,
      onClick: () => {
        chatState.openOrderDetailFn(orderId);
      },
    });
    orderLinkBox.appendChild(orderBtn);
    bubble.appendChild(orderLinkBox);
  }

  // Collapsible Trace Timeline Component
  if (Array.isArray(data.trace) && data.trace.length > 0) {
    const traceEl = renderTrace(data.trace, {
      source: data.source,
      steps_used: data.steps_used,
      tool_calls_used: data.tool_calls_used,
      stopped_reason: data.stopped_reason,
    });
    if (traceEl) bubble.appendChild(traceEl);
  }

  row.appendChild(bubble);
  listEl.appendChild(row);
}

/**
 * Render typing indicator bubble with animated dots.
 */
function appendTypingIndicator(listEl) {
  const row = createEl('div', { className: 'chat-row chat-row-assistant typing-row' });
  const bubble = createEl('div', { className: 'chat-bubble chat-bubble-assistant typing-bubble' });

  const label = createEl('span', { className: 'typing-label', textContent: 'Assistant is thinking' });
  const dots = createEl('span', { className: 'typing-dots' });
  dots.appendChild(createEl('span', { className: 'dot' }));
  dots.appendChild(createEl('span', { className: 'dot' }));
  dots.appendChild(createEl('span', { className: 'dot' }));

  bubble.appendChild(label);
  bubble.appendChild(dots);
  row.appendChild(bubble);
  listEl.appendChild(row);
  return row;
}

/**
 * Render inline error bubble with server detail and rate-limit countdown lock.
 */
function appendErrorMessage(error, listEl, sendBtn, textareaEl) {
  const row = createEl('div', { className: 'chat-row chat-row-error' });
  const bubble = createEl('div', { className: 'chat-bubble chat-bubble-error' });

  const header = createEl('div', { className: 'error-header' });
  header.appendChild(createEl('span', { className: 'error-icon', textContent: '⚠' }));
  header.appendChild(createEl('span', {
    className: 'error-title',
    textContent: error.status === 429 ? 'Rate Limit Exceeded' : 'Request Failed',
  }));
  bubble.appendChild(header);

  const detailText = error.detail || error.message || 'An error occurred while contacting the assistant.';
  const msgBody = createEl('div', {
    className: 'error-body',
    textContent: detailText,
  });
  bubble.appendChild(msgBody);

  row.appendChild(bubble);
  listEl.appendChild(row);

  // If 429 Rate Limit: temporarily lock send button for 5 seconds with countdown
  if (error.status === 429) {
    sendBtn.setAttribute('data-rate-locked', 'true');
    sendBtn.disabled = true;
    textareaEl.disabled = true;

    let countdown = 5;
    const origText = sendBtn.textContent;
    sendBtn.textContent = `Wait ${countdown}s`;

    const timer = setInterval(() => {
      countdown -= 1;
      if (countdown <= 0) {
        clearInterval(timer);
        sendBtn.removeAttribute('data-rate-locked');
        sendBtn.disabled = false;
        textareaEl.disabled = false;
        sendBtn.textContent = origText;
        textareaEl.focus();
      } else {
        sendBtn.textContent = `Wait ${countdown}s`;
      }
    }, 1000);
  }
}

/**
 * Render prominent Confirmation Card for pending destructive actions.
 */
export function appendConfirmationCard(pendingInfo, listEl) {
  const { confirmation_id: confirmationId, summary, expires_at: expiresAtStr } = pendingInfo;

  const card = createEl('div', {
    className: 'confirm-card',
    id: `confirm-card-${confirmationId}`,
  });

  // Header
  const header = createEl('div', { className: 'confirm-card-header' });
  const titleRow = createEl('div', { className: 'confirm-title-row' });
  titleRow.appendChild(createEl('span', { className: 'confirm-icon', textContent: '🛡️' }));
  titleRow.appendChild(createEl('h4', { className: 'confirm-title', textContent: 'Confirmation Required' }));
  header.appendChild(titleRow);

  // Live Countdown Badge
  const timerBadge = createEl('span', { className: 'badge confirm-timer-badge', textContent: 'Expires in ...' });
  header.appendChild(timerBadge);
  card.appendChild(header);

  // Body
  const body = createEl('div', { className: 'confirm-card-body' });

  // Action Summary (verbatim from server)
  const summaryEl = createEl('p', {
    className: 'confirm-summary-text',
    textContent: summary,
  });
  body.appendChild(summaryEl);

  // Prominent warning line
  const warningEl = createEl('p', {
    className: 'confirm-warning-text',
    textContent: '⚠ Nothing has been changed yet. Please confirm or reject this destructive action.',
  });
  body.appendChild(warningEl);

  // Action Buttons Group
  const btnGroup = createEl('div', { className: 'confirm-btn-group' });

  const btnConfirm = createEl('button', {
    type: 'button',
    className: 'btn btn-danger btn-confirm-action',
    textContent: 'Confirm Action',
  });

  const btnReject = createEl('button', {
    type: 'button',
    className: 'btn btn-secondary btn-reject-action',
    textContent: 'Reject',
  });

  btnGroup.appendChild(btnConfirm);
  btnGroup.appendChild(btnReject);
  body.appendChild(btnGroup);
  card.appendChild(body);

  listEl.appendChild(card);
  scrollToBottom(listEl);

  // Countdown timer logic
  const expiresAt = new Date(expiresAtStr).getTime();

  function updateTimer() {
    const now = Date.now();
    const remainingSeconds = Math.max(0, Math.floor((expiresAt - now) / 1000));

    timerBadge.textContent = `Expires in ${formatCountdown(remainingSeconds)}`;

    if (remainingSeconds <= 0) {
      clearInterval(intervalId);
      chatState.activeCountdowns.delete(confirmationId);

      btnConfirm.disabled = true;
      btnReject.disabled = true;
      timerBadge.textContent = 'Expired';
      timerBadge.className = 'badge badge-failed';

      warningEl.textContent = '⏳ This confirmation request has expired. Please ask the assistant again.';
      warningEl.className = 'confirm-warning-text text-dim';
    }
  }

  const intervalId = setInterval(updateTimer, 1000);
  chatState.activeCountdowns.set(confirmationId, intervalId);
  updateTimer();

  // Action Handlers
  btnConfirm.addEventListener('click', async () => {
    btnConfirm.disabled = true;
    btnReject.disabled = true;
    btnConfirm.textContent = 'Executing...';

    try {
      const res = await api.agentConfirm(confirmationId, chatState.sessionId, true);
      clearInterval(intervalId);
      chatState.activeCountdowns.delete(confirmationId);

      // Replace card with success banner
      card.innerHTML = '';
      card.className = 'confirm-card confirm-card-resolved confirm-card-success';

      const banner = createEl('div', { className: 'confirm-resolved-content' });
      banner.appendChild(createEl('span', { className: 'resolved-icon', textContent: '✓' }));
      banner.appendChild(createEl('strong', { textContent: res.message || 'Action executed successfully.' }));
      card.appendChild(banner);

      showToast(res.message || 'Action confirmed and executed.', 'success');

      // Refresh live orders and detail view on main page
      if (typeof chatState.refreshOrdersFn === 'function') {
        chatState.refreshOrdersFn();
      }
      if (typeof chatState.refreshCurrentOrderDetailFn === 'function') {
        chatState.refreshCurrentOrderDetailFn();
      }
    } catch (err) {
      clearInterval(intervalId);
      chatState.activeCountdowns.delete(confirmationId);

      // Display server error in card and disable buttons
      warningEl.textContent = `⛔ Cannot execute: ${err.detail || err.message}`;
      warningEl.className = 'confirm-warning-text text-danger';
      btnConfirm.disabled = true;
      btnReject.disabled = true;
      btnConfirm.textContent = 'Action Aborted';
    }
  });

  btnReject.addEventListener('click', async () => {
    btnConfirm.disabled = true;
    btnReject.disabled = true;
    btnReject.textContent = 'Rejecting...';

    try {
      const res = await api.agentConfirm(confirmationId, chatState.sessionId, false);
      clearInterval(intervalId);
      chatState.activeCountdowns.delete(confirmationId);

      // Replace card with rejection message
      card.innerHTML = '';
      card.className = 'confirm-card confirm-card-resolved confirm-card-rejected';

      const banner = createEl('div', { className: 'confirm-resolved-content' });
      banner.appendChild(createEl('span', { className: 'resolved-icon', textContent: '✕' }));
      banner.appendChild(createEl('span', { textContent: res.message || 'Cancelled. Nothing was changed.' }));
      card.appendChild(banner);

      showToast('Action rejected. No changes made.', 'info');
    } catch (err) {
      warningEl.textContent = `Error: ${err.detail || err.message}`;
    }
  });
}

/**
 * Fetch and re-render any active pending actions for this session upon load or open.
 */
async function syncPendingActions(listEl) {
  if (!chatState.sessionId) return;
  try {
    const pendingActions = await api.agentPending(chatState.sessionId);
    if (Array.isArray(pendingActions)) {
      pendingActions.forEach((act) => {
        // Prevent duplicate rendering of same confirmation card
        if (!document.getElementById(`confirm-card-${act.confirmation_id}`)) {
          appendConfirmationCard(act, listEl);
        }
      });
    }
  } catch {
    // Non-blocking sync
  }
}

function scrollToBottom(el) {
  el.scrollTop = el.scrollHeight;
}
