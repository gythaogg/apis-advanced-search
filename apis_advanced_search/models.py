from django.conf import settings
from django.db import models


class SavedQuery(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_queries"
    )
    name = models.CharField(max_length=300)
    # "app_label.model_name" of the model the query starts from - same
    # convention used throughout querybuilder/ for relation/target models.
    model_label = models.CharField(max_length=200)
    tree = models.JSONField()
    # Private by default; the owner can opt in to letting anyone load and
    # run it. Never grants anyone but the owner the ability to edit/delete it.
    is_public = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.name
