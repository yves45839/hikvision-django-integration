from __future__ import annotations

from employees.models import Employee


def _iso_or_empty(value):
    if value is None:
        return ""
    return value.isoformat()


def _normalize_attr_name(value: str) -> str:
    return str(value or "").strip().lower()


def build_user_info_payload(employee: Employee) -> dict:
    attrs = {_normalize_attr_name(item.name): item.value for item in employee.attributes.all()}

    person_name = employee.name or employee.full_name or employee.employee_no
    validity = {
        "enable": bool(employee.is_active),
    }
    if employee.valid_from is not None:
        validity["beginTime"] = _iso_or_empty(employee.valid_from)
    if employee.valid_to is not None:
        validity["endTime"] = _iso_or_empty(employee.valid_to)

    user_info = {
        "employeeNo": employee.employee_no,
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
    payloads = []
    for card in employee.cards.all():
        payloads.append(
            {
                "CardInfo": {
                    "employeeNo": employee.employee_no,
                    "cardNo": card.card_no,
                    "cardType": card.card_type or "normalCard",
                    "leaderCard": False,
                    "deleteCard": False,
                }
            }
        )

    if payloads:
        return payloads

    # Backward compatibility with legacy attributes-based card fields.
    attrs = {_normalize_attr_name(item.name): item.value for item in employee.attributes.all()}
    card_no = str(attrs.get("card_no") or "").strip()
    if not card_no:
        return []

    return [
        {
            "CardInfo": {
                "employeeNo": employee.employee_no,
                "cardNo": card_no,
                "cardType": attrs.get("card_type", "normalCard"),
                "leaderCard": False,
                "deleteCard": False,
            }
        }
    ]
