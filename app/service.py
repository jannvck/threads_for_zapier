from __future__ import annotations

from datetime import datetime

from .config import Settings
from .schemas import (
    CreateThreadRequest,
    CreateThreadResponse,
    NewThreadsTriggerRequest,
    NewThreadsTriggerResponse,
    OAuthExchangeRequest,
    OAuthExchangeResponse,
    RefreshTokenRequest,
)
from .storage import StoredToken, TokenStore
from .threads_client import ThreadsAPIError, ThreadsClient


class ServiceError(RuntimeError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class ThreadsZapierService:
    def __init__(self, settings: Settings, client: ThreadsClient, store: TokenStore) -> None:
        self._settings = settings
        self._client = client
        self._store = store

    def exchange_token(self, request: OAuthExchangeRequest) -> OAuthExchangeResponse:
        token = self._client.exchange_code_for_token(request.code, request.redirect_uri)
        stored = self._store.save(request.user_id, token)
        return OAuthExchangeResponse(
            access_token=token.access_token,
            refresh_token=token.refresh_token,
            expires_in=token.expires_in,
            token_type=token.token_type,
            scope=token.scope,
            obtained_at=stored.obtained_at,
        )

    def refresh_token(self, request: RefreshTokenRequest) -> OAuthExchangeResponse:
        stored = self._require_token(request.user_id)
        if not stored.token.refresh_token:
            raise ServiceError("Refresh token not available", status_code=400)
        token = self._client.refresh_access_token(stored.token.refresh_token)
        stored = self._store.save(request.user_id, token)
        return OAuthExchangeResponse(
            access_token=token.access_token,
            refresh_token=token.refresh_token,
            expires_in=token.expires_in,
            token_type=token.token_type,
            scope=token.scope,
            obtained_at=stored.obtained_at,
        )

    def build_authorize_url(
        self,
        *,
        state: str,
        redirect_uri: str | None = None,
        scope: str | None = None,
    ) -> str:
        return self._client.build_authorize_url(
            state=state, redirect_uri=redirect_uri, scope=scope
        )

    def create_thread(self, request: CreateThreadRequest) -> CreateThreadResponse:
        stored = self._require_token(request.user_id)
        try:
            resource = self._client.create_thread(
                access_token=stored.token.access_token,
                text=request.text,
                reply_to_id=request.reply_to_id,
                media_urls=request.media_urls,
            )
        except ThreadsAPIError as exc:
            raise ServiceError(str(exc.payload or exc), status_code=exc.status_code) from exc
        return CreateThreadResponse(thread=resource)

    def fetch_threads(self, request: NewThreadsTriggerRequest) -> NewThreadsTriggerResponse:
        stored = self._require_token(request.user_id)
        try:
            threads = self._client.get_recent_threads(
                access_token=stored.token.access_token,
                user_id=request.user_id,
                since=request.since,
                limit=request.limit,
            )
        except ThreadsAPIError as exc:
            raise ServiceError(str(exc.payload or exc), status_code=exc.status_code) from exc
        return NewThreadsTriggerResponse(threads=list(threads), last_polled_at=datetime.utcnow())

    def _require_token(self, user_id: str) -> StoredToken:
        stored = self._store.get(user_id)
        if stored is None:
            raise ServiceError("No token registered for user", status_code=404)
        return stored
