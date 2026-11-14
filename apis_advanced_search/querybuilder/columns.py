"""
Result-table columns for a model: which of its own (native) fields can be
shown and sorted, what each model shows by default, and how values are
rendered for display.

Phase 1 covers the root model's native, non-relational fields only.
Foreign keys, many-to-many fields and relation columns come in later
phases (see local/docs/decisions/0004-m03-result-columns.md).
"""

import dataclasses

from apis_core.relations.models import Relation
from django.conf import settings
from django.db.models import F
from django.utils.formats import localize
from django.utils.translation import gettext as _

from apis_advanced_search.querybuilder.introspection import (
    RELATION_GENERIC_FK_FIELDS,
    classify_field,
)

NATIVE_COLUMN_TYPES = {"text", "number", "date", "datetime", "boolean"}

# Long text fields are cut short in the table; the full value is on the
# detail page, which the label column links to.
TEXT_PREVIEW_CHARS = 200


@dataclasses.dataclass
class ColumnInfo:
    name: str
    label: str
    type: str

    def to_dict(self):
        return {"name": self.name, "label": self.label, "type": self.type}


def native_columns(model) -> list[ColumnInfo]:
    """The model's own non-relational fields, in declaration order. Each one
    is both displayable and sortable. The primary key is left out: the label
    column already links to the object."""
    columns = []
    for field in model._meta.fields:
        if field.primary_key:
            continue
        # Foreign keys, one-to-one parent links etc. are relations, not
        # native values - they are handled in a later phase.
        if getattr(field, "remote_field", None) is not None:
            continue
        if issubclass(model, Relation) and field.name in RELATION_GENERIC_FK_FIELDS:
            continue
        field_type = classify_field(field)
        if field_type not in NATIVE_COLUMN_TYPES:
            continue
        columns.append(ColumnInfo(field.name, str(field.verbose_name), field_type))
    return columns


def native_column_map(model) -> dict[str, ColumnInfo]:
    return {column.name: column for column in native_columns(model)}


def configured_columns() -> dict:
    """The APIS_ADVANCED_SEARCH_COLUMNS setting, keyed by "app_label.model".
    Validated by checks.py, so here it is only read."""
    return getattr(settings, "APIS_ADVANCED_SEARCH_COLUMNS", None) or {}


def default_column_names(model) -> list[str]:
    """The developer's configured default columns for this model, in the
    configured order. Anything that isn't a native column of the model is
    dropped here (checks.py already warns about it at startup). A model with
    no entry gets no default columns, so only the label column shows."""
    label = f"{model._meta.app_label}.{model._meta.model_name}"
    names = configured_columns().get(label, [])
    available = native_column_map(model)
    return [name for name in names if name in available]


def format_value(value, column_type):
    if value is None or value == "":
        return ""
    if column_type == "boolean":
        return _("Yes") if value else _("No")
    text = localize(value)
    if column_type == "text" and len(text) > TEXT_PREVIEW_CHARS:
        text = text[:TEXT_PREVIEW_CHARS].rstrip() + "…"
    return text


def row_values(obj, columns: list[ColumnInfo]) -> dict[str, str]:
    return {column.name: format_value(getattr(obj, column.name), column.type) for column in columns}


def apply_ordering(queryset, sort: dict | None):
    """Order by the requested native field if there is one, otherwise by the
    model's own Meta.ordering. Primary key is always the last key, so rows
    with equal sort values keep a stable order across pages."""
    keys = []
    if sort:
        field = F(sort["field"])
        keys.append(field.desc(nulls_last=True) if sort["direction"] == "desc" else field.asc(nulls_last=True))
    else:
        keys.extend(queryset.model._meta.ordering)
    keys.append("pk")
    return queryset.order_by(*keys)
