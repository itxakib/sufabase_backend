"""Selector tests for the bookings app.

The query-count tests here are the reason this file exists at all. Every selector
in this app returns correct rows even with all eager loading removed - it just
returns them one query per row - so nothing but an explicit query count can tell
the difference.
"""

from django.test import TestCase

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
from bookings.selectors.booking_selectors import (
    PACKAGE_PREFETCHES,
    RELATED_BY_MODEL,
    SERVICE_RECORD_RELATED,
    BookingSelector,
)
from common.tests.factories import make_company, make_user
from customers.models import Customer


class BookingSelectorFixtureMixin:
    """One record of every booking model, plus a package that composes three."""

    def setUp(self):
        super().setUp()
        self.company = make_company()
        self.other_company = make_company()
        self.agent = make_user(company=self.company)

        self.customer = Customer.objects.create(
            company=self.company,
            full_name='Ali Khan',
            phone='03001112223',
        )
        self.other_customer = Customer.objects.create(
            company=self.company,
            full_name='Sara Ahmed',
            phone='03219998887',
        )
        self.foreign_customer = Customer.objects.create(
            company=self.other_company,
            full_name='Foreign Customer',
            phone='03000000000',
        )

        common = {
            'company': self.company,
            'customer': self.customer,
            'sales_agent': self.agent,
        }

        self.hajj = HajjBooking.objects.create(
            hajj_year='2026', package_name='Economy Hajj', **common,
        )
        self.umrah = UmrahBooking.objects.create(
            umrah_year_season='Ramadan 2026', package_name='Umrah Plus', **common,
        )
        self.tour = TourBooking.objects.create(
            tour_name='Turkey Highlights', destination_country='Turkey', **common,
        )
        self.ticket = TicketingBooking.objects.create(
            passenger_name='Ali Khan', pnr='AAA111', airline='PIA',
            origin='KHI', destination='JED', **common,
        )
        self.hotel = HotelBooking.objects.create(
            lead_guest_name='Ali Khan', hotel_name='Hilton Makkah', city='Makkah',
            room_type='Double', **common,
        )
        self.transport = TransportBooking.objects.create(
            service_type='AIRPORT_TRANSFER', pickup_location='JED Airport',
            dropoff_location='Hilton Makkah', pickup_time='02:30',
            number_of_passengers=2, vehicle_type='Hiace', **common,
        )

        # A record for a different customer in the same tenant, so "scoped to the
        # customer" is distinguishable from "scoped to the company".
        self.other_ticket = TicketingBooking.objects.create(
            company=self.company, customer=self.other_customer, sales_agent=self.agent,
            passenger_name='Sara Ahmed', pnr='BBB222', airline='Airblue',
            origin='LHE', destination='DXB',
        )
        # And one in another tenant entirely.
        self.foreign_hajj = HajjBooking.objects.create(
            company=self.other_company, customer=self.foreign_customer,
            hajj_year='2026', package_name='Other Tenant Hajj',
        )

        self.package = Package.objects.create(company=self.company, name='Ali trip')
        PackageComponent.objects.create(
            company=self.company, package=self.package, hotel_booking=self.hotel,
        )
        PackageComponent.objects.create(
            company=self.company, package=self.package, ticketing_booking=self.ticket,
        )
        PackageComponent.objects.create(
            company=self.company, package=self.package, transport_booking=self.transport,
        )


