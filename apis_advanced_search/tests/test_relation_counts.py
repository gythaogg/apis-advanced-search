from django.test import TestCase

from apis_advanced_search.querybuilder.compiler import build_queryset
from apis_advanced_search.querybuilder.describe import describe_tree
from apis_advanced_search.querybuilder.tree import QueryTreeError, empty_group, validate_node
from sample_project.models import Person, PersonLivedInPlace, Place

LIVED_IN = "sample_project.personlivedinplace"


def relation(min_count=None, max_count=None):
    node: dict = {"type": "relation", "relation_model": LIVED_IN, "direction": "obj"}
    if min_count is not None:
        node["min_count"] = min_count
    if max_count is not None or min_count is not None:
        node["max_count"] = max_count
    return {"type": "group", "operator": "AND", "negate": False, "children": [node]}


class RelationCountTests(TestCase):
    """Persons with 0, 1, 2 and 3 lived-in relation rows."""

    @classmethod
    def setUpTestData(cls):
        places = [Place.objects.create(label=f"Place {i}") for i in range(4)]
        cls.none = Person.objects.create(forename="None", surname="X")
        cls.one = Person.objects.create(forename="One", surname="X")
        cls.two = Person.objects.create(forename="Two", surname="X")
        cls.three = Person.objects.create(forename="Three", surname="X")
        PersonLivedInPlace.objects.create(subj=cls.one, obj=places[0])
        for place in places[:2]:
            PersonLivedInPlace.objects.create(subj=cls.two, obj=place)
        for place in places[:3]:
            PersonLivedInPlace.objects.create(subj=cls.three, obj=place)

    def names(self, tree):
        return set(build_queryset(Person, tree).values_list("forename", flat=True))

    def test_has_relation_is_at_least_one(self):
        self.assertEqual(self.names(relation(1, None)), {"One", "Two", "Three"})

    def test_does_not_have_relation(self):
        self.assertEqual(self.names(relation(0, 0)), {"None"})

    def test_at_least_two(self):
        self.assertEqual(self.names(relation(2, None)), {"Two", "Three"})

    def test_at_least_three(self):
        self.assertEqual(self.names(relation(3, None)), {"Three"})

    def test_at_most_one_includes_zero(self):
        self.assertEqual(self.names(relation(0, 1)), {"None", "One"})

    def test_at_most_two(self):
        self.assertEqual(self.names(relation(0, 2)), {"None", "One", "Two"})

    def test_exactly_two(self):
        self.assertEqual(self.names(relation(2, 2)), {"Two"})

    def test_exactly_one(self):
        self.assertEqual(self.names(relation(1, 1)), {"One"})

    def test_between_two_and_three(self):
        self.assertEqual(self.names(relation(2, 3)), {"Two", "Three"})

    def test_counts_relation_rows_not_distinct_places(self):
        # Two rows pointing at the same place still count as two.
        place = Place.objects.create(label="Shared")
        PersonLivedInPlace.objects.create(subj=self.none, obj=place)
        PersonLivedInPlace.objects.create(subj=self.none, obj=place)
        self.assertEqual(self.names(relation(2, None)), {"None", "Two", "Three"})

    def test_legacy_negate_true_is_does_not_have(self):
        tree = {
            "type": "group",
            "operator": "AND",
            "negate": False,
            "children": [
                {"type": "relation", "relation_model": LIVED_IN, "direction": "obj", "negate": True}
            ],
        }
        self.assertEqual(self.names(tree), {"None"})

    def test_legacy_negate_false_is_has(self):
        tree = {
            "type": "group",
            "operator": "AND",
            "negate": False,
            "children": [
                {"type": "relation", "relation_model": LIVED_IN, "direction": "obj", "negate": False}
            ],
        }
        self.assertEqual(self.names(tree), {"One", "Two", "Three"})

    def test_describe_shows_grouped_count_for_several_rows(self):
        text = describe_tree(Person, relation(2, None))
        self.assertIn(".annotate(", text)
        self.assertIn("relation_count=Count('pk')", text)
        self.assertIn("filter(relation_count__gte=2)", text)

    def test_describe_negates_at_most(self):
        text = describe_tree(Person, relation(0, 0))
        self.assertIn("~(", text)
        self.assertNotIn("relation_count", text)


class RelationCountValidationTests(TestCase):
    def test_minimum_above_maximum_is_rejected(self):
        with self.assertRaises(QueryTreeError):
            validate_node(relation(3, 2))

    def test_negative_count_is_rejected(self):
        with self.assertRaises(QueryTreeError):
            validate_node(relation(-1, None))

    def test_non_integer_count_is_rejected(self):
        with self.assertRaises(QueryTreeError):
            validate_node(relation("2", None))

    def test_boolean_count_is_rejected(self):
        with self.assertRaises(QueryTreeError):
            validate_node(relation(True, None))

    def test_unbounded_minimum_zero_is_rejected(self):
        with self.assertRaises(QueryTreeError):
            validate_node(relation(0, None))

    def test_direct_slot_only_accepts_has_or_does_not_have(self):
        node = {"type": "relation", "relation_model": None, "direction": "obj"}
        node.update({"min_count": 2, "max_count": None})
        tree = {"type": "group", "operator": "AND", "negate": False, "children": [node]}
        with self.assertRaises(QueryTreeError):
            validate_node(tree)


class DirectSlotCountTests(TestCase):
    """A Relation's own slot: the relation model itself is the starting point."""

    @classmethod
    def setUpTestData(cls):
        cls.place = Place.objects.create(label="Vienna")
        cls.person = Person.objects.create(forename="Ada", surname="X")
        cls.lived = PersonLivedInPlace.objects.create(subj=cls.person, obj=cls.place)

    def direct(self, min_count, max_count):
        node = {"type": "relation", "relation_model": None, "direction": "obj"}
        node.update({"min_count": min_count, "max_count": max_count})
        return {"type": "group", "operator": "AND", "negate": False, "children": [node]}

    def test_has_slot(self):
        rows = build_queryset(PersonLivedInPlace, self.direct(1, None))
        self.assertEqual(list(rows), [self.lived])

    def test_does_not_have_slot(self):
        rows = build_queryset(PersonLivedInPlace, self.direct(0, 0))
        self.assertEqual(list(rows), [])

    def test_unsupported_count_raises_at_compile(self):
        with self.assertRaises(QueryTreeError):
            build_queryset(PersonLivedInPlace, self.direct(2, None))
