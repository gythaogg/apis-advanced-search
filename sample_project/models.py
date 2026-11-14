from django.db import models
from django.utils.translation import gettext_lazy as _

from apis_core.entities.abc import E21_Person, E53_Place, E74_Group, SimpleLabelModel
from apis_core.relations.models import Relation


class Profession(SimpleLabelModel):
    pass


class Person(E21_Person):
    profession = models.ManyToManyField(Profession, blank=True, related_name="persons")
    place_of_birth = models.ForeignKey(
        "Place",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="people_born_here",
    )


class Place(E53_Place):
    pass


class Institution(E74_Group):
    pass


class PersonLivedInPlace(Relation):
    subj_model = Person
    obj_model = Place

    @classmethod
    def name(cls) -> str:
        return _("lived in")

    @classmethod
    def reverse_name(cls) -> str:
        return _("was the place of residence of")

    pass


class PersonWorkedAtInstitution(Relation):
    subj_model = Person
    obj_model = Institution

    @classmethod
    def name(cls) -> str:
        return _("worked at")

    @classmethod
    def reverse_name(cls) -> str:
        return _("place of work of")


class GroupLocatedInPlace(Relation):
    subj_model = Institution
    obj_model = Place

    @classmethod
    def name(cls) -> str:
        return _("located in")

    @classmethod
    def reverse_name(cls) -> str:
        return _("is the location of")


class PlaceLocatedInPlace(Relation):
    subj_model = Place
    obj_model = Place

    @classmethod
    def name(cls) -> str:
        return _("located in")

    @classmethod
    def reverse_name(cls) -> str:
        return _("contains")
