# Settings

## `APIS_ANON_VIEWS_ALLOWED`

Set by `apis-core-rdf`. When `True`, anonymous users can see search results.

## `APIS_ADVANCED_SEARCH_COLUMNS`

Default results columns per model, keyed by `app_label.model_name`.

```python
APIS_ADVANCED_SEARCH_COLUMNS = {
    "sample_project.person": ["date_of_birth", "sample_project.personlivedinplace:obj.label"],
    "sample_project.place": ["label", "sample_project.personlivedinplace:subj"],
}
```

See [Columns](../search/columns.md) for the column name format.

## `APIS_ADVANCED_SEARCH_DEBUG`

Default: `True`.

Enables the [Inspect query](../beta/inspect-query.md) panel and its endpoints. Set it to `False` on public sites, so the generated ORM code and timings are not exposed.

```python
APIS_ADVANCED_SEARCH_DEBUG = False
```

## `apis_core.collections`

Not a setting, but an app. Add it to `INSTALLED_APPS` to enable [Save results](../beta/save-results.md).
