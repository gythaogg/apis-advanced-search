"""
Relation columns: the related entities reached through a relation from the
queried model, and fields of those entities.

Each relation the model takes part in is a "group". A group offers one
column for the related object itself (its text), plus one column per native
field of the related model. Relation values are loaded for one page at a
time, with two queries per shown relation (the links, then the targets),
however many rows there are.

Column names (these are what the setting and the browser use):

- from an entity: "<app_label>.<relation_model>:<direction>" for the object,
  and "<app_label>.<relation_model>:<direction>.<field>" for one of its
  fields. `direction` names the slot the related object sits in ("subj" or
  "obj"), the same meaning as in the relation filter.
- from a Relation model: "subj" / "obj" for the subject or object, and
  "subj.<field>" / "obj.<field>" for one of their fields.

Design: local/docs/decisions/0004-m03-result-columns.md
"""

import dataclasses

from django.contrib.contenttypes.models import ContentType

from apis_advanced_search.querybuilder.columns import (
    NATIVE_TYPES,
    RELATION_TYPE,
    ColumnInfo,
    format_value,
    join_preview,
    own_columns,
)
from apis_advanced_search.querybuilder.registry import resolve_model
from apis_advanced_search.querybuilder.relations import relation_options


@dataclasses.dataclass
class RelationGroup:
    key: str
    label: str  # the relation's verb ("lived in") or "the subject"/"the object"
    direction: str  # slot the related object sits in: "subj" or "obj"
    relation_model: type | None  # None when the queried model is itself a Relation
    target_model: type
    fields: list[ColumnInfo]

    @property
    def title(self) -> str:
        return f"{self.label}: {self.target_model._meta.verbose_name}"


def split_column_name(name: str) -> tuple[str, str | None]:
    """(group key, field name or None) for a relation column name. For
    columns that aren't relation columns, the key is the whole name."""
    if ":" in name:
        head, _sep, tail = name.partition(":")
        direction, _sep, field = tail.partition(".")
        return f"{head}:{direction}", field or None
    key, _sep, field = name.partition(".")
    return key, field or None


def relation_groups(model, viewable=lambda m: True) -> list[RelationGroup]:
    """Every relation group the model offers, leaving out any relation or
    related model the user may not view."""
    groups = []
    for option in relation_options(model):
        target_model = resolve_model(*option["target_model"].split("."))
        if target_model is None or not viewable(target_model):
            continue
        relation_model = None
        key = option["direction"]
        if option["relation_model"] is not None:
            relation_model = resolve_model(*option["relation_model"].split("."))
            if relation_model is None or not viewable(relation_model):
                continue
            key = f"{option['relation_model']}:{option['direction']}"
        fields = [
            column
            for column in own_columns(target_model)
            if column.type in NATIVE_TYPES
        ]
        groups.append(
            RelationGroup(
                key=key,
                label=option["label"],
                direction=option["direction"],
                relation_model=relation_model,
                target_model=target_model,
                fields=fields,
            )
        )
    return groups


def group_columns(group: RelationGroup) -> list[ColumnInfo]:
    columns = [
        ColumnInfo(
            name=group.key,
            label=group.title,
            type=RELATION_TYPE,
            group=group.key,
            group_title=group.title,
        )
    ]
    for field in group.fields:
        columns.append(
            ColumnInfo(
                name=f"{group.key}.{field.name}",
                label=f"{group.title} · {field.label}",
                type=field.type,
                group=group.key,
                group_title=group.title,
            )
        )
    return columns


def all_columns(model, viewable=lambda m: True) -> dict[str, ColumnInfo]:
    """Every column the model can show: its own fields, then relation columns."""
    columns = {column.name: column for column in own_columns(model)}
    for group in relation_groups(model, viewable):
        for column in group_columns(group):
            columns[column.name] = column
    return columns


def _links_from_entity(model, group, objects):
    """(subject pk, related object pk) pairs for an entity's relation group."""
    current = "subj" if group.direction == "obj" else "obj"
    root_ct = ContentType.objects.get_for_model(model)
    target_ct = ContentType.objects.get_for_model(group.target_model)
    links = group.relation_model.objects.filter(
        **{
            f"{current}_content_type": root_ct,
            f"{current}_object_id__in": [obj.pk for obj in objects],
            f"{group.direction}_content_type": target_ct,
        }
    )
    return list(links.values_list(f"{current}_object_id", f"{group.direction}_object_id"))


def load_group_matches(model, group: RelationGroup, objects) -> dict:
    """For each object of the page, the related objects it has in this group,
    in the related model's own default ordering, with duplicates removed.
    Keyed by the object's pk; objects with no matches are left out."""
    if not objects:
        return {}

    if group.relation_model is None:
        # The queried model is a Relation: each row has exactly one subject
        # or object, held in a plain id column.
        slot = f"{group.direction}_object_id"
        wanted = {obj.pk: getattr(obj, slot) for obj in objects}
        targets = {
            target.pk: target
            for target in group.target_model.objects.filter(
                pk__in={v for v in wanted.values() if v is not None}
            )
        }
        return {
            pk: [targets[target_pk]]
            for pk, target_pk in wanted.items()
            if target_pk in targets
        }

    links = _links_from_entity(model, group, objects)
    target_pks = {target_pk for _subject, target_pk in links}
    # Ordered by the related model's own Meta.ordering, so a cell lists the
    # objects in the same order the related model's lists show them.
    ordered = list(group.target_model.objects.filter(pk__in=target_pks))
    by_pk = {target.pk: target for target in ordered}
    position = {target.pk: index for index, target in enumerate(ordered)}

    matches: dict = {}
    seen: set = set()
    for subject_pk, target_pk in links:
        if target_pk not in by_pk or (subject_pk, target_pk) in seen:
            continue
        seen.add((subject_pk, target_pk))
        matches.setdefault(subject_pk, []).append(by_pk[target_pk])
    for targets in matches.values():
        targets.sort(key=lambda target: position[target.pk])
    return matches


def _cell_texts(column: ColumnInfo, targets) -> list[str]:
    """The text each matched object contributes to a cell: its own text for
    the object column, or just its value for a field column. Empty values
    are left out rather than shown as blanks."""
    _key, field = split_column_name(column.name)
    if field is None:
        return [str(target) for target in targets]
    values = [format_value(getattr(target, field), column.type) for target in targets]
    return [value for value in values if value]


def relation_values(model, objects, columns: list[ColumnInfo], groups: dict) -> dict:
    """Display values for the relation columns among `columns`, for each object
    of the page: {object pk: {column name: text}}. Every requested relation
    column has an entry for every object, empty where there is no match."""
    relation_columns = [column for column in columns if column.group is not None]
    values = {obj.pk: {column.name: "" for column in relation_columns} for obj in objects}
    if not relation_columns:
        return values

    by_group: dict[str, list[ColumnInfo]] = {}
    for column in relation_columns:
        by_group.setdefault(column.group, []).append(column)

    for key, group_cols in by_group.items():
        matches = load_group_matches(model, groups[key], objects)
        for subject_pk, targets in matches.items():
            for column in group_cols:
                values[subject_pk][column.name] = join_preview(_cell_texts(column, targets))
    return values
