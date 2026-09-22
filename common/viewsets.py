"""Shared ViewSet infrastructure for SUFABASE.

``TenantScopedViewSetMixin`` is mixed into every tenant-scoped ViewSet.
It enforces company scoping on reads and stamps ``company`` / ``created_by`` /
``updated_by`` on writes — the one place this logic lives, per the rule:
never hand-filter tenant data per view.
"""

from common.permissions import HasCompanyContext
from rest_framework.permissions import IsAuthenticated


class TenantScopedViewSetMixin:
    """Auto-filters the queryset to the request's company and stamps
    ``company`` / ``created_by`` / ``updated_by`` on save.

    The company is resolved from ``request.company`` (set by
    ``CompanyContextMiddleware`` from the ``X-Company-ID`` header on
    real requests) with a fallback to ``request.user.company`` (for
    DRF test client, which runs ``force_authenticate`` after middleware).

    Views that mix this in must declare ``queryset`` on the class — the
    mixin calls ``super().get_queryset().filter(company=...)``.
    """

    permission_classes = [IsAuthenticated, HasCompanyContext]

    def _resolve_company(self):
        """Return the tenant, preferring the middleware-set value.

        Falls back to ``request.user.company`` when the middleware didn't run
        (DRF test client) but the header was validated by HasCompanyContext.
        """
        return getattr(self.request, "company", None) or getattr(
            self.request.user, "company", None
        )

    def _has_company_context(self):
        """Check whether the X-Company-ID header matches the user's company.

        This validates the header even when the middleware didn't run (tests).
        """
        header_value = self.request.headers.get("X-Company-ID")
        if not header_value:
            return False
        try:
            company_id = int(header_value)
        except (TypeError, ValueError):
            return False
        user = getattr(self.request, "user", None)
        return user is not None and user.company_id == company_id

    def get_queryset(self):
        # swagger_fake_view guard: drf-spectacular introspects querysets
        # with an AnonymousUser that has no company.  Without this, the
        # schema generator aborts model derivation and silently drops
        # every filter parameter.  Returning an empty queryset during
        # schema generation is the documented workaround.
        if getattr(self, "swagger_fake_view", False):
            return self.queryset.model.objects.none()
        return super().get_queryset().filter(company=self._resolve_company())

    def perform_create(self, serializer):
        """Stamp company and created_by on every new record."""
        serializer.save(
            company=self._resolve_company(),
            created_by=self.request.user,
        )

    def perform_update(self, serializer):
        """Stamp updated_by on every edit.  company is immutable after creation."""
        serializer.save(updated_by=self.request.user)
