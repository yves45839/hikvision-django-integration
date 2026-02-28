from __future__ import annotations


def _as_list(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def extract_devices(payload: dict) -> list[dict]:
    if not isinstance(payload, dict):
        return []

    search_result = payload.get("SearchResult", {})
    match_list = _as_list(search_result.get("MatchList")) if isinstance(search_result, dict) else []
    from_match_list = [item.get("Device") for item in match_list if isinstance(item, dict) and isinstance(item.get("Device"), dict)]

    candidates = [
        payload.get("DeviceList", {}).get("Device", []) if isinstance(payload.get("DeviceList"), dict) else [],
        payload.get("DeviceList", {}).get("devices", []) if isinstance(payload.get("DeviceList"), dict) else [],
        payload.get("Device", []),
        from_match_list,
    ]

    for candidate in candidates:
        if isinstance(candidate, list) and candidate:
            return [item for item in candidate if isinstance(item, dict)]

    return []


def normalize_device(item: dict) -> dict:
    ehome_params = item.get("EhomeParams", {}) if isinstance(item.get("EhomeParams"), dict) else {}

    return {
        "serial_number": (
            item.get("serialNumber")
            or item.get("deviceSerialNo")
            or ehome_params.get("EhomeID")
            or ""
        ),
        "dev_index": item.get("devIndex") or item.get("devIndexCode") or item.get("devMode") or "",
        "device_name": item.get("deviceName") or item.get("devName") or "",
        "status": item.get("status") or item.get("devStatus") or "",
        "protocol_type": item.get("protocolType") or item.get("protocolTypeName") or "",
        "device_type": item.get("deviceType") or item.get("devType") or "",
        "raw": item,
    }
