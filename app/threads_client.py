from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional
from urllib import parse, request
from urllib.error import HTTPError

from .config import Settings
from .schemas import ThreadResource, TokenPayload


class ThreadsAPIError(RuntimeError):
    def __init__(self, message: str, status_code: int, payload: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}


class ThreadsClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def exchange_code_for_token(self, code: str, redirect_uri: Optional[str]) -> TokenPayload:
        payload = {
            "client_id": self._settings.threads_client_id,
            "client_secret": self._settings.threads_client_secret,
            "redirect_uri": redirect_uri or self._settings.threads_redirect_uri,
            "grant_type": "authorization_code",
            "code": code,
        }
        data = self._post("/oauth/token", data=payload, as_json=False)
        return TokenPayload.from_dict(data)

    def refresh_access_token(self, refresh_token: str) -> TokenPayload:
        payload = {
            "client_id": self._settings.threads_client_id,
            "client_secret": self._settings.threads_client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        data = self._post("/oauth/token", data=payload, as_json=False)
        return TokenPayload.from_dict(data)

    def create_thread(
        self,
        access_token: str,
        text: str,
        reply_to_id: Optional[str] = None,
        media_urls: Optional[Iterable[str]] = None,
    ) -> ThreadResource:
        payload: Dict[str, Any] = {"text": text}
        if reply_to_id:
            payload["reply_to_id"] = reply_to_id
        if media_urls:
            payload["media_urls"] = list(media_urls)

        data = self._post("/v1.0/threads", json_body=payload, access_token=access_token)
        resource = {
            "id": data.get("id", ""),
            "created_at": data.get("created_at", datetime.utcnow().isoformat()),
            "text": data.get("text", text),
            "author_id": data.get("author_id"),
            "permalink": data.get("permalink"),
        }
        return ThreadResource.from_dict(resource)

    def get_recent_threads(
        self,
        access_token: str,
        user_id: str,
        *,
        since: Optional[datetime] = None,
        limit: int = 20,
    ) -> List[ThreadResource]:
        params: Dict[str, Any] = {"limit": limit}
        if since is not None:
            params["since"] = since.isoformat()
        data = self._get(f"/v1.0/users/{user_id}/threads", params=params, access_token=access_token)
        items = data.get("data", [])
        return [ThreadResource.from_dict(item) for item in items]

    def _post(
        self,
        path: str,
        *,
        data: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        access_token: Optional[str] = None,
        as_json: bool = True,
    ) -> Dict[str, Any]:
        headers = {"Accept": "application/json"}
        if json_body is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(json_body).encode("utf-8")
        elif data is not None:
            if as_json:
                headers["Content-Type"] = "application/json"
                body = json.dumps(data).encode("utf-8")
            else:
                headers["Content-Type"] = "application/x-www-form-urlencoded"
                body = parse.urlencode(data).encode("utf-8")
        else:
            body = None
        return self._request("POST", path, body=body, headers=headers, access_token=access_token)

    def _get(
        self,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        access_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        query = f"?{parse.urlencode(params)}" if params else ""
        headers = {"Accept": "application/json"}
        return self._request("GET", f"{path}{query}", headers=headers, access_token=access_token)

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: Optional[bytes] = None,
        headers: Optional[Dict[str, str]] = None,
        access_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        url = f"{self._settings.threads_api_base_url.rstrip('/')}{path}"
        headers = headers or {}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"

        req = request.Request(url, data=body, headers=headers, method=method)
        try:
            with request.urlopen(req, timeout=self._settings.request_timeout_seconds) as resp:
                content = resp.read().decode("utf-8") or "{}"
                return json.loads(content)
        except HTTPError as exc:  # pragma: no cover - network error handling
            raw = exc.read().decode("utf-8")
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {"raw": raw}
            raise ThreadsAPIError(
                message=f"Threads API request failed with status {exc.code}",
                status_code=exc.code,
                payload=payload,
            ) from exc
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise ThreadsAPIError("Threads API did not return JSON payload", 500) from exc
