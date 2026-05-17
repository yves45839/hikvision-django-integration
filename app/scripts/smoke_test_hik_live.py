"""Smoke test live Hik Device Gateway — LECTURE SEULE.

Usage (depuis la racine du repo):
    cd app
    .venv\\Scripts\\activate.bat   # ou source .venv/bin/activate
    python manage.py shell < scripts/smoke_test_hik_live.py

ou plus simple:
    cd app
    python scripts/smoke_test_hik_live.py

N'écrit RIEN dans la base de données ni sur la gateway.
Utilise les credentials HIK_DEVICE_GATEWAY_* du .env du projet.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# Permettre l'exécution standalone (sans manage.py shell)
if "DJANGO_SETTINGS_MODULE" not in os.environ:
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
    BASE_DIR = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(BASE_DIR))

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402

from hik_gateway.client import HikGatewayClient  # noqa: E402


def _section(title: str) -> None:
    bar = "─" * 68
    print(f"\n{bar}\n  {title}\n{bar}")


def main() -> int:
    base_url = (getattr(settings, "HIK_DEVICE_GATEWAY_BASE_URL", "") or "").strip()
    username = (getattr(settings, "HIK_DEVICE_GATEWAY_USERNAME", "") or "").strip()
    password = (getattr(settings, "HIK_DEVICE_GATEWAY_PASSWORD", "") or "").strip()

    _section("Configuration lue")
    print(f"  base_url: {base_url or '(vide)'}")
    print(f"  username: {username or '(vide)'}")
    print(f"  password: {'(défini)' if password else '(vide)'}")

    if not (base_url and username and password):
        print("\n  ❌ Configuration HIK_DEVICE_GATEWAY_* incomplète. Stop.")
        return 1

    client = HikGatewayClient(base_url, username, password, timeout=15)

    # ── 1. Connectivité TCP / HTTP ────────────────────────────────
    _section("1. Connectivité de base (HTTP HEAD)")
    import requests

    t0 = time.time()
    try:
        r = requests.head(base_url, timeout=10, allow_redirects=False)
        dt = (time.time() - t0) * 1000
        print(f"  HTTP {r.status_code} en {dt:.0f} ms — gateway joignable")
    except Exception as exc:
        dt = (time.time() - t0) * 1000
        print(f"  ❌ Échec HEAD {base_url} après {dt:.0f} ms : {exc}")
        return 2

    # ── 2. Liste devices (lecture seule, max 5) ──────────────────
    _section("2. device_list (max 5, lecture seule)")
    t0 = time.time()
    try:
        result = client.device_list(max_result=5)
        dt = (time.time() - t0) * 1000
        print(f"  ✅ Réponse en {dt:.0f} ms")
    except Exception as exc:
        dt = (time.time() - t0) * 1000
        print(f"  ❌ Échec après {dt:.0f} ms : {exc}")
        return 3

    devices = (
        result.get("DeviceListResponse", {})
        .get("DeviceList", {})
        .get("Device", [])
    )
    total = (
        result.get("DeviceListResponse", {}).get("DeviceList", {}).get("totalMatches")
        or result.get("DeviceListResponse", {}).get("DeviceList", {}).get("numOfMatches")
    )
    print(f"  total devices déclarés sur la gateway : {total}")
    print(f"  échantillon (max 5) : {len(devices)} entrée(s)")

    for i, dev in enumerate(devices[:5], 1):
        # On reste laconique pour ne pas leaker les serial complets
        serial = dev.get("serialNumber", "")
        masked = serial[:4] + "…" + serial[-4:] if len(serial) > 10 else serial
        print(
            f"    [{i}] devIndex={dev.get('devIndex','?')} "
            f"name={dev.get('name','?')!r} "
            f"protocol={dev.get('protocolType','?')} "
            f"status={dev.get('devStatus','?')} "
            f"serial={masked}"
        )

    # ── 3. Vérification résilience (présence du module) ──────────
    _section("3. Résilience câblée ?")
    try:
        from hik_gateway.resilience import resilient_gateway_call  # noqa: F401

        print("  Module resilience.py présent ✅")
    except ImportError as exc:
        print(f"  ❌ resilience.py introuvable : {exc}")

    # Vérifier que gateway_connection.py l'utilise
    from hik_gateway.services import gateway_connection

    src = Path(gateway_connection.__file__).read_text(encoding="utf-8")
    if "resilient_gateway_call" in src:
        print("  gateway_connection.py utilise resilient_gateway_call ✅")
    else:
        print(
            "  ⚠️  gateway_connection.py n'appelle PAS resilient_gateway_call — "
            "résilience non câblée en runtime."
        )

    _section("Résumé")
    print("  Connectivité : OK")
    print(f"  Devices visibles : {total}")
    print("  Smoke test terminé sans modification de l'état de la gateway.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
