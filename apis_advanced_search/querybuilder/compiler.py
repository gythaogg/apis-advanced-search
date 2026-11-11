"""
Compile a query tree (see tree.py) for a given model into a Django
QuerySet. This is the only place that talks to the Django ORM - the
rest of the package only ever produces/consumes the JSON tree.
"""

from django.db.models import Q, QuerySet

from apis_advanced_search.querybuilder.introspection import get_filterable_field_map
from apis_advanced_search.querybuilder.tree import validate_node


class QueryCompileError(ValueError):
    pass


def _lookup_option(field_info, lookup_value):
    for opt in field_info.lookups:
        if opt["value"] == lookup_value:
            return opt
    return None


def _condition_q(node, field_map):
    field_name = node["field"]
    lookup_value = node["lookup"]

    field_info = field_map.get(field_name)
    if field_info is None:
        raise QueryCompileError(f"'{field_name}' is not a filterable field on this model")

    option = _lookup_option(field_info, lookup_value)
    if option is None:
        raise QueryCompileError(f"Lookup {lookup_value!r} is not valid for field {field_name!r}")

    if option["lookup"] is None:  # "empty" / "not_empty"
        q = Q(**{f"{field_name}__isnull": True})
        if field_info.type == "text":
            q |= Q(**{f"{field_name}__exact": ""})
        if option["negate"]:
            q = ~q
        return q

    django_lookup = option["lookup"]
    raw_value = node.get("value")

    if option["multi"] and isinstance(raw_value, list):
        values = [v for v in raw_value if v not in (None, "")]
        if not values:
            raise QueryCompileError(f"'{field_name}' needs at least one value")
        if django_lookup == "exact":
            # A plain "is one of" - __in already expresses the OR across
            # values in a single query.
            q = Q(**{f"{field_name}__in": values})
        else:
            # icontains/istartswith/iendswith have no __in equivalent, so
            # the OR across values has to be built by hand.
            q = Q()
            for value in values:
                q |= Q(**{f"{field_name}__{django_lookup}": value})
    else:
        value = raw_value[0] if isinstance(raw_value, list) else raw_value
        q = Q(**{f"{field_name}__{django_lookup}": value})

    if option["negate"]:
        q = ~q
    return q


def _group_q(node, field_map):
    operator = node.get("operator", "AND")
    children = node.get("children", [])

    combined = Q()
    for index, child in enumerate(children):
        child_q = _node_q(child, field_map)
        if index == 0:
            combined = child_q
        elif operator == "AND":
            combined &= child_q
        else:
            combined |= child_q

    if node.get("negate"):
        combined = ~combined
    return combined


def _node_q(node, field_map):
    if node.get("type") == "group":
        return _group_q(node, field_map)
    return _condition_q(node, field_map)


def build_queryset(model, tree: dict) -> QuerySet:
    validate_node(tree)
    field_map = get_filterable_field_map(model)
    try:
        q = _node_q(tree, field_map)
    except (TypeError, ValueError) as exc:
        if isinstance(exc, QueryCompileError):
            raise
        raise QueryCompileError(f"Could not apply filter: {exc}") from exc
    return model.objects.filter(q).distinct()
