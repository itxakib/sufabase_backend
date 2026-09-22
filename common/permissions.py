"""Shared permission classes for the SUFABASE API."""

from rest_framework.permissions import BasePermission


class HasCompanyContext(BasePermission):
    """Blocks any request where the ``X-Company-ID`` header is missing,
    wrong, or doesn't match the authenticated user's own company.

    Distinct from ``IsAuthenticated``: a valid token with no/bad header still
    gets blocked here.  The two are always used together on tenant-scoped
    viewsets (``permission_classes = [IsAuthenticated, HasCompanyContext]``).
    """

    def has_permission(self, request, view):
        # If the middleware already validated the header, trust it.
        if getattr(request, "company", None) is not None:
            return True
        # Otherwise validate the header ourselves — this path is hit by
        # DRF's test client (where force_authenticate patches request.user
        # after middleware runs) and by any request that bypasses middleware.
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return False
        header_value = request.headers.get("X-Company-ID")
        if not header_value:
            return False
        try:
            company_id = int(header_value)
        except (TypeError, ValueError):
            return False
        return user.company_id == company_id
