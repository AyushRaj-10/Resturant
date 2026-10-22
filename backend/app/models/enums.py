import enum


class OrderStatus(str, enum.Enum):
    """Lifecycle status of a customer order."""

    PLACED = "PLACED"
    PREPARING = "PREPARING"
    SERVED = "SERVED"
    PAID = "PAID"
    CANCELLED = "CANCELLED"


class AuditDecision(str, enum.Enum):
    """Decision outcome evaluated for an agent tool execution."""

    ALLOWED = "ALLOWED"
    BLOCKED = "BLOCKED"
    PENDING_CONFIRMATION = "PENDING_CONFIRMATION"
