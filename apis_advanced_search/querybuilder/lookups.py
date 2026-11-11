"""
The lookups offered per field type.

Each entry is a dict:
    value  - the identifier stored in a condition's "lookup" key
    label  - the human-readable phrase shown in the UI
    lookup - the actual Django field lookup to compile with (None for the
             synthetic "empty" / "not_empty" checks)
    negate - whether choosing this phrase wraps the resulting Q in NOT
    multi  - whether this phrase accepts more than one value, compiled as
             an OR across the given values for that one field

Negation is fused into the phrasing ("contains" / "does not contain")
rather than exposed as a separate control, so a condition reads as one
plain-English choice instead of a lookup plus a NOT flag the user has to
compose themselves.

Ordering comparisons (gt/gte/lt/lte) are deliberately single-value only:
"less than 160 or less than 150" is a redundant, confusing thing to be
able to build - it always collapses to the less restrictive bound. A
real range ("between 30 and 40") is already expressible as two ordinary
AND'd conditions on the same field, so no dedicated range lookup is
needed. The same trick covers "has all of" for multi-valued relations
(two AND'd single-value "includes" conditions), so there's no separate
all-of lookup either.
"""


def _opt(value, label, lookup, negate=False, multi=True):
    return {"value": value, "label": label, "lookup": lookup, "negate": negate, "multi": multi}


TEXT_LOOKUPS = [
    # "contains" first and default - an exact match is rarely what's
    # wanted on messy historical text data (spelling variants, titles,
    # partial names), so substring search leads rather than equality.
    _opt("icontains", "contains", "icontains"),
    _opt("not_icontains", "does not contain", "icontains", negate=True),
    _opt("exact", "is", "exact"),
    _opt("not_exact", "is not", "exact", negate=True),
    _opt("istartswith", "starts with", "istartswith"),
    _opt("not_istartswith", "does not start with", "istartswith", negate=True),
    _opt("iendswith", "ends with", "iendswith"),
    _opt("not_iendswith", "does not end with", "iendswith", negate=True),
    _opt("empty", "is empty", None, multi=False),
    _opt("not_empty", "is not empty", None, negate=True, multi=False),
]

NUMBER_LOOKUPS = [
    _opt("exact", "is", "exact"),
    _opt("not_exact", "is not", "exact", negate=True),
    _opt("gt", ">", "gt", multi=False),
    _opt("gte", ">=", "gte", multi=False),
    _opt("lt", "<", "lt", multi=False),
    _opt("lte", "<=", "lte", multi=False),
    _opt("empty", "is empty", None, multi=False),
    _opt("not_empty", "is not empty", None, negate=True, multi=False),
]

DATE_LOOKUPS = [
    _opt("exact", "on", "exact"),
    _opt("not_exact", "not on", "exact", negate=True),
    _opt("gt", "after", "gt", multi=False),
    _opt("gte", "on or after", "gte", multi=False),
    _opt("lt", "before", "lt", multi=False),
    _opt("lte", "on or before", "lte", multi=False),
    _opt("empty", "is empty", None, multi=False),
    _opt("not_empty", "is not empty", None, negate=True, multi=False),
]

BOOLEAN_LOOKUPS = [
    # A single Yes/No pick already says everything there is to say about a
    # boolean - "is" is the only meaningful lookup, and multiple values
    # ("is True or False") would match everything, so it stays single-value.
    _opt("exact", "is", "exact", multi=False),
    _opt("empty", "is empty", None, multi=False),
    _opt("not_empty", "is not empty", None, negate=True, multi=False),
]

FK_LOOKUPS = [
    _opt("exact", "is", "exact"),
    _opt("not_exact", "is not", "exact", negate=True),
    _opt("empty", "is empty", None, multi=False),
    _opt("not_empty", "is not empty", None, negate=True, multi=False),
]

M2M_LOOKUPS = [
    _opt("exact", "includes", "exact"),
    _opt("not_exact", "excludes", "exact", negate=True),
    _opt("empty", "is empty", None, multi=False),
    _opt("not_empty", "is not empty", None, negate=True, multi=False),
]

LOOKUPS_BY_TYPE = {
    "text": TEXT_LOOKUPS,
    "number": NUMBER_LOOKUPS,
    "date": DATE_LOOKUPS,
    "datetime": DATE_LOOKUPS,
    "boolean": BOOLEAN_LOOKUPS,
    "fk": FK_LOOKUPS,
    "m2m": M2M_LOOKUPS,
}
