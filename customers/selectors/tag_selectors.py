"""Selectors for the customers app's tag vocabulary."""

from customers.models import Tag


class TagSelector:
    """Lookup and query logic for Tag records.

    Static methods only, ``company`` always an explicit parameter - the same
    contract as every other selector in this project.
    """

    @staticmethod
    def for_company(company):
        """Return a base queryset scoped to a specific tenant."""
        return Tag.objects.filter(company=company).order_by('name')

    @staticmethod
    def by_name(company, name):
        """Case-insensitive lookup within a tenant; ``None`` when absent.

        Exists so a future create flow can be idempotent - the model's
        ``unique_together`` is on exact ``name``, so "VIP" and "vip" are two rows
        unless the caller normalises first.
        """
        return TagSelector.for_company(company).filter(name__iexact=name).first()
