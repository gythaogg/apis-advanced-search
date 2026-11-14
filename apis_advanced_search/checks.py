from django.conf import settings
from django.core.checks import Warning, register


@register()
def check_collections_app_installed(app_configs, **kwargs):
    if "apis_core.collections" in settings.INSTALLED_APPS:
        return []
    return [
        Warning(
            "'apis_core.collections' is not in INSTALLED_APPS.",
            hint=(
                "APIS Advanced Search's 'add results to a collection' "
                "feature will not be available."
            ),
            id="apis_advanced_search.W001",
        )
    ]


@register()
def check_result_columns_setting(app_configs, **kwargs):
    """Every entry in APIS_ADVANCED_SEARCH_COLUMNS must name a registered
    model and fields of it. Anything else would silently show no
    column, so it is reported here instead."""
    from apis_advanced_search.querybuilder.columns import (
        configured_columns,
        own_column_map,
    )
    from apis_advanced_search.querybuilder.registry import resolve_model

    config = configured_columns()
    if not isinstance(config, dict):
        return [
            Warning(
                "APIS_ADVANCED_SEARCH_COLUMNS must be a dict of 'app_label.model' to lists of field names.",
                id="apis_advanced_search.W002",
            )
        ]

    problems = []
    for label, names in config.items():
        app_label, _, model_name = str(label).partition(".")
        model = resolve_model(app_label, model_name) if model_name else None
        if model is None:
            problems.append(
                Warning(
                    f"APIS_ADVANCED_SEARCH_COLUMNS: {label!r} is not a registered entity or relation model.",
                    id="apis_advanced_search.W002",
                )
            )
            continue
        if not isinstance(names, (list, tuple)):
            problems.append(
                Warning(
                    f"APIS_ADVANCED_SEARCH_COLUMNS: the columns for {label!r} must be a list.",
                    id="apis_advanced_search.W002",
                )
            )
            continue
        available = own_column_map(model)
        for name in names:
            if name not in available:
                problems.append(
                    Warning(
                        f"APIS_ADVANCED_SEARCH_COLUMNS: {name!r} is not a field of {label!r}.",
                        hint="Only the model's own fields can be columns in this version.",
                        id="apis_advanced_search.W002",
                    )
                )
    return problems
