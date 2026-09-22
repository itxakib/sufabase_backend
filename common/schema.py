"""Custom ``AutoSchema`` that auto-tags endpoints by app name.

Instead of manually decorating every viewset with ``@extend_schema(tags=...)``,
this inspects the view's module path and derives the tag from the app label
(e.g. ``customers.api.views`` → ``Customers``).  Falls back to ``V1`` for
anything outside the known app structure.
"""

from drf_spectacular.openapi import AutoSchema

# Map app module prefixes to Swagger tag names.
_APP_TAGS = {
    "users": "Users",
    "tenant": "Tenants",
    "customers": "Customers",
    "catalog": "Catalog",
    "bookings": "Bookings",
    "consultancy": "Consultancy",
    "directory": "Directory",
    "simplejwt": "Auth",
    # Checked before the app prefixes above would ever match: the attachment
    # ViewSet lives in ``common``, but grouping it under a "Common" heading
    # says nothing to a frontend developer. ``attachment`` also keeps the
    # per-resource ``/{id}/attachments/`` actions (which live in each app's
    # ``views`` module) tagged with their own app, as they should be.
    "attachment": "Attachments",
}


class AppTaggedSchema(AutoSchema):
    """Schema generator that tags every endpoint by its Django app."""

    def get_tags(self):
        tags = super().get_tags()
        # Derive from the view's module path.
        view = self.view
        module = getattr(view, "__module__", "") or ""
        for prefix, tag in _APP_TAGS.items():
            if prefix in module:
                return [tag]
        return tags or ["API"]
