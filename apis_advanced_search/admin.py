from django.contrib import admin

from apis_advanced_search.models import SavedQuery


@admin.register(SavedQuery)
class SavedQueryAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "name",
        "owner",
        "model_label",
        "tree",
        "is_public",
        "created_at",
        "updated_at",
    ]
    fields = [
        "owner",
        "name",
        "model_label",
        "tree",
        "is_public",
        "created_at",
        "updated_at",
    ]
    readonly_fields = ["created_at", "updated_at"]
