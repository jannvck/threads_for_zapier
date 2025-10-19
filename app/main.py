from __future__ import annotations

import json
import logging
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Type
from urllib.parse import urlparse

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

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length", "0"))
            data = self.rfile.read(length) if length > 0 else b"{}"
            try:
                return json.loads(data.decode("utf-8"))
            except json.JSONDecodeError as exc:
                raise ServiceError("Invalid JSON payload", status_code=400) from exc

        def _validate_zapier(self) -> None:
            token = settings.zapier_verification_token
            if not token:
                return
            header_token = self.headers.get("X-Zapier-Signature") or self.headers.get("X-Zapier-Token")
            if header_token != token:
                raise ServiceError("Invalid Zapier verification token", status_code=401)

        def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler naming)
            parsed = urlparse(self.path)
            if parsed.path == "/healthz":
                self._json_response(HTTPStatus.OK, {"status": "ok"})
                return
            self._json_response(HTTPStatus.NOT_FOUND, {"detail": "Not found"})

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/oauth/exchange":
                    payload = OAuthExchangeRequest.from_dict(self._read_json())
                    response = service.exchange_token(payload)
                    self._json_response(HTTPStatus.OK, response.to_dict())
                elif parsed.path == "/oauth/refresh":
                    payload = RefreshTokenRequest.from_dict(self._read_json())
                    response = service.refresh_token(payload)
                    self._json_response(HTTPStatus.OK, response.to_dict())
                elif parsed.path == "/zapier/actions/create-thread":
                    self._validate_zapier()
                    payload = CreateThreadRequest.from_dict(self._read_json())
                    response = service.create_thread(payload)
                    self._json_response(HTTPStatus.OK, response.to_dict())
                elif parsed.path == "/zapier/triggers/new-thread":
                    self._validate_zapier()
                    payload = NewThreadsTriggerRequest.from_dict(self._read_json())
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
