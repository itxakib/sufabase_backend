"""Query-string filters for the customer tag vocabulary."""

from django_filters import CharFilter

from common.filters import StrictBooleanFilter, TenantAwareFilterSet
from customers.models import Tag


class TagFilter(TenantAwareFilterSet):
    """Filters for ``GET /api/v1/tags/``.

    Small on purpose - a tag is two columns - but ``used`` is the parameter that
    earns its place: every tenant accumulates labels nobody ever applied, and
    "which tags are actually in use" is how a tag list gets cleaned up instead of
    growing forever.
    """

    name = CharFilter(field_name='name', lookup_expr='icontains')
    name_exact = CharFilter(field_name='name', lookup_expr='iexact')
    color = CharFilter(field_name='color', lookup_expr='iexact')
    has_color = StrictBooleanFilter(method='filter_has_color')
    used = StrictBooleanFilter(method='filter_used')

    class Meta:
        model = Tag
        fields = []

    def filter_has_color(self, queryset, name, value):
        """``?has_color=false`` - tags still wearing the default appearance."""
        if value:
            return queryset.exclude(color='')
        return queryset.filter(color='')

    def filter_used(self, queryset, name, value):
        """``?used=false`` - defined but applied to no customer.

        Crosses the many-to-many, so it de-duplicates; without ``distinct`` a tag
        on five customers would be counted five times.
        """
        return queryset.filter(customers__isnull=not value).distinct()
