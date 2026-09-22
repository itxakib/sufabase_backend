"""Selectors for the bookings app.

Two kinds of method live here:

* ``for_company`` / ``for_customer`` - generic, model-agnostic entry points that
  apply the correct loading strategy for you, so a new list view cannot
  accidentally introduce an N+1 by forgetting ``select_related``.
* the six named ``*_for_customer`` wrappers - thin, so call sites read as
  ``BookingSelector.hajj_for_customer(customer)`` rather than passing model classes
  around everywhere.

The queries themselves live in ``common.selectors.TenantScopedSelector``, which is
what keeps the tenant filter in exactly one place across all eight service models.
"""

from django.db.models import Prefetch

from bookings.models import (
    HajjBooking,
    HotelBooking,
    Package,
    PackageComponent,
    TicketingBooking,
    TourBooking,
    TransportBooking,
    UmrahBooking,
)
from common.selectors import TenantScopedSelector

#: Relations every ``ServiceRecordBase`` subclass needs eagerly loaded.
#:
#: All six share these three foreign keys (``company``, ``customer``,
#: ``sales_agent``), so the set is declared once instead of six times. Without it,
#: rendering a page of bookings costs a query per row for the tenant, the customer
#: and the agent - three N+1s hiding inside one list view.
SERVICE_RECORD_RELATED = ('company', 'customer', 'sales_agent')

#: The loading strategy per model, so callers pass a model class and get the right
#: ``select_related`` without having to know each model's foreign keys. This is not
#: a nicety: ``select_related('customer')`` on ``Package`` raises ``FieldError``
#: because ``Package`` has no customer link at all, so a single shared set applied
#: to every model would be a genuine bug rather than a missed optimisation.
RELATED_BY_MODEL = {
    HajjBooking: SERVICE_RECORD_RELATED,
    UmrahBooking: SERVICE_RECORD_RELATED,
    TourBooking: SERVICE_RECORD_RELATED,
    TicketingBooking: SERVICE_RECORD_RELATED,
    HotelBooking: SERVICE_RECORD_RELATED,
    TransportBooking: SERVICE_RECORD_RELATED,
    # Package carries a tenant and an optional template, no customer.
    Package: ('company', 'template'),
    PackageComponent: (
        'company',
        'package',
        'hotel_booking',
        'ticketing_booking',
        'transport_booking',
    ),
}

#: What a package needs to render: its link rows, with each booking's customer,
#: agent and tenant already joined. One prefetch, not three many-to-many loads.
_COMPONENT_RELATED = tuple(
    f'{booking}__{related}'
    for booking in ('hotel_booking', 'ticketing_booking', 'transport_booking')
    for related in SERVICE_RECORD_RELATED
)
PACKAGE_PREFETCHES = (
    Prefetch(
        'components',
        queryset=PackageComponent.objects.select_related(*_COMPONENT_RELATED),
    ),
)


class BookingSelector:
    """Lookup and query logic for the booking models, including the bundle."""

    @staticmethod
    def for_company(model_cls, company, **filters):
        """Company-scoped records of ``model_cls``, with its relations loaded.

        Works for any of the seven models - the loading set is looked up per model
        in :data:`RELATED_BY_MODEL`. Unknown models get no eager loading rather
        than an exception, so this stays usable for a model added later without a
        corresponding entry.
        """
        return TenantScopedSelector.for_company(
            model_cls,
            company,
            select_related=RELATED_BY_MODEL.get(model_cls, ()),
            **filters,
        )

    @staticmethod
    def for_customer(model_cls, customer, **filters):
        """One customer's records of a given service-record model.

        Service records only - ``Package`` has no ``customer`` field (the customer
        lives on the trip record that composes the package), so it is not a valid
        argument here. Reach a package through :meth:`package_with_components`.
        """
        return TenantScopedSelector.for_customer(
            model_cls,
            customer,
            select_related=RELATED_BY_MODEL.get(model_cls, ()),
            **filters,
        )

    @staticmethod
    def hajj_for_customer(customer):
        """This customer's Hajj records."""
        return BookingSelector.for_customer(HajjBooking, customer)

    @staticmethod
    def umrah_for_customer(customer):
        """This customer's Umrah records."""
        return BookingSelector.for_customer(UmrahBooking, customer)

    @staticmethod
    def tour_for_customer(customer):
        """This customer's tour records."""
        return BookingSelector.for_customer(TourBooking, customer)

    @staticmethod
    def ticketing_for_customer(customer):
        """This customer's ticket records."""
        return BookingSelector.for_customer(TicketingBooking, customer)

    @staticmethod
    def hotel_for_customer(customer):
        """This customer's hotel-stay records."""
        return BookingSelector.for_customer(HotelBooking, customer)

    @staticmethod
    def transport_for_customer(customer):
        """This customer's ground-transport records."""
        return BookingSelector.for_customer(TransportBooking, customer)

    @staticmethod
    def package_with_components(package_id, company):
        """A package plus its linked hotel/ticket/transport records, or ``None``.

        For the customer detail view. Every component comes back with its own
        customer, agent and tenant already loaded, so rendering a package with a
        dozen components stays at a fixed number of queries rather than growing
        with the component count.

        Scoped by ``company`` as well as id, so a package id belonging to another
        tenant resolves to ``None`` rather than to somebody else's trip.
        """
        return (
            Package.objects
            .filter(company=company, pk=package_id)
            .select_related('company', 'template')
            .prefetch_related(*PACKAGE_PREFETCHES)
            .first()
        )