class PerCustomerSelectorTests(BookingSelectorFixtureMixin, TestCase):
    """Each named wrapper returns one model, for one customer, in one tenant."""

    def test_each_wrapper_returns_only_its_own_model(self):
        calls = {
            'hajj': (BookingSelector.hajj_for_customer, self.hajj),
            'umrah': (BookingSelector.umrah_for_customer, self.umrah),
            'tour': (BookingSelector.tour_for_customer, self.tour),
            'ticketing': (BookingSelector.ticketing_for_customer, self.ticket),
            'hotel': (BookingSelector.hotel_for_customer, self.hotel),
            'transport': (BookingSelector.transport_for_customer, self.transport),
        }
        for name, (selector, expected) in calls.items():
            with self.subTest(service=name):
                self.assertEqual(
                    list(selector(self.customer)),
                    [expected],
                    f'{name} selector returned the wrong rows',
                )

    def test_ticketing_wrapper_excludes_the_same_model_for_another_customer(self):
        """Scoped to the customer, not merely to the company."""
        self.assertEqual(
            list(BookingSelector.ticketing_for_customer(self.customer)),
            [self.ticket],
        )
        self.assertEqual(
            list(BookingSelector.ticketing_for_customer(self.other_customer)),
            [self.other_ticket],
        )

    def test_no_wrapper_returns_another_tenants_records(self):
        """A Hajj exists for the foreign customer, and must stay invisible."""
        self.assertNotIn(
            self.foreign_hajj,
            list(BookingSelector.hajj_for_customer(self.customer)),
        )

    def test_for_customer_scopes_to_that_customers_own_tenant(self):
        """The foreign customer has their own Hajj, and it *is* returned here.

        That is the documented contract, not a leak: ``for_customer`` trusts
        ``customer.company_id``, so it answers "this person's records" for whoever
        it is handed.
        """
        self.assertEqual(BookingSelector.hajj_for_customer(self.foreign_customer).count(), 1)

    def test_the_tenant_boundary_is_the_customer_lookup_not_the_selector(self):
        """Where cross-tenant protection actually lives, pinned.

        Nothing stops ``for_customer`` from reading another tenant's rows if it is
        handed another tenant's customer - the selector is not the guard. The
        guard is that an API view obtains a customer through
        ``CustomerSelector.get_by_id(company, pk)``, which returns ``None`` for an
        id outside the caller's tenant. So a foreign customer can never reach this
        selector in the first place, and the two halves are tested together here
        because neither is safe to change alone.
        """
        from customers.selectors.customer_selectors import CustomerSelector

        self.assertIsNone(
            CustomerSelector.get_by_id(self.company, self.foreign_customer.pk),
        )
        self.assertIsNotNone(
            CustomerSelector.get_by_id(self.company, self.customer.pk),
        )

    def test_for_company_works_for_every_model_including_package(self):
        """``RELATED_BY_MODEL`` must cover every bookings model, including the bundle.

        ``Package`` is the trap here: it has no ``customer`` FK, so applying the
        service-record loading set to it raises ``FieldError``. This test is what
        proves the per-model map is doing its job rather than a shared set being
        applied blindly.
        """
        models = (
            HajjBooking, UmrahBooking, TourBooking,
            TicketingBooking, HotelBooking, TransportBooking,
            Package, PackageComponent,
        )
        for model in models:
            with self.subTest(model=model.__name__):
                self.assertIsNotNone(BookingSelector.for_company(model, self.company).count())

        self.assertIn(Package, RELATED_BY_MODEL)
        self.assertNotEqual(RELATED_BY_MODEL[Package], SERVICE_RECORD_RELATED)


class PackageSelectorTests(BookingSelectorFixtureMixin, TestCase):
    def test_returns_the_package_with_its_components(self):
        package = BookingSelector.package_with_components(self.package.pk, self.company)

        linked = {
            component.component.pk
            for component in package.components.all()
        }
        self.assertEqual(linked, {self.hotel.pk, self.ticket.pk, self.transport.pk})

    def test_returns_none_for_another_tenants_package(self):
        """A package id from another tenant resolves to ``None``, not a leak."""
        self.assertIsNone(
            BookingSelector.package_with_components(self.package.pk, self.other_company),
        )

    def test_returns_none_when_missing(self):
        self.assertIsNone(BookingSelector.package_with_components(10_000_000, self.company))

    def test_components_arrive_with_their_relations_already_loaded(self):
        """The nested ``Prefetch`` querysets, pinned.

        A plain ``prefetch_related('hotels', ...)`` would load the hotel rows and
        then let each one fetch its own customer, agent and tenant while rendering
        - three queries per component, which is precisely the N+1 the prefetch was
        supposed to remove. Zero queries here is the proof it actually removed it.
        """
        package = BookingSelector.package_with_components(self.package.pk, self.company)
        bookings = [component.component for component in package.components.all()]

        with self.assertNumQueries(0):
            for booking in bookings:
                booking.company.name
                booking.customer.full_name
                booking.sales_agent.username

    def test_prefetch_configuration_is_not_silently_emptied(self):
        self.assertEqual(len(PACKAGE_PREFETCHES), 1)
        self.assertEqual(PACKAGE_PREFETCHES[0].prefetch_through, 'components')


class EagerLoadingTests(BookingSelectorFixtureMixin, TestCase):
    """A list of booking rows must not cost a query per row."""

    def test_touching_relations_on_a_ticket_list_costs_no_extra_queries(self):
        tickets = list(BookingSelector.for_company(TicketingBooking, self.company))

        self.assertGreater(len(tickets), 1, 'the test needs more than one row')

        with self.assertNumQueries(0):
            for ticket in tickets:
                ticket.company.name
                ticket.customer.full_name
                ticket.sales_agent.username

    def test_touching_relations_on_a_customer_scoped_list_costs_no_extra_queries(self):
        """``for_customer`` must apply the same loading strategy as ``for_company``."""
        tickets = list(BookingSelector.for_customer(TicketingBooking, self.customer))

        with self.assertNumQueries(0):
            for ticket in tickets:
                ticket.customer.full_name
                ticket.sales_agent.username

    def test_an_unmapped_model_degrades_to_no_eager_loading(self):
        """The lookup defaults to ``()``, so a model added later still queries.

        Only the model-class lookup is asserted here - the selector itself needs a
        real Django model, which by definition an unmapped one is not.
        """

        class NotAMappedModel:
            pass

        self.assertEqual(RELATED_BY_MODEL.get(NotAMappedModel, ()), ())
        self.assertEqual(len(RELATED_BY_MODEL), 8)
