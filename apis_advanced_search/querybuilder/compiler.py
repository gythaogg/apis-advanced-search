"""
Compile a query tree (see tree.py) for a given model into a Django
QuerySet. This is the only place that talks to the Django ORM - the
rest of the package only ever produces/consumes the JSON tree.
"""

from django.db.models import Q, QuerySet

from apis_advanced_search.querybuilder.introspection import get_filterable_field_map
from apis_advanced_search.querybuilder.registry import resolve_model
from apis_advanced_search.querybuilder.relations import is_relation_model
from apis_advanced_search.querybuilder.tree import validate_node


class QueryCompileError(ValueError):
    pass


def _resolve_relation_model(relation_label):
    app_label, model_name = relation_label.split(".")
    model = resolve_model(app_label, model_name)
    if model is None or not is_relation_model(model):
        raise QueryCompileError(f"Unknown relation model: {relation_label!r}")
    return model


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


def _group_q(node, model, field_map):
    operator = node.get("operator", "AND")
    children = node.get("children", [])

    combined = Q()
    for index, child in enumerate(children):
        child_q = _node_q(child, model, field_map)
        if index == 0:
            combined = child_q
        elif operator == "AND":
            combined &= child_q
        else:
            combined |= child_q

    if node.get("negate"):
        combined = ~combined
    return combined


def _filtered_pks(model, filter_tree):
    """pks of `model` matching `filter_tree`, or None if there's no filter
    (i.e. "any" of them count, not "none" of them)."""
    if filter_tree is None:
        return None
    field_map = get_filterable_field_map(model)
    q = _node_q(filter_tree, model, field_map)
    return model.objects.filter(q).values("pk")


def _relation_q(node, model):
    direction = node.get("direction")
    if direction not in ("subj", "obj"):
        raise QueryCompileError(f"Invalid relation direction: {direction!r}")
    relation_label = node.get("relation_model")
    target_filter = node.get("target_filter")

    if relation_label is None:
        # Direct mode: `model` IS the relation, and we're filtering its own
        # fixed subject or object slot directly - no subquery needed, this
        # is a plain forward filter on the relation's own GFK columns.
        if not is_relation_model(model):
            raise QueryCompileError(
                "A relation node without 'relation_model' can only be used "
                "when the current model is itself a Relation"
            )
        target_model = model.subj_model_type() if direction == "subj" else model.obj_model_type()
        target_pks = _filtered_pks(target_model, target_filter)
        if target_pks is not None:
            q = Q(**{f"{direction}_object_id__in": target_pks})
        else:
            q = Q(**{f"{direction}_object_id__isnull": False})
    else:
        # Traverse mode: `model` is an entity reachable via this relation.
        # `direction` names the slot the *target* sits in, so `model`
        # necessarily sits in the other one.
        relation_model = _resolve_relation_model(relation_label)
        current_side = "subj" if direction == "obj" else "obj"
        target_model = (
            relation_model.subj_model_type() if direction == "subj" else relation_model.obj_model_type()
        )

        relation_qs = relation_model.objects.all()
        own_filter = node.get("own_filter")
        if own_filter is not None:
            relation_field_map = get_filterable_field_map(relation_model)
            relation_qs = relation_qs.filter(_node_q(own_filter, relation_model, relation_field_map))
        target_pks = _filtered_pks(target_model, target_filter)
        if target_pks is not None:
            relation_qs = relation_qs.filter(**{f"{direction}_object_id__in": target_pks})

        q = Q(pk__in=relation_qs.values(f"{current_side}_object_id"))

    if node.get("negate"):
        q = ~q
    return q


def _node_q(node, model, field_map):
    node_type = node.get("type")
    if node_type == "group":
        return _group_q(node, model, field_map)
    if node_type == "relation":
        return _relation_q(node, model)
    return _condition_q(node, field_map)


def build_queryset(model, tree: dict) -> QuerySet:
    validate_node(tree)
    field_map = get_filterable_field_map(model)
    try:
        q = _node_q(tree, model, field_map)
    except (TypeError, ValueError) as exc:
        if isinstance(exc, QueryCompileError):
            raise
        raise QueryCompileError(f"Could not apply filter: {exc}") from exc
    return model.objects.filter(q).distinct()
