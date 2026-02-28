from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import requests
from requests.auth import HTTPDigestAuth


class HikGatewayClient:
    def __init__(self, base_url: str, username: str, password: str, timeout: int = 20):
        self.base_url = base_url.rstrip("/") + "/"
        self.auth = HTTPDigestAuth(username, password)
        self.timeout = timeout

    def _post(
        self,
        path: str,
        payload: dict[str, Any],
        params: dict[str, Any] | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        url = urljoin(self.base_url, path.lstrip("/"))
        response = requests.post(
            url,
            json=payload,
            params=params or {},
            auth=self.auth,
            timeout=timeout or self.timeout,
        )
        response.raise_for_status()
        return response.json() if response.content else {}

    def _put(self, path: str, payload: dict[str, Any], params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = urljoin(self.base_url, path.lstrip("/"))
        response = requests.put(url, json=payload, params=params or {}, auth=self.auth, timeout=self.timeout)
        response.raise_for_status()
        return response.json() if response.content else {}

    def device_list(self, payload: dict[str, Any] | None = None, timeout: int | None = None) -> dict[str, Any]:
        request_payload = payload or {
            "SearchDescription": {
                "position": 0,
                "maxResult": 100,
                "Filter": {
                    "key": "",
                    "devType": "",
                    "protocolType": ["ehomeV5"],
                    "devStatus": ["online", "offline"],
                },
            }
        }

        return self._post(
            "/ISAPI/ContentMgmt/DeviceMgmt/deviceList",
            payload=request_payload,
            params={"format": "json"},
            timeout=timeout,
        )

    def set_http_host(self, dev_index: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._put(
            "/ISAPI/Event/notification/httpHosts",
            payload=payload,
            params={"format": "json", "devIndex": dev_index},
        )

    def acs_event_search(self, dev_index: str, cond: dict[str, Any]) -> dict[str, Any]:
        return self._post(
            "/ISAPI/AccessControl/AcsEvent",
            payload=cond,
            params={"format": "json", "devIndex": dev_index},
        )
