"""
Introspect a registered model to find the fields the query builder can
filter on, and the lookups each of them supports.
"""

import dataclasses

from django.contrib.contenttypes.models import ContentType
from django.db.models import (
    BooleanField,
    CharField,
    DateField,
    DateTimeField,
    DecimalField,
    FloatField,
    IntegerField,
    TextField,
)
from django.db.models.fields.related import ForeignKey, ManyToManyField
from django.urls import reverse

from apis_core.relations.models import Relation

from apis_advanced_search.querybuilder.lookups import LOOKUPS_BY_TYPE

# These back the generic FK subj/obj pair on Relation models. Filtering on
# the raw content-type/object-id is not meaningful to end users - filtering
# the subject/object entities themselves is the relations filter (M02).
RELATION_GENERIC_FK_FIELDS = {
    "subj_content_type",
    "subj_object_id",
    "obj_content_type",
    "obj_object_id",
}


@dataclasses.dataclass
class FieldInfo:
    name: str
    label: str
    type: str
    lookups: list
    target_model: str | None = None
    autocomplete_url: str | None = None

    def to_dict(self):
        return {
            "name": self.name,
            "label": self.label,
            "type": self.type,
            # Only what the frontend needs to render a lookup option - the
            # actual Django lookup and whether it negates are compile-time
            # details that stay server-side.
            "lookups": [
                {"value": opt["value"], "label": opt["label"], "multi": opt["multi"]}
                for opt in self.lookups
            ],
            "target_model": self.target_model,
            "autocomplete_url": self.autocomplete_url,
        }


def classify_field(field) -> str | None:
    if isinstance(field, ManyToManyField):
        return "m2m"
    if isinstance(field, ForeignKey):
        return "fk"
    if isinstance(field, BooleanField):
        return "boolean"
    if isinstance(field, DateTimeField):
        return "datetime"
    if isinstance(field, DateField):
        return "date"
    if isinstance(field, (IntegerField, FloatField, DecimalField)):
        return "number"
    if isinstance(field, (CharField, TextField)):
        return "text"
    return None


def get_filterable_fields(model) -> list[FieldInfo]:
    infos = []
    pk_infos = []
    # _meta.fields + _meta.many_to_many (rather than the superset
    # _meta.get_fields()) already gives exactly this model's own concrete
    # fields plus its forward M2M fields, with no need to special-case
    # ManyToManyField.concrete being False - this is the same idiom
    # django-filter itself uses (django_filters.utils.get_all_model_fields).
    for field in list(model._meta.fields) + list(model._meta.many_to_many):
        # Multi-table-inheritance pointer fields (e.g. relation_ptr) are
        # structural, not a business field a user would filter on.
        remote_field = getattr(field, "remote_field", None)
        if remote_field is not None and getattr(remote_field, "parent_link", False):
            continue
        if issubclass(model, Relation) and field.name in RELATION_GENERIC_FK_FIELDS:
            continue
        field_type = classify_field(field)
        if field_type is None:
            continue

        info = FieldInfo(
            name=field.name,
            label=str(getattr(field, "verbose_name", field.name)),
            type=field_type,
            lookups=LOOKUPS_BY_TYPE[field_type],
        )
        if field_type in ("fk", "m2m"):
            target_ct = ContentType.objects.get_for_model(field.related_model)
            info.target_model = f"{target_ct.app_label}.{target_ct.model}"
            info.autocomplete_url = reverse("apis_core:generic:autocomplete", args=[target_ct])
        # The primary key is a technical identifier, not something a user
        # would reach for first - Django's own field order puts it first
        # regardless of model, so move it to the back rather than guessing
        # at an order for the rest of the fields.
        if getattr(field, "primary_key", False):
            pk_infos.append(info)
        else:
            infos.append(info)
    return infos + pk_infos


def get_filterable_field_map(model) -> dict[str, FieldInfo]:
    return {info.name: info for info in get_filterable_fields(model)}
