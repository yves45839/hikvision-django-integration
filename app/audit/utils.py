from audit.models import AuditEvent


def get_client_ip(request):
    """Extract client IP from request, handling X-Forwarded-For headers."""
    if request is None:
        return None
    
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def audit_log(actor=None, action="", target_obj=None, request=None, tenant_code="",
              target_model="", target_id="", **extra):
    """
    0.5: Helper to log audit events.

    Args:
        actor: User instance performing the action
        action: Action name (e.g., "create_device", "update_employee")
        target_obj: Model instance being acted upon (optional)
        request: HTTP request object (optional, for IP extraction)
        tenant_code: Tenant code (optional)
        target_model / target_id: explicit target override when the instance is
            no longer available (e.g. after a delete)
        **extra: Additional context data

    Returns:
        Created AuditEvent instance
    """
    if target_obj:
        target_model = target_obj.__class__.__name__
        target_id = str(target_obj.pk)
    
    ip_address = None
    if request:
        ip_address = get_client_ip(request)
    
    return AuditEvent.objects.create(
        actor=actor,
        action=action,
        target_model=target_model,
        target_id=target_id,
        ip_address=ip_address,
        tenant_code=tenant_code,
        extra=extra,
    )
