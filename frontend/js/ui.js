/**
 * UI components, safe rendering helpers, toast notifications, and modal dialogs.
 * Strictly avoids innerHTML with user input to prevent XSS.
 */

const currencyFormatter = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
});

export function formatCurrency(amount) {
  const numeric = typeof amount === 'string' ? parseFloat(amount) : (amount || 0);
  return currencyFormatter.format(isNaN(numeric) ? 0 : numeric);
}

export function formatDate(isoString) {
  if (!isoString) return '—';
  try {
    const d = new Date(isoString);
    return d.toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return isoString;
  }
}

/**
 * Safe DOM element factory ensuring user-controlled text uses textContent.
 */
export function createEl(tag, attrs = {}, children = []) {
  const el = document.createElement(tag);
  for (const [key, val] of Object.entries(attrs)) {
    if (key === 'className') {
      el.className = val;
    } else if (key === 'textContent') {
      el.textContent = val;
    } else if (key.startsWith('on') && typeof val === 'function') {
      el.addEventListener(key.slice(2).toLowerCase(), val);
    } else if (key === 'disabled') {
      if (val) el.setAttribute('disabled', '');
      else el.removeAttribute('disabled');
    } else if (val !== null && val !== undefined) {
      el.setAttribute(key, val);
    }
  }

  const childList = Array.isArray(children) ? children : [children];
  for (const child of childList) {
    if (child === null || child === undefined) continue;
    if (typeof child === 'string' || typeof child === 'number') {
      el.appendChild(document.createTextNode(String(child)));
    } else if (child instanceof Node) {
      el.appendChild(child);
    }
  }
  return el;
}

/**
 * Create a colored status badge element.
 */
export function createStatusBadge(status) {
  const badgeClass = `badge status-${(status || '').toLowerCase()}`;
  return createEl('span', { className: badgeClass, textContent: status });
}

/**
 * Toast notifications.
 */
export function showToast(message, type = 'info') {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = createEl('div', { id: 'toast-container', className: 'toast-container' });
    document.body.appendChild(container);
  }

  const toast = createEl('div', { className: `toast toast-${type}` });
  const icon = createEl('span', {
    className: 'toast-icon',
    textContent: type === 'success' ? '✓' : type === 'error' ? '⚠' : 'ℹ',
  });
  const text = createEl('div', { className: 'toast-message', textContent: message });
  const closeBtn = createEl('button', {
    className: 'toast-close',
    type: 'button',
    textContent: '×',
    onClick: () => removeToast(toast),
  });

  toast.appendChild(icon);
  toast.appendChild(text);
  toast.appendChild(closeBtn);
  container.appendChild(toast);

  // Auto dismiss after 4 seconds
  const timeoutId = setTimeout(() => {
    removeToast(toast);
  }, 4000);

  function removeToast(t) {
    clearTimeout(timeoutId);
    t.classList.add('fade-out');
    t.addEventListener('animationend', () => {
      if (t.parentNode) t.parentNode.removeChild(t);
    });
  }
}

/**
 * Custom accessible confirm modal dialog returning a Promise<boolean>.
 */
export function showConfirmDialog({
  title = 'Confirmation Required',
  message = 'Are you sure you want to proceed?',
  confirmText = 'Confirm',
  cancelText = 'Cancel',
  isDanger = false,
}) {
  return new Promise((resolve) => {
    const backdrop = createEl('div', { className: 'modal-backdrop' });
    const dialog = createEl('div', {
      className: 'modal-dialog modal-confirm',
      role: 'alertdialog',
      'aria-modal': 'true',
    });

    const header = createEl('div', { className: 'modal-header' });
    const titleEl = createEl('h3', { textContent: title });
    header.appendChild(titleEl);

    const body = createEl('div', { className: 'modal-body' });
    const msgEl = createEl('p', { textContent: message });
    body.appendChild(msgEl);

    const footer = createEl('div', { className: 'modal-footer' });
    const cancelBtn = createEl('button', {
      className: 'btn btn-secondary',
      type: 'button',
      textContent: cancelText,
      onClick: () => cleanup(false),
    });
    const confirmBtn = createEl('button', {
      className: `btn ${isDanger ? 'btn-danger' : 'btn-primary'}`,
      type: 'button',
      textContent: confirmText,
      onClick: () => cleanup(true),
    });

    footer.appendChild(cancelBtn);
    footer.appendChild(confirmBtn);

    dialog.appendChild(header);
    dialog.appendChild(body);
    dialog.appendChild(footer);
    backdrop.appendChild(dialog);
    document.body.appendChild(backdrop);

    // Focus confirm or cancel
    confirmBtn.focus();

    // Keydown listener for Esc and Tab trapping
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        cleanup(false);
      } else if (e.key === 'Tab') {
        const focusables = [cancelBtn, confirmBtn];
        if (e.shiftKey && document.activeElement === focusables[0]) {
          e.preventDefault();
          focusables[1].focus();
        } else if (!e.shiftKey && document.activeElement === focusables[1]) {
          e.preventDefault();
          focusables[0].focus();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);

    // Backdrop click
    backdrop.addEventListener('click', (e) => {
      if (e.target === backdrop) cleanup(false);
    });

    function cleanup(result) {
      window.removeEventListener('keydown', handleKeyDown);
      if (backdrop.parentNode) {
        backdrop.parentNode.removeChild(backdrop);
      }
      resolve(result);
    }
  });
}
