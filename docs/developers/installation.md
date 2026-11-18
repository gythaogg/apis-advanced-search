# Installation

## Install the package

```bash
uv add apis-advanced-search
```

## Add the app

Add it to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    ...,
    "apis_advanced_search",
]
```

## Include the URLs

Include the package URLs in the project's root `urls.py`:

```python
from django.urls import include, path

urlpatterns = [
    ...,
    path("advanced-search/", include("apis_advanced_search.urls")),
]
```

The URL prefix is your choice. The package checks at startup that its URLs are included, and raises `ImproperlyConfigured` if they are not.

## Base template

The package markup uses Bootstrap 5 class names. The host project's base template must load Bootstrap 5.

## Collections (optional)

To use [Save results](../beta/save-results.md), add `apis_core.collections` to `INSTALLED_APPS`. Without it, the package logs a warning at startup and the save results feature is unavailable.

## Open the search

Start the server and open the URL prefix you chose, for example `/advanced-search/`.

## Next steps

- [Simple search](../search/simple-search.md)
- [Settings](settings.md)
- [Sample project](https://github.com/gythaogg/apis-advanced-search/tree/main/sample_project) for a working example configuration
