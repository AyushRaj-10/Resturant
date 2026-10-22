/**
 * Main application entry point for Restaurant Order Management System.
 * Connects API, UI, and State without external frameworks.
 */

import * as api from './api.js';
import { state, setMenu, setOrders, setCurrentOrder, setFilters, resetPagination } from './state.js';
import {
  createEl,
  createStatusBadge,
  formatCurrency,
  formatDate,
  showConfirmDialog,
  showToast,
} from './ui.js';

// DOM Selectors
const elements = {
  lookupForm: document.getElementById('lookup-form'),
  lookupId: document.getElementById('lookup-id'),
  btnRefreshAll: document.getElementById('btn-refresh-all'),

  // New Order Form
  orderForm: document.getElementById('order-form'),
  customerNameInput: document.getElementById('customer-name'),
  tableNoInput: document.getElementById('table-no'),
  orderItemsList: document.getElementById('order-items-list'),
  btnAddItem: document.getElementById('btn-add-item'),
  formTotalPreview: document.getElementById('form-total-preview'),
  btnSubmitOrder: document.getElementById('btn-submit-order'),

  // Orders Table & Filters
  filterStatus: document.getElementById('filter-status'),
  filterTable: document.getElementById('filter-table'),
  ordersTable: document.getElementById('orders-table'),
  ordersTbody: document.getElementById('orders-tbody'),
  ordersEmptyState: document.getElementById('orders-empty-state'),
  ordersCountLabel: document.getElementById('orders-count-label'),
  paginationInfo: document.getElementById('pagination-info'),
  pageIndicator: document.getElementById('page-indicator'),
  btnPagePrev: document.getElementById('btn-page-prev'),
  btnPageNext: document.getElementById('btn-page-next'),

  // Detail Modal
  detailModal: document.getElementById('detail-modal'),
  modalTitle: document.getElementById('modal-title'),
  modalStatusBadge: document.getElementById('modal-status-badge'),
  modalSubtitle: document.getElementById('modal-subtitle'),
  modalItemsTbody: document.getElementById('modal-items-tbody'),
  billAdjustForm: document.getElementById('bill-adjust-form'),
  adjustDiscountInput: document.getElementById('adjust-discount'),
  adjustServiceInput: document.getElementById('adjust-service'),
  btnApplyBill: document.getElementById('btn-apply-bill'),
  modalSubtotalVal: document.getElementById('modal-subtotal-val'),
  rowDiscount: document.getElementById('row-discount'),
  modalDiscountLabel: document.getElementById('modal-discount-label'),
  modalDiscountVal: document.getElementById('modal-discount-val'),
  rowService: document.getElementById('row-service'),
  modalServiceLabel: document.getElementById('modal-service-label'),
  modalServiceVal: document.getElementById('modal-service-val'),
  modalGrandTotal: document.getElementById('modal-grand-total'),
  modalActionsContainer: document.getElementById('modal-actions-container'),
  btnCloseModal: document.getElementById('btn-close-modal'),
  btnModalDone: document.getElementById('btn-modal-done'),
};

// ==========================================
// Initialization
// ==========================================

async function init() {
  bindEventListeners();

  try {
    // 1. Fetch Menu Items
    const menuItems = await api.getMenu(true);
    setMenu(menuItems);

    // Initialize line items row
    addLineItemRow();

    // 2. Fetch Live Orders
    await fetchOrders();
  } catch (error) {
    showToast(error.detail || error.message || 'Failed to initialize app data.', 'error');
  }
}

