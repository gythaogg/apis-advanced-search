from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apis_advanced_search.api.permissions import can_view_model
from apis_advanced_search.querybuilder.collections import (
    COLLECTIONS_AVAILABLE,
    bulk_add_to_collection,
)
from apis_advanced_search.querybuilder.compiler import QueryCompileError, build_queryset
from apis_advanced_search.querybuilder.introspection import get_filterable_fields
from apis_advanced_search.querybuilder.registry import (
    get_queryable_models,
    model_kind,
    resolve_model,
)
from apis_advanced_search.querybuilder.relations import relation_options
from apis_advanced_search.querybuilder.tree import QueryTreeError, empty_group

if COLLECTIONS_AVAILABLE:
    from apis_core.collections.models import SkosCollection

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


class ModelRelationsView(ModelResolvingAPIView):
    """The relation-traversal options offerable from this model - each
    naming a relation (or, for a Relation model itself, its fixed
    subject/object slots) plus the far-side target model, filtered down
    to what the requesting user may actually view."""

    def get(self, request, app_label, model_name):
        data = []
        for option in relation_options(self.query_model):
            if option["relation_model"] is not None:
                relation_model = resolve_model(*option["relation_model"].split("."))
                if relation_model is None or not can_view_model(request, relation_model):
                    continue
            target_model = resolve_model(*option["target_model"].split("."))
            if target_model is None or not can_view_model(request, target_model):
                continue
            data.append(option)
        return Response(data)


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


class CollectionListView(APIView):
    """Existing collections to offer in the "add results to a collection"
    picker. Listing names isn't sensitive, so unlike actually adding to one,
    this doesn't require login."""

    permission_classes = [AllowAny]

    def get(self, request):
        if not COLLECTIONS_AVAILABLE:
            return Response(
                {"error": "Collections are not enabled on this instance."},
                status=status.HTTP_501_NOT_IMPLEMENTED,
            )
        collections = SkosCollection.objects.order_by("name")
        return Response([{"id": c.pk, "name": c.name} for c in collections])


class AddResultsToCollectionView(ModelResolvingAPIView):
    """Bulk-add every object currently matching a query tree to a SKOS
    collection - an existing one (`collection_id`) or a new one
    (`collection_name`). Requires login, same as apis_core's own collection
    views."""

    permission_classes = [IsAuthenticated]

    def post(self, request, app_label, model_name):
        if not COLLECTIONS_AVAILABLE:
            return Response(
                {"error": "Collections are not enabled on this instance."},
                status=status.HTTP_501_NOT_IMPLEMENTED,
            )
        tree = request.data.get("query") or empty_group()
        try:
            queryset = build_queryset(self.query_model, tree)
        except (QueryTreeError, QueryCompileError) as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        collection_id = request.data.get("collection_id")
        collection_name = (request.data.get("collection_name") or "").strip()

        if collection_id:
            collection = SkosCollection.objects.filter(pk=collection_id).first()
            if collection is None:
                return Response(
                    {"error": "No such collection"}, status=status.HTTP_404_NOT_FOUND
                )
        elif collection_name:
            collection = SkosCollection.objects.create(
                name=collection_name, creator=request.user.get_username()
            )
        else:
            return Response(
                {"error": "Provide collection_id or collection_name"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        pks = list(queryset.values_list("pk", flat=True))
        added = bulk_add_to_collection(collection, self.query_model, pks)

        collection_ct = ContentType.objects.get_for_model(SkosCollection)
        return Response(
            {
                "collection": {
                    "id": collection.pk,
                    "name": collection.name,
                    "url": reverse(
                        "apis_core:generic:detail", args=[collection_ct, collection.pk]
                    ),
                },
                "matched": len(pks),
                "added": added,
            }
        )
