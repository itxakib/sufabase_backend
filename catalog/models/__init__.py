"""Catalog models.

The sellable package lives here. The booked trip — real hotel, ticket and
transport rows — lives in ``bookings.Package`` and only optionally points at
a template.
"""

from catalog.models.template import PackageTemplate, PackageTemplateLine

__all__ = [
    'PackageTemplate',
    'PackageTemplateLine',
]
