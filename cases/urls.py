from django.urls import path
from . import views

urlpatterns = [
    path("requests/", views.file_request),
    path("cases/", views.list_cases),
    path("cases/<str:number>/", views.case_detail),
    path("cases/<str:number>/retry/", views.retry_case),
]
