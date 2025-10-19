from __future__ import annotations

import json
import logging
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Type
from urllib.parse import parse_qs, urlparse

from .config import Settings, get_settings
from .schemas import (
    CreateThreadRequest,
    NewThreadsTriggerRequest,
    OAuthExchangeRequest,
    RefreshTokenRequest,
)
from .service import ServiceError, ThreadsZapierService
from .storage import InMemoryTokenStore
from .threads_client import ThreadsClient

logger = logging.getLogger(__name__)


def create_service(settings: Settings | None = None) -> ThreadsZapierService:
    settings = settings or get_settings()
    client = ThreadsClient(settings)
    store = InMemoryTokenStore()
    return ThreadsZapierService(settings, client, store)


def _normalize_path(raw_path: str) -> str:
    """Normalize incoming request paths for consistent routing."""

    if not raw_path:
        return "/"
    normalized = raw_path.rstrip("/")
    return normalized or "/"


def parse_request_payload(
    content_type: str | None,
    body: bytes,
    *,
    allow_form: bool = False,
) -> dict[str, str]:
    """Parse request payloads supporting JSON and optional form data."""

    media_type = (content_type or "").split(";", 1)[0].strip().lower()
    if allow_form and media_type == "application/x-www-form-urlencoded":
        form = parse_qs(body.decode("utf-8"), keep_blank_values=True)
        return {key: values[-1] for key, values in form.items() if values}

    text = body.decode("utf-8") if body else ""
    if not text:
        return {}

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ServiceError("Invalid JSON payload", status_code=400) from exc


def create_handler_factory(service: ThreadsZapierService, settings: Settings) -> Type[BaseHTTPRequestHandler]:
    class ThreadsHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _json_response(self, status: HTTPStatus, payload: dict) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status.value)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_body(self) -> bytes:
            length = int(self.headers.get("Content-Length", "0"))
            return self.rfile.read(length) if length > 0 else b""

        def _read_payload(self, *, allow_form: bool = False) -> dict:
            body = self._read_body()
            content_type = self.headers.get("Content-Type")
            return parse_request_payload(content_type, body, allow_form=allow_form)

        def _validate_zapier(self) -> None:
            token = settings.zapier_verification_token
            if not token:
                return
            header_token = self.headers.get("X-Zapier-Signature") or self.headers.get("X-Zapier-Token")
            if header_token != token:
                raise ServiceError("Invalid Zapier verification token", status_code=401)

        def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler naming)
            parsed = urlparse(self.path)
            path = _normalize_path(parsed.path)

            if path == "/healthz":
                self._json_response(HTTPStatus.OK, {"status": "ok"})
                return
            if path == "/oauth/authorize":
                params = parse_qs(parsed.query)
                state = params.get("state", [None])[0]
                redirect_uri = params.get("redirect_uri", [None])[0]
                scope = params.get("scope", [None])[0]
                location = service.build_authorize_url(
                    state=state, redirect_uri=redirect_uri, scope=scope
                )
                self.send_response(HTTPStatus.FOUND.value)
                self.send_header("Location", location)
                self.end_headers()
                return
            if path in {"/zapier/auth/test", "/zapier/actions/create-thread", "/zapier/triggers/new-thread"}:
                self._json_response(
                    HTTPStatus.METHOD_NOT_ALLOWED,
                    {"detail": "Use POST with a JSON payload for Zapier endpoints"},
                )
                return
            self._json_response(HTTPStatus.NOT_FOUND, {"detail": "Not found"})

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = _normalize_path(parsed.path)
            try:
                if path == "/oauth/exchange":
                    payload = OAuthExchangeRequest.from_dict(
                        self._read_payload(allow_form=True)
                    )
                    response = service.exchange_token(payload)
                    self._json_response(HTTPStatus.OK, response.to_dict())
                elif path == "/oauth/refresh":
                    payload = RefreshTokenRequest.from_dict(
                        self._read_payload(allow_form=True)
                    )
                    response = service.refresh_token(payload)
                    self._json_response(HTTPStatus.OK, response.to_dict())
                elif path == "/oauth/token":
                    form = self._read_payload(allow_form=True)
                    grant_type = form.get("grant_type")
                    if grant_type == "authorization_code":
                        code = form.get("code")
                        state = form.get("state") or form.get("user_id")
                        if not code:
                            self._json_response(
                                HTTPStatus.BAD_REQUEST,
                                {"detail": "Missing authorization code"},
                            )
                            return
                        if not state:
                            self._json_response(
                                HTTPStatus.BAD_REQUEST,
                                {"detail": "Missing state parameter for user identification"},
                            )
                            return
                        redirect_uri = form.get("redirect_uri")
                        payload = OAuthExchangeRequest(
                            code=code,
                            user_id=state,
                            redirect_uri=redirect_uri,
                        )
                        response = service.exchange_token(payload)
                        self._json_response(HTTPStatus.OK, response.to_dict())
                    elif grant_type == "refresh_token":
                        refresh_token = form.get("refresh_token")
                        state = form.get("state") or form.get("user_id")
                        if not refresh_token:
                            self._json_response(
                                HTTPStatus.BAD_REQUEST,
                                {"detail": "Missing refresh token"},
                            )
                            return
                        if not state:
                            self._json_response(
                                HTTPStatus.BAD_REQUEST,
                                {"detail": "Missing state parameter for user identification"},
                            )
                            return
                        payload = RefreshTokenRequest(user_id=state, refresh_token=refresh_token)
                        response = service.refresh_token(payload)
                        self._json_response(HTTPStatus.OK, response.to_dict())
                    else:
                        self._json_response(
                            HTTPStatus.BAD_REQUEST,
                            {"detail": "Unsupported grant_type"},
                        )
                elif path == "/zapier/actions/create-thread":
                    self._validate_zapier()
                    payload = CreateThreadRequest.from_dict(self._read_payload())
                    response = service.create_thread(payload)
                    self._json_response(HTTPStatus.OK, response.to_dict())
                elif path == "/zapier/triggers/new-thread":
                    self._validate_zapier()
                    payload = NewThreadsTriggerRequest.from_dict(self._read_payload())
                    response = service.fetch_threads(payload)
                    self._json_response(HTTPStatus.OK, response.to_dict())
                else:
                    self._json_response(HTTPStatus.NOT_FOUND, {"detail": "Not found"})
            except ServiceError as exc:
                logger.debug("Service error: %s", exc)
                self._json_response(HTTPStatus(exc.status_code), {"detail": str(exc)})
            except Exception as exc:  # pragma: no cover - unexpected
                logger.exception("Unhandled error")
                self._json_response(HTTPStatus.INTERNAL_SERVER_ERROR, {"detail": "Internal Server Error"})

        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            logger.info("%s - %s", self.address_string(), format % args)

    return ThreadsHandler


def run() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    service = create_service(settings)
    handler = create_handler_factory(service, settings)
    port = int(os.getenv("PORT", "8080"))
    server = ThreadingHTTPServer(("", port), handler)
    logger.info("Starting Threads Zapier service on port %s", port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover - manual stop
        logger.info("Shutting down Threads Zapier service")
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
