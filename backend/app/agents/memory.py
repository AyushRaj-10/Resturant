"""In-memory session history storage for multi-agent conversations.

NOTE: This session memory is entirely in-process and resets on application restart.
"""

from collections import OrderedDict
import threading
from typing import Dict, List
from app.config import get_settings

# Maximum concurrent user sessions kept in memory before evicting the oldest
MAX_CONCURRENT_SESSIONS = 500


class SessionMemory:
    """Thread-safe, bounded in-memory conversation memory."""

    def __init__(self, max_sessions: int = MAX_CONCURRENT_SESSIONS):
        self._max_sessions = max_sessions
        # OrderedDict preserving access / insertion order for LRU eviction
        self._sessions: OrderedDict[str, List[Dict[str, str]]] = OrderedDict()
        self._lock = threading.Lock()

    def get_history(self, session_id: str) -> List[Dict[str, str]]:
        """Retrieve recent conversation turns for a session as a list of dicts with role and content."""
        with self._lock:
            if session_id in self._sessions:
                # Move to end to indicate recent activity
                self._sessions.move_to_end(session_id)
                # Return a copy to avoid mutation outside lock
                return list(self._sessions[session_id])
            return []

    def add_turn(self, session_id: str, user_message: str, assistant_reply: str) -> None:
        """Append a user-assistant dialogue turn to the session history, respecting turn caps."""
        settings = get_settings()
        max_turns = int(getattr(settings, "AGENT_MAX_HISTORY_TURNS", 6))
        # Each turn consists of 2 messages (user + assistant)
        max_messages = max_turns * 2

        with self._lock:
            if session_id not in self._sessions:
                # Evict oldest session if at capacity
                if len(self._sessions) >= self._max_sessions:
                    self._sessions.popitem(last=False)
                self._sessions[session_id] = []
            else:
                self._sessions.move_to_end(session_id)

            history = self._sessions[session_id]
            history.append({"role": "user", "content": user_message})
            history.append({"role": "assistant", "content": assistant_reply})

            # Trim to max messages
            if len(history) > max_messages:
                self._sessions[session_id] = history[-max_messages:]

    def clear_session(self, session_id: str) -> None:
        """Clear history for a specific session."""
        with self._lock:
            self._sessions.pop(session_id, None)

    def clear_all(self) -> None:
        """Clear all active session histories (useful for tests or diagnostics)."""
        with self._lock:
            self._sessions.clear()


# Global singleton instance
memory = SessionMemory()
