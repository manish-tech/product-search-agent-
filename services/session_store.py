from datetime import datetime, timedelta
from typing import Dict, Optional
import os

from models.schemas import Session


class SessionStore:
    """In-memory session store with TTL support."""

    def __init__(self, ttl_minutes: int = 30):
        self._sessions: Dict[str, Session] = {}
        self.ttl_minutes = ttl_minutes

    def get(self, session_id: str) -> Optional[Session]:
        """
        Get session by ID, returns None if not found or expired.
        """
        session = self._sessions.get(session_id)
        if session is None:
            return None

        # Check if session has expired
        if self._is_expired(session):
            self.delete(session_id)
            return None

        return session

    def get_or_create(self, session_id: str, tenant_id: str) -> Session:
        """
        Get existing session or create a new one.
        """
        session = self.get(session_id)
        if session is not None:
            # Update last_active timestamp
            session.last_active = datetime.utcnow()
            return session

        # Create new session
        session = Session(
            session_id=session_id,
            tenant_id=tenant_id,
            filters={},
            last_result_ids=[],
            created_at=datetime.utcnow(),
            last_active=datetime.utcnow()
        )
        self._sessions[session_id] = session
        return session

    def save(self, session: Session) -> None:
        """
        Save/update a session.
        """
        session.last_active = datetime.utcnow()
        self._sessions[session.session_id] = session

    def delete(self, session_id: str) -> None:
        """
        Delete a session by ID.
        """
        self._sessions.pop(session_id, None)

    def _is_expired(self, session: Session) -> bool:
        """
        Check if a session has expired based on TTL.
        """
        expiry_time = session.last_active + timedelta(minutes=self.ttl_minutes)
        return datetime.utcnow() > expiry_time

    def cleanup_expired(self) -> int:
        """
        Remove all expired sessions. Returns count of removed sessions.
        """
        expired_ids = [
            sid for sid, session in self._sessions.items()
            if self._is_expired(session)
        ]
        for sid in expired_ids:
            self.delete(sid)
        return len(expired_ids)

    def count(self) -> int:
        """Return the number of active sessions."""
        return len(self._sessions)


# Singleton instance
_session_store: Optional[SessionStore] = None


def get_session_store() -> SessionStore:
    """Get or create the singleton session store instance."""
    global _session_store
    if _session_store is None:
        ttl = int(os.getenv("SESSION_TTL_MINUTES", "30"))
        _session_store = SessionStore(ttl_minutes=ttl)
    return _session_store
