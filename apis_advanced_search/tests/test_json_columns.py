import json

from django.test import TestCase

from apis_advanced_search.querybuilder.columns import ColumnInfo, own_columns, row_values
from apis_advanced_search.querybuilder.relation_columns import (
    all_columns,
    group_columns,
    relation_groups,
)
from sample_project.models import Person, PersonLivedInPlace, Place

DETAILS = {"address": {"city": "Graz"}, "note": "city"}


class JSONColumnTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.graz = Place.objects.create(label="Graz")
        cls.person = Person.objects.create(
            forename="Ada", surname="Example", details=DETAILS
        )
        PersonLivedInPlace.objects.create(subj=cls.person, obj=cls.graz)

    def test_own_json_field_is_a_column(self):
        columns = {column.name: column for column in own_columns(Person)}
        self.assertEqual(columns["details"].type, "json")

    def test_json_column_is_not_sortable(self):
        column = ColumnInfo("details", "details", "json")
        self.assertFalse(column.sortable)

    def test_json_value_is_shown_as_json_text(self):
        columns = {column.name: column for column in own_columns(Person)}
        values = row_values(self.person, [columns["details"]])
        # Key order is not promised by the database, so compare the content.
        self.assertEqual(json.loads(values["details"]), DETAILS)

    def test_json_column_is_offered_for_the_selected_model(self):
        self.assertIn("details", all_columns(Person))

    def test_json_column_is_offered_for_a_related_model(self):
        # Viewed from a place: the people who live there, and their JSON field.
        groups = {group.key: group for group in relation_groups(Place)}
        group = groups["sample_project.personlivedinplace:subj"]
        names = {column.name: column for column in group_columns(group)}
        name = "sample_project.personlivedinplace:subj.details"
        self.assertIn(name, names)
        self.assertEqual(names[name].type, "json")
