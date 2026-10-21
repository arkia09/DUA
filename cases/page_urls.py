from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("files/", views.files_page, name="files"),
    path("files/<str:number>/", views.file_page, name="file"),
    path("<slug:slug>/", views.department_page, name="department"),
]
