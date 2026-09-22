"""Query logic for the Company model.

This is the one selector in the codebase with no ``company`` scoping argument:
a company is not tenant-owned, so there is nothing to scope it by. Every other
selector takes ``company`` explicitly.
"""

from django.db.models import Q, QuerySet

from tenant.models import Company


class CompanySelector:
    """All Company lookups live here. Staticmethods only, no instance state."""

    @staticmethod
    def list_companies(
        *,
        is_active: bool | None = None,
        plan: str | None = None,
        country: str | None = None,
        search: str | None = None,
    ) -> QuerySet[Company]:
        queryset = Company.objects.all()
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        if plan:
            queryset = queryset.filter(plan=plan)
        if country:
            queryset = queryset.filter(country__iexact=country)
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(slug__icontains=search)
                | Q(legal_name__icontains=search)
                | Q(contact_email__icontains=search)
            )
        return queryset.order_by('name')

    @staticmethod
    def get_active() -> QuerySet[Company]:
        return CompanySelector.list_companies(is_active=True)

    @staticmethod
    def get_by_id(company_id) -> Company:
        """Raises Company.DoesNotExist when there is no such company."""
        return Company.objects.get(pk=company_id)

    @staticmethod
    def get_by_slug(slug: str) -> Company:
        """Raises Company.DoesNotExist when there is no such company."""
        return Company.objects.get(slug=slug)
