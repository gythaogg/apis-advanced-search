"""
The query tree is a plain JSON-friendly structure:

A condition node:
    {"type": "condition", "field": "surname", "lookup": "icontains",
     "value": "Smith"}
    {"type": "condition", "field": "surname", "lookup": "icontains",
     "value": ["Smith", "Smyth"]}

"lookup" is one of the per-field-type options from lookups.py. Negation
is fused into the lookup itself (e.g. "not_icontains" = "does not
contain") rather than a separate flag, so a condition always reads as
one plain-English phrase. "value" may be a list for lookups that accept
more than one value (compiled as an OR across them for that field) -
see lookups.py for which ones do.

A group node:
    {"type": "group", "operator": "AND" | "OR", "negate": false,
     "children": [condition-or-group, ...]}

"negate" is optional on a group and defaults to False - unlike a
condition, a group has no single lookup to fuse it into, so it stays an
explicit "exclude this group" flag.
"""


class QueryTreeError(ValueError):
    pass


def validate_node(node, _depth=0):
    if _depth > 25:
        raise QueryTreeError("Query is nested too deeply")
    if not isinstance(node, dict):
        raise QueryTreeError("Each node of the query must be an object")

    node_type = node.get("type")
    if node_type == "group":
        operator = node.get("operator", "AND")
        if operator not in ("AND", "OR"):
            raise QueryTreeError(f"Invalid group operator: {operator!r}")
        children = node.get("children", [])
        if not isinstance(children, list):
            raise QueryTreeError("A group's children must be a list")
        for child in children:
            validate_node(child, _depth + 1)
    elif node_type == "condition":
        if not node.get("field"):
            raise QueryTreeError("A condition is missing 'field'")
        if not node.get("lookup"):
            raise QueryTreeError("A condition is missing 'lookup'")
    else:
        raise QueryTreeError(f"Unknown query node type: {node_type!r}")


def empty_group():
    return {"type": "group", "operator": "AND", "negate": False, "children": []}
