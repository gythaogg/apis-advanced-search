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
from apis_advanced_search.querybuilder.columns import (
    apply_ordering,
    default_column_names,
    native_column_map,
    native_columns,
    row_values,
)
from apis_advanced_search.querybuilder.compiler import QueryCompileError, build_queryset
from apis_advanced_search.querybuilder.introspection import get_filterable_fields
from apis_advanced_search.querybuilder.registry import (
    get_queryable_models,
    model_kind,
    resolve_model,
)
from apis_advanced_search.querybuilder.relations import relation_options
from apis_advanced_search.querybuilder.tree import QueryTreeError, empty_group, validate_node
from apis_advanced_search.models import SavedQuery

if COLLECTIONS_AVAILABLE:
    from apis_core.collections.models import SkosCollection

PAGE_SIZE = 25


def _parse_sort(raw, model):
    """Validate a requested sort, `{"field": ..., "direction": "asc"|"desc"}`
    or null. Only native columns of the queried model can be sorted on."""
    if raw in (None, ""):
        return None
    if not isinstance(raw, dict):
        raise ValueError("Invalid sort.")
    field = raw.get("field")
    direction = raw.get("direction", "asc")
    if field not in native_column_map(model):
        raise ValueError(f"Cannot sort on {field!r}.")
    if direction not in ("asc", "desc"):
        raise ValueError("Sort direction must be 'asc' or 'desc'.")
    return {"field": field, "direction": direction}


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


class ModelColumnsView(ModelResolvingAPIView):
    """The result-table columns offered for this model, and the defaults
    the developer configured for it (see columns.py)."""

    def get(self, request, app_label, model_name):
        return Response(
            {
                "available": [column.to_dict() for column in native_columns(self.query_model)],
                "defaults": default_column_names(self.query_model),
            }
        )


class ModelQueryView(ModelResolvingAPIView):
    def post(self, request, app_label, model_name):
        tree = request.data.get("query") or empty_group()
        try:
            queryset = build_queryset(self.query_model, tree)
        except (QueryTreeError, QueryCompileError) as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            sort = _parse_sort(request.data.get("sort"), self.query_model)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            page = max(int(request.data.get("page", 1)), 1)
        except (TypeError, ValueError):
            page = 1

        queryset = apply_ordering(queryset, sort)
        columns = native_columns(self.query_model)
        total = queryset.count()
        offset = (page - 1) * PAGE_SIZE
        content_type = ContentType.objects.get_for_model(self.query_model)
        results = [
            {
                "id": obj.pk,
                "label": str(obj),
                "url": reverse("apis_core:generic:detail", args=[content_type, obj.pk]),
                "values": row_values(obj, columns),
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


def _serialize_saved_query(query, request):
    return {
        "id": query.pk,
        "name": query.name,
        "model_label": query.model_label,
        "is_public": query.is_public,
        "is_owner": request.user.is_authenticated and query.owner_id == request.user.pk,
    }


class SavedQueryListCreateView(APIView):
    """List saved queries visible to the requester (their own, plus anyone's
    public ones) and save new ones. Listing is open to anyone - loading a
    public query needs no login, same as apis_core's own collections - but
    saving a new one does, since it needs an owner."""

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated()]
        return [AllowAny()]

    def get(self, request):
        queryset = SavedQuery.objects.filter(is_public=True)
        if request.user.is_authenticated:
            queryset = (queryset | SavedQuery.objects.filter(owner=request.user)).distinct()
        return Response([_serialize_saved_query(q, request) for q in queryset])

    def post(self, request):
        name = (request.data.get("name") or "").strip()
        if not name:
            return Response({"error": "Name is required."}, status=status.HTTP_400_BAD_REQUEST)

        model_label = request.data.get("model_label") or ""
        try:
            app_label, model_name = model_label.split(".")
        except ValueError:
            return Response(
                {"error": "Invalid model_label."}, status=status.HTTP_400_BAD_REQUEST
            )
        model = resolve_model(app_label, model_name)
        if model is None or not can_view_model(request, model):
            return Response(
                {"error": "Unknown or unviewable model."}, status=status.HTTP_400_BAD_REQUEST
            )

        tree = request.data.get("query") or empty_group()
        try:
            validate_node(tree)
        except QueryTreeError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        query = SavedQuery.objects.create(
            owner=request.user,
            name=name,
            model_label=model_label,
            tree=tree,
            is_public=bool(request.data.get("is_public", False)),
        )
        return Response(_serialize_saved_query(query, request), status=status.HTTP_201_CREATED)


class SavedQueryDetailView(APIView):
    """Load (anyone, if public or own), rename/toggle public, or delete
    (owner only) a single saved query. "Not visible to you" and "doesn't
    exist" are both reported as 404, so a private query's existence isn't
    revealed to anyone but its owner."""

    def get_permissions(self):
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAuthenticated()]

    def _visible_or_none(self, request, pk):
        query = SavedQuery.objects.filter(pk=pk).first()
        if query is None:
            return None
        if query.is_public or (request.user.is_authenticated and query.owner_id == request.user.pk):
            return query
        return None

    def get(self, request, pk):
        query = self._visible_or_none(request, pk)
        if query is None:
            return Response({"error": "No such saved query."}, status=status.HTTP_404_NOT_FOUND)
        return Response({**_serialize_saved_query(query, request), "query": query.tree})

    def _owned_or_none(self, request, pk):
        query = SavedQuery.objects.filter(pk=pk).first()
        if query is None or query.owner_id != request.user.pk:
            return None
        return query

    def patch(self, request, pk):
        query = self._owned_or_none(request, pk)
        if query is None:
            return Response({"error": "No such saved query."}, status=status.HTTP_404_NOT_FOUND)
        if "name" in request.data:
            name = (request.data.get("name") or "").strip()
            if not name:
                return Response(
                    {"error": "Name is required."}, status=status.HTTP_400_BAD_REQUEST
                )
            query.name = name
        if "is_public" in request.data:
            query.is_public = bool(request.data.get("is_public"))
        query.save()
        return Response(_serialize_saved_query(query, request))

    def delete(self, request, pk):
        query = self._owned_or_none(request, pk)
        if query is None:
            return Response({"error": "No such saved query."}, status=status.HTTP_404_NOT_FOUND)
        query.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
