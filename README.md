# APIS Advanced Search

A model-agnostic query builder/search interface for [APIS](https://github.com/acdh-oeaw/apis-core-rdf) instances.

## Installation

```bash
uv add apis-advanced-search
```

Add it to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    ...,
    "apis_advanced_search",
]
```

Include its URLs somewhere in your project's root `urls.py`:

```python
urlpatterns = [
    ...,
    path("advanced-search/", include("apis_advanced_search.urls")),
]
```

The URL prefix (`advanced-search/` above) is up to you. The app checks at startup that its URLs were included somewhere, and raises `ImproperlyConfigured` with a clear message if you forget this step.

In case of trouble, compare your APIS instance with the sample_project APIS instance included here.

## Settings
`APIS_ANON_VIEWS_ALLOWED` from `apis-core-rdf` is used to determine if the results can be shown to anonymous users.

`APIS_ADVANCED_SEARCH_COLUMNS` sets the columns shown by default in the results table, per model.

```python
APIS_ADVANCED_SEARCH_COLUMNS = {
    "sample_project.person": ["date_of_birth", "place_of_bairth", "sample_project.personlivedinplace:obj.label"],
    "sample_project.place": ["label", "sample_project.personlivedinplace:subj"],
    }
```

Relation columns are named after the relation and the side the related object is on. `"sample_project.personlivedinplace:obj"` shows the related place, and `"sample_project.personlivedinplace:obj.latitude"` shows the latitude.

If `apis_core.collections` is not included in `INSTALLED_APPS`, it will not be possible to add search results to a collection. A warning will be logged when the server starts.

## Why

The generic list views allow searching across multiple fields of a single model, but only using AND conditions. They do not support checking for empty values or more precise matching, such as exact matches or values starting with a particular string. Searching across related models is also limited, making it difficult to specify precise criteria for the attributes of subject and object models.

For example, a researcher might want to find Expressions that:
- Have Persian as one of their Language values.
- Are a copy of a Work (via the `ACopyOf` relation) that has History as one of its Subject Heading values.


```python
Expression.objects.filter(
    language__name="Persian",
    pk__in=ACopyOf.objects.filter(
        obj_object_id__in=Work.objects.filter(
            subject_heading__name="History"
        ).values("pk")
    ).values("subj_object_id")
).distinct()
```

The above query to retrieve these records is not complex, but humanities researchers neither have access to the backend to run such queries nor the technical know-how to write them. 

This package provides a way for users to build such queries through a single, more flexible search interface, without having to write Django ORM queries themselves.

