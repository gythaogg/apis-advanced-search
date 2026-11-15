from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apis_advanced_search.querybuilder.tree import empty_group


def _url(name):
    return reverse(
        f"apis_advanced_search:{name}",
        kwargs={"app_label": "sample_project", "model_name": "person"},
    )


@override_settings(APIS_ADVANCED_SEARCH_DEBUG=True)
class SearchAndTimingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.body = {"query": empty_group(), "page": 1, "sort": None, "columns": None}

    def test_search_returns_a_page(self):
        response = self.client.post(_url("api-model-query"), self.body, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(response.json()),
            {"count", "page", "page_size", "results", "loaded_columns"},
        )

    def test_timing_reports_phases_and_statements(self):
        response = self.client.post(
            _url("api-model-query-timing"), self.body, format="json"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(set(data["phases"]), {"compile", "count", "page", "rows"})
        self.assertGreater(data["queries"], 0)
        self.assertGreaterEqual(data["total_ms"], 0)
        self.assertIn("count", data)

    @override_settings(APIS_ADVANCED_SEARCH_DEBUG=False)
    def test_timing_not_served_when_disabled(self):
        response = self.client.post(
            _url("api-model-query-timing"), self.body, format="json"
        )
        self.assertEqual(response.status_code, 404)
