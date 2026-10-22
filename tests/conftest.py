"""Central pytest fixtures and configuration for isolated test execution.

Ensures:
- Isolated SQLite in-memory database with foreign keys enabled
- No real network calls (socket.connect blocked)
- No real Groq API or MySQL connections
- Controllable clock, StubLLM, and settings overrides
- Clean in-memory stores (sessions, confirmations, rate limits) per test
"""

from collections.abc import Generator
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import json
from pathlib import Path
import socket
import sys
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, TypeVar
import pytest
from pydantic import BaseModel
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

# Ensure backend directory is in sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import app.database as app_db
from app.database import Base, get_db
from app.config import Settings, get_settings
from app.main import app as fastapi_app
import app.models  # registers all models on Base.metadata
from app.models.enums import OrderStatus
from app.models.menu_item import MenuItem
from app.models.order import Order, OrderItem
from app.agents.groq_tools_client import ChatCompletionResult, ToolCallRaw
from app.llm.base import LLMResult

T = TypeVar("T", bound=BaseModel)

# Isolated in-memory SQLite engine
TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(test_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine,
)

# Bind app.database.SessionLocal and engine to test engine
app_db.SessionLocal = TestingSessionLocal
app_db.engine = test_engine


# =========================================================================
# Safety Fixtures: Network & Database Isolation
# =========================================================================

