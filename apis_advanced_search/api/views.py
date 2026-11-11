from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apis_advanced_search.api.permissions import can_view_model
from apis_advanced_search.querybuilder.compiler import QueryCompileError, build_queryset
from apis_advanced_search.querybuilder.introspection import get_filterable_fields
from apis_advanced_search.querybuilder.registry import (
    get_queryable_models,
    model_kind,
    resolve_model,
)
from apis_advanced_search.querybuilder.tree import QueryTreeError, empty_group

PAGE_SIZE = 25


class ModelResolvingAPIView(APIView):
    """Resolve <app_label>/<model_name> to a registered queryable model,
    checking it exists and the user may view it, before dispatching."""

    # Permissions are checked per-model (via can_view_model) rather than
    # through DRF's default DjangoModelPermissions, since the model being
    # accessed is dynamic and only known once the URL is resolved.
    permission_classes = [AllowAny]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        model = resolve_model(kwargs["app_label"], kwargs["model_name"])
        if model is None:
            raise NotFound("No such registered entity or relation model")
        if not can_view_model(request, model):
            raise PermissionDenied("You may not view this model")
        self.query_model = model


class ModelListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        data = []
        for model in get_queryable_models():
            if not can_view_model(request, model):
                continue
            entry = {
                "app_label": model._meta.app_label,
                "model": model._meta.model_name,
                "label": f"{model._meta.app_label}.{model._meta.model_name}",
                "verbose_name": str(model._meta.verbose_name),
                "kind": model_kind(model),
            }
            data.append(entry)
        return Response(data)


class ModelFieldsView(ModelResolvingAPIView):
    def get(self, request, app_label, model_name):
        fields = [info.to_dict() for info in get_filterable_fields(self.query_model)]
        return Response(fields)


class ModelQueryView(ModelResolvingAPIView):
    def post(self, request, app_label, model_name):
        tree = request.data.get("query") or empty_group()
        try:
            queryset = build_queryset(self.query_model, tree)
        except (QueryTreeError, QueryCompileError) as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            page = max(int(request.data.get("page", 1)), 1)
        except (TypeError, ValueError):
            page = 1

        total = queryset.count()
        offset = (page - 1) * PAGE_SIZE
        content_type = ContentType.objects.get_for_model(self.query_model)
        results = [
            {
                "id": obj.pk,
                "label": str(obj),
                "url": reverse("apis_core:generic:detail", args=[content_type, obj.pk]),
            }
            for obj in queryset[offset : offset + PAGE_SIZE]
        ]
        return Response(
            {
                "count": total,
                "page": page,
                "page_size": PAGE_SIZE,
                "results": results,
            }
        )
