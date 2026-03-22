from __future__ import annotations

import json
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
        ok = getattr(response, "ok", None)
        if ok is None:
            status_code = int(getattr(response, "status_code", 200) or 200)
            ok = 200 <= status_code < 400

        if not ok:
            body = (response.text or "").strip()
            body = body[:1000]
            raise requests.HTTPError(
                f"{getattr(response, 'status_code', 'unknown')} "
                f"{getattr(response, 'reason', '')} for url: {getattr(response, 'url', url)}; body={body}",
                response=response,
            )
        return response.json() if response.content else {}

    def _post_multipart(
        self,
        path: str,
        *,
        files: dict[str, Any],
        params: dict[str, Any] | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        url = urljoin(self.base_url, path.lstrip("/"))
        response = requests.post(
            url,
            files=files,
            params=params or {},
            auth=self.auth,
            timeout=timeout or self.timeout,
        )
        ok = getattr(response, "ok", None)
        if ok is None:
            status_code = int(getattr(response, "status_code", 200) or 200)
            ok = 200 <= status_code < 400

        if not ok:
            body = (response.text or "").strip()
            body = body[:1000]
            raise requests.HTTPError(
                f"{getattr(response, 'status_code', 'unknown')} "
                f"{getattr(response, 'reason', '')} for url: {getattr(response, 'url', url)}; body={body}",
                response=response,
            )
        return response.json() if response.content else {}

    def _put(self, path: str, payload: dict[str, Any], params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = urljoin(self.base_url, path.lstrip("/"))
        response = requests.put(url, json=payload, params=params or {}, auth=self.auth, timeout=self.timeout)
        ok = getattr(response, "ok", None)
        if ok is None:
            status_code = int(getattr(response, "status_code", 200) or 200)
            ok = 200 <= status_code < 400

        if not ok:
            body = (response.text or "").strip()
            body = body[:1000]
            raise requests.HTTPError(
                f"{getattr(response, 'status_code', 'unknown')} "
                f"{getattr(response, 'reason', '')} for url: {getattr(response, 'url', url)}; body={body}",
                response=response,
            )
        return response.json() if response.content else {}

    def _put_text(self, path: str, payload: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = urljoin(self.base_url, path.lstrip("/"))
        response = requests.put(
            url,
            data=str(payload),
            params=params or {},
            auth=self.auth,
            timeout=self.timeout,
            headers={"Content-Type": "text/plain; charset=utf-8"},
        )
        ok = getattr(response, "ok", None)
        if ok is None:
            status_code = int(getattr(response, "status_code", 200) or 200)
            ok = 200 <= status_code < 400

        if not ok:
            body = (response.text or "").strip()
            body = body[:1000]
            raise requests.HTTPError(
                f"{getattr(response, 'status_code', 'unknown')} "
                f"{getattr(response, 'reason', '')} for url: {getattr(response, 'url', url)}; body={body}",
                response=response,
            )
        return response.json() if response.content else {}

    def _delete(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = urljoin(self.base_url, path.lstrip("/"))
        response = requests.delete(url, params=params or {}, auth=self.auth, timeout=self.timeout)
        ok = getattr(response, "ok", None)
        if ok is None:
            status_code = int(getattr(response, "status_code", 200) or 200)
            ok = 200 <= status_code < 400

        if not ok:
            body = (response.text or "").strip()
            body = body[:1000]
            raise requests.HTTPError(
                f"{getattr(response, 'status_code', 'unknown')} "
                f"{getattr(response, 'reason', '')} for url: {getattr(response, 'url', url)}; body={body}",
                response=response,
            )
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

    def add_device(self, payload: dict[str, Any], timeout: int | None = None) -> dict[str, Any]:
        return self._post(
            "/ISAPI/ContentMgmt/DeviceMgmt/addDevice",
            payload=payload,
            params={"format": "json"},
            timeout=timeout,
        )

    def delete_device(self, dev_index: str) -> dict[str, Any]:
        return self._delete(
            "/ISAPI/ContentMgmt/DeviceMgmt/delDevice",
            params={"format": "json", "devIndex": dev_index},
        )

    def reboot_device(self, dev_index: str) -> dict[str, Any]:
        return self._put(
            "/ISAPI/System/reboot",
            payload={},
            params={"format": "json", "devIndex": dev_index},
        )

    def set_device_time_sync(self, dev_index: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._put(
            "/ISAPI/System/time",
            payload=payload,
            params={"format": "json", "devIndex": dev_index},
        )

    def set_device_time_zone(self, dev_index: str, time_zone: str) -> dict[str, Any]:
        return self._put_text(
            "/ISAPI/System/time/timeZone",
            payload=str(time_zone),
            params={"devIndex": dev_index},
        )

    def add_access_user(self, dev_index: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post(
            "/ISAPI/AccessControl/UserInfo/Record",
            payload=payload,
            params={"format": "json", "devIndex": dev_index},
        )

    def add_access_card(self, dev_index: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post(
            "/ISAPI/AccessControl/CardInfo/Record",
            payload=payload,
            params={"format": "json", "devIndex": dev_index},
        )

    def search_access_users(
        self,
        dev_index: str,
        *,
        search_id: str = "1",
        search_result_position: int = 0,
        max_results: int = 50,
    ) -> dict[str, Any]:
        payload = {
            "UserInfoSearchCond": {
                "searchID": search_id,
                "searchResultPosition": search_result_position,
                "maxResults": max_results,
            }
        }
        return self._post(
            "/ISAPI/AccessControl/UserInfo/Search",
            payload=payload,
            params={"format": "json", "devIndex": dev_index},
        )

    def search_access_users_all(self, dev_index: str, *, max_results: int = 50) -> dict[str, Any]:
        position = 0
        total_matches = 0
        users: list[dict[str, Any]] = []

        while True:
            payload = self.search_access_users(
                dev_index=dev_index,
                search_result_position=position,
                max_results=max_results,
            )
            search = payload.get("UserInfoSearch", {}) if isinstance(payload, dict) else {}
            batch = search.get("UserInfo", []) if isinstance(search, dict) else []
            if isinstance(batch, dict):
                batch = [batch]
            if not isinstance(batch, list):
                batch = []

            num_of_matches = int(search.get("numOfMatches", len(batch)) or 0)
            total_matches = int(search.get("totalMatches", total_matches) or total_matches)
            users.extend([item for item in batch if isinstance(item, dict)])

            position += num_of_matches
            if num_of_matches <= 0:
                break
            if total_matches and position >= total_matches:
                break

        return {
            "UserInfoSearch": {
                "searchID": "1",
                "responseStatusStrg": "OK",
                "numOfMatches": len(users),
                "totalMatches": total_matches or len(users),
                "UserInfo": users,
            }
        }

    def search_access_cards(
        self,
        dev_index: str,
        *,
        search_id: str = "1",
        search_result_position: int = 0,
        max_results: int = 50,
    ) -> dict[str, Any]:
        payload = {
            "CardInfoSearchCond": {
                "searchID": search_id,
                "searchResultPosition": search_result_position,
                "maxResults": max_results,
            }
        }
        return self._post(
            "/ISAPI/AccessControl/CardInfo/Search",
            payload=payload,
            params={"format": "json", "devIndex": dev_index},
        )

    def search_access_cards_all(self, dev_index: str, *, max_results: int = 50) -> dict[str, Any]:
        position = 0
        total_matches = 0
        cards: list[dict[str, Any]] = []

        while True:
            payload = self.search_access_cards(
                dev_index=dev_index,
                search_result_position=position,
                max_results=max_results,
            )
            search = payload.get("CardInfoSearch", {}) if isinstance(payload, dict) else {}
            batch = search.get("CardInfo", []) if isinstance(search, dict) else []
            if isinstance(batch, dict):
                batch = [batch]
            if not isinstance(batch, list):
                batch = []

            num_of_matches = int(search.get("numOfMatches", len(batch)) or 0)
            total_matches = int(search.get("totalMatches", total_matches) or total_matches)
            cards.extend([item for item in batch if isinstance(item, dict)])

            position += num_of_matches
            if num_of_matches <= 0:
                break
            if total_matches and position >= total_matches:
                break

        return {
            "CardInfoSearch": {
                "searchID": "1",
                "responseStatusStrg": "OK",
                "numOfMatches": len(cards),
                "totalMatches": total_matches or len(cards),
                "CardInfo": cards,
            }
        }

    def add_access_fingerprint(self, dev_index: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post(
            "/ISAPI/AccessControl/FingerPrintDownload",
            payload=payload,
            params={"format": "json", "devIndex": dev_index},
        )

    def add_access_face(
        self,
        dev_index: str,
        *,
        employee_no: str,
        face_image: bytes,
        face_lib_type: str = "blackFD",
        content_type: str = "image/jpeg",
        filename: str = "face.jpg",
    ) -> dict[str, Any]:
        face_info = {
            "FaceInfo": {
                "employeeNo": str(employee_no or "").strip(),
                "faceLibType": str(face_lib_type or "blackFD").strip() or "blackFD",
            }
        }
        files = {
            "FaceDataRecord": (None, json.dumps(face_info), "application/json"),
            "FaceImage": (filename, face_image, content_type or "image/jpeg"),
        }
        return self._post_multipart(
            "/ISAPI/Intelligent/FDLib/FaceDataRecord",
            files=files,
            params={"format": "json", "devIndex": dev_index},
        )

    def capture_fingerprint(
        self,
        dev_index: str,
        *,
        finger_no: int,
    ) -> dict[str, Any]:
        payload = {
            "CaptureFingerPrintCond": {
                "fingerNo": int(finger_no),
            }
        }
        return self._post(
            "/ISAPI/AccessControl/CaptureFingerPrint",
            payload=payload,
            params={"format": "json", "devIndex": dev_index},
        )

    def search_access_fingerprints(self, dev_index: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post(
            "/ISAPI/AccessControl/FingerPrintUpload",
            payload=payload,
            params={"format": "json", "devIndex": dev_index},
        )

    def search_access_fingerprints_all(
        self,
        dev_index: str,
        *,
        employee_no: str,
        search_id: str = "1",
        max_attempts: int = 16,
    ) -> dict[str, Any]:
        normalized_employee_no = str(employee_no or "").strip()
        if not normalized_employee_no:
            return {
                "FingerPrintInfo": {
                    "searchID": str(search_id),
                    "status": "NoFP",
                    "FingerPrintList": [],
                }
            }

        found: list[dict[str, Any]] = []
        dedupe_keys: set[tuple[Any, ...]] = set()
        status_value = "NoFP"

        for _ in range(max(1, int(max_attempts or 1))):
            payload = self.search_access_fingerprints(
                dev_index=dev_index,
                payload={
                    "FingerPrintCond": {
                        "searchID": str(search_id),
                        "employeeNo": normalized_employee_no,
                    }
                },
            )
            info = payload.get("FingerPrintInfo", {}) if isinstance(payload, dict) else {}
            if not isinstance(info, dict):
                break

            status_value = str(info.get("status") or "").strip() or status_value
            rows = info.get("FingerPrintList", [])
            if isinstance(rows, dict):
                rows = [rows]
            if not isinstance(rows, list):
                rows = []

            new_added = 0
            for row in rows:
                if not isinstance(row, dict):
                    continue
                key = (
                    str(row.get("cardReaderNo") or ""),
                    str(row.get("fingerPrintID") or ""),
                    str(row.get("fingerData") or ""),
                )
                if key in dedupe_keys:
                    continue
                dedupe_keys.add(key)
                found.append(row)
                new_added += 1

            normalized_status = status_value.upper().replace(" ", "")
            if normalized_status in {"NOFP", "NOMATCH", "NO"}:
                break
            if not rows or new_added == 0:
                break

        return {
            "FingerPrintInfo": {
                "searchID": str(search_id),
                "status": status_value,
                "FingerPrintList": found,
            }
        }
