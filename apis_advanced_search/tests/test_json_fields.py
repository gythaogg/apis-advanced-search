from django.db import connection
from django.test import TestCase

from apis_advanced_search.querybuilder.compiler import QueryCompileError, build_queryset
from apis_advanced_search.querybuilder.describe import describe_tree
from apis_advanced_search.querybuilder.introspection import (
    classify_field,
    get_filterable_field_map,
)
from apis_advanced_search.querybuilder.tree import empty_group
from sample_project.models import Person

IS_POSTGRES = connection.vendor == "postgresql"


def _condition(**node):
    group = empty_group()
    group["children"].append({"type": "condition", "field": "details", **node})
    return group


class JSONFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        cls.ada = Person.objects.create(
            forename="Ada",
            surname="Example",
            details={"address": {"city": "Graz"}, "note": "city"},
        )
        cls.ben = Person.objects.create(
            forename="Ben",
            surname="Other",
            details={"address": {"city": "Vienna"}},
        )
        cls.cy = Person.objects.create(forename="Cy", surname="Missing")
        cls.dee = Person.objects.create(
            forename="Dee", surname="Null", details={"address": None}
        )

    def names(self, tree):
        return set(build_queryset(Person, tree).values_list("forename", flat=True))


class JSONFieldSearchTests(JSONFixtureMixin, TestCase):
    def test_json_field_is_filterable(self):
        self.assertEqual(classify_field(Person._meta.get_field("details")), "json")
        info = get_filterable_field_map(Person)["details"]
        self.assertEqual(info.type, "json")

    def test_contains_searches_within_the_key(self):
        tree = _condition(key="address.city", lookup="icontains", value="graz")
        self.assertEqual(self.names(tree), {"Ada"})

    def test_key_names_are_not_searched(self):
        # "note" holds the text "city"; searching the key "address.city"
        # for "note" must not match Ada through her "note" key.
        tree = _condition(key="address.city", lookup="icontains", value="note")
        self.assertEqual(self.names(tree), set())

    def test_is_matches_the_value_ignoring_case(self):
        tree = _condition(key="address.city", lookup="iexact", value="VIENNA")
        self.assertEqual(self.names(tree), {"Ben"})

    def test_is_empty_with_a_key_matches_missing_keys(self):
        tree = _condition(key="address.city", lookup="empty")
        self.assertEqual(self.names(tree), {"Cy", "Dee"})

    def test_is_not_empty_with_a_key(self):
        tree = _condition(key="address.city", lookup="not_empty")
        self.assertEqual(self.names(tree), {"Ada", "Ben"})

    def test_is_empty_without_a_key_checks_the_whole_field(self):
        tree = _condition(lookup="empty")
        self.assertEqual(self.names(tree), {"Cy"})

    def test_a_null_value_counts_as_empty(self):
        tree = _condition(key="address.city", lookup="not_empty")
        self.assertNotIn("Dee", self.names(tree))

    def test_other_lookups_need_a_key(self):
        tree = _condition(lookup="iexact", value="graz")
        with self.assertRaises(QueryCompileError):
            build_queryset(Person, tree)

    def test_a_key_with_double_underscores_is_rejected(self):
        tree = _condition(key="address__city", lookup="icontains", value="graz")
        with self.assertRaises(QueryCompileError):
            build_queryset(Person, tree)

    def test_debug_text_shows_the_key_path(self):
        tree = _condition(key="address.city", lookup="icontains", value="graz")
        self.assertIn("details__address__city__icontains", describe_tree(Person, tree))

    def test_debug_text_shows_the_all_values_lookup(self):
        tree = _condition(lookup="icontains", value="graz")
        self.assertIn("details__values_icontains", describe_tree(Person, tree))


class AllValuesSearchOnOtherDatabasesTests(JSONFixtureMixin, TestCase):
    """Searching every value needs PostgreSQL. On any other database the
    user gets a clear message, not a database error."""

    def test_clear_error_when_not_postgres(self):
        if IS_POSTGRES:
            self.skipTest("Runs on databases other than PostgreSQL only.")
        tree = _condition(lookup="icontains", value="graz")
        with self.assertRaisesMessage(QueryCompileError, "needs a PostgreSQL database"):
            build_queryset(Person, tree)


class AllValuesSearchTests(JSONFixtureMixin, TestCase):
    """Searching every string value, at any depth, with no key given.
    These run only on PostgreSQL."""

    def setUp(self):
        if not IS_POSTGRES:
            self.skipTest("Searching all JSON values needs PostgreSQL.")

    def test_matches_a_value_at_any_depth(self):
        tree = _condition(lookup="icontains", value="graz")
        self.assertEqual(self.names(tree), {"Ada"})

    def test_ignores_case(self):
        tree = _condition(lookup="icontains", value="VIENNA")
        self.assertEqual(self.names(tree), {"Ben"})

    def test_key_names_are_not_matched(self):
        # "city" is a key in Ben's record, not a value.
        # Ada's value "city" is under the key "note", so she matches.
        tree = _condition(lookup="icontains", value="city")
        self.assertEqual(self.names(tree), {"Ada"})

    def test_a_key_name_alone_matches_nothing(self):
        tree = _condition(lookup="icontains", value="address")
        self.assertEqual(self.names(tree), set())

    def test_does_not_contain_excludes_matches(self):
        tree = _condition(lookup="not_icontains", value="graz")
        self.assertEqual(self.names(tree), {"Ben", "Cy", "Dee"})

    def test_percent_and_underscore_are_literal(self):
        Person.objects.create(
            forename="Eve", surname="Literal", details={"note": "100% sure_ok"}
        )
        self.assertEqual(
            self.names(_condition(lookup="icontains", value="100%")), {"Eve"}
        )
        self.assertEqual(
            self.names(_condition(lookup="icontains", value="sure_ok")), {"Eve"}
        )
        self.assertEqual(self.names(_condition(lookup="icontains", value="sureXok")), set())

    def test_several_values_match_any(self):
        tree = _condition(lookup="icontains", value=["graz", "vienna"])
        self.assertEqual(self.names(tree), {"Ada", "Ben"})

    def test_numbers_are_not_searched(self):
        Person.objects.create(forename="Fay", surname="Number", details={"n": 2024})
        self.assertEqual(self.names(_condition(lookup="icontains", value="2024")), set())
