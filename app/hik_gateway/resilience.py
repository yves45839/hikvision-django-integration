"""
PHASE 11.1 — Retry + Circuit Breaker pour la résilience Hikvision
Utilise tenacity pour les retries et pybreaker pour le circuit breaker.
"""
import logging
from typing import Any, Callable

import pybreaker
import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

logger = logging.getLogger(__name__)

# Circuit breaker partagé par tenant
_breakers: dict[str, pybreaker.CircuitBreaker] = {}


def get_circuit_breaker(tenant_code: str) -> pybreaker.CircuitBreaker:
    """
    Obtient ou crée un circuit breaker pour un tenant donné.

    Args:
        tenant_code: Code du tenant

    Returns:
        Instance de CircuitBreaker
    """
    if tenant_code not in _breakers:
        _breakers[tenant_code] = pybreaker.CircuitBreaker(
            fail_max=5,  # Ouvre le circuit après 5 échecs
            reset_timeout=60,  # Réessaie après 60 secondes
            name=f"hik_gateway_{tenant_code}",
            listeners=[_breaker_listener],
        )
    return _breakers[tenant_code]


def _breaker_listener(cb, *args, **kwargs):
    """Listener pour enregistrer les changements d'état du circuit breaker."""
    if cb.current_state == "open":
        logger.warning(f"Circuit breaker {cb.name} is OPEN")
    elif cb.current_state == "closed":
        logger.info(f"Circuit breaker {cb.name} is CLOSED")
    elif cb.current_state == "half-open":
        logger.info(f"Circuit breaker {cb.name} is HALF-OPEN (testing)")


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((requests.Timeout, requests.ConnectionError)),
    reraise=True,
)
def _retry_wrapper(func: Callable, *args, **kwargs) -> Any:
    """Wrapper interne pour la logique de retry."""
    return func(*args, **kwargs)


def resilient_gateway_call(
    func: Callable,
    tenant_code: str,
    *args,
    **kwargs,
) -> Any:
    """
    Exécute un appel gateway avec retry + circuit breaker.

    Wrapper pour les appels HTTP critiques. Combine:
    - Retry avec backoff exponentiel (max 3 tentatives)
    - Circuit breaker (5 échecs = circuit ouvert)
    - Timeout de 20s par défaut

    Args:
        func: Fonction à appeler
        tenant_code: Code du tenant (pour le circuit breaker)
        *args: Arguments positionnels
        **kwargs: Arguments nommés

    Returns:
        Résultat de func(*args, **kwargs)

    Raises:
        requests.Timeout: Si timeout après 3 tentatives
        requests.ConnectionError: Si erreur de connexion après 3 tentatives
        pybreaker.CircuitBreakerError: Si circuit ouvert
    """
    breaker = get_circuit_breaker(tenant_code)

    try:
        # Le circuit breaker va appeler _retry_wrapper
        # qui va lui-même retry si timeout/connexion
        return breaker.call(_retry_wrapper, func, *args, **kwargs)
    except pybreaker.CircuitBreakerError as exc:
        logger.error(f"Circuit breaker for {tenant_code} is open, request rejected")
        raise
    except (requests.Timeout, requests.ConnectionError) as exc:
        logger.error(f"Gateway call failed after 3 retries for {tenant_code}: {exc}")
        raise
    except Exception as exc:
        logger.error(f"Unexpected error in resilient gateway call: {exc}")
        raise
