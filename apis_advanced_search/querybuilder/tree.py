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
     "children": [condition-or-group-or-relation, ...]}

"negate" is optional on a group and defaults to False - unlike a
condition, a group has no single lookup to fuse it into, so it stays an
explicit "exclude this group" flag.

A relation node:
    {"type": "relation", "relation_model": "sample_project.personlivedinplace",
     "direction": "obj", "negate": false,
     "own_filter": group-or-null, "target_filter": group-or-null}

"direction" always names which GFK slot (subj/obj) the *target* sits in,
regardless of mode:

- "relation_model" set: traversal from an entity, through that relation,
  to the entity on the other side. The current model necessarily sits in
  whichever slot "direction" does *not* name. "own_filter" filters the
  relation's own fields, "target_filter" filters the far entity (which
  may itself contain further relation nodes - this is how traversal
  nests). Both are optional.
- "relation_model" is null: the current model IS a Relation, and this
  filters its own fixed subject or object slot directly. "own_filter"
  isn't meaningful here (there's no separate relation to traverse into -
  you're already at it) and is ignored if present.

Relation nodes are depth-limited separately from (and more strictly
than) plain group nesting, since each one is a real correlated subquery
rather than just boolean logic.
"""


class QueryTreeError(ValueError):
    pass


MAX_GROUP_DEPTH = 25
MAX_RELATION_DEPTH = 4


def validate_node(node, _depth=0, _relation_depth=0):
    if _depth > MAX_GROUP_DEPTH:
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
            validate_node(child, _depth + 1, _relation_depth)
    elif node_type == "condition":
        if not node.get("field"):
            raise QueryTreeError("A condition is missing 'field'")
        if not node.get("lookup"):
            raise QueryTreeError("A condition is missing 'lookup'")
    elif node_type == "relation":
        if _relation_depth >= MAX_RELATION_DEPTH:
            raise QueryTreeError("Relation traversal is nested too deeply")
        if node.get("direction") not in ("subj", "obj"):
            raise QueryTreeError(f"Invalid relation direction: {node.get('direction')!r}")
        own_filter = node.get("own_filter")
        if own_filter is not None:
            validate_node(own_filter, _depth + 1, _relation_depth)
        target_filter = node.get("target_filter")
        if target_filter is not None:
            validate_node(target_filter, _depth + 1, _relation_depth + 1)
    else:
        raise QueryTreeError(f"Unknown query node type: {node_type!r}")


def empty_group():
    return {"type": "group", "operator": "AND", "negate": False, "children": []}
