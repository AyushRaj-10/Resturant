/**
 * Shared state container for Restaurant OMS frontend.
 */

export const state = {
  menu: [],
  orders: [],
  currentOrder: null,
  allowedActions: [],
  filters: {
    status: '',
    table_no: '',
    skip: 0,
    limit: 10,
  },
  submitting: false,
};

export function setMenu(items) {
  state.menu = items || [];
}

export function setOrders(orders) {
  state.orders = orders || [];
}

export function setCurrentOrder(order, allowedActions = []) {
  state.currentOrder = order;
  state.allowedActions = allowedActions || [];
}

export function setFilters(partialFilters) {
  state.filters = { ...state.filters, ...partialFilters };
}

export function resetPagination() {
  state.filters.skip = 0;
}
