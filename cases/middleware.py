from django.conf import settings

from .wipe import wipe_cases


class FreshStartMiddleware:
    """Delete every case when this server process handles its first request, so nothing outlives a restart.

    Off with WIPE_ON_START=false. The wipe is per process: run one worker (gunicorn's default), or each extra worker
    would wipe again when it starts.
    """
    wiped = False

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if settings.WIPE_ON_START and not FreshStartMiddleware.wiped:
            FreshStartMiddleware.wiped = True
            wipe_cases()
        return self.get_response(request)


class KeepSessionOnErrorMiddleware:
    """Send the session cookie even with a 5xx response.

    Django leaves the cookie off 5xx responses, and a review that fails (model down, timeout) answers 5xx. Without this
    a first-time visitor would never receive the cookie for the case that just failed, and could not send it back for
    review. Must sit after SessionMiddleware in MIDDLEWARE.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        key = getattr(getattr(request, "session", None), "session_key", None)
        name = settings.SESSION_COOKIE_NAME
        if response.status_code >= 500 and key and request.COOKIES.get(name) != key and name not in response.cookies:
            response.set_cookie(
                name, key, max_age=settings.SESSION_COOKIE_AGE, domain=settings.SESSION_COOKIE_DOMAIN,
                path=settings.SESSION_COOKIE_PATH, secure=settings.SESSION_COOKIE_SECURE or None,
                httponly=settings.SESSION_COOKIE_HTTPONLY or None, samesite=settings.SESSION_COOKIE_SAMESITE)
        return response
