from django.views.generic import TemplateView

from apis_advanced_search.querybuilder.collections import COLLECTIONS_AVAILABLE


class SearchView(TemplateView):
    template_name = "apis_advanced_search/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["collections_enabled"] = COLLECTIONS_AVAILABLE
        return context
