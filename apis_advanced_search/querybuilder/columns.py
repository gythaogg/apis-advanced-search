"""
Result-table columns for a model: which of its own fields can be shown and
sorted, what each model shows by default, and how values are rendered.

"Own" fields are the queried model's own fields: native values (text, number,
date, boolean), its foreign keys, and its many-to-many fields. Relation
columns - the entities reached through a relation - come in a later phase
(see local/docs/decisions/0004-m03-result-columns.md).

Foreign-key and many-to-many values are only loaded for columns that are
actually shown, so the cost of the table follows what the user chose.
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

NATIVE_TYPES = {"text", "number", "date", "datetime", "boolean"}
FK_TYPE = "fk"
M2M_TYPE = "m2m"
COLUMN_TYPES = NATIVE_TYPES | {FK_TYPE, M2M_TYPE}
# Foreign-key and many-to-many values are loaded per page, so only the
# shown ones are fetched - see requested_columns() below.
LOADED_ON_DEMAND_TYPES = {FK_TYPE, M2M_TYPE}

# Long text fields are cut short in the table; the full value is on the
# detail page, which the label column links to.
TEXT_PREVIEW_CHARS = 200
# A many-to-many cell lists this many related objects, then says how many
# more there are. Same cap as the relation columns, for consistency.
MULTI_VALUE_PREVIEW = 3


@dataclasses.dataclass
class ColumnInfo:
    name: str
    label: str
    type: str

    @property
    def sortable(self) -> bool:
        # Many-to-many can't be sorted on: a row with several values would
        # have to repeat, which breaks both sorting and the page counts.
        return self.type != M2M_TYPE

    @property
    def on_demand(self) -> bool:
        return self.type in LOADED_ON_DEMAND_TYPES

    def to_dict(self):
        return {
            "name": self.name,
            "label": self.label,
            "type": self.type,
            "sortable": self.sortable,
            "on_demand": self.on_demand,
        }


def own_columns(model) -> list[ColumnInfo]:
    """The model's own fields that can be shown as columns, in declaration
    order. The primary key is left out: the label column already links to
    the object. The primary key is still used as the final sort key."""
    columns = []
    for field in list(model._meta.fields) + list(model._meta.many_to_many):
        if field.primary_key:
            continue
        # One-to-one parent links (multi-table inheritance) are structure,
        # not a value a user would look at.
        remote_field = getattr(field, "remote_field", None)
        if remote_field is not None and getattr(remote_field, "parent_link", False):
            continue
        # A Relation's generic subject/object plumbing is shown through the
        # relation columns of a later phase, not as raw foreign keys.
        if issubclass(model, Relation) and field.name in RELATION_GENERIC_FK_FIELDS:
            continue
        field_type = classify_field(field)
        if field_type not in COLUMN_TYPES:
            continue
        columns.append(ColumnInfo(field.name, str(field.verbose_name), field_type))
    return columns


def own_column_map(model) -> dict[str, ColumnInfo]:
    return {column.name: column for column in own_columns(model)}


def configured_columns() -> dict:
    """The APIS_ADVANCED_SEARCH_COLUMNS setting, keyed by "app_label.model".
    Validated by checks.py, so here it is only read."""
    return getattr(settings, "APIS_ADVANCED_SEARCH_COLUMNS", None) or {}


def default_column_names(model) -> list[str]:
    """The developer's configured default columns for this model, in the
    configured order. Anything that isn't an own column of the model is
    dropped here (checks.py already warns about it at startup). A model with
    no entry gets no default columns, so only the label column shows."""
    label = f"{model._meta.app_label}.{model._meta.model_name}"
    names = configured_columns().get(label, [])
    available = own_column_map(model)
    return [name for name in names if name in available]


def requested_columns(model, names) -> list[ColumnInfo]:
    """The own columns to load values for: all native values (already on the
    row, so they cost nothing), plus the foreign-key and many-to-many columns
    the browser asked for. Raises ValueError for names the model doesn't have."""
    available = own_column_map(model)
    wanted = set(names or [])
    unknown = wanted - set(available)
    if unknown:
        raise ValueError(f"Unknown column(s): {', '.join(sorted(unknown))}.")
    return [
        column
        for column in available.values()
        if not column.on_demand or column.name in wanted
    ]


def load_relations(queryset, columns: list[ColumnInfo]):
    """Fetch the foreign-key and many-to-many values the shown columns need,
    in a fixed number of queries per page rather than one per row."""
    fks = [c.name for c in columns if c.type == FK_TYPE]
    m2ms = [c.name for c in columns if c.type == M2M_TYPE]
    if fks:
        queryset = queryset.select_related(*fks)
    if m2ms:
        queryset = queryset.prefetch_related(*m2ms)
    return queryset


def format_value(value, column_type):
    if value is None or value == "":
        return ""
    if column_type == "boolean":
        return _("Yes") if value else _("No")
    text = localize(value)
    if column_type == "text" and len(text) > TEXT_PREVIEW_CHARS:
        text = text[:TEXT_PREVIEW_CHARS].rstrip() + "…"
    return text


def _format_many(objects):
    texts = [str(obj) for obj in objects]
    if not texts:
        return ""
    shown = ", ".join(texts[:MULTI_VALUE_PREVIEW])
    extra = len(texts) - MULTI_VALUE_PREVIEW
    if extra > 0:
        shown += f" and {extra} more"
    return shown


def row_values(obj, columns: list[ColumnInfo]) -> dict[str, str]:
    values = {}
    for column in columns:
        attr = getattr(obj, column.name)
        if column.type == FK_TYPE:
            values[column.name] = str(attr) if attr is not None else ""
        elif column.type == M2M_TYPE:
            values[column.name] = _format_many(attr.all())
        else:
            values[column.name] = format_value(attr, column.type)
    return values


def _ordering_for(column: ColumnInfo, model, direction):
    """Sort keys for a column. A foreign key is sorted the way the related
    model is listed (its Meta.ordering), not by the raw id, which would give
    an order nobody reads. Nulls go last whichever direction is chosen."""
    if column.type == FK_TYPE:
        target = model._meta.get_field(column.name).related_model
        keys = []
        for entry in target._meta.ordering:
            descending = entry.startswith("-")
            path = f"{column.name}__{entry.lstrip('-')}"
            keys.append(_direction(F(path), descending != (direction == "desc")))
        if keys:
            return keys
    return [_direction(F(column.name), direction == "desc")]


def _direction(expression, descending):
    return expression.desc(nulls_last=True) if descending else expression.asc(nulls_last=True)


def apply_ordering(queryset, sort: dict | None, columns: dict[str, ColumnInfo] | None = None):
    """Order by the requested own column if there is one, otherwise by the
    model's own Meta.ordering. The primary key is always the last key, so
    rows with equal sort values keep a stable order across pages."""
    keys = []
    if sort:
        column = (columns or own_column_map(queryset.model))[sort["field"]]
        keys.extend(_ordering_for(column, queryset.model, sort["direction"]))
    else:
        keys.extend(queryset.model._meta.ordering)
    keys.append("pk")
    return queryset.order_by(*keys)
