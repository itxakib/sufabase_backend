"""Query-string filters for the company (tenant) directory."""

from django_filters import CharFilter, ChoiceFilter, DateTimeFilter

from common.filters import InCharFilter, StrictBooleanFilter, TenantAwareFilterSet
from tenant.models import Company


class CompanyFilter(TenantAwareFilterSet):
    """Filters for ``GET /api/v1/companies/``.

    Every filter here targets a column on ``Company`` itself - no filter crosses
    into tenant-owned data. That is deliberate: a parameter like "companies with
    more than N customers" would turn this endpoint into a cross-tenant reporting
    tool, which is Module 07 (``saas_admin``) work that has to be explicit and
    visible rather than a side effect of a query string.
    """

    # ── Identity ─────────────────────────────────────────────────────────────
    name = CharFilter(field_name='name', lookup_expr='icontains')
    name_exact = CharFilter(field_name='name', lookup_expr='iexact')
    slug = CharFilter(field_name='slug', lookup_expr='iexact')
    legal_name = CharFilter(field_name='legal_name', lookup_expr='icontains')

    # ── Contact and location ─────────────────────────────────────────────────
    contact_email = CharFilter(field_name='contact_email', lookup_expr='icontains')
    contact_phone = CharFilter(field_name='contact_phone', lookup_expr='icontains')
    address = CharFilter(field_name='address', lookup_expr='icontains')
    city = CharFilter(field_name='city', lookup_expr='icontains')
    country = CharFilter(field_name='country', lookup_expr='iexact')
    timezone = CharFilter(field_name='timezone', lookup_expr='iexact')

    # ── Commercial state ─────────────────────────────────────────────────────
    plan = ChoiceFilter(field_name='plan', choices=Company.Plan.choices)
    plan_in = InCharFilter(field_name='plan')
    plan_not = InCharFilter(field_name='plan', exclude=True)
    is_active = StrictBooleanFilter(field_name='is_active')
    onboarded = StrictBooleanFilter(method='filter_onboarded')

    # ── Timestamps ───────────────────────────────────────────────────────────
    onboarded_after = DateTimeFilter(field_name='onboarded_at', lookup_expr='gte')
    onboarded_before = DateTimeFilter(field_name='onboarded_at', lookup_expr='lte')

    class Meta:
        model = Company
        fields = []

    def filter_onboarded(self, queryset, name, value):
        """``?onboarded=false`` - created but never actually went live.

        This is the standing "stuck in setup" list for company onboarding, and it
        is not the same thing as ``is_active=false``: a company can be newly
        created and active while ``onboarded_at`` is still empty.
        """
        return queryset.filter(onboarded_at__isnull=not value)
