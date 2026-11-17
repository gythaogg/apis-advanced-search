"""
Render a query tree as the Django ORM code that compiler.build_queryset runs.

This is for the developer debug panel only. It mirrors compiler.py branch by
branch: each function here produces the same filter arguments the compiler
passes to Django, but as text. It never touches the database.

If the compiler changes, change this module too. The tests in
apis_advanced_search/tests/test_describe.py compare the two on sample trees.
"""

from django.conf import settings

from apis_advanced_search.querybuilder.compiler import (
    QueryCompileError,
    _lookup_option,
    _resolve_relation_model,
    condition_path,
)
from apis_advanced_search.querybuilder.introspection import get_filterable_field_map
from apis_advanced_search.querybuilder.relations import is_relation_model
from apis_advanced_search.querybuilder.tree import validate_node


def debug_enabled() -> bool:
    """The debug panel and its endpoint are on unless explicitly turned off."""
    return bool(getattr(settings, "APIS_ADVANCED_SEARCH_DEBUG", True))


LINE_WIDTH = 80


def _indent(text: str) -> str:
    return "\n".join(f"    {line}" for line in text.splitlines())


def _wrap(prefix: str, inner: str, force: bool = False) -> str:
    """`prefix(inner)`. The inner text goes on indented lines of its own when
    it's multi-line, too long for one line, or `force` is set."""
    if force or "\n" in inner or len(prefix) + len(inner) > LINE_WIDTH:
        return f"{prefix}(\n{_indent(inner)}\n)"
    return f"{prefix}({inner})"


def _call(name: str, arg: str) -> str:
    """`name(arg)`. A nested query call always goes on its own lines, so the
    structure of the query can be read down the page."""
    return _wrap(name, arg, force="(" in arg)


def _join(children: list[str], joiner: str) -> str:
    """Children joined by AND/OR. Each operator starts its own line when the
    join is long or any child spans lines."""
    if len(children) == 1:
        return children[0]
    one_line = joiner.join(children)
    if any("\n" in child for child in children) or len(one_line) > LINE_WIDTH:
        lines = [children[0]] + [f"{joiner.strip()} {child}" for child in children[1:]]
        body = "\n".join(lines)
        return f"(\n{_indent(body)}\n)"
    return f"({one_line})"


def _chain(base: str, calls: list[tuple[str, str]]) -> str:
    text = base
    for method, arg in calls:
        text += "." + _call(method, arg)
    return text


def _condition(node: dict, field_map: dict) -> str:
    field_name = node["field"]
    field_info = field_map.get(field_name)
    if field_info is None:
        raise QueryCompileError(
            f"'{field_name}' is not a filterable field on this model"
        )
    option = _lookup_option(field_info, node["lookup"])
    if option is None:
        raise QueryCompileError(
            f"Lookup {node['lookup']!r} is not valid for field {field_name!r}"
        )

    path = condition_path(field_name, field_info, node, option)

    if option["lookup"] is None:  # "empty" / "not_empty"
        text = _call("Q", f"{path}__isnull=True")
        if field_info.type == "text":
            empty_text = _call("Q", f"{path}__exact={''!r}")
            text = _join([text, empty_text], " | ")
    else:
        django_lookup = option["lookup"]
        raw_value = node.get("value")
        if option["multi"] and isinstance(raw_value, list):
            values = [v for v in raw_value if v not in (None, "")]
            if not values:
                raise QueryCompileError(f"'{field_name}' needs at least one value")
            if django_lookup == "exact":
                text = _call("Q", f"{path}__in={values!r}")
            else:
                parts = [
                    _call("Q", f"{path}__{django_lookup}={v!r}") for v in values
                ]
                text = _join(parts, " | ")
        else:
            value = raw_value[0] if isinstance(raw_value, list) else raw_value
            text = _call("Q", f"{path}__{django_lookup}={value!r}")

    return _wrap("~", text) if option["negate"] else text


def _group(node: dict, model, field_map: dict) -> str:
    operator = node.get("operator", "AND")
    children = [_node(child, model, field_map) for child in node.get("children", [])]
    if not children:
        text = "Q()"
    else:
        text = _join(children, " & " if operator == "AND" else " | ")
    return _wrap("~", text) if node.get("negate") else text


def _target_pks(model, filter_tree: dict | None) -> str | None:
    """Mirrors compiler._filtered_pks. None means "no filter", so any target counts."""
    if filter_tree is None:
        return None
    inner = _node(filter_tree, model, get_filterable_field_map(model))
    return _chain(
        f"{model._meta.object_name}.objects", [("filter", inner), ("values", '"pk"')]
    )


def _relation(node: dict, model) -> str:
    direction = node.get("direction")
    if direction not in ("subj", "obj"):
        raise QueryCompileError(f"Invalid relation direction: {direction!r}")
    relation_label = node.get("relation_model")
    target_filter = node.get("target_filter")

    if relation_label is None:
        # Direct mode: `model` is the relation itself, filtered on its own slot.
        if not is_relation_model(model):
            raise QueryCompileError(
                "A relation node without 'relation_model' can only be used "
                "when the current model is itself a Relation"
            )
        target_model = (
            model.subj_model_type() if direction == "subj" else model.obj_model_type()
        )
        pks = _target_pks(target_model, target_filter)
        if pks is None:
            text = _call("Q", f"{direction}_object_id__isnull=False")
        else:
            text = _call("Q", f"{direction}_object_id__in={pks}")
    else:
        # Traverse mode: `model` is reached through the relation.
        relation_model = _resolve_relation_model(relation_label)
        current_side = "subj" if direction == "obj" else "obj"
        target_model = (
            relation_model.subj_model_type()
            if direction == "subj"
            else relation_model.obj_model_type()
        )

        calls: list[tuple[str, str]] = []
        own_filter = node.get("own_filter")
        if own_filter is not None:
            own_inner = _node(
                own_filter, relation_model, get_filterable_field_map(relation_model)
            )
            calls.append(("filter", own_inner))
        pks = _target_pks(target_model, target_filter)
        if pks is not None:
            calls.append(("filter", f"{direction}_object_id__in={pks}"))
        calls.append(("values", f'"{current_side}_object_id"'))

        relation_qs = _chain(f"{relation_model._meta.object_name}.objects", calls)
        text = _call("Q", f"pk__in={relation_qs}")

    return _wrap("~", text) if node.get("negate") else text


def _node(node: dict, model, field_map: dict) -> str:
    node_type = node.get("type")
    if node_type == "group":
        return _group(node, model, field_map)
    if node_type == "relation":
        return _relation(node, model)
    return _condition(node, field_map)


def describe_tree(model, tree: dict) -> str:
    """The ORM expression that build_queryset(model, tree) runs, as text."""
    validate_node(tree)
    body = _node(tree, model, get_filterable_field_map(model))
    return _chain(
        f"{model._meta.object_name}.objects", [("filter", body), ("distinct", "")]
    )