function bindEventListeners() {
  // Quick Search by Order ID
  elements.lookupForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const id = parseInt(elements.lookupId.value.trim(), 10);
    if (!id || id <= 0) return;
    try {
      await openOrderDetail(id);
      elements.lookupId.value = '';
    } catch (err) {
      if (err.status === 404) {
        showToast(`Order #${id} not found.`, 'error');
      } else {
        showToast(err.detail || err.message, 'error');
      }
    }
  });

  // Global Refresh
  elements.btnRefreshAll.addEventListener('click', async () => {
    await fetchOrders();
    showToast('Orders refreshed.', 'info');
  });

  // Add Item in New Order form
  elements.btnAddItem.addEventListener('click', () => {
    addLineItemRow();
  });

  // Submit New Order
  elements.orderForm.addEventListener('submit', handleCreateOrder);

  // Filter Orders
  elements.filterStatus.addEventListener('change', (e) => {
    setFilters({ status: e.target.value.trim() });
    resetPagination();
    fetchOrders();
  });

  elements.filterTable.addEventListener('input', (e) => {
    const val = e.target.value.trim();
    setFilters({ table_no: val ? parseInt(val, 10) : '' });
    resetPagination();
    fetchOrders();
  });

  // Pagination buttons
  elements.btnPagePrev.addEventListener('click', () => {
    if (state.filters.skip <= 0) return;
    setFilters({ skip: Math.max(0, state.filters.skip - state.filters.limit) });
    fetchOrders();
  });

  elements.btnPageNext.addEventListener('click', () => {
    setFilters({ skip: state.filters.skip + state.filters.limit });
    fetchOrders();
  });

  // Modal Close Events
  elements.btnCloseModal.addEventListener('click', closeDetailModal);
  elements.btnModalDone.addEventListener('click', closeDetailModal);

  elements.detailModal.addEventListener('click', (e) => {
    if (e.target === elements.detailModal) closeDetailModal();
  });

  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !elements.detailModal.classList.contains('hidden')) {
      closeDetailModal();
    }
  });

  // Bill Adjustment Form
  elements.billAdjustForm.addEventListener('submit', handleApplyBillAdjustment);
}

// ==========================================
// New Order Form Logic
// ==========================================

function addLineItemRow(menuItemId = null, quantity = 1) {
  const row = createEl('div', { className: 'item-row' });

  // Menu item select dropdown
  const select = createEl('select', { className: 'form-select select-menu-item' });
  select.appendChild(createEl('option', { value: '', textContent: '-- Select Menu Item --' }));

  for (const item of state.menu) {
    const opt = createEl('option', {
      value: item.id.toString(),
      textContent: `${item.name} (${formatCurrency(item.price)})`,
    });
    if (menuItemId && item.id === menuItemId) {
      opt.selected = true;
    }
    select.appendChild(opt);
  }

  // Quantity input
  const qtyInput = createEl('input', {
    type: 'number',
    className: 'form-control input-item-qty',
    min: '1',
    max: '50',
    value: quantity.toString(),
  });

  // Remove row button
  const removeBtn = createEl('button', {
    type: 'button',
    className: 'btn-remove-item',
    textContent: '×',
    title: 'Remove item line',
    onClick: () => {
      row.remove();
      updateFormTotal();
      toggleRemoveButtons();
    },
  });

  select.addEventListener('change', updateFormTotal);
  qtyInput.addEventListener('input', updateFormTotal);

  row.appendChild(select);
  row.appendChild(qtyInput);
  row.appendChild(removeBtn);

  elements.orderItemsList.appendChild(row);
  updateFormTotal();
  toggleRemoveButtons();
}

function toggleRemoveButtons() {
  const rows = elements.orderItemsList.querySelectorAll('.item-row');
  const removeBtns = elements.orderItemsList.querySelectorAll('.btn-remove-item');
  if (rows.length <= 1) {
    removeBtns.forEach((btn) => btn.setAttribute('disabled', ''));
  } else {
    removeBtns.forEach((btn) => btn.removeAttribute('disabled'));
  }
}

function updateFormTotal() {
  let total = 0;
  const rows = elements.orderItemsList.querySelectorAll('.item-row');

  for (const row of rows) {
    const select = row.querySelector('.select-menu-item');
    const qtyInput = row.querySelector('.input-item-qty');
    const itemId = parseInt(select.value, 10);
    const qty = parseInt(qtyInput.value, 10);

    if (itemId && qty > 0) {
      const item = state.menu.find((m) => m.id === itemId);
      if (item) {
        total += parseFloat(item.price) * qty;
      }
    }
  }

  elements.formTotalPreview.textContent = formatCurrency(total);
}

