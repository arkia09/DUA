from django.contrib import admin

from .models import Case


@admin.register(Case)
class CaseAdmin(admin.ModelAdmin):
    list_display = ("number", "department", "status", "created_at")
    list_filter = ("department", "status")
    readonly_fields = ("number", "created_at")
