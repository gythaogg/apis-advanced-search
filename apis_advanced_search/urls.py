from apis_advanced_search.views import SearchView
from django.urls import path

app_name = "apis_advanced_search"
urlpatterns = [
    path("", SearchView.as_view(), name="search"),
]
