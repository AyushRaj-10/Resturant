# System Architecture & Technical Design

This document details the software architecture, data flow, component boundaries, and key design decisions of the Restaurant Order Management System (OMS).

---

## 1. System Architecture Overview

The system is organized into decoupled layers that strictly isolate **untrusted model text generation** from **state-mutating database execution**.

```mermaid
flowchart TB
    subgraph Browser ["Web Browser Client (Port 3000)"]
        UI_Orders["Order Management UI"]
        UI_Chat["Assistant Chat Panel"]
        UI_Audit["Audit Log Viewer"]
    end

    subgraph FastAPI ["FastAPI Application (Port 8000)"]
        subgraph Routers ["FastAPI Routers"]
            R_Menu["/menu Router"]
            R_Orders["/orders Router"]
            R_AI["/ai Router"]
            R_Agent["/agent Router"]
        end

        subgraph Core_Services ["Service & Domain Logic Layer"]
            S_Order["order_service.py"]
            S_Menu["menu_service.py"]
            S_Rules["order_rules.py (Pure State Machine)"]
        end

        subgraph LLM_Gen ["Generation-Only Module (app/llm)"]
            direction TB
            LLM_Client["LLMClient (Text / Proposals)"]
            LLM_Note["[CRITICAL: NO DB ACCESS / NO SERVICES]"]
        end

        subgraph Agent_Subsystem ["Multi-Agent Execution Layer (app/agents)"]
            Orchestrator["Orchestrator"]
            RouterAgent["Router Agent"]
            OrderAgent["Order Specialist"]
            BillingAgent["Billing Specialist"]
            GroqTools["Groq Function Calling Client"]
            Memory["Session Memory Store"]
        end

        subgraph Guardrail_Subsystem ["Deterministic Guardrail Layer (app/agents/guard)"]
            Guard["Deterministic Guard Pipeline (9 Rules)"]
            ConfirmStore["Confirmation Store (In-Memory)"]
            AuditLogger["Audit Logger (Fail-Closed)"]
        end

        subgraph Tool_Layer ["Tool Subsystem (app/agents/tools)"]
            ToolRegistry["Tool Registry (Arg Schemas)"]
        end
    end

    subgraph Database ["Persistent Storage Layer"]
        MySQL[("MySQL Database")]
        T_Menu[("menu_items")]
        T_Orders[("orders & order_items")]
        T_Audit[("agent_audit_log")]
    end

    %% Client to Routers
    UI_Orders -->|REST Requests| R_Orders
    UI_Orders -->|Catalog Queries| R_Menu
    UI_Chat -->|Draft & Summaries| R_AI
    UI_Chat -->|Chat & Confirmations| R_Agent
    UI_Audit -->|Log Queries| R_Agent

    %% Routers to Services & LLM
    R_Menu --> S_Menu
    R_Orders --> S_Order
    R_AI --> LLM_Client
    R_AI -.->|Read-only Context| S_Order
    R_Agent --> Orchestrator
    R_Agent --> ConfirmStore
    R_Agent --> AuditLogger

    %% Services to Pure Rules & DB
    S_Order --> S_Rules
    S_Order --> MySQL
    S_Menu --> MySQL

    %% Agent Routing & Execution
    Orchestrator --> RouterAgent
    RouterAgent -->|Order Intent| OrderAgent
    RouterAgent -->|Billing Intent| BillingAgent
    OrderAgent --> GroqTools
    BillingAgent --> GroqTools
    GroqTools --> ToolRegistry

    %% Guardrail Intervention
    ToolRegistry --> Guard
    Guard --> S_Rules
    Guard -.->|Destructive Proposal| ConfirmStore
    Guard --> AuditLogger
    Guard -->|If ALLOWED| S_Order

    %% Separate Human Confirmation Flow
    R_Agent ==>|Execute Confirmed Token| ConfirmStore
    ConfirmStore ==>|Re-validate & Run| S_Order

    %% Logging
    AuditLogger --> T_Audit
```

---

## 2. Sequence Diagrams

### 2.1 Standard Safe Agent Execution ("Create an order for Priya...")

In a standard safe write action, the model's function call is checked against the deterministic guard. Because `create_order` has `RiskLevel.WRITE`, it is validated against quotas and limits, executed directly, and recorded in the audit log.

