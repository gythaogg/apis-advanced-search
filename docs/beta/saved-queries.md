# Saved queries

!!! warning "Beta"

    Saved queries may change before the feature is final.

Saved queries store a query so it can be loaded and run again. A saved query stores the query definition and its starting model, not the results.

## Save a query

1. Build the query.
2. Enter a name in the save controls.
3. Tick **Public** to allow anyone to load it. Leave it unticked to keep it private.
4. Click **Save query**.

<!-- Screenshot: docs/assets/screenshots/saved-queries-save.png - save controls with Public checkbox -->

## Load a query

Choose a query in **Load saved search…**. The builder is filled with the saved query, and you can run or change it.

## Ownership

- Queries are private by default.
- A public query can be loaded and run by anyone.
- Only the owner can edit or delete a query.

## Manage queries in the admin

Saved queries are also available in the Django admin, under `SavedQuery`.

## Related

- [Save results](save-results.md)
- [Inspect query](inspect-query.md)
