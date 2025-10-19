from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import Lock
from typing import Dict, Optional

from .schemas import TokenPayload


@dataclass
class StoredToken:
    user_id: str
    token: TokenPayload
    obtained_at: datetime

    @property
    def expires_at(self) -> Optional[datetime]:
        if self.token.expires_in is None:
            return None
        return self.obtained_at + timedelta(seconds=self.token.expires_in)


class TokenStore:
    def save(self, user_id: str, payload: TokenPayload) -> StoredToken:
        raise NotImplementedError

    def get(self, user_id: str) -> Optional[StoredToken]:
        raise NotImplementedError

    def delete(self, user_id: str) -> None:
        raise NotImplementedError


class InMemoryTokenStore(TokenStore):
    def __init__(self) -> None:
        self._tokens: Dict[str, StoredToken] = {}
        self._lock = Lock()

    def save(self, user_id: str, payload: TokenPayload) -> StoredToken:
        with self._lock:
            stored = StoredToken(user_id=user_id, token=payload, obtained_at=datetime.utcnow())
            self._tokens[user_id] = stored
            return stored

    def get(self, user_id: str) -> Optional[StoredToken]:
        with self._lock:
            return self._tokens.get(user_id)

    def delete(self, user_id: str) -> None:
        with self._lock:
            self._tokens.pop(user_id, None)
