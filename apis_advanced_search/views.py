from django.views.generic import TemplateView


class SearchView(TemplateView):
    template_name = "apis_advanced_search/index.html"
