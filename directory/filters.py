"""Query-string filters for the B2B directory list."""

from django_filters import CharFilter

from common.filters import TenantAwareFilterSet
from directory.models import DirectoryCompany


class DirectoryCompanyFilter(TenantAwareFilterSet):
    """Filters for ``GET /api/v1/directory-companies/``.

    Sector, sub-sector, membership type and email are exact: the list controls
    send a value copied from the imported row, and a substring match would
    treat ``STEEL`` as a hit on ``STAINLESS STEEL``.

    ``sheet_name`` is the chamber category (Manufacturers, Importers, Exporters,
    Traders, Services). It lives on ``DirectoryBusinessActivity``, not on the
    company, so the filter crosses that relation. ``distinct`` keeps a company
    that sits on one sheet from being counted twice if the join multiplies rows.
    """

    business_sector = CharFilter(lookup_expr='exact')
    sub_sector = CharFilter(lookup_expr='exact')
    membership_type = CharFilter(lookup_expr='exact')
    email = CharFilter(lookup_expr='exact')
    sheet_name = CharFilter(method='filter_sheet_name')

    def filter_sheet_name(self, queryset, name, value):
        if not value:
            return queryset
        # The join to activities can drop the model's default ordering once
        # distinct() is applied, and an unordered page shifts between requests.
        return (
            queryset.filter(activities__sheet_name=value)
            .distinct()
            .order_by('company_name', 'pk')
        )

    class Meta:
        model = DirectoryCompany
        fields = [
            'business_sector',
            'sub_sector',
            'membership_type',
            'email',
            'sheet_name',
        ]
