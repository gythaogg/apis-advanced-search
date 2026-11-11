"""
Relation-traversal options.

Relation.subj/obj are GenericForeignKeys with no GenericRelation declared
back on Entity, so there is no Django-native reverse accessor to traverse
(e.g. no `person.personlivedinplace_set`). The compiler (see compiler.py)
builds an explicit correlated subquery instead. This module only answers
"what relation traversals can be offered from this model, and what should
each be called" - it does not touch the ORM.

Two shapes, both represented the same way to the frontend/tree:

- From an Entity (or any non-Relation model): enumerate the registered
  Relation subclasses that have this model as their subj or obj type
  (apis_core.relations.utils.relation_content_types already does exactly
  this lookup). A self-referential relation (subj_model == obj_model)
  yields two distinct options, one per direction.
- From a Relation model itself: there is nothing to enumerate - every
  relation has exactly one fixed subject and one fixed object slot, so
  the two options are always just "the subject" / "the object".

In both cases `direction` means the same thing: which GFK slot (subj or
obj) the *target* side sits in - not which slot the current model sits
in. For the entity case that's necessarily "whichever slot isn't the
current model's slot"; for the relation case it's a direct choice.
"""

from apis_core.relations.models import Relation
from apis_core.relations.utils import relation_content_types


def is_relation_model(model) -> bool:
    return issubclass(model, Relation)


def _model_label(model) -> str:
    return f"{model._meta.app_label}.{model._meta.model_name}"


def relation_options(model) -> list[dict]:
    if is_relation_model(model):
        subj_model = model.subj_model_type()
        obj_model = model.obj_model_type()
        return [
            {
                "relation_model": None,
                "direction": "subj",
                "label": "the subject",
                "target_model": _model_label(subj_model),
                "target_verbose_name": str(subj_model._meta.verbose_name),
            },
            {
                "relation_model": None,
                "direction": "obj",
                "label": "the object",
                "target_model": _model_label(obj_model),
                "target_verbose_name": str(obj_model._meta.verbose_name),
            },
        ]

    options = []
    for content_type in relation_content_types(any_model=model):
        relation_model = content_type.model_class()
        subj_model = relation_model.subj_model_type()
        obj_model = relation_model.obj_model_type()
        relation_label = _model_label(relation_model)

        if subj_model is model:
            options.append(
                {
                    "relation_model": relation_label,
                    "direction": "obj",
                    "label": str(relation_model.name()),
                    "target_model": _model_label(obj_model),
                    "target_verbose_name": str(obj_model._meta.verbose_name),
                }
            )
        if obj_model is model:
            options.append(
                {
                    "relation_model": relation_label,
                    "direction": "subj",
                    "label": str(relation_model.reverse_name()),
                    "target_model": _model_label(subj_model),
                    "target_verbose_name": str(subj_model._meta.verbose_name),
                }
            )
    return options
