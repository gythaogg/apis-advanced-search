from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from apis_advanced_search.querybuilder.relation_columns import (
    group_columns,
    relation_groups,
    relation_values,
)
from sample_project.models import Person, PersonLivedInPlace, Place, Profession


class RelationGroupFieldTests(TestCase):
    """Relation groups offer every field of the related model, including
    foreign keys and many-to-many fields, not only the native ones."""

    @classmethod
    def setUpTestData(cls):
        cls.graz = Place.objects.create(label="Graz")
        cls.vienna = Place.objects.create(label="Vienna")
        cls.painter = Profession.objects.create(label="Painter")
        cls.writer = Profession.objects.create(label="Writer")
        cls.person = Person.objects.create(
            forename="Ada", surname="Example", place_of_birth=cls.graz
        )
        cls.person.profession.set([cls.painter, cls.writer])
        cls.other = Person.objects.create(
            forename="Ben", surname="Other", place_of_birth=cls.graz
        )
        cls.other.profession.set([cls.painter])
        PersonLivedInPlace.objects.create(subj=cls.person, obj=cls.vienna)
        PersonLivedInPlace.objects.create(subj=cls.other, obj=cls.vienna)

    def _group(self, groups, key):
        return next(group for group in groups if group.key == key)

    def test_group_offers_foreign_key_and_many_to_many_fields(self):
        groups = relation_groups(Place)
        group = self._group(groups, "sample_project.personlivedinplace:subj")
        names = [column.name for column in group_columns(group)]
        self.assertIn("sample_project.personlivedinplace:subj.place_of_birth", names)
        self.assertIn("sample_project.personlivedinplace:subj.profession", names)
        types = {column.name: column.type for column in group_columns(group)}
        self.assertEqual(types["sample_project.personlivedinplace:subj.place_of_birth"], "fk")
        self.assertEqual(types["sample_project.personlivedinplace:subj.profession"], "m2m")

    def test_foreign_key_and_many_to_many_values_are_shown(self):
        groups = {group.key: group for group in relation_groups(Place)}
        columns = [
            column
            for group in groups.values()
            for column in group_columns(group)
            if column.name
            in {
                "sample_project.personlivedinplace:subj.place_of_birth",
                "sample_project.personlivedinplace:subj.profession",
            }
        ]
        values = relation_values(Place, [self.vienna], columns, groups)[self.vienna.pk]
        self.assertEqual(
            values["sample_project.personlivedinplace:subj.place_of_birth"], "Graz"
        )
        self.assertEqual(
            values["sample_project.personlivedinplace:subj.profession"],
            "Painter, Writer",
        )

    def test_loading_related_fields_adds_a_fixed_number_of_queries(self):
        groups = {group.key: group for group in relation_groups(Place)}
        columns = [
            column
            for column in group_columns(groups["sample_project.personlivedinplace:subj"])
            if column.name.endswith((".place_of_birth", ".profession"))
        ]
        with CaptureQueriesContext(connection) as ctx:
            relation_values(Place, [self.vienna], columns, groups)
        # Links, targets, the foreign key's targets (select_related, so none
        # extra), and the many-to-many prefetch: well under one per person.
        self.assertLessEqual(len(ctx.captured_queries), 4)
