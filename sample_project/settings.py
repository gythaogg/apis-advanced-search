from apis_acdhch_default_settings.settings import *

DEBUG = True

ROOT_URLCONF = "sample_project.urls"
APIS_BASE_URL = ""

APPS_TO_REMOVE = ["apis_core.search", "apis_ontology"]

for app in APPS_TO_REMOVE:
    if app in INSTALLED_APPS:
        INSTALLED_APPS.remove(app)

ADDITIONAL_APPS = ["sample_project", "apis_advanced_search"]

for app in ADDITIONAL_APPS:
    if app not in INSTALLED_APPS:
        INSTALLED_APPS.append(app)


APIS_ANON_VIEWS_ALLOWED = True
