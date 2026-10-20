from django.urls import path
from . import views

urlpatterns = [
    path("requests/", views.file_request),
    path("cases/", views.list_cases),
]
