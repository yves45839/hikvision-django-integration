from __future__ import annotations

import re
from datetime import datetime
from datetime import timezone as dt_timezone

from django.utils import timezone

from employees.models import Employee


def _iso_or_empty(value):
    if value is None:
        return ""
    # Hikvision expects naive datetime format: YYYY-MM-DDTHH:MM:SS
    if timezone.is_aware(value):
        value = timezone.localtime(value, dt_timezone.utc).replace(tzinfo=None)
    return value.strftime("%Y-%m-%dT%H:%M:%S")


def _normalize_attr_name(value: str) -> str:
    return str(value or "").strip().lower()


def _normalize_hik_identifier(value: str) -> str:
    # Gateway rejects identifiers containing '-' and other special chars.
    normalized = re.sub(r"[^A-Za-z0-9]", "", str(value or ""))
    return normalized.strip()


def _normalize_hik_card_no(value: str) -> str:
    # Preserve the original card number format (e.g. CARD-10001, hex, etc.).
    # Some terminals reject card values if we alter characters before sync.
    return str(value or "").strip()


def build_user_info_payload(employee: Employee) -> dict:
    attrs = {_normalize_attr_name(item.name): item.value for item in employee.attributes.all()}
    employee_no = _normalize_hik_identifier(attrs.get("gateway_employee_no", employee.employee_no))

    person_name = employee.name or employee.full_name or employee.employee_no
    valid_from = employee.valid_from or timezone.now()
    valid_to = employee.valid_to or datetime(2037, 12, 31, 23, 59, 59, tzinfo=dt_timezone.utc)
    validity = {
        "enable": bool(employee.is_active),
        "beginTime": _iso_or_empty(valid_from),
        "endTime": _iso_or_empty(valid_to),
    }

    user_info = {
        "employeeNo": employee_no,
        "name": person_name,
        "userType": attrs.get("user_type", "normal"),
        "Valid": validity,
        "doorRight": attrs.get("door_right", "1"),
        "RightPlan": [
            {
                "doorNo": int(attrs.get("door_no", "1")),
                "planTemplateNo": attrs.get("plan_template_no", "1"),
            }
        ],
        "localUIRight": bool(employee.is_active),
    }

    if employee.phone:
        user_info["phoneNo"] = employee.phone
    if employee.email:
        user_info["email"] = employee.email

    return {
        "UserInfo": user_info,
    }


def build_card_info_payload(employee: Employee) -> dict | None:
    payloads = build_card_info_payloads(employee)
    if not payloads:
        return None
    return payloads[0]


def build_card_info_payloads(employee: Employee) -> list[dict]:
    attrs = {_normalize_attr_name(item.name): item.value for item in employee.attributes.all()}
    employee_no = _normalize_hik_identifier(attrs.get("gateway_employee_no", employee.employee_no))
    payloads = []
    for card in employee.cards.all():
        card_no = _normalize_hik_card_no(card.card_no)
        if not card_no:
            continue
        payloads.append(
            {
                "CardInfo": {
                    "employeeNo": employee_no,
                    "cardNo": card_no,
                    "cardType": card.card_type or "normalCard",
                }
            }
        )

    if payloads:
        return payloads

    # Backward compatibility with legacy attributes-based card fields.
    card_no = _normalize_hik_card_no(str(attrs.get("card_no") or "").strip())
    if not card_no:
        return []

    return [
        {
            "CardInfo": {
                "employeeNo": employee_no,
                "cardNo": card_no,
                "cardType": attrs.get("card_type", "normalCard"),
            }
        }
    ]
