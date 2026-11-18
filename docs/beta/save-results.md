# Save results

!!! warning "Beta"

    Save results may change before the feature is final.

Save results adds every object that matches the current query to a SKOS collection. It is not limited to the page on screen.

## Requirements

- `apis_core.collections` is in `INSTALLED_APPS`. See [Installation](../developers/installation.md).
- You are logged in. Anonymous users cannot add results to a collection.

## Add results to a collection

1. Run a search.
2. In the collection controls above the results, choose an existing collection, or choose **+ New collection…** and enter a name.
3. Click **Add all to collection**.

<!-- Screenshot: docs/assets/screenshots/save-results-controls.png - collection controls above the results table -->

## Related

- [Saved queries](saved-queries.md)
- [Inspect query](inspect-query.md)