async function handleCreateOrder(e) {
  e.preventDefault();
  if (state.submitting) return;

  const customerName = elements.customerNameInput.value.trim();
  const tableNo = parseInt(elements.tableNoInput.value.trim(), 10);

  // Client validations
  if (!customerName) {
    showToast('Customer name is required.', 'error');
    elements.customerNameInput.focus();
    return;
  }

  if (isNaN(tableNo) || tableNo < 1 || tableNo > 200) {
    showToast('Table number must be between 1 and 200.', 'error');
    elements.tableNoInput.focus();
    return;
  }

  const rows = elements.orderItemsList.querySelectorAll('.item-row');
  const items = [];
  const seenItemIds = new Set();
  const duplicates = [];

  for (const row of rows) {
    const select = row.querySelector('.select-menu-item');
    const qtyInput = row.querySelector('.input-item-qty');
    const menuItemId = parseInt(select.value, 10);
    const quantity = parseInt(qtyInput.value, 10);

    if (!menuItemId) continue;

    if (isNaN(quantity) || quantity < 1 || quantity > 50) {
      showToast('Quantity for each item must be between 1 and 50.', 'error');
      qtyInput.focus();
      return;
    }

    if (seenItemIds.has(menuItemId)) {
      duplicates.push(menuItemId);
    }
    seenItemIds.add(menuItemId);

    items.push({ menu_item_id: menuItemId, quantity });
  }

  if (duplicates.length > 0) {
    showToast('Duplicate menu items selected. Please combine quantities into a single item line.', 'error');
    return;
  }

  if (items.length === 0) {
    showToast('Please select at least one menu item for the order.', 'error');
    return;
  }

  state.submitting = true;
  elements.btnSubmitOrder.disabled = true;
  elements.btnSubmitOrder.textContent = 'Placing Order...';

  try {
    const newOrder = await api.createOrder({
      customer_name: customerName,
      table_no: tableNo,
      items,
    });

    showToast(`Order #${newOrder.id} placed successfully!`, 'success');

    // Reset form
    elements.orderForm.reset();
    elements.orderItemsList.innerHTML = '';
    addLineItemRow();

    // Refresh orders list
    await fetchOrders();
  } catch (err) {
    showToast(err.detail || err.message || 'Failed to place order.', 'error');
  } finally {
    state.submitting = false;
    elements.btnSubmitOrder.disabled = false;
    elements.btnSubmitOrder.textContent = 'Place Order';
  }
}

// ==========================================
// Orders Table & List Logic
// ==========================================

async function fetchOrders() {
  try {
    elements.ordersCountLabel.textContent = 'Fetching orders...';
    const orders = await api.listOrders(state.filters);
    setOrders(orders);
    renderOrdersTable();
  } catch (err) {
    elements.ordersCountLabel.textContent = 'Error loading orders.';
    showToast(err.detail || err.message || 'Could not load orders.', 'error');
  }
}

