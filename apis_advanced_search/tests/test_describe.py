from django.apps import apps
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apis_advanced_search.querybuilder.describe import describe_tree
from apis_advanced_search.querybuilder.tree import empty_group


def group(*children, operator="AND", negate=False):
    return {
        "type": "group",
        "operator": operator,
        "negate": negate,
        "children": list(children),
    }


def condition(field, lookup, value):
    return {"type": "condition", "field": field, "lookup": lookup, "value": value}


class DescribeTreeTests(TestCase):
    def setUp(self):
        self.person = apps.get_model("sample_project", "person")
        self.place = apps.get_model("sample_project", "place")

    def test_empty_tree_matches_everything(self):
        self.assertEqual(
            describe_tree(self.person, empty_group()),
            "Person.objects.filter(Q()).distinct()",
        )

    def test_single_condition(self):
        tree = group(condition("label", "icontains", "Vienna"))
        self.assertEqual(
            describe_tree(self.place, tree),
            "Place.objects.filter(Q(label__icontains='Vienna')).distinct()",
        )

    def test_negated_relation_with_target_filter(self):
        tree = group(
            {
                "type": "relation",
                "relation_model": "sample_project.personlivedinplace",
                "direction": "obj",
                "negate": True,
                "own_filter": None,
                "target_filter": group(condition("label", "icontains", "Vienna")),
            }
        )
        self.assertEqual(
            describe_tree(self.person, tree),
            "Person.objects.filter("
            "~(Q(pk__in=PersonLivedInPlace.objects.filter("
            "obj_object_id__in=Place.objects.filter(Q(label__icontains='Vienna')).values(\"pk\")"
            ').values("subj_object_id")))'
            ").distinct()",
        )


@override_settings(APIS_ADVANCED_SEARCH_DEBUG=True)
class DebugEndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse(
            "apis_advanced_search:api-model-query-debug",
            kwargs={"app_label": "sample_project", "model_name": "place"},
        )
        self.tree = group(condition("label", "icontains", "Vienna"))

    def test_returns_orm_text(self):
        response = self.client.post(self.url, {"query": self.tree}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["orm"],
            "Place.objects.filter(Q(label__icontains='Vienna')).distinct()",
        )

    @override_settings(APIS_ADVANCED_SEARCH_DEBUG=False)
    def test_not_served_when_disabled(self):
        response = self.client.post(self.url, {"query": self.tree}, format="json")
        self.assertEqual(response.status_code, 404)

    def test_invalid_tree_is_rejected(self):
        bad = group(condition("no_such_field", "icontains", "x"))
        response = self.client.post(self.url, {"query": bad}, format="json")
        self.assertEqual(response.status_code, 400)
