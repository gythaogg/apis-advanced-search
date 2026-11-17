# APIS Advanced Search

A model-agnostic query builder/search interface for [APIS](https://github.com/acdh-oeaw/apis-core-rdf) instances.

## Installation

```bash
uv add apis-advanced-search
```

Add it to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    ...,
    "apis_advanced_search",
]
```

Include its URLs somewhere in your project's root `urls.py`:

```python
urlpatterns = [
    ...,
    path("advanced-search/", include("apis_advanced_search.urls")),
]
```

The URL prefix (`advanced-search/` above) is up to you. The app checks at startup that its URLs were included somewhere, and raises `ImproperlyConfigured` with a clear message if you forget this step.

In case of trouble, compare your APIS instance with the sample_project APIS instance included here.

The package's markup and styles depend on Bootstrap 5 class names, and expects the host project's base template to load it. 

## Sample project database (PostgreSQL)

The sample project uses PostgreSQL. Searching all values of a JSON field (a condition with no key) only works on PostgreSQL. The other search features also run on SQLite, but the sample project uses PostgreSQL so that the full test suite runs.

The connection settings are in `sample_project/settings.py`:

```python
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "advanced_search_sample_project_db",
        "USER": "advanced_search_admin",
        "PASSWORD": "advanced_search_password",
        "HOST": "localhost",
        "PORT": "5432",
    }
}
```

The password is for local development only. Do not reuse it anywhere else.

### Create the role and database

Run these as a PostgreSQL superuser. `sudo -u postgres psql`.

```sql
-- The role needs CREATEDB so Django's test runner can create its own
-- test database (test_advanced_search_sample_project_db).
CREATE ROLE advanced_search_admin WITH LOGIN PASSWORD 'advanced_search_password' CREATEDB;

CREATE DATABASE advanced_search_sample_project_db OWNER advanced_search_admin;

\c advanced_search_sample_project_db
GRANT ALL ON SCHEMA public TO advanced_search_admin;

-- Optional: check the result.
\du advanced_search_admin
\l advanced_search_sample_project_db
```

`GRANT ALL ON SCHEMA public` is needed on PostgreSQL 15 and later, where the `public` schema is no longer writable by every user.

If the role or database already exist, drop them first (this deletes all data in the database):

```sql
DROP DATABASE IF EXISTS advanced_search_sample_project_db;
DROP ROLE IF EXISTS advanced_search_admin;
```

### Create the tables and run the sample project

From the project root:

```bash
uv run python manage.py migrate
uv run python manage.py runserver
```

`migrate` creates the tables in the new database. Run it again after pulling changes that add migrations.

### Run the tests

```bash
uv run python manage.py test apis_advanced_search
```

The test runner creates and drops its own `test_advanced_search_sample_project_db`, so the sample database is not touched. This needs the `CREATEDB` role attribute set above.

## Settings
`APIS_ANON_VIEWS_ALLOWED` from `apis-core-rdf` is used to determine if the results can be shown to anonymous users.

`APIS_ADVANCED_SEARCH_COLUMNS` sets the columns shown by default in the results table, per model.

```python
APIS_ADVANCED_SEARCH_COLUMNS = {
    "sample_project.person": ["date_of_birth", "place_of_bairth", "sample_project.personlivedinplace:obj.label"],
    "sample_project.place": ["label", "sample_project.personlivedinplace:subj"],
    }
```

Relation columns are named after the relation and the side the related object is on. `"sample_project.personlivedinplace:obj"` shows the related place, and `"sample_project.personlivedinplace:obj.latitude"` shows the latitude.

If `apis_core.collections` is not included in `INSTALLED_APPS`, it will not be possible to add search results to a collection. A warning will be logged when the server starts.

## Why

The generic list views allow searching across multiple fields of a single model, but only using AND conditions. They do not support checking for empty values or more precise matching, such as exact matches or values starting with a particular string. Searching across related models is also limited, making it difficult to specify precise criteria for the attributes of subject and object models.

For example, a researcher might want to find Expressions that:
- Have Persian as one of their Language values.
- Are a copy of a Work (via the `ACopyOf` relation) that has History as one of its Subject Heading values.


```python
Expression.objects.filter(
    language__name="Persian",
    pk__in=ACopyOf.objects.filter(
        obj_object_id__in=Work.objects.filter(
            subject_heading__name="History"
        ).values("pk")
    ).values("subj_object_id")
).distinct()
```

The above query to retrieve these records is not complex, but humanities researchers neither have access to the backend to run such queries nor the technical know-how to write them. 

This package provides a way for users to build such queries through a single, more flexible search interface, without having to write Django ORM queries themselves.

