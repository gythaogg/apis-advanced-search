"""
Discovery of the models the query builder can start a query from.

Registration is implicit: any model that subclasses Entity or Relation
and is installed in INSTALLED_APPS is automatically discoverable. The
actual discovery is delegated to apis_core's own helpers, which already
get this right (in particular, excluding the base Relation model itself,
which is a concrete model of its own for untyped relations, not a
queryable "type" the way its subclasses are) - this module adds the
sorting, combined entity+relation lookup, and app_label/model_name
resolution that apis_core's helpers don't provide on their own.
"""

from apis_core.entities.abc import Entity
from apis_core.entities.templatetags.entities import get_entitymodels
from apis_core.relations.templatetags.relations import get_relationmodels


def get_entity_models():
    return sorted(get_entitymodels(), key=lambda m: str(m._meta.verbose_name).lower())


def get_relation_models():
    return sorted(get_relationmodels(), key=lambda m: str(m._meta.verbose_name).lower())


def get_queryable_models():
    return get_entity_models() + get_relation_models()


def model_kind(model):
    return "entity" if issubclass(model, Entity) else "relation"


def resolve_model(app_label, model_name):
    """Return the model class for app_label/model_name if it is a registered
    queryable (Entity or Relation) model, else None."""
    for model in get_queryable_models():
        if model._meta.app_label == app_label and model._meta.model_name == model_name.lower():
            return model
    return None
