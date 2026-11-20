"""
The query tree is a plain JSON-friendly structure:

A condition node:
    {"type": "condition", "field": "surname", "lookup": "icontains",
     "value": "Smith"}
    {"type": "condition", "field": "surname", "lookup": "icontains",
     "value": ["Smith", "Smyth"]}
    {"type": "condition", "field": "details", "key": "address.city",
     "lookup": "icontains", "value": "Graz"}

"key" is only used for JSON fields: the dotted path to the value to search
within (see compiler.py, json_key_path).

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
     "direction": "obj", "min_count": 1, "max_count": null,
     "own_filter": group-or-null, "target_filter": group-or-null}

"min_count" and "max_count" bound how many matching relation rows the
current entity must have (see relation_count_bounds). "max_count": 0 is
"does not have". Older trees may carry "negate" instead; it is read as
the equivalent count bounds. See local/docs/decisions/0009.

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


def relation_count_bounds(node) -> tuple[int, int | None]:
    """The (min, max) matching relation rows a relation node requires.

    max is None for no upper bound. Legacy trees with "negate" (no count
    keys) map to the equivalent bounds: negated is (0, 0), otherwise (1, None).
    """
    if "min_count" not in node and "max_count" not in node:
        return (0, 0) if node.get("negate") else (1, None)

    low = node.get("min_count", 0)
    high = node.get("max_count")
    if isinstance(low, bool) or not isinstance(low, int) or low < 0:
        raise QueryTreeError("A relation's minimum count must be a whole number, 0 or more")
    if high is not None:
        if isinstance(high, bool) or not isinstance(high, int) or high < 0:
            raise QueryTreeError("A relation's maximum count must be a whole number, 0 or more")
        if high < low:
            raise QueryTreeError("A relation's maximum count is below its minimum count")
    if low == 0 and high is None:
        raise QueryTreeError("A relation filter needs a minimum count or a maximum count")
    return low, high


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
        key = node.get("key")
        if key is not None and not isinstance(key, str):
            raise QueryTreeError("A condition's 'key' must be text")
    elif node_type == "relation":
        if _relation_depth >= MAX_RELATION_DEPTH:
            raise QueryTreeError("Relation traversal is nested too deeply")
        if node.get("direction") not in ("subj", "obj"):
            raise QueryTreeError(f"Invalid relation direction: {node.get('direction')!r}")
        bounds = relation_count_bounds(node)
        if node.get("relation_model") is None and bounds not in ((1, None), (0, 0)):
            raise QueryTreeError(
                "A relation's own slot can only be has or does not have"
            )
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
