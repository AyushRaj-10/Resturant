# REST API Specification & Reference

This document provides a complete reference for all HTTP endpoints exposed by the Restaurant Order Management System backend.

> [!IMPORTANT]
> **No Arbitrary Tool Execution Endpoint**: There is deliberately no HTTP endpoint in this system that executes arbitrary tools or functions. All agent tool calls are invoked strictly within internal orchestrator loops, subject to allowlists, deterministic guardrails, and human confirmations.

---

## 1. Registered Endpoints Summary

All routes are mounted on the FastAPI application instance at `http://localhost:8000`.

### 1.1 Health Check Endpoints
| Method | Path | Purpose | Request Body | Success Code | Error Codes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `GET` | `/health` | Basic application liveness check | None | `200 OK` | `500` |
| `GET` | `/health/db` | Database connectivity readiness probe | None | `200 OK` | `503 Service Unavailable` |

### 1.2 Menu Endpoints
| Method | Path | Purpose | Request Body | Success Code | Error Codes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `GET` | `/menu` | List all menu items (optional `available_only` query) | None | `200 OK` | `500` |
| `GET` | `/menu/{item_id}` | Retrieve specific menu item by primary key | None | `200 OK` | `404 Not Found` |
| `POST` | `/menu` | Create a new menu item | JSON (`name`, `price`, `description`, `available`) | `201 Created` | `400 Bad Request`, `422` |

### 1.3 Orders Endpoints
| Method | Path | Purpose | Request Body | Success Code | Error Codes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `POST` | `/orders` | Place a new customer order with line items | JSON (`customer_name`, `table_no`, `items`) | `201 Created` | `400`, `404`, `422` |
| `GET` | `/orders` | List orders with pagination & filtering (`status`, `table_no`) | None | `200 OK` | `422` |
| `GET` | `/orders/{order_id}` | Retrieve full details of an order | None | `200 OK` | `404 Not Found` |
| `GET` | `/orders/{order_id}/allowed-actions` | Get list of currently allowed operations for order | None | `200 OK` | `404 Not Found` |
| `PATCH` | `/orders/{order_id}/items/{item_id}` | Update quantity of a line item (only if `PLACED`) | JSON (`quantity`) | `200 OK` | `400`, `404`, `409 Conflict`, `422` |
| `PATCH` | `/orders/{order_id}/bill` | Apply discount or service charge (if not `PAID`/`CANCELLED`) | JSON (`discount_percent`, `service_charge_percent`) | `200 OK` | `400`, `404`, `409 Conflict`, `422` |
| `POST` | `/orders/{order_id}/status` | Transition order status (`PLACED` &rarr; `PREPARING` &rarr; `SERVED` &rarr; `PAID`) | JSON (`status`) | `200 OK` | `400`, `404`, `409 Conflict`, `422` |
| `POST` | `/orders/{order_id}/cancel` | Cancel an order (only allowed if currently `PLACED`) | None | `200 OK` | `404`, `409 Conflict` |
| `DELETE` | `/orders/{order_id}` | Permanently delete an order (only if `PAID` or `CANCELLED`) | None | `200 OK` | `404`, `409 Conflict` |

### 1.4 AI Generation Endpoints (No Side Effects)
| Method | Path | Purpose | Request Body | Success Code | Error Codes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `GET` | `/ai/status` | Check if live Groq LLM provider is active or in fallback | None | `200 OK` | `500` |
| `POST` | `/ai/ping` | Diagnostic round-trip ping to LLM provider | JSON (`message`) | `200 OK` | `500` |
| `GET` | `/ai/orders/{order_id}/confirmation` | Generate order placement confirmation message | None | `200 OK` | `404 Not Found` |
| `GET` | `/ai/orders/{order_id}/summary` | Generate formatted order summary | None | `200 OK` | `404 Not Found` |
| `GET` | `/ai/orders/{order_id}/bill-explanation` | Generate plain-language bill breakdown | None | `200 OK` | `404 Not Found` |
| `GET` | `/ai/orders/{order_id}/suggestions` | Generate contextual dish recommendations | None | `200 OK` | `404 Not Found` |
| `GET` | `/ai/menu/{item_id}/description` | Generate enhanced culinary description for dish | None | `200 OK` | `404 Not Found` |
| `POST` | `/ai/draft-order` | Parse unstructured text into draft order proposal | JSON (`text`) | `200 OK` | `422` |