function renderOrdersTable() {
  const tbody = elements.ordersTbody;
  tbody.innerHTML = '';

  const { orders, filters } = state;

  if (orders.length === 0) {
    elements.ordersTable.classList.add('hidden');
    elements.ordersEmptyState.classList.remove('hidden');
    elements.ordersCountLabel.textContent = '0 orders found';
  } else {
    elements.ordersTable.classList.remove('hidden');
    elements.ordersEmptyState.classList.add('hidden');
    elements.ordersCountLabel.textContent = `${orders.length} orders shown`;

    for (const order of orders) {
      const tr = createEl('tr');

      // ID
      tr.appendChild(createEl('td', {
        className: 'font-mono font-semibold',
        textContent: `#${order.id}`,
      }));

      // Customer name safely using textContent
      tr.appendChild(createEl('td', {
        className: 'font-semibold',
        textContent: order.customer_name,
      }));

      // Table
      tr.appendChild(createEl('td', {
        textContent: `Table ${order.table_no}`,
      }));

      // Status
      const statusTd = createEl('td');
      statusTd.appendChild(createStatusBadge(order.status));
      tr.appendChild(statusTd);

      // Items count
      tr.appendChild(createEl('td', {
        textContent: `${order.item_count} items`,
      }));

      // Total bill
      tr.appendChild(createEl('td', {
        className: 'font-semibold',
        textContent: formatCurrency(order.total_bill),
      }));

      // Created at
      tr.appendChild(createEl('td', {
        className: 'text-dim text-xs',
        textContent: formatDate(order.created_at),
      }));

      // View details button
      const actionTd = createEl('td');
      const viewBtn = createEl('button', {
        type: 'button',
        className: 'btn btn-outline btn-sm',
        textContent: 'View Details',
        onClick: () => openOrderDetail(order.id),
      });
      actionTd.appendChild(viewBtn);
      tr.appendChild(actionTd);

      tbody.appendChild(tr);
    }
  }

  // Update pagination UI
  const currentPage = Math.floor(filters.skip / filters.limit) + 1;
  elements.pageIndicator.textContent = `Page ${currentPage}`;
  elements.paginationInfo.textContent = `Showing offset ${filters.skip} to ${filters.skip + orders.length}`;

  elements.btnPagePrev.disabled = filters.skip <= 0;
  // If fewer items returned than limit, we're likely on last page
  elements.btnPageNext.disabled = orders.length < filters.limit;
}

// ==========================================
// Order Detail Modal Logic
// ==========================================

export async function openOrderDetail(orderId) {
  try {
    const [order, allowedActionsInfo] = await Promise.all([
      api.getOrder(orderId),
      api.getAllowedActions(orderId),
    ]);

    setCurrentOrder(order, allowedActionsInfo.allowed || []);
    renderModalContent();
    elements.detailModal.classList.remove('hidden');
  } catch (err) {
    throw err;
  }
}

function closeDetailModal() {
  elements.detailModal.classList.add('hidden');
  setCurrentOrder(null, []);
}

