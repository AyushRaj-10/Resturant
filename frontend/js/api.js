/**
 * API client module for Restaurant Order Management System.
 * Connects directly to FastAPI backend without third-party libraries.
 */

export const API_BASE = 'http://localhost:8000';

export class ApiError extends Error {
  constructor(status, detail, code) {
    super(detail || `API error with status ${status}`);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
    this.code = code;
  }
}

/**
 * Core HTTP request helper with unified error handling and JSON serialization.
 */
async function request(method, path, body = null) {
  const url = `${API_BASE}${path}`;
  const options = {
    method,
    headers: {
      'Accept': 'application/json',
    },
  };

  if (body !== null) {
    options.headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(url, options);
  } catch (networkError) {
    throw new ApiError(
      0,
      'Cannot reach the server. Make sure the backend is running on http://localhost:8000.',
      'NETWORK_ERROR'
    );
  }

  // Handle empty bodies (e.g. 204 No Content)
  const contentType = response.headers.get('content-type') || '';
  let data = null;
  if (contentType.includes('application/json')) {
    try {
      data = await response.json();
    } catch {
      data = null;
    }
  }

  if (!response.ok) {
    const detail = data?.detail || response.statusText || 'An unexpected error occurred.';
    const code = data?.code || `HTTP_${response.status}`;
    throw new ApiError(response.status, detail, code);
  }

  return data;
}

// Menu endpoints
export async function getMenu(onlyAvailable = true) {
  const query = onlyAvailable ? '?only_available=true' : '';
  return request('GET', `/menu${query}`);
}

// Order endpoints
export async function createOrder(orderData) {
  return request('POST', '/orders', orderData);
}

export async function listOrders({ status = null, table_no = null, skip = 0, limit = 10 } = {}) {
  const params = new URLSearchParams();
  if (status) params.append('status', status);
  if (table_no) params.append('table_no', table_no);
  params.append('skip', skip.toString());
  params.append('limit', limit.toString());

  return request('GET', `/orders?${params.toString()}`);
}

export async function getOrder(orderId) {
  return request('GET', `/orders/${orderId}`);
}

export async function updateQuantity(orderId, itemId, quantity) {
  return request('PATCH', `/orders/${orderId}/items/${itemId}`, { quantity });
}

export async function updateBill(orderId, billData) {
  return request('PATCH', `/orders/${orderId}/bill`, billData);
}

export async function changeStatus(orderId, status) {
  return request('POST', `/orders/${orderId}/status`, { status });
}

export async function cancelOrder(orderId) {
  return request('POST', `/orders/${orderId}/cancel`);
}

export async function deleteOrder(orderId) {
  return request('DELETE', `/orders/${orderId}`);
}

export async function getAllowedActions(orderId) {
  return request('GET', `/orders/${orderId}/allowed-actions`);
}
