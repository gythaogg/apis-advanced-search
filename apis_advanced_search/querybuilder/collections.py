"""
Bulk-add compiled query results to an apis_core SKOS collection.

`apis_core.collections.SkosCollection` only supports adding one object at a
time (`SkosCollection.add()`, a `get_or_create` per call) - looping that over
an entire query result set doesn't scale. This isolates a bulk variant in one
place, so that once apis_core (whose maintainers we're one of) grows an
equivalent upstream, this module can be swapped for a thin call into it
without touching its call sites.
"""

from django.conf import settings
from django.contrib.contenttypes.models import ContentType

# `apis_core.collections` is an optional app (apis-core-rdf instances can
# remove it, same as this project's own sample_project removes
# apis_core.search) - importing its models when it isn't installed raises a
# RuntimeError from Django's model registration, not a clean ImportError, so
# this is checked and the import skipped up front rather than guarded with
# try/except.
COLLECTIONS_AVAILABLE = "apis_core.collections" in settings.INSTALLED_APPS

if COLLECTIONS_AVAILABLE:
    from apis_core.collections.models import SkosCollectionContentObject


def bulk_add_to_collection(collection, model, pks) -> int:
    """Add every object of `model` whose pk is in `pks` to `collection`.
    Returns how many new memberships were created - pks already in the
    collection are left alone, not counted again."""
    pks = list(pks)
    content_type = ContentType.objects.get_for_model(model)
    existing = set(
        SkosCollectionContentObject.objects.filter(
            collection=collection, content_type=content_type, object_id__in=pks
        ).values_list("object_id", flat=True)
    )
    to_create = [
        SkosCollectionContentObject(collection=collection, content_type=content_type, object_id=pk)
        for pk in pks
        if pk not in existing
    ]
    SkosCollectionContentObject.objects.bulk_create(to_create)
    return len(to_create)
