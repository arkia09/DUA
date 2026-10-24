from django.conf import settings


def site(request):
    """Template variables every page needs."""
    return {"DEMO_MODE": settings.DEMO_MODE}
