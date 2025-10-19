from __future__ import annotations

import pathlib
import sys
from datetime import datetime, timedelta
from urllib.parse import urlencode

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.config import Settings
from app.schemas import (
    CreateThreadRequest,
    NewThreadsTriggerRequest,
    OAuthExchangeRequest,
    RefreshTokenRequest,
    ThreadResource,
    TokenPayload,
)
from app.main import _normalize_path, parse_request_payload
from app.service import ServiceError, ThreadsZapierService
from app.storage import InMemoryTokenStore


class DummyThreadsClient:
    def build_authorize_url(
        self,
        *,
        state: str | None,
        redirect_uri: str | None = None,
        scope: str | None = None,
    ) -> str:
        if state is not None:
            assert state == "state-123"
        redirect = redirect_uri or "https://example.com/oauth/callback"
        scope_value = scope or "threads.basic"
        params = {
            "redirect_uri": redirect,
            "scope": scope_value,
        }
        if state is not None:
            params["state"] = state
        query = urlencode(params)
        return f"https://auth.threads.test/oauth?{query}"

    def exchange_code_for_token(self, code: str, redirect_uri: str | None):
        return TokenPayload(access_token="access", refresh_token="refresh", expires_in=3600, scope="threads.write")

    def refresh_access_token(self, refresh_token: str):
        if refresh_token != "refresh":
            raise AssertionError("unexpected refresh token")
        return TokenPayload(access_token="new-access", refresh_token="refresh", expires_in=3600)

    def create_thread(
        self,
        access_token: str,
        text: str,
        reply_to_id: str | None = None,
        media_urls: list[str] | None = None,
    ) -> ThreadResource:
        if not access_token:
            raise AssertionError("missing access token")
        return ThreadResource(
            id="123",
            created_at=datetime.utcnow(),
            text=text,
            author_id="user-1",
            permalink="https://threads.net/t/123",
        )

    def get_recent_threads(
        self,
        access_token: str,
        user_id: str,
        *,
        since: datetime | None = None,
        limit: int = 20,
    ) -> list[ThreadResource]:
        base_time = datetime.utcnow()
        return [
            ThreadResource(
                id="abc",
                created_at=base_time - timedelta(minutes=1),
                text="Hello",
                author_id=user_id,
                permalink="https://threads.net/t/abc",
            )
        ][:limit]


@pytest.fixture
def service() -> ThreadsZapierService:
    settings = Settings(
        threads_redirect_uri="https://example.com/oauth/callback",
        threads_scope="threads.basic",
    )
    store = InMemoryTokenStore()
    store.save("user-1", TokenPayload(access_token="access-token", refresh_token="refresh", expires_in=3600))
    client = DummyThreadsClient()
    return ThreadsZapierService(settings, client, store)


def test_create_thread(service: ThreadsZapierService):
    request = CreateThreadRequest(user_id="user-1", text="Zapier post")
    response = service.create_thread(request)
    assert response.thread.text == "Zapier post"


def test_fetch_threads(service: ThreadsZapierService):
    request = NewThreadsTriggerRequest(user_id="user-1", limit=5)
    response = service.fetch_threads(request)
    assert len(response.threads) == 1
    assert response.threads[0].text == "Hello"


def test_exchange_and_refresh(service: ThreadsZapierService):
    exchange_request = OAuthExchangeRequest(code="demo-code", user_id="user-2")
    exchange_response = service.exchange_token(exchange_request)
    assert exchange_response.access_token == "access"

    refresh_request = RefreshTokenRequest(user_id="user-1")
    refresh_response = service.refresh_token(refresh_request)
    assert refresh_response.access_token == "new-access"


def test_oauth_exchange_request_accepts_state():
    request = OAuthExchangeRequest.from_dict({"code": "abc", "state": "user-5"})
    assert request.user_id == "user-5"


def test_oauth_exchange_request_requires_identifier():
    with pytest.raises(ValueError):
        OAuthExchangeRequest.from_dict({"code": "abc"})


def test_refresh_request_accepts_state_alias():
    request = RefreshTokenRequest.from_dict({"state": "user-6", "refresh_token": "tok"})
    assert request.user_id == "user-6"


def test_refresh_request_requires_identifier():
    with pytest.raises(ValueError):
        RefreshTokenRequest.from_dict({"refresh_token": "tok"})


def test_build_authorize_url(service: ThreadsZapierService):
    url = service.build_authorize_url(
        state="state-123",
        redirect_uri="https://zapier.com/dashboard/auth/oauth/App123/oauth/callback",
    )
    assert url.startswith("https://auth.threads.test/oauth")
    assert "state=state-123" in url
    assert "redirect_uri=https%3A%2F%2Fzapier.com%2Fdashboard%2Fauth%2Foauth%2FApp123%2Foauth%2Fcallback" in url
    assert "scope=threads.basic" in url


def test_build_authorize_url_without_state(service: ThreadsZapierService):
    url = service.build_authorize_url(state=None)
    assert "state=" not in url


def test_missing_user_token_raises(service: ThreadsZapierService):
    request = CreateThreadRequest(user_id="missing", text="Zap")
    with pytest.raises(ServiceError) as exc:
        service.create_thread(request)
    assert exc.value.status_code == 404


def test_refresh_token_with_explicit_value(service: ThreadsZapierService):
    request = RefreshTokenRequest(user_id="user-3", refresh_token="refresh")
    response = service.refresh_token(request)
    assert response.access_token == "new-access"


def test_normalize_path_handles_trailing_slash():
    assert _normalize_path("/oauth/token/") == "/oauth/token"
    assert _normalize_path("/oauth/token") == "/oauth/token"


def test_normalize_path_handles_empty_values():
    assert _normalize_path("") == "/"
    assert _normalize_path("/") == "/"


def test_parse_request_payload_supports_form_data():
    body = b"code=abc&user_id=user-1"
    payload = parse_request_payload("application/x-www-form-urlencoded", body, allow_form=True)
    assert payload == {"code": "abc", "user_id": "user-1"}


def test_parse_request_payload_rejects_form_without_flag():
    body = b"code=abc&user_id=user-1"
    with pytest.raises(ServiceError):
        parse_request_payload("application/x-www-form-urlencoded", body, allow_form=False)


def test_parse_request_payload_handles_empty_body():
    payload = parse_request_payload("application/json", b"", allow_form=True)
    assert payload == {}


def test_parse_request_payload_invalid_json():
    with pytest.raises(ServiceError):
        parse_request_payload("application/json", b"not-json", allow_form=False)


def test_parse_request_payload_handles_form_without_content_type():
    body = b"code=abc&user_id=user-1"
    payload = parse_request_payload(None, body, allow_form=True)
    assert payload == {"code": "abc", "user_id": "user-1"}
