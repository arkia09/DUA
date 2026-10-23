from django.urls import path
from . import views

urlpatterns = [
    path("requests/", views.file_request),
    path("requests/upload/", views.upload_request),
    path("cases/", views.list_cases),
    path("cases/<str:number>/", views.case_detail),
    path("cases/<str:number>/retry/", views.retry_case),
    path("cases/<str:number>/shred/", views.shred_case),
    path("cases/<str:number>/tasks/<int:index>/", views.set_task_done),
    path("cases/<str:number>/carry-over/", views.carry_over),
    path("cases/<str:number>/export/<str:fmt>/", views.export_case),
]