```mermaid
sequenceDiagram
    autonumber
    actor User as Diner / Waitstaff
    participant UI as Chat Panel
    participant Router as /agent/chat Router
    participant Orch as Orchestrator
    participant Model as Groq LLM
    participant Guard as Guard Pipeline
    participant Tool as Tool Registry
    participant Service as Order Service
    participant Audit as Audit Log (DB)
    participant DB as MySQL DB

    User->>UI: "Create an order for Priya at Table 5: 1 Butter Chicken, 2 Naan"
    UI->>Router: POST /agent/chat {message, session_id}
    Router->>Orch: handle_message()
    Orch->>Model: Classify intent & extract specialist
    Model-->>Orch: Route to "order" specialist
    Orch->>Model: Run order agent with allowed tool specs
    Model-->>Orch: Tool Call: create_order(customer_name='Priya', table_no=5, items=[...])
    
    Orch->>Tool: execute_tool(create_order, args)
    Tool->>Guard: evaluate(tool_spec, args, context)
    
    Note over Guard: Evaluates 9 deterministic rules:<br/>1. Kill switches (Writes enabled)<br/>2. Allowlist (Allowed for order_agent)<br/>3. Rate limit (< 20 calls/min)<br/>4. Request cap (1/3 writes used)<br/>5. Deduplication check<br/>6. Provenance check (Not destructive)<br/>7. Business rules precheck<br/>8. Value limit (< ₹20,000)<br/>9. Risk level check (WRITE -> ALLOW)
    
    Guard->>Audit: Log tool attempt (Decision: ALLOWED)
    Guard-->>Tool: GuardDecision(outcome="allow")
    
    Tool->>Service: create_order(OrderCreate)
    Service->>DB: INSERT orders & order_items
    DB-->>Service: Committed (Order #12 created)
    Service-->>Tool: OrderResponse (id=12, total=₹500.00)
    Tool-->>Orch: ToolResult(ok=True, data={...})
    
    Orch->>Model: Format final response with tool results
    Model-->>Orch: "I have created Order #12 for Priya at Table 5."
    Orch-->>Router: AgentChatResponse(reply, trace, pending_confirmation=None)
    Router-->>UI: HTTP 200 JSON
    UI-->>User: Displays assistant reply and execution trace
```

---

### 2.2 Guarded Destructive Action ("Cancel Order 5")

When an agent proposes a destructive action (`cancel_order` or `delete_order`), the guard intercepts the operation, issues an ephemeral, single-use confirmation token, and presents the decision to the human user. No database state changes until the user explicitly confirms.

```mermaid
sequenceDiagram
    autonumber
    actor User as Diner / Waitstaff
    participant UI as Chat Panel
    participant Router as /agent/chat & /agent/confirm
    participant Guard as Guard Pipeline
    participant Store as In-Memory Confirmation Store
    participant Service as Order Service
    participant Audit as Audit Log (DB)
    participant DB as MySQL DB

    User->>UI: "Cancel order 5"
    UI->>Router: POST /agent/chat {"message": "Cancel order 5"}
    Router->>Guard: Intercept tool call: cancel_order(order_id=5)
    
    Note over Guard: Provenance Check: "5" exists in human prompt<br/>Business Rule Precheck: Order #5 status is PLACED (can cancel)<br/>Rule 9: DESTRUCTIVE -> needs_confirmation
    
    Guard->>Store: create_confirmation(tool="cancel_order", args={order_id: 5}, ttl=120s)
    Store-->>Guard: confirmation_id = "tok_8f9c1..."
    Guard->>Audit: Log attempt (Decision: PENDING_CONFIRMATION)
    Guard-->>Router: Pending confirmation details
    Router-->>UI: Response with pending_confirmation card
    UI-->>User: Displays warning banner: "Confirm cancellation of Order #5?"

    Note over DB: Database remains 100% UNCHANGED at this stage

    User->>UI: Clicks [Confirm Cancellation]
    UI->>Router: POST /agent/confirm {confirmation_id: "tok_8f9c1...", approve: true}
    Router->>Store: consume_confirmation("tok_8f9c1...")
    Store-->>Router: Confirmed action payload
    
    Note over Router: Re-validates state:<br/>Has Order #5 status transitioned to PREPARING?<br/>If still PLACED, proceed with cancellation.
    
    Router->>Service: cancel_order(order_id=5)
    Service->>DB: UPDATE orders SET status = 'CANCELLED' WHERE id = 5
    DB-->>Service: Updated
    Service-->>Router: Order cancelled successfully
    Router->>Audit: Log execution (Decision: ALLOWED, result={status: "CANCELLED"})
    Router-->>UI: HTTP 200 {success: true, message: "Order #5 cancelled"}
    UI-->>User: Success toast and order status updated on dashboard
```

---

## 3. Relational Database Schema (ER Diagram)

The relational schema is implemented in SQLAlchemy 2.x and persisted in MySQL 8.0:

```mermaid
erDiagram
    MENU_ITEMS ||--o{ ORDER_ITEMS : "referenced_by"
    ORDERS ||--|{ ORDER_ITEMS : "contains"

    MENU_ITEMS {
        int id PK "autoincrement"
        string name "VARCHAR(100), UNIQUE"
        string description "VARCHAR(255), NULLABLE"
        numeric price "NUMERIC(10,2), CHECK(price > 0)"
        boolean available "BOOLEAN, DEFAULT true"
        datetime created_at "DATETIME, server_default=now()"
    }

    ORDERS {
        int id PK "autoincrement"
        string customer_name "VARCHAR(100)"
        int table_no "INTEGER, INDEX"
        enum status "ENUM('PLACED','PREPARING','SERVED','PAID','CANCELLED'), INDEX"
        numeric total_bill "NUMERIC(10,2), DEFAULT 0.00"
        numeric discount_percent "NUMERIC(5,2), NULLABLE"
        numeric service_charge_percent "NUMERIC(5,2), NULLABLE"
        datetime created_at "DATETIME, server_default=now()"
        datetime updated_at "DATETIME, onupdate=now()"
    }

    ORDER_ITEMS {
        int id PK "autoincrement"
        int order_id FK "orders.id, ON DELETE CASCADE, INDEX"
        int menu_item_id FK "menu_items.id"
        int quantity "INTEGER, CHECK(quantity > 0)"
        numeric price_at_order_time "NUMERIC(10,2)"
    }

    AGENT_AUDIT_LOG {
        int id PK "autoincrement"
        string agent_name "VARCHAR(50)"
        string tool_name "VARCHAR(50)"
        json arguments "JSON, NULLABLE"
        enum decision "ENUM('ALLOWED','BLOCKED','PENDING_CONFIRMATION')"
        string reason "VARCHAR(255), NULLABLE"
        json result "JSON, NULLABLE"
        datetime created_at "DATETIME, server_default=now(), INDEX"
    }
```

---

## 4. Layer Responsibilities & Isolation Boundaries

To prevent security vulnerabilities and architectural decay, the codebase enforces strict separation of concerns:

| Layer | Permitted Capabilities | Prohibited Capabilities | Enforcement Mechanism |
| :--- | :--- | :--- | :--- |
| **Routers** (`app/routers/`) | HTTP parameter extraction, status codes, dependency injection (`db: Session`). | Must **not** contain business logic or direct database queries. | Code review & structural encapsulation. |
| **Services** (`app/services/`) | Database transactions, domain operations, calculations. | Must **not** import FastAPI, HTTP exceptions, or request objects. | Automated unit tests verify zero FastAPI imports in `app/services/`. |
| **Pure Rules** (`app/services/order_rules.py`) | Transition validation, business permission checks. | Must **not** access the database, network, or external state. | Tested with table-driven unit tests. |
| **Generation LLM** (`app/llm/`) | Free-text generation, proposal structuring, summarization. | Must **not** access the database, call services, or perform tool execution. | AST static analysis tests (`tests/unit/test_llm_boundary.py`) fail if DB/service imports are added. |
| **Guard Pipeline** (`app/agents/guard/`) | Deterministic validation, rate limiting, kill switches. | Must **not** call LLMs or prompt external models for security opinions. | Structural AST test (`test_guard_module_has_zero_llm_imports`) asserts zero LLM imports. |

---

## 5. Architectural Design Decisions & Rationales

### 5.1 Historical Price Snapshotting (`price_at_order_time`)
- **Decision**: When an order item is added, `menu_items.price` is copied into `order_items.price_at_order_time`.
- **Rationale**: Menu prices fluctuate over time. An order placed at ₹260.00 must not change in retrospect if the restaurant later updates the item price to ₹280.00. Billing and financial auditability require immutability of historical transaction prices.

### 5.2 Services Reused as Agent Tools
- **Decision**: Agent tools in `app/agents/tools/registry.py` wrap the identical service functions used by the standard REST API (`create_order`, `change_status`, `update_bill`, etc.).
- **Rationale**: Eliminates duplicate business logic. Every validation check, constraint, and calculation applied to human waitstaff is inherently enforced when an AI agent performs the action.

### 5.3 Pure Domain State Machine (`order_rules.py`)
- **Decision**: Allowed order transitions and mutation permissions are isolated in a dependency-free module.
- **Rationale**: Allows the deterministic guard to precheck whether an operation is legal before presenting a confirmation card or attempting an execution, without initiating database locks or side effects.

### 5.4 Strict Pydantic Schemas (`extra="forbid"`)
- **Decision**: All request models and agent tool argument schemas set `model_config = ConfigDict(extra="forbid")`.
- **Rationale**: Blocks prompt injection attacks where an attacker tricks an LLM into injecting unrecognized parameters, bypassing filters, or polluting data structures.

### 5.5 Fail-Closed Audit Logging
- **Decision**: Audit records are written via a dedicated database session with immediate flush. If audit logging fails, the entire tool operation is rejected.
- **Rationale**: Ensures complete visibility into all agent attempts. An attacker cannot suppress audit records by intentionally triggering transaction rollbacks.

### 5.6 In-Memory Confirmations and Session Memory (Case Study vs. Production)
- **Current Implementation**: Ephemeral confirmations and session histories are stored in process-local memory (`_pending_confirmations` dictionary with thread locks).
- **Production Architecture**: In a distributed multi-worker deployment (e.g. Kubernetes with multiple Uvicorn workers), this in-memory store would be replaced with **Redis** or a database-backed distributed lock with native TTL support (`SET key val EX 120 NX`).