function renderModalContent() {
  const { currentOrder: order, allowedActions } = state;
  if (!order) return;

  // Header info safely via textContent
  elements.modalTitle.textContent = `Order #${order.id}`;
  elements.modalStatusBadge.innerHTML = '';
  elements.modalStatusBadge.appendChild(createStatusBadge(order.status));
  elements.modalSubtitle.textContent = `Table ${order.table_no} • Customer: ${order.customer_name} • Placed ${formatDate(order.created_at)}`;

  // Populate Line Items
  const itemsTbody = elements.modalItemsTbody;
  itemsTbody.innerHTML = '';

  const canEditQuantity = allowedActions.includes('update_quantity');

  for (const item of order.items) {
    const tr = createEl('tr');

    // Item name
    tr.appendChild(createEl('td', {
      className: 'font-semibold',
      textContent: item.menu_item_name || `Item #${item.menu_item_id}`,
    }));

    // Qty
    const qtyTd = createEl('td');
    if (canEditQuantity) {
      const box = createEl('div', { className: 'inline-qty-box' });
      const qtyInput = createEl('input', {
        type: 'number',
        className: 'form-control input-inline-qty',
        min: '1',
        max: '50',
        value: item.quantity.toString(),
      });
      const saveBtn = createEl('button', {
        type: 'button',
        className: 'btn btn-secondary btn-sm',
        textContent: 'Save',
        onClick: async () => {
          const newQty = parseInt(qtyInput.value, 10);
          if (isNaN(newQty) || newQty < 1 || newQty > 50) {
            showToast('Quantity must be between 1 and 50.', 'error');
            return;
          }
          try {
            await api.updateQuantity(order.id, item.id, newQty);
            showToast('Item quantity updated successfully.', 'success');
            await openOrderDetail(order.id);
            await fetchOrders();
          } catch (err) {
            showToast(err.detail || err.message || 'Failed to update quantity.', 'error');
          }
        },
      });
      box.appendChild(qtyInput);
      box.appendChild(saveBtn);
      qtyTd.appendChild(box);
    } else {
      qtyTd.appendChild(createEl('span', { textContent: item.quantity.toString() }));
    }
    tr.appendChild(qtyTd);

    // Unit Price
    tr.appendChild(createEl('td', {
      textContent: formatCurrency(item.price_at_order_time),
    }));

    // Line Total
    tr.appendChild(createEl('td', {
      className: 'font-semibold',
      textContent: formatCurrency(item.line_total),
    }));

    // Action status note
    const actionTd = createEl('td');
    if (!canEditQuantity) {
      const lockNote = createEl('span', {
        className: 'text-dim text-xs',
        textContent: 'Locked',
        title: 'Item quantities can only be modified for PLACED orders.',
      });
      actionTd.appendChild(lockNote);
    } else {
      actionTd.appendChild(createEl('span', {
        className: 'text-success text-xs',
        textContent: 'Editable',
      }));
    }
    tr.appendChild(actionTd);

    itemsTbody.appendChild(tr);
  }

  // Populate Bill Summaries
  const subtotal = order.items.reduce((sum, it) => sum + parseFloat(it.line_total || 0), 0);
  elements.modalSubtotalVal.textContent = formatCurrency(subtotal);

  if (order.discount_percent && parseFloat(order.discount_percent) > 0) {
    const discAmt = (subtotal * parseFloat(order.discount_percent)) / 100;
    elements.rowDiscount.style.display = 'flex';
    elements.modalDiscountLabel.textContent = `Discount (${parseFloat(order.discount_percent)}%):`;
    elements.modalDiscountVal.textContent = `-${formatCurrency(discAmt)}`;
  } else {
    elements.rowDiscount.style.display = 'none';
  }

  if (order.service_charge_percent && parseFloat(order.service_charge_percent) > 0) {
    const servAmt = (subtotal * parseFloat(order.service_charge_percent)) / 100;
    elements.rowService.style.display = 'flex';
    elements.modalServiceLabel.textContent = `Service Charge (${parseFloat(order.service_charge_percent)}%):`;
    elements.modalServiceVal.textContent = `+${formatCurrency(servAmt)}`;
  } else {
    elements.rowService.style.display = 'none';
  }

  elements.modalGrandTotal.textContent = formatCurrency(order.total_bill);

  // Setup Bill Adjustment inputs
  elements.adjustDiscountInput.value = order.discount_percent ? order.discount_percent.toString() : '';
  elements.adjustServiceInput.value = order.service_charge_percent ? order.service_charge_percent.toString() : '';

  const canEditBill = allowedActions.includes('update_bill');
  elements.btnApplyBill.disabled = !canEditBill;
  elements.adjustDiscountInput.disabled = !canEditBill;
  elements.adjustServiceInput.disabled = !canEditBill;

  if (!canEditBill) {
    elements.btnApplyBill.title = 'Bill discounts and service charges are only allowed on PLACED, PREPARING, or SERVED orders.';
  } else {
    elements.btnApplyBill.removeAttribute('title');
  }

  // Render Lifecycle Buttons
  renderLifecycleActionButtons();
}

