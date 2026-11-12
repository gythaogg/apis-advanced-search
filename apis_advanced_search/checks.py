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
