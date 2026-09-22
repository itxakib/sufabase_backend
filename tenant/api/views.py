"""Thin viewsets for the tenant app: parse request -> selector -> serialize."""

from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import generics, mixins
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ReadOnlyModelViewSet

from common.permissions import HasCompanyContext
from tenant.filters.company import CompanyFilter
from tenant.selectors.company_selectors import CompanySelector
from tenant.serializers.company import CompanySerializer, SettingsCompanySerializer


class CompanyViewSet(ReadOnlyModelViewSet):
    """Read-only tenant directory.

    Read-only on purpose for Module 01: company creation/editing is Module 07
    (platform admin) work, and no permission classes exist yet to gate writes.
    Query-param filtering is owned by ``CompanyFilter``, while ``CompanySelector``
    owns the base queryset for non-HTTP callers.
    """

    serializer_class = CompanySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = CompanyFilter
    search_fields = [
        'name',
        'slug',
        'legal_name',
        'contact_email',
        'contact_phone',
        'address',
        'city',
        'country',
    ]
    ordering_fields = [
        'name',
        'slug',
        'plan',
        'is_active',
        'city',
        'country',
        'onboarded_at',
        'created_at',
        'updated_at',
    ]
    ordering = ['name']

    def get_queryset(self):
        return CompanySelector.list_companies()


@extend_schema(tags=['Settings'])
class SettingsCompanyView(
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    generics.GenericAPIView,
):
    """GET /settings/company/ — returns the authenticated user's own company.
    PATCH /settings/company/ — updates the authenticated user's own company.

    This is the frontend settings panel endpoint. Only the user's own company
    is accessible — no cross-tenant reads or writes. The serializer maps
    frontend field names (email, phone, address_line1) to model fields.
    """

    serializer_class = SettingsCompanySerializer
    permission_classes = [IsAuthenticated, HasCompanyContext]

    def get_object(self):
        company = getattr(self.request, 'company', None)
        if company is None:
            company = getattr(self.request.user, 'company', None)
        return company

    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)

    def patch(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)