function renderLifecycleActionButtons() {
  const { currentOrder: order, allowedActions } = state;
  const container = elements.modalActionsContainer;
  container.innerHTML = '';

  // 1. Transition progression buttons
  const transitionTargets = [
    { target: 'PREPARING', label: 'Mark as Preparing', btnClass: 'btn-primary' },
    { target: 'SERVED', label: 'Mark as Served', btnClass: 'btn-primary' },
    { target: 'PAID', label: 'Mark as Paid', btnClass: 'btn-primary' },
  ];

  for (const { target, label, btnClass } of transitionTargets) {
    const actionKey = `change_status:${target}`;
    const isAllowed = allowedActions.includes(actionKey);

    // Only display the transition button if it's the valid next step
    if (isAllowed) {
      const btn = createEl('button', {
        type: 'button',
        className: `btn ${btnClass}`,
        textContent: label,
        onClick: async () => {
          try {
            await api.changeStatus(order.id, target);
            showToast(`Order #${order.id} transitioned to ${target}!`, 'success');
            await openOrderDetail(order.id);
            await fetchOrders();
          } catch (err) {
            showToast(err.detail || err.message || 'Status transition failed.', 'error');
          }
        },
      });
      container.appendChild(btn);
    }
  }

  // 2. Cancel Button
  const canCancel = allowedActions.includes('cancel');
  const cancelBtn = createEl('button', {
    type: 'button',
    className: 'btn btn-outline',
    textContent: 'Cancel Order',
    disabled: !canCancel,
    title: canCancel ? '' : 'Only PLACED orders can be cancelled.',
    onClick: async () => {
      const confirmed = await showConfirmDialog({
        title: 'Cancel Order',
        message: `Are you sure you want to cancel Order #${order.id}?`,
        confirmText: 'Yes, Cancel Order',
        isDanger: true,
      });

      if (!confirmed) return;

      try {
        await api.cancelOrder(order.id);
        showToast(`Order #${order.id} has been cancelled.`, 'success');
        await openOrderDetail(order.id);
        await fetchOrders();
      } catch (err) {
        showToast(err.detail || err.message || 'Failed to cancel order.', 'error');
      }
    },
  });
  container.appendChild(cancelBtn);

  // 3. Delete Button
  const canDelete = allowedActions.includes('delete');
  const deleteBtn = createEl('button', {
    type: 'button',
    className: 'btn btn-danger',
    textContent: 'Delete Order',
    disabled: !canDelete,
    title: canDelete ? '' : 'Only CANCELLED or PAID orders can be deleted.',
    onClick: async () => {
      const confirmed = await showConfirmDialog({
        title: 'Delete Order Permanently',
        message: `Are you sure you want to delete Order #${order.id}? This action cannot be undone.`,
        confirmText: 'Delete Permanently',
        isDanger: true,
      });

      if (!confirmed) return;

      try {
        await api.deleteOrder(order.id);
        showToast(`Order #${order.id} deleted successfully.`, 'success');
        closeDetailModal();
        await fetchOrders();
      } catch (err) {
        showToast(err.detail || err.message || 'Failed to delete order.', 'error');
      }
    },
  });
  container.appendChild(deleteBtn);
}

async function handleApplyBillAdjustment(e) {
  e.preventDefault();
  const { currentOrder: order } = state;
  if (!order) return;

  const discVal = elements.adjustDiscountInput.value.trim();
  const servVal = elements.adjustServiceInput.value.trim();

  const payload = {};
  if (discVal !== '') {
    const d = parseFloat(discVal);
    if (isNaN(d) || d < 0 || d > 100) {
      showToast('Discount percent must be between 0 and 100.', 'error');
      return;
    }
    payload.discount_percent = d.toFixed(2);
  }

  if (servVal !== '') {
    const s = parseFloat(servVal);
    if (isNaN(s) || s < 0 || s > 30) {
      showToast('Service charge percent must be between 0 and 30.', 'error');
      return;
    }
    payload.service_charge_percent = s.toFixed(2);
  }

  if (Object.keys(payload).length === 0) {
    showToast('Please enter a discount or service charge percentage.', 'error');
    return;
  }

  try {
    await api.updateBill(order.id, payload);
    showToast('Bill adjustments applied successfully.', 'success');
    await openOrderDetail(order.id);
    await fetchOrders();
  } catch (err) {
    showToast(err.detail || err.message || 'Failed to apply bill adjustment.', 'error');
  }
}

// Start application when DOM is ready
document.addEventListener('DOMContentLoaded', init);
