import hashlib

from django.conf import settings
from django.core.cache import cache


def client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (forwarded.split(",", 1)[0] if forwarded else request.META.get("REMOTE_ADDR", "")).strip() or "unknown"


def _key(scope, value):
    digest = hashlib.sha256(value.lower().strip().encode("utf-8")).hexdigest()
    return f"auth-rate:{scope}:{digest}"


def rate_limit_exceeded(scope, value, limit):
    key = _key(scope, value)
    if cache.add(key, 1, timeout=settings.AUTH_RATE_LIMIT_WINDOW_SECONDS):
        return False
    try:
        attempts = cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=settings.AUTH_RATE_LIMIT_WINDOW_SECONDS)
        return False
    return attempts > limit


def auth_request_limited(request, email):
    return (
        rate_limit_exceeded("email", email, settings.AUTH_RATE_LIMIT_EMAIL_ATTEMPTS)
        or rate_limit_exceeded("ip", client_ip(request), settings.AUTH_RATE_LIMIT_IP_ATTEMPTS)
    )
