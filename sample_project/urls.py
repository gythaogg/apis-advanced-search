from django.urls import include, path
from apis_acdhch_default_settings.urls import *

app_name = "sample_project"

urlpatterns += [
    path(
        "advanced-search/",
        include(
            "apis_advanced_search.urls",
        ),
    ),
]