### 1.5 Multi-Agent & Guardrail Endpoints
| Method | Path | Purpose | Request Body | Success Code | Error Codes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `GET` | `/agent/tools` | Inspect registered agent tools and risk levels | None | `200 OK` | `500` |
| `POST` | `/agent/chat` | Send conversational prompt to multi-agent assistant | JSON (`message`, `session_id`) | `200 OK` | `422`, `429 Too Many Requests` |
| `POST` | `/agent/confirm` | Approve or reject a pending destructive action | JSON (`confirmation_id`, `session_id`, `approve`) | `200 OK` | `400 Bad Request`, `404`, `409` |
| `GET` | `/agent/pending` | Query active pending confirmations for session | None (`session_id` query) | `200 OK` | `422` |
| `GET` | `/agent/audit-log` | Inspect immutable audit log records with filters | None (`agent_name`, `decision`, `limit`, `skip`) | `200 OK` | `422` |

---

## 2. API Examples with `curl`

### 2.1 Create an Order
```bash
curl -X POST "http://localhost:8000/orders" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_name": "Aarav Sharma",
    "table_no": 4,
    "items": [
      {"menu_item_id": 1, "quantity": 2},
      {"menu_item_id": 9, "quantity": 4}
    ]
  }'
```

**Response (`201 Created`):**
```json
{
  "id": 1,
  "customer_name": "Aarav Sharma",
  "table_no": 4,
  "status": "PLACED",
  "total_bill": "760.00",
  "discount_percent": null,
  "service_charge_percent": null,
  "created_at": "2026-10-22T17:00:00",
  "updated_at": "2026-10-22T17:00:00",
  "items": [
    {
      "id": 1,
      "menu_item_id": 1,
      "menu_item_name": "Paneer Tikka",
      "quantity": 2,
      "price_at_order_time": "260.00",
      "subtotal": "520.00"
    },
    {
      "id": 2,
      "menu_item_id": 9,
      "menu_item_name": "Garlic Naan",
      "quantity": 4,
      "price_at_order_time": "60.00",
      "subtotal": "240.00"
    }
  ]
}
```

---

### 2.2 Update Line-Item Quantity
```bash
curl -X PATCH "http://localhost:8000/orders/1/items/1" \
  -H "Content-Type: application/json" \
  -d '{"quantity": 3}'
```

**Response (`200 OK`):**
```json
{
  "id": 1,
  "customer_name": "Aarav Sharma",
  "table_no": 4,
  "status": "PLACED",
  "total_bill": "1020.00",
  "discount_percent": null,
  "service_charge_percent": null,
  "created_at": "2026-10-22T17:00:00",
  "updated_at": "2026-10-22T17:02:15",
  "items": [
    {
      "id": 1,
      "menu_item_id": 1,
      "menu_item_name": "Paneer Tikka",
      "quantity": 3,
      "price_at_order_time": "260.00",
      "subtotal": "780.00"
    },
    {
      "id": 2,
      "menu_item_id": 9,
      "menu_item_name": "Garlic Naan",
      "quantity": 4,
      "price_at_order_time": "60.00",
      "subtotal": "240.00"
    }
  ]
}
```

---

### 2.3 Apply Discount & Service Charge
```bash
curl -X PATCH "http://localhost:8000/orders/1/bill" \
  -H "Content-Type: application/json" \
  -d '{
    "discount_percent": 10.0,
    "service_charge_percent": 5.0
  }'
```

**Response (`200 OK`):**
```json
{
  "id": 1,
  "customer_name": "Aarav Sharma",
  "table_no": 4,
  "status": "PLACED",
  "total_bill": "969.00",
  "discount_percent": "10.00",
  "service_charge_percent": "5.00",
  "created_at": "2026-10-22T17:00:00",
  "updated_at": "2026-10-22T17:03:00",
  "items": [...]
}
```

---

### 2.4 Transition Order Status
```bash
curl -X POST "http://localhost:8000/orders/1/status" \
  -H "Content-Type: application/json" \
  -d '{"status": "PREPARING"}'
```

**Response (`200 OK`):**
```json
{
  "id": 1,
  "status": "PREPARING",
  "updated_at": "2026-10-22T17:05:00"
}
```

---