@pytest.fixture(autouse=True)
def block_network_calls(monkeypatch):
    """Enforce complete network isolation by blocking raw socket connect attempts."""
    def _blocked_connect(*args, **kwargs):
        raise RuntimeError("External network call attempted in test environment!")

    monkeypatch.setattr(socket.socket, "connect", _blocked_connect)


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Create all tables in memory once for the test session."""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(autouse=True)
def clean_database():
    """Wipe database rows between tests to prevent test pollution."""
    yield
    with test_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture(autouse=True)
def reset_in_memory_stores():
    """Clear memory, confirmations, and rate limiters before and after each test."""
    from app.agents.memory import memory
    from app.agents.guard.confirmations import confirmations_store as store
    from app.agents.guard.policy import reset_guard_rate_limits
    from app.routers.rate_limiter import reset_rate_limits

    def _reset():
        memory.clear_all()
        store.clear()
        reset_guard_rate_limits()
        reset_rate_limits()

    _reset()
    yield
    _reset()


# =========================================================================
# Database & Client Fixtures
# =========================================================================

@pytest.fixture
def db() -> Generator[Session, None, None]:
    """Provide a database session bound to the isolated SQLite test engine."""
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def db_session(db: Session) -> Session:
    """Alias for backwards compatibility with earlier model tests."""
    return db


@pytest.fixture
def client(db: Session) -> Generator[TestClient, None, None]:
    """TestClient wired to isolated test database."""
    def _override_get_db():
        try:
            yield db
        finally:
            pass

    fastapi_app.dependency_overrides[get_db] = _override_get_db
    with TestClient(fastapi_app) as tc:
        yield tc
    fastapi_app.dependency_overrides.pop(get_db, None)


# =========================================================================
# Seed Data & Factories
# =========================================================================

@pytest.fixture
def seed_menu(db: Session) -> List[MenuItem]:
    """Seed a fixed 6-item menu with exact round decimal prices.
    
    Includes 5 available items and 1 unavailable item (ID 6).
    """
    items = [
        MenuItem(id=1, name="Butter Naan", description="Crisp tandoori bread with butter", price=Decimal("50.00"), available=True),
        MenuItem(id=2, name="Paneer Tikka", description="Spiced grilled paneer cubes", price=Decimal("250.00"), available=True),
        MenuItem(id=3, name="Dal Makhani", description="Slow cooked creamy black lentils", price=Decimal("200.00"), available=True),
        MenuItem(id=4, name="Jeera Rice", description="Basmati rice tempered with cumin", price=Decimal("120.00"), available=True),
        MenuItem(id=5, name="Gulab Jamun", description="Warm milk dumplings in saffron syrup", price=Decimal("80.00"), available=True),
        MenuItem(id=6, name="Seasonal Fish Fry", description="Unavailable seasonal catch", price=Decimal("350.00"), available=False),
    ]
    for item in items:
        db.merge(item)
    db.commit()
    return items


@pytest.fixture
def make_order(db: Session, seed_menu: List[MenuItem]) -> Callable[..., Order]:
    """Factory fixture to create populated, persisted orders with exact totals."""
    def _create(
        customer_name: str = "Test Customer",
        table_no: int = 1,
        items: Optional[List[Tuple[int, int]]] = None,  # (menu_item_id, quantity)
        status: OrderStatus = OrderStatus.PLACED,
        discount_percent: Optional[Decimal] = None,
        service_charge_percent: Optional[Decimal] = None,
    ) -> Order:
        if items is None:
            items = [(1, 2)]  # 2 x 50.00 = 100.00

        order = Order(
            customer_name=customer_name,
            table_no=table_no,
            status=status,
            discount_percent=discount_percent,
            service_charge_percent=service_charge_percent,
            total_bill=Decimal("0.00"),
        )
        db.add(order)
        db.flush()

        subtotal = Decimal("0.00")
        for m_id, qty in items:
            mi = db.query(MenuItem).filter(MenuItem.id == m_id).first()
            price = mi.price if mi else Decimal("50.00")
            oi = OrderItem(
                order_id=order.id,
                menu_item_id=m_id,
                quantity=qty,
                price_at_order_time=price,
            )
            db.add(oi)
            subtotal += price * qty

        bill = subtotal
        if discount_percent:
            disc = (subtotal * discount_percent / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            bill -= disc
        if service_charge_percent:
            svc = (subtotal * service_charge_percent / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            bill += svc

        order.total_bill = bill
        db.commit()
        db.refresh(order)
        return order

    return _create


# =========================================================================
# Controllable Clock & Settings Overrides
# =========================================================================

class ControllableClock:
    """Controllable in-memory clock to advance time without sleeping."""

    def __init__(self, start_time: Optional[datetime] = None):
        self._current = start_time or datetime(2026, 1, 1, 12, 0, 0)

    def utcnow(self) -> datetime:
        return self._current

    def now(self, tz=None) -> datetime:
        return self._current

    def advance(self, seconds: float):
        self._current += timedelta(seconds=seconds)

    def time(self) -> float:
        return self._current.timestamp()


@pytest.fixture
def fake_clock(monkeypatch) -> ControllableClock:
    """Provide a mock clock and wire it into confirmations and policy."""
    clock = ControllableClock()

    class _MockDateTime:
        @classmethod
        def utcnow(cls):
            return clock.utcnow()

        @classmethod
        def now(cls, tz=None):
            return clock.utcnow()

        def __getattr__(self, name):
            return getattr(datetime, name)

    monkeypatch.setattr("app.agents.guard.confirmations.datetime", _MockDateTime)
    return clock


@pytest.fixture
def settings_override():
    """Fixture enabling per-test temporary mutation of Settings."""
    settings = get_settings()
    original_values: Dict[str, Any] = {}

    def _override(**kwargs):
        for k, v in kwargs.items():
            if k not in original_values:
                original_values[k] = getattr(settings, k)
            setattr(settings, k, v)
        from app.llm.client import get_llm_client
        get_llm_client.cache_clear()
        return settings

    yield _override

    for k, v in original_values.items():
        setattr(settings, k, v)
    from app.llm.client import get_llm_client
    get_llm_client.cache_clear()


# =========================================================================
# Scriptable Stub LLM
# =========================================================================

class StubLLM:
    """Scriptable test double for Groq function-calling client and generation client."""

    def __init__(self):
        self.responses: List[Any] = []
        self.recorded_calls: List[Dict[str, Any]] = []
        self.provider_name = "groq"
        self.model = "llama-3.3-70b-versatile"
        self._available = True

    def is_available(self) -> bool:
        return self._available

    def set_available(self, val: bool):
        self._available = val

    def queue_text(self, text: str):
        """Queue a plain text assistant message."""
        self.responses.append(ChatCompletionResult(content=text, tool_calls=[]))

    def queue_tool_call(self, tool_name: str, arguments: Dict[str, Any], call_id: str = "call_stub_1"):
        """Queue a tool call with name and arguments dict."""
        tc = ToolCallRaw(
            id=call_id,
            name=tool_name,
            arguments=json.dumps(arguments) if isinstance(arguments, dict) else str(arguments),
        )
        self.responses.append(ChatCompletionResult(content=None, tool_calls=[tc]))

    def queue_tool_calls(self, tool_calls: List[Tuple[str, Dict[str, Any]]]):
        """Queue multiple simultaneous tool calls in one turn."""
        tcs = [
            ToolCallRaw(
                id=f"call_{idx}",
                name=name,
                arguments=json.dumps(args) if isinstance(args, dict) else str(args),
            )
            for idx, (name, args) in enumerate(tool_calls, start=1)
        ]
        self.responses.append(ChatCompletionResult(content=None, tool_calls=tcs))

    def queue_response(self, response: Any):
        """Queue an arbitrary response object (ChatCompletionResult, string, dict, or LLMResult)."""
        self.responses.append(response)

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> ChatCompletionResult:
        """Emulate Groq tool chat completions."""
        self.recorded_calls.append({
            "type": "chat",
            "messages": list(messages),
            "tools": list(tools) if tools else None,
        })
        if not self.is_available():
            return ChatCompletionResult(error="Groq LLM is not configured or unavailable.")

        if not self.responses:
            return ChatCompletionResult(content="Stub fallback answer.", tool_calls=[])

        resp = self.responses.pop(0)
        if isinstance(resp, ChatCompletionResult):
            return resp
        if isinstance(resp, str):
            return ChatCompletionResult(content=resp, tool_calls=[])
        if isinstance(resp, dict):
            if "tool" in resp:
                return ChatCompletionResult(
                    tool_calls=[
                        ToolCallRaw(
                            id="call_stub",
                            name=resp["tool"],
                            arguments=json.dumps(resp.get("args", {})),
                        )
                    ]
                )
            return ChatCompletionResult(content=json.dumps(resp), tool_calls=[])
        return ChatCompletionResult(content=str(resp), tool_calls=[])

    def generate_text(self, *args, **kwargs) -> LLMResult:
        """Emulate text generation for /ai/ features."""
        task = kwargs.get("task", args[0] if len(args) > 0 else "")
        system = kwargs.get("system", kwargs.get("system_instruction", args[1] if len(args) > 1 else ""))
        user_content = kwargs.get("user_content", kwargs.get("prompt", args[2] if len(args) > 2 else ""))
        fallback = kwargs.get("fallback", "")

        self.recorded_calls.append({
            "type": "generate_text",
            "task": task,
            "system": system,
            "user_content": user_content,
            "fallback": fallback,
        })
        if not self.is_available():
            return LLMResult(text=fallback, source="fallback", error="LLM unavailable")

        if not self.responses:
            return LLMResult(text=fallback or "Default stub text", source="llm", model=self.model, provider=self.provider_name)

        resp = self.responses.pop(0)
        if isinstance(resp, LLMResult):
            return resp
        if isinstance(resp, ChatCompletionResult):
            text_val = resp.content or ""
        elif isinstance(resp, str):
            text_val = resp
        else:
            text_val = json.dumps(resp)
        return LLMResult(text=text_val, source="llm", model=self.model, provider=self.provider_name)

    def generate_json(self, *args, **kwargs) -> Tuple[Any, LLMResult]:
        """Emulate structured JSON generation."""
        task = kwargs.get("task", args[0] if len(args) > 0 else "")
        system = kwargs.get("system", kwargs.get("system_instruction", args[1] if len(args) > 1 else ""))
        user_content = kwargs.get("user_content", kwargs.get("prompt", args[2] if len(args) > 2 else ""))
        schema = kwargs.get("schema", args[3] if len(args) > 3 else None)
        fallback = kwargs.get("fallback", None)

        self.recorded_calls.append({
            "type": "generate_json",
            "task": task,
            "system": system,
            "user_content": user_content,
            "schema": schema,
            "fallback": fallback,
        })
        if not self.is_available():
            return fallback, LLMResult(text="", source="fallback", error="LLM unavailable")

        if not self.responses:
            return fallback, LLMResult(text="", source="fallback", error="No stub response queued")

        resp = self.responses.pop(0)
        raw_text = resp if isinstance(resp, str) else json.dumps(resp)
        try:
            if schema is not None:
                parsed = schema.model_validate_json(raw_text)
            else:
                parsed = json.loads(raw_text)
            return parsed, LLMResult(text=raw_text, source="llm", model=self.model, provider=self.provider_name)
        except Exception as e:
            return fallback, LLMResult(text=raw_text, source="fallback", error=str(e))


@pytest.fixture
def stub_llm(monkeypatch) -> StubLLM:
    """Fixture providing a scriptable StubLLM plugged into all agent and text components."""
    stub = StubLLM()

    # Wire into agent components
    monkeypatch.setattr("app.agents.groq_tools_client.get_groq_tools_client", lambda: stub)
    monkeypatch.setattr("app.agents.orchestrator.get_groq_tools_client", lambda: stub)
    monkeypatch.setattr("app.agents.runner.get_groq_tools_client", lambda: stub)
    monkeypatch.setattr("app.agents.router_agent.get_groq_tools_client", lambda: stub)

    # Wire into text generation /ai components
    monkeypatch.setattr("app.llm.client.get_llm_client", lambda: stub)
    monkeypatch.setattr("app.llm.get_llm_client", lambda: stub)
    monkeypatch.setattr("app.routers.ai.get_llm_client", lambda: stub)
    monkeypatch.setattr("app.services.ai_features.get_llm_client", lambda: stub)

    return stub
