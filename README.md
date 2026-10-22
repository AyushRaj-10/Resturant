# Restaurant Order Management System (Restaurant OMS)

A modern Restaurant Order Management System built with FastAPI, MySQL, and a lightweight HTML/CSS/JS frontend. Designed with a layered architecture to support future Generative AI and multi-agent workflows.

---

## Project Structure

```
restaurant-oms/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI app, CORS, health endpoints
│   │   ├── config.py            # Pydantic BaseSettings configuration
│   │   ├── database.py          # SQLAlchemy engine, session maker, get_db
│   │   ├── models/
│   │   │   ├── __init__.py      # Exports all models and domain enums
│   │   │   ├── enums.py         # OrderStatus & AuditDecision enums
│   │   │   ├── menu_item.py     # MenuItem model
│   │   │   ├── order.py         # Order and OrderItem models
│   │   │   └── audit.py         # AgentAuditLog model
│   │   ├── schemas/__init__.py  # Pydantic schemas (reserved for future steps)
│   │   ├── routers/__init__.py  # API route definitions
│   │   ├── services/__init__.py # Core business logic layer
│   │   ├── agents/__init__.py   # Multi-agent workflows & guarded tools
│   │   └── llm/__init__.py      # LLM integrations
│   ├── scripts/
│   │   ├── init_db.py           # Table creation and --reset script
│   │   └── seed_menu.py         # Idempotent menu seed script
│   └── requirements.txt         # Pinned backend dependencies
├── frontend/
│   ├── index.html               # Frontend dashboard
│   ├── css/style.css            # Stylesheet
│   └── js/app.js                # Health check client logic
├── tests/
│   ├── conftest.py              # Test database engine and session fixtures
│   ├── test_health.py           # Pytest test suite for health endpoints
│   └── test_models.py           # Pytest test suite for models and constraints
├── .env.example                 # Example environment variables
├── .gitignore                   # Ignored files (venv, cache, .env)
├── pytest.ini                   # Pytest path and runner configuration
└── README.md                    # Setup and execution guide
```

---

## Setup Instructions

### 1. Prerequisites
- Python 3.11+
- MySQL 8.0+

### 2. Create and Activate Virtual Environment

From the project root:

```bash
# Create virtual environment
python3 -m venv venv

# Activate on macOS / Linux:
source venv/bin/activate

# (On Windows):
# .\venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install --upgrade pip
pip install -r backend/requirements.txt
```

### 4. Configure Environment Variables

Copy `.env.example` to `.env` in the project root:

```bash
cp .env.example .env
```

Edit `.env` to match your local MySQL credentials:

```env
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_mysql_password
DB_NAME=restaurant_oms
APP_ENV=development
LLM_API_KEY=
LLM_MODEL=gpt-4o
```

### 5. Create the MySQL Database

Log in to your MySQL server and create the database:

```sql
CREATE DATABASE IF NOT EXISTS restaurant_oms CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

---

## Database Management

### 1. Initialize Database Tables
Create all database tables (`menu_items`, `orders`, `order_items`, `agent_audit_log`):

```bash
python backend/scripts/init_db.py
```
*(This script is safe to run repeatedly; it will only create tables that do not already exist).*

### 2. Reset Database Tables (`--reset`)
To drop all existing tables and re-create fresh empty tables:

```bash
python backend/scripts/init_db.py --reset
```
> [!IMPORTANT]
> The `--reset` command requires typing `yes` to confirm. It will automatically refuse to run if `APP_ENV=production`.

### 3. Seed Menu Data
Populate `menu_items` with realistic Indian restaurant offerings (starters, mains, breads, desserts, beverages) priced in INR:

```bash
python backend/scripts/seed_menu.py
```
*(This script is idempotent: it checks if `menu_items` has records and skips seeding if already populated).*

---

## Running the Application

### Start the Backend Server

Navigate into the `backend/` directory and run Uvicorn:

```bash
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The API will be accessible at:
- Base / Swagger Docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- API Health: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)
- Database Health: [http://127.0.0.1:8000/health/db](http://127.0.0.1:8000/health/db)

### Open the Frontend

Open `frontend/index.html` in your browser, or serve it using a local static server:

```bash
# From project root:
open frontend/index.html

# Or with python http server:
python3 -m http.server 3000 --directory frontend
```

---

## Running Tests

From the project root with the virtual environment activated:

```bash
pytest
```
