from django.urls import path

from apis_advanced_search.api import views as api_views
from apis_advanced_search.views import SearchView

app_name = "apis_advanced_search"
urlpatterns = [
    path("", SearchView.as_view(), name="search"),
    path("api/models/", api_views.ModelListView.as_view(), name="api-models"),
    path(
        "api/models/<str:app_label>/<str:model_name>/fields/",
        api_views.ModelFieldsView.as_view(),
        name="api-model-fields",
    ),
    path(
        "api/models/<str:app_label>/<str:model_name>/relations/",
        api_views.ModelRelationsView.as_view(),
        name="api-model-relations",
    ),
    path(
        "api/models/<str:app_label>/<str:model_name>/query/",
        api_views.ModelQueryView.as_view(),
        name="api-model-query",
    ),
]