### 2.5 Business Rule Conflict Error (`409 Conflict`)
Attempting to modify line-item quantities on an order that has already transitioned to `PREPARING`:

```bash
curl -X PATCH "http://localhost:8000/orders/1/items/1" \
  -H "Content-Type: application/json" \
  -d '{"quantity": 5}'
```

**Response (`409 Conflict`):**
```json
{
  "detail": {
    "message": "Cannot update item quantity for order #1 because it is currently PREPARING. Quantity updates are only allowed while the order is in PLACED status.",
    "code": "CANNOT_UPDATE_QUANTITY"
  }
}
```

---

### 2.6 Natural Language Draft Order (`POST /ai/draft-order`)
```bash
curl -X POST "http://localhost:8000/ai/draft-order" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Table 4 would like 2 butter chicken and 3 garlic naan for Rahul"
  }'
```

**Response (`200 OK`):**
```json
{
  "customer_name": "Rahul",
  "table_no": 4,
  "items": [
    {
      "menu_item_id": 4,
      "name": "Butter Chicken",
      "quantity": 2,
      "price": "380.00",
      "subtotal": "760.00"
    },
    {
      "menu_item_id": 9,
      "name": "Garlic Naan",
      "quantity": 3,
      "price": "60.00",
      "subtotal": "180.00"
    }
  ],
  "estimated_total": "940.00",
  "confidence": "high",
  "warnings": []
}
```
*Notice: This endpoint merely returns a proposal. Nothing is written to the database.*

---

### 2.7 Agent Chat with Pending Confirmation (`POST /agent/chat`)
```bash
curl -X POST "http://localhost:8000/agent/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Cancel order 1 please",
    "session_id": "demo_session_101"
  }'
```

**Response (`200 OK`):**
```json
{
  "session_id": "demo_session_101",
  "reply": "I have prepared a request to cancel Order #1. Because cancelling an order is a destructive action, please review and confirm the cancellation.",
  "agent": "order",
  "trace": [
    {
      "agent": "router",
      "kind": "message",
      "tool": null,
      "arguments": null,
      "ok": null,
      "summary": "Routing to order specialist: Order cancellation request"
    },
    {
      "agent": "order",
      "kind": "tool_call",
      "tool": "cancel_order",
      "arguments": {"order_id": 1},
      "ok": null,
      "summary": "Proposing tool call: cancel_order"
    },
    {
      "agent": "order",
      "kind": "blocked",
      "tool": "cancel_order",
      "arguments": {"order_id": 1},
      "ok": false,
      "summary": "Confirmation required: This destructive action will cancel order Order #1."
    }
  ],
  "source": "llm",
  "stopped_reason": "completed",
  "pending_confirmation": {
    "confirmation_id": "8a3e7b1c4d9e0f2a4b6c8d0e1f3a5b7c",
    "summary": "Cancel order Order #1",
    "expires_at": "2026-10-22T17:07:00"
  }
}
```

---

### 2.8 Confirm Pending Action (`POST /agent/confirm`)
```bash
curl -X POST "http://localhost:8000/agent/confirm" \
  -H "Content-Type: application/json" \
  -d '{
    "confirmation_id": "8a3e7b1c4d9e0f2a4b6c8d0e1f3a5b7c",
    "session_id": "demo_session_101",
    "approve": true
  }'
```

**Response (`200 OK`):**
```json
{
  "success": true,
  "message": "Action 'cancel_order' was approved and executed successfully."
}
```

---

### 2.9 View Agent Audit Log (`GET /agent/audit-log`)
```bash
curl -X GET "http://localhost:8000/agent/audit-log?limit=5"
```

**Response (`200 OK`):**
```json
{
  "total": 3,
  "logs": [
    {
      "id": 1,
      "agent_name": "order",
      "tool_name": "cancel_order",
      "arguments": {"order_id": 1},
      "decision": "PENDING_CONFIRMATION",
      "reason": "This destructive action will cancel order Order #1. Human confirmation is required before changes can be made.",
      "result": null,
      "created_at": "2026-10-22T17:05:01"
    },
    {
      "id": 2,
      "agent_name": "order",
      "tool_name": "cancel_order",
      "arguments": {"order_id": 1},
      "decision": "ALLOWED",
      "reason": "Action approved by human user.",
      "result": {"status": "CANCELLED"},
      "created_at": "2026-10-22T17:05:30"
    }
  ]
}
```
