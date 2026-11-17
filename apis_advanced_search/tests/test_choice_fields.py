from django.test import TestCase

from apis_advanced_search.querybuilder.columns import own_columns
from apis_advanced_search.querybuilder.compiler import build_queryset
from apis_advanced_search.querybuilder.describe import describe_tree
from apis_advanced_search.querybuilder.introspection import (
    classify_field,
    get_filterable_field_map,
)
from apis_advanced_search.querybuilder.tree import empty_group
from sample_project.models import Person


def _condition(**node):
    group = empty_group()
    group["children"].append({"type": "condition", "field": "status", **node})
    return group


class ChoiceFieldTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.active = Person.objects.create(forename="Ada", surname="A", status="active")
        cls.retired = Person.objects.create(forename="Ben", surname="B", status="retired")
        cls.unknown = Person.objects.create(forename="Cy", surname="C", status="unknown")
        cls.blank = Person.objects.create(forename="Dee", surname="D", status="")

    def names(self, tree):
        return set(build_queryset(Person, tree).values_list("forename", flat=True))

    def test_choice_field_is_classified_and_lists_its_choices(self):
        self.assertEqual(classify_field(Person._meta.get_field("status")), "choice")
        info = get_filterable_field_map(Person)["status"]
        self.assertEqual(info.type, "choice")
        self.assertEqual(
            info.to_dict()["choices"],
            [
                {"value": "active", "label": "Active"},
                {"value": "retired", "label": "Retired"},
                {"value": "unknown", "label": "Unknown"},
            ],
        )

    def test_lookups_are_the_many_to_many_style_lookups(self):
        info = get_filterable_field_map(Person)["status"]
        self.assertEqual(
            [(opt["value"], opt["label"], opt["multi"]) for opt in info.lookups],
            [
                ("exact", "includes", True),
                ("not_exact", "excludes", True),
                ("empty", "is empty", False),
                ("not_empty", "is not empty", False),
            ],
        )

    def test_includes_matches_one_or_more_choices(self):
        tree = _condition(lookup="exact", value=["active", "retired"])
        self.assertEqual(self.names(tree), {"Ada", "Ben"})

    def test_excludes_removes_the_chosen_values(self):
        tree = _condition(lookup="not_exact", value=["active"])
        self.assertEqual(self.names(tree), {"Ben", "Cy", "Dee"})

    def test_is_empty_includes_a_blank_value(self):
        tree = _condition(lookup="empty")
        self.assertEqual(self.names(tree), {"Dee"})

    def test_is_not_empty(self):
        tree = _condition(lookup="not_empty")
        self.assertEqual(self.names(tree), {"Ada", "Ben", "Cy"})

    def test_debug_text_uses_the_selected_values(self):
        tree = _condition(lookup="exact", value=["active", "retired"])
        self.assertIn("status__in=['active', 'retired']", describe_tree(Person, tree))

    def test_choice_field_is_offered_as_a_column(self):
        columns = {column.name: column for column in own_columns(Person)}
        self.assertEqual(columns["status"].type, "choice")
