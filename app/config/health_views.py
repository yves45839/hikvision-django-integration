"""Health check endpoints for monitoring and readiness."""

import json
from django.http import JsonResponse
from django.db import connection
from django.db.utils import OperationalError


def health_check(request):
    """Health check complet — DB + appli.

    Returns:
    - 200: OK - both app and DB are healthy
    - 503: Degraded - DB is down
    """
    try:
        connection.ensure_connection()
        db_ok = True
    except OperationalError:
        db_ok = False

    status = 200 if db_ok else 503
    return JsonResponse(
        {
            "status": "ok" if db_ok else "degraded",
            "db": "ok" if db_ok else "error",
        },
        status=status,
    )


def readiness_check(request):
    """Readiness — l'app est prête à recevoir du trafic.

    Returns:
    - 200: Ready to accept traffic
    """
    return JsonResponse({"status": "ready"}, status=200)
