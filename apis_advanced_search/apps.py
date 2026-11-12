from django.apps import AppConfig
from django.core.exceptions import ImproperlyConfigured
from django.urls import get_resolver


class APISAdvancedSearchConfig(AppConfig):
    name = "apis_advanced_search"
    verbose_name = "APIS Advanced Search"

    def ready(self):
        from apis_advanced_search import checks  # noqa: F401 - registers system checks

        resolver = get_resolver()

        def has_package_urls(patterns):
            for pattern in patterns:
                if getattr(pattern, "app_name", None) == "apis_advanced_search":
                    return True

                nested = getattr(pattern, "url_patterns", None)
                if nested and has_package_urls(nested):
                    return True

            return False

        if not has_package_urls(resolver.url_patterns):
            raise ImproperlyConfigured(
                "APIS Advanced Search URLs are not included in "
                "the project's root URL configuration."
            )
