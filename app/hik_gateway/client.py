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

    def _device_search_payload(
        self,
        position: int = 0,
        max_result: int = 100,
        protocol_types: list[str] | None = None,
        statuses: list[str] | None = None,
        dev_type: str = "",
        key: str = "",
    ) -> dict[str, Any]:
        return {
            "SearchDescription": {
                "position": position,
                "maxResult": max_result,
                "Filter": {
                    "key": key,
                    "devType": dev_type,
                    "protocolType": protocol_types if protocol_types is not None else ["ehomeV5"],
                    "devStatus": statuses if statuses is not None else ["online", "offline"],
                },
            }
        }

    def device_list(
        self,
        payload: dict[str, Any] | None = None,
        timeout: int | None = None,
        *,
        position: int = 0,
        max_result: int = 100,
        protocol_types: list[str] | None = None,
        statuses: list[str] | None = None,
        dev_type: str = "",
        key: str = "",
    ) -> dict[str, Any]:
        request_payload = payload or self._device_search_payload(
            position=position,
            max_result=max_result,
            protocol_types=protocol_types,
            statuses=statuses,
            dev_type=dev_type,
            key=key,
        )

        return self._post(
            "/ISAPI/ContentMgmt/DeviceMgmt/deviceList",
            payload=request_payload,
            params={"format": "json"},
            timeout=timeout,
        )

    def device_list_all(
        self,
        *,
        max_result: int = 100,
        protocol_types: list[str] | None = None,
        statuses: list[str] | None = None,
        dev_type: str = "",
        key: str = "",
        timeout: int | None = None,
    ) -> dict[str, Any]:
        position = 0
        total_matches = 0
        match_list: list[dict[str, Any]] = []

        while True:
            payload = self.device_list(
                position=position,
                max_result=max_result,
                protocol_types=protocol_types,
                statuses=statuses,
                dev_type=dev_type,
                key=key,
                timeout=timeout,
            )
            search_result = payload.get("SearchResult", {}) if isinstance(payload, dict) else {}
            page_matches = search_result.get("MatchList", []) if isinstance(search_result, dict) else []
            if isinstance(page_matches, dict):
                page_matches = [page_matches]
            if not isinstance(page_matches, list):
                page_matches = []

            num_of_matches = int(search_result.get("numOfMatches", len(page_matches)) or 0)
            total_matches = int(search_result.get("totalMatches", total_matches) or total_matches)
            match_list.extend([item for item in page_matches if isinstance(item, dict)])

            position += num_of_matches
            if num_of_matches <= 0:
                break
            if total_matches and position >= total_matches:
                break

        return {
            "SearchResult": {
                "position": 0,
                "numOfMatches": len(match_list),
                "totalMatches": total_matches or len(match_list),
                "MatchList": match_list,
            }
        }

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
