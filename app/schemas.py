from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, List, Optional


def _parse_datetime(value: str | None) -> Optional[datetime]:
    if value is None:
        return None
    return datetime.fromisoformat(value)


@dataclass
class TokenPayload:
    access_token: str
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None
    token_type: str = "Bearer"
    scope: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "TokenPayload":
        return cls(
            access_token=str(data["access_token"]),
            refresh_token=data.get("refresh_token"),
            expires_in=data.get("expires_in"),
            token_type=data.get("token_type", "Bearer"),
            scope=data.get("scope"),
        )

    def to_dict(self) -> dict:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_in": self.expires_in,
            "token_type": self.token_type,
            "scope": self.scope,
        }


@dataclass
class OAuthExchangeRequest:
    code: str
    user_id: str
    redirect_uri: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "OAuthExchangeRequest":
        if "code" not in data or "user_id" not in data:
            raise ValueError("Missing required fields for OAuth exchange")
        redirect = data.get("redirect_uri")
        return cls(code=str(data["code"]), user_id=str(data["user_id"]), redirect_uri=redirect)


@dataclass
class OAuthExchangeResponse(TokenPayload):
    obtained_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        payload = super().to_dict()
        payload["obtained_at"] = self.obtained_at.isoformat()
        return payload


@dataclass
class RefreshTokenRequest:
    user_id: str
    refresh_token: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "RefreshTokenRequest":
        if "user_id" not in data:
            raise ValueError("Missing user_id for refresh request")
        refresh_token = data.get("refresh_token")
        return cls(user_id=str(data["user_id"]), refresh_token=refresh_token)


@dataclass
class CreateThreadRequest:
    user_id: str
    text: str
    reply_to_id: Optional[str] = None
    media_urls: Optional[List[str]] = None

    @classmethod
    def from_dict(cls, data: dict) -> "CreateThreadRequest":
        if "user_id" not in data or "text" not in data:
            raise ValueError("Missing required fields for create thread")
        media_urls = data.get("media_urls")
        return cls(
            user_id=str(data["user_id"]),
            text=str(data["text"]),
            reply_to_id=data.get("reply_to_id"),
            media_urls=list(media_urls)
            if isinstance(media_urls, Iterable) and not isinstance(media_urls, (str, bytes))
            else None,
        )


@dataclass
class ThreadResource:
    id: str
    created_at: datetime
    text: str
    author_id: Optional[str] = None
    permalink: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "ThreadResource":
        return cls(
            id=str(data["id"]),
            created_at=_parse_datetime(data.get("created_at")) or datetime.utcnow(),
            text=data.get("text", ""),
            author_id=data.get("author_id"),
            permalink=data.get("permalink"),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat(),
            "text": self.text,
            "author_id": self.author_id,
            "permalink": self.permalink,
        }


@dataclass
class CreateThreadResponse:
    thread: ThreadResource

    def to_dict(self) -> dict:
        return {"thread": self.thread.to_dict()}


@dataclass
class NewThreadsTriggerRequest:
    user_id: str
    since: Optional[datetime] = None
    limit: int = 20

    @classmethod
    def from_dict(cls, data: dict) -> "NewThreadsTriggerRequest":
        if "user_id" not in data:
            raise ValueError("Missing user_id for trigger request")
        since = data.get("since")
        limit = int(data.get("limit", 20))
        if limit < 1 or limit > 100:
            raise ValueError("Limit must be between 1 and 100")
        return cls(user_id=str(data["user_id"]), since=_parse_datetime(since), limit=limit)


@dataclass
class NewThreadsTriggerResponse:
    threads: List[ThreadResource]
    last_polled_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "threads": [thread.to_dict() for thread in self.threads],
            "last_polled_at": self.last_polled_at.isoformat(),
        }
