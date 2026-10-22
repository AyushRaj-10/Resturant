"""In-memory store for destructive actions awaiting human confirmation.

NOTE: This store is strictly in-process and resets upon server restart.
"""

from datetime import datetime, timedelta
import logging
import secrets
import threading
from typing import Any, Dict, List, Optional
from app.agents.guard.models import ActionStatus, PendingAction
from app.config import get_settings

logger = logging.getLogger(__name__)


class ConfirmationStore:
    """Thread-safe in-memory registry of pending destructive actions."""

    def __init__(self):
        self._actions: Dict[str, PendingAction] = {}
        self._lock = threading.Lock()

    def create_pending_action(
        self,
        session_id: str,
        agent_name: str,
        tool_name: str,
        arguments: Dict[str, Any],
        summary: str,
        snapshot: Dict[str, Any],
        ttl_seconds: Optional[int] = None,
    ) -> PendingAction:
        """Create and register a new random unguessable confirmation token."""
        settings = get_settings()
        ttl = ttl_seconds if ttl_seconds is not None else int(getattr(settings, "AGENT_CONFIRM_TTL_SECONDS", 120))
        token = secrets.token_urlsafe(16)
        now = datetime.utcnow()
        expires_at = now + timedelta(seconds=ttl)

        action = PendingAction(
            confirmation_id=token,
            session_id=session_id,
            agent_name=agent_name,
            tool_name=tool_name,
            arguments=arguments,
            summary=summary,
            snapshot=snapshot,
            created_at=now,
            expires_at=expires_at,
            status="pending",
        )

        with self._lock:
            # Housekeeping: prune old consumed or expired records
            self._prune_expired()
            self._actions[token] = action

        return action

    def get_action(self, confirmation_id: str) -> Optional[PendingAction]:
        """Look up pending action, automatically updating status if expired."""
        with self._lock:
            action = self._actions.get(confirmation_id)
            if action is None:
                return None

            now = datetime.utcnow()
            if action.status == "pending" and now > action.expires_at:
                action.status = "expired"

            return action

    def update_status(self, confirmation_id: str, status: ActionStatus) -> None:
        """Update lifecycle state of an action (e.g. approved, rejected, consumed)."""
        with self._lock:
            action = self._actions.get(confirmation_id)
            if action:
                action.status = status

    def list_pending(self, session_id: str) -> List[PendingAction]:
        """List active, non-expired pending actions for a session."""
        now = datetime.utcnow()
        with self._lock:
            results = []
            for action in self._actions.values():
                if action.session_id == session_id:
                    if action.status == "pending" and now > action.expires_at:
                        action.status = "expired"
                    if action.status == "pending":
                        results.append(action)
            return results

    def _prune_expired(self) -> None:
        """Remove actions expired more than 1 hour ago."""
        now = datetime.utcnow()
        cutoff = now - timedelta(hours=1)
        to_delete = [
            cid for cid, act in self._actions.items()
            if act.expires_at < cutoff or act.status in {"consumed", "rejected"}
        ]
        for cid in to_delete:
            del self._actions[cid]

    def clear(self) -> None:
        """Clear all pending confirmations (test/diagnostic helper)."""
        with self._lock:
            self._actions.clear()


# Global singleton instance
confirmations_store = ConfirmationStore()
