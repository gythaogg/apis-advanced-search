"""
Search every string value of a JSON field, at any depth, without naming a key.

Django has no lookup for "any value in the JSON", and a text lookup on the
whole field also matches the key names. So this adds one lookup,
`values_icontains`, to JSONField. It is PostgreSQL-only: it walks the
document with jsonb_path_query. Other databases get a clear error rather
than a SQL failure (the compiler checks first, see compiler.py).

Only string values are searched. Numbers and booleans are not converted to
text, so "2024" does not match a number 2024 here.

Registered in apps.py. Design: local/docs/decisions/0007-json-field-search.md
"""

from django.db import NotSupportedError
from django.db.models import Lookup
from django.db.models.fields.json import JSONField

VALUE_LOOKUP = "values_icontains"


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class JSONValuesIContains(Lookup):
    lookup_name = VALUE_LOOKUP
    # The right-hand side is plain text to search for, not a JSON value, so
    # it must not be encoded as JSON the way the field would encode it.
    prepare_rhs = False

    def as_sql(self, compiler, connection):
        if connection.vendor != "postgresql":
            raise NotSupportedError("Searching all values of a JSON field needs PostgreSQL.")
        lhs_sql, lhs_params = compiler.compile(self.lhs)
        pattern = "%" + _escape_like(str(self.rhs)) + "%"
        # '$.**' visits every node of the document. Only string nodes are
        # kept, and #>> '{}' turns a JSON string into its plain text.
        sql = (
            "EXISTS (SELECT 1 FROM jsonb_path_query("
            + lhs_sql
            + ", 'strict $.**') AS v WHERE jsonb_typeof(v) = 'string'"
            + " AND (v #>> '{}') ILIKE %s)"
        )
        return sql, [*lhs_params, pattern]


def register():
    JSONField.register_lookup(JSONValuesIContains)
