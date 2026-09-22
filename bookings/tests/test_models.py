"""Schema-level tests for the bookings app models.

These are structural tests - field types, delete rules, accessor names, choice
widths and tenant isolation - rather than workflow tests, because this pass is
schema only. The delete-rule and isolation tests are the ones that matter most:
they are the cursor rules (no silent cross-tenant reads, no accidental
destruction of live client data) expressed as something that fails loudly.
"""

from django.apps import apps
from django.db import IntegrityError, models, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from bookings.choices import (
    BookingStageChoices,
    CabinClassChoices,
    HotelStatusChoices,
    RefundStatusChoices,
    TicketStatusChoices,
)
from bookings.models import (
    HajjBooking,
    HotelBooking,
    Package,
    PackageComponent,
    ServiceRecordBase,
    TicketingBooking,
    TourBooking,
    TransportBooking,
    UmrahBooking,
)
from common.models import TenantScopedModel
from common.tests.factories import make_attachment, make_company, make_user
from common.tests.mixins import MediaRootMixin
from customers.models import Customer

# The six models that inherit ServiceRecordBase, in no particular order.
SERVICE_RECORD_MODELS = (
    TicketingBooking,
    HotelBooking,
    TransportBooking,
    HajjBooking,
    UmrahBooking,
    TourBooking,
)

EXPECTED_CONCRETE_MODELS = {
    'HajjBooking',
    'HotelBooking',
    'Package',
    'PackageComponent',
    'TicketingBooking',
    'TourBooking',
    'TransportBooking',
    'UmrahBooking',
}


def make_customer(company, **overrides):
    """Create the Customer every booking in these tests hangs off."""
    defaults = {
        'company': company,
        'full_name': 'Test Customer',
        'phone': '03001234567',
    }
    defaults.update(overrides)
    return Customer.objects.create(**defaults)


class BookingAppShapeTests(TestCase):
    """Guard the shape of the app itself, not any one model."""

    def test_app_owns_exactly_the_expected_concrete_models(self):
        """Eight tables — six service records, the trip bundle, and its link rows.

        Another model appearing here means something was added without a
        deliberate decision, and this test is the tripwire.
        """
        names = {model.__name__ for model in apps.get_app_config('bookings').get_models()}
        self.assertEqual(names, EXPECTED_CONCRETE_MODELS)

    def test_service_record_base_is_abstract(self):
        """The base must never become a table of its own."""
        self.assertTrue(ServiceRecordBase._meta.abstract)
        self.assertNotIn('ServiceRecordBase', EXPECTED_CONCRETE_MODELS)

    def test_every_service_record_inherits_tenant_scoping(self):
        for model in SERVICE_RECORD_MODELS:
            with self.subTest(model=model.__name__):
                self.assertTrue(issubclass(model, TenantScopedModel))

    def test_package_is_tenant_scoped(self):
        self.assertTrue(issubclass(Package, TenantScopedModel))
        self.assertTrue(issubclass(PackageComponent, TenantScopedModel))

    def test_every_choice_value_fits_its_column(self):
        """A choice value longer than its column is a data-loss bug waiting.

        This is here because the failure mode is silent-ish and easy to ship: add
        an option with a long name, forget to widen the CharField, and the value
        is rejected (or truncated, depending on backend) only at write time in
        production. Checking every choice field on every service record catches
        the whole class of mistake at once.
        """
        offenders = []
        for model in SERVICE_RECORD_MODELS:
            for field in model._meta.get_fields():
                if isinstance(field, models.CharField) and field.choices:
                    longest = max(len(str(value)) for value, _ in field.choices)
                    if longest > field.max_length:
                        offenders.append(
                            f'{model.__name__}.{field.name} needs {longest}, '
                            f'has {field.max_length}'
                        )
        self.assertEqual(offenders, [])


class SharedFieldTests(TestCase):
    """The fields every service record inherits from ServiceRecordBase."""

    def setUp(self):
        self.company = make_company()
        self.customer = make_customer(self.company)

    def test_customer_is_protected_not_cascaded(self):
        """Deleting a customer must not silently destroy their booking history."""
        for model in SERVICE_RECORD_MODELS:
            with self.subTest(model=model.__name__):
                field = model._meta.get_field('customer')
                self.assertIs(field.remote_field.on_delete, models.PROTECT)
                self.assertFalse(field.null)

    def test_company_is_protected(self):
        """Inherited from TenantScopedModel - a booking always has a tenant."""
        field = TicketingBooking._meta.get_field('company')
        self.assertIs(field.remote_field.on_delete, models.PROTECT)
        self.assertFalse(field.null)

    def test_sales_agent_is_nullable_set_null(self):
        """Losing an assignment must never block removing a staff account."""
        for model in SERVICE_RECORD_MODELS:
            with self.subTest(model=model.__name__):
                field = model._meta.get_field('sales_agent')
                self.assertIs(field.remote_field.on_delete, models.SET_NULL)
                self.assertTrue(field.null)
                self.assertTrue(field.blank)

    def test_amount_shape(self):
        field = HajjBooking._meta.get_field('amount')
        self.assertEqual(field.max_digits, 12)
        self.assertEqual(field.decimal_places, 2)
        self.assertTrue(field.null)

    def test_currency_defaults_to_pkr(self):
        booking = TicketingBooking.objects.create(
            company=self.company,
            customer=self.customer,
            passenger_name='A Passenger',
            pnr='ABC123',
            airline='PIA',
            origin='KHI',
            destination='JED',
        )
        self.assertEqual(booking.currency, 'PKR')

    def test_dates_are_nullable(self):
        """Hajj/Umrah are year-based, so dated columns must allow null."""
        for name in ('start_date', 'end_date'):
            with self.subTest(field=name):
                field = UmrahBooking._meta.get_field(name)
                self.assertTrue(field.null)
                self.assertTrue(field.blank)

    def test_booking_reference_is_optional(self):
        field = TourBooking._meta.get_field('booking_reference')
        self.assertTrue(field.blank)
        self.assertFalse(field.null)

    def test_every_service_record_can_hold_attachments(self):
        """Documents/Voucher columns are covered by one generic relation."""
        for model in SERVICE_RECORD_MODELS:
            with self.subTest(model=model.__name__):
                self.assertTrue(hasattr(model, 'attachments'))

    def test_customer_has_a_distinct_reverse_accessor_per_record_type(self):
        """``related_name='%(class)s_set'`` - unique per concrete subclass.

        If two subclasses ever produced the same accessor, Django would raise a
        system check error, so this pins the naming convention rather than
        discovering it in production.
        """
        for model in SERVICE_RECORD_MODELS:
            accessor = f'{model._meta.model_name}_set'
            with self.subTest(model=model.__name__):
                self.assertTrue(hasattr(self.customer, accessor))

    def test_reverse_accessors_are_not_shared_between_record_types(self):
        ticket = TicketingBooking.objects.create(
            company=self.company,
            customer=self.customer,
            passenger_name='A Passenger',
            pnr='ABC123',
            airline='PIA',
            origin='KHI',
            destination='JED',
        )
        self.assertEqual(list(self.customer.ticketingbooking_set.all()), [ticket])
        self.assertEqual(self.customer.hajjbooking_set.count(), 0)


class ProtectedDeleteTests(TestCase):
    """The two PROTECT edges the client explicitly asked for.

    Both are about the same thing: live client business data must fail loudly
    rather than disappear, and the friction of an explicit two-step delete is the
    point, not an obstacle.
    """

    def setUp(self):
        self.company = make_company()
        self.customer = make_customer(self.company)

    def _make_hajj(self):
        return HajjBooking.objects.create(
            company=self.company,
            customer=self.customer,
            hajj_year='2026',
            package_name='Economy Hajj',
        )

    def test_deleting_a_customer_with_bookings_is_blocked(self):
        booking = self._make_hajj()

        with self.assertRaises(ProtectedError):
            self.customer.delete()

        # Nothing was destroyed by the failed attempt.
        self.assertTrue(Customer.objects.filter(pk=self.customer.pk).exists())
        self.assertTrue(HajjBooking.objects.filter(pk=booking.pk).exists())

    def test_deleting_a_customer_without_bookings_still_works(self):
        """Proves the protection is conditional, not a blanket block on delete."""
        self.customer.delete()
        self.assertFalse(Customer.objects.filter(pk=self.customer.pk).exists())

    def test_deleting_a_company_with_bookings_is_blocked(self):
        self._make_hajj()

        with self.assertRaises(ProtectedError):
            self.company.delete()

        self.assertTrue(Customer.objects.filter(pk=self.customer.pk).exists())

    def test_deleting_the_sales_agent_keeps_the_booking(self):
        """SET_NULL, not PROTECT: an assignment is not part of the record."""
        agent = make_user(company=self.company)
        booking = TicketingBooking.objects.create(
            company=self.company,
            customer=self.customer,
            sales_agent=agent,
            passenger_name='A Passenger',
            pnr='ABC123',
            airline='PIA',
            origin='KHI',
            destination='JED',
        )

        agent.delete()
        booking.refresh_from_db()

        self.assertIsNone(booking.sales_agent)
        self.assertTrue(TicketingBooking.objects.filter(pk=booking.pk).exists())


class TenantIsolationTests(TestCase):
    """Cursor Rule 3, expressed as a test: no cross-tenant reads."""

    def setUp(self):
        self.company_a = make_company()
        self.company_b = make_company()
        self.customer_a = make_customer(self.company_a, full_name='Customer A')
        self.customer_b = make_customer(self.company_b, full_name='Customer B')

    def test_bookings_do_not_leak_across_tenants(self):
        booking_a = TicketingBooking.objects.create(
            company=self.company_a,
            customer=self.customer_a,
            passenger_name='A Passenger',
            pnr='AAA111',
            airline='PIA',
            origin='KHI',
            destination='JED',
        )
        TicketingBooking.objects.create(
            company=self.company_b,
            customer=self.customer_b,
            passenger_name='B Passenger',
            pnr='BBB222',
            airline='Airblue',
            origin='LHE',
            destination='DXB',
        )

        visible = TicketingBooking.objects.filter(company=self.company_a)

        self.assertEqual(list(visible), [booking_a])
        self.assertNotIn(booking_a, TicketingBooking.objects.filter(company=self.company_b))

    def test_company_filter_is_the_only_thing_separating_the_two(self):
        """Filtering by company returns exactly the other tenant's rows.

        Stated explicitly so the filtering contract is impossible to misread:
        nothing but the ``company`` filter does the isolation work here, so a
        selector that forgets it returns both tenants' data.
        """
        TicketingBooking.objects.create(
            company=self.company_a,
            customer=self.customer_a,
            passenger_name='A Passenger',
            pnr='AAA111',
            airline='PIA',
            origin='KHI',
            destination='JED',
        )
        TicketingBooking.objects.create(
            company=self.company_b,
            customer=self.customer_b,
            passenger_name='B Passenger',
            pnr='BBB222',
            airline='Airblue',
            origin='LHE',
            destination='DXB',
        )

        self.assertEqual(TicketingBooking.objects.count(), 2)
        self.assertEqual(TicketingBooking.objects.filter(company=self.company_a).count(), 1)
        self.assertEqual(TicketingBooking.objects.filter(company=self.company_b).count(), 1)


class PackageTests(TestCase):
    """Package composes real component records; it is not a sellable catalogue."""

    def setUp(self):
        self.company = make_company()
        self.customer = make_customer(self.company)
        self.package = Package.objects.create(company=self.company, name='Umrah 2026')

    def _make_ticket(self, pnr):
        return TicketingBooking.objects.create(
            company=self.company,
            customer=self.customer,
            passenger_name='A Passenger',
            pnr=pnr,
            airline='PIA',
            origin='KHI',
            destination='JED',
        )

    def _make_hotel(self):
        return HotelBooking.objects.create(
            company=self.company,
            customer=self.customer,
            lead_guest_name='A Guest',
            hotel_name='Hilton Makkah',
            city='Makkah',
            room_type='Double',
        )

    def _make_transport(self):
        return TransportBooking.objects.create(
            company=self.company,
            customer=self.customer,
            service_type='AIRPORT_TRANSFER',
            pickup_location='JED Airport',
            dropoff_location='Hilton Makkah',
            pickup_time='02:30',
            number_of_passengers=4,
            vehicle_type='Hiace',
        )

    def _link(self, **booking):
        return PackageComponent.objects.create(
            company=self.company,
            package=self.package,
            **booking,
        )

    def test_package_composes_components(self):
        ticket = self._make_ticket('AAA111')
        hotel = self._make_hotel()
        transport = self._make_transport()

        self._link(ticketing_booking=ticket)
        self._link(hotel_booking=hotel)
        self._link(transport_booking=transport)

        self.assertEqual(self.package.components.count(), 3)

    def test_package_can_hold_more_than_one_of_a_component(self):
        """Outbound and return are frequently booked as separate tickets."""
        self._link(ticketing_booking=self._make_ticket('AAA111'))
        self._link(ticketing_booking=self._make_ticket('BBB222'))

        self.assertEqual(
            self.package.components.filter(ticketing_booking__isnull=False).count(),
            2,
        )

    def test_the_same_booking_cannot_be_linked_twice(self):
        hotel = self._make_hotel()
        self._link(hotel_booking=hotel)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._link(hotel_booking=hotel)

    def test_a_component_with_no_booking_is_rejected_by_the_database(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PackageComponent.objects.create(company=self.company, package=self.package)

    def test_a_linked_booking_cannot_be_deleted(self):
        hotel = self._make_hotel()
        self._link(hotel_booking=hotel)
        with self.assertRaises(ProtectedError):
            hotel.delete()

    def test_components_expose_the_reverse_accessor(self):
        hotel = self._make_hotel()
        link = self._link(hotel_booking=hotel)

        self.assertEqual(list(hotel.package_components.all()), [link])
        self.assertEqual(link.component, hotel)

    def test_deleting_a_package_keeps_the_bookings(self):
        """Deleting the bundle deletes the link rows, not the bookings."""
        ticket = self._make_ticket('AAA111')
        self._link(ticketing_booking=ticket)

        self.package.delete()

        self.assertTrue(TicketingBooking.objects.filter(pk=ticket.pk).exists())
        self.assertFalse(PackageComponent.objects.filter(ticketing_booking=ticket).exists())

    def test_stays_are_kept_when_the_package_row_is_deleted(self):
        hotel = self._make_hotel()
        transport = self._make_transport()
        self._link(hotel_booking=hotel)
        self._link(transport_booking=transport)

        self.package.delete()

        self.assertTrue(HotelBooking.objects.filter(pk=hotel.pk).exists())
        self.assertTrue(TransportBooking.objects.filter(pk=transport.pk).exists())

    def test_trips_can_be_unlinked_from_a_package_without_losing_the_trip(self):
        """The trip -> package FK is SET_NULL, so the trip survives."""
        hajj = HajjBooking.objects.create(
            company=self.company,
            customer=self.customer,
            hajj_year='2026',
            package_name='Economy Hajj',
            package=self.package,
        )

        self.package.delete()
        hajj.refresh_from_db()

        self.assertIsNone(hajj.package)
        self.assertTrue(HajjBooking.objects.filter(pk=hajj.pk).exists())

    def test_each_trip_type_has_its_own_reverse_name(self):
        """Three foreign keys cannot share ``related_name='trips'``."""
        hajj = HajjBooking.objects.create(
            company=self.company,
            customer=self.customer,
            hajj_year='2026',
            package_name='Economy Hajj',
            package=self.package,
        )
        self.assertEqual(list(self.package.hajj_trips.all()), [hajj])
        self.assertTrue(hasattr(self.package, 'umrah_trips'))
        self.assertTrue(hasattr(self.package, 'tour_trips'))

    def test_bundle_does_not_store_operational_fields(self):
        names = {field.name for field in Package._meta.local_fields}
        self.assertTrue({'pnr', 'lead_guest_name', 'ticket_number', 'price'}.isdisjoint(names))
        component_names = {field.name for field in PackageComponent._meta.local_fields}
        self.assertTrue(
            {'pnr', 'lead_guest_name', 'room_type', 'number_of_adults'}.isdisjoint(component_names),
        )


class PackageAttachmentTests(MediaRootMixin, TestCase):
    """A package carries the trip-wide paperwork; its parts carry theirs.

    This reverses an earlier decision. The original schema said attachments
    belong only to the service record that was sold, and ``Package`` was left
    out of it. Real trips disagreed: the consolidated itinerary, the group visa
    list and a supplier contract covering several components at once do not
    belong to any single hotel or ticket row, and forcing them onto an arbitrary
    component makes them unfindable exactly when they are needed.

    Package now declares the same generic relation every service record has, so
    "documents for this trip" can be answered from the bundle as well as from
    each part of it. Pinned here because it is a decision, not an accident.
    """

    def setUp(self):
        self.company = make_company()
        self.customer = make_customer(self.company)
        self.package = Package.objects.create(
            company=self.company, name='Hajj Bundle',
        )

    def test_package_declares_the_generic_attachment_relation(self):
        self.assertTrue(hasattr(Package, 'attachments'))

    def test_attachment_saved_against_a_package_resolves_back(self):
        attachment = make_attachment(
            company=self.company,
            target=self.package,
            doc_type='Consolidated itinerary',
        )

        self.assertEqual(list(self.package.attachments.all()), [attachment])
        self.assertEqual(attachment.content_object, self.package)

    def test_package_attachments_do_not_leak_onto_its_components(self):
        """The bundle's documents are the bundle's, not the hotel's.

        A package that carried its attachments implicitly would make "which
        hotel is this voucher for" unanswerable, so the two buckets stay
        separate and this pins that they do.
        """
        hotel = HotelBooking.objects.create(
            company=self.company,
            customer=self.customer,
            lead_guest_name='A Guest',
            hotel_name='Hilton Makkah',
            city='Makkah',
            room_type='Double',
        )
        PackageComponent.objects.create(
            company=self.company, package=self.package, hotel_booking=hotel,
        )
        make_attachment(company=self.company, target=self.package)

        self.assertEqual(self.package.attachments.count(), 1)
        self.assertEqual(hotel.attachments.count(), 0)

    def test_company_scoping_still_applies_to_package_attachments(self):
        """The generic FK must not become a way around the tenant filter.

        Nothing in the schema ties an attachment's ``object_id`` to its
        ``company``, so this asserts the selector - not the model - is what
        keeps another tenant's documents out of reach.
        """
        make_attachment(company=self.company, target=self.package)
        other_company = make_company()

        from common.attachment_selectors import AttachmentSelector

        self.assertEqual(
            AttachmentSelector.for_object(self.package, other_company).count(), 0,
        )
        self.assertEqual(
            AttachmentSelector.for_object(self.package, self.company).count(), 1,
        )


class ServiceSpecificFieldTests(TestCase):
    """The fields that make each service line different."""

    def setUp(self):
        self.company = make_company()
        self.customer = make_customer(self.company)

    def test_ticket_defaults_to_reserved(self):
        booking = TicketingBooking.objects.create(
            company=self.company,
            customer=self.customer,
            passenger_name='A Passenger',
            pnr='AAA111',
            airline='PIA',
            origin='KHI',
            destination='JED',
        )
        self.assertEqual(booking.status, TicketStatusChoices.RESERVED)
        self.assertEqual(booking.refund_status, '')

    def test_ticket_choice_columns_are_wide_enough(self):
        self.assertEqual(TicketingBooking._meta.get_field('cabin_class').max_length, 20)
        self.assertEqual(TicketingBooking._meta.get_field('trip_type').max_length, 15)
        self.assertEqual(TicketingBooking._meta.get_field('passenger_type').max_length, 10)

    def test_hotel_defaults_to_inquiry(self):
        booking = HotelBooking.objects.create(
            company=self.company,
            customer=self.customer,
            lead_guest_name='A Guest',
            hotel_name='Hilton Makkah',
            city='Makkah',
            room_type='Double',
        )
        self.assertEqual(booking.status, HotelStatusChoices.INQUIRY)
        self.assertIsNone(booking.cancellation_deadline)
        self.assertIsNone(booking.number_of_rooms)

    def test_transport_requires_the_price_determining_fields(self):
        """What a quote is built from must exist before the job can be sold.

        ``pickup_time`` is deliberately *not* in this list. It was, and that was
        reversed: a vehicle gets booked before the pickup time is settled, and
        requiring it up front only ever collected a placeholder. It is required
        from ``DRIVER_ASSIGNED`` instead - see ``bookings/status_rules.py``.
        """
        for name in ('number_of_passengers', 'service_type', 'vehicle_type'):
            with self.subTest(field=name):
                field = TransportBooking._meta.get_field(name)
                self.assertFalse(field.blank)

    def test_pickup_time_is_settled_after_the_booking(self):
        """Nullable because the time arrives later; not because it is optional."""
        field = TransportBooking._meta.get_field('pickup_time')

        self.assertTrue(field.null)
        self.assertTrue(field.blank)

    def test_transport_optional_counts_are_nullable(self):
        for name in ('number_of_vehicles',):
            with self.subTest(field=name):
                field = TransportBooking._meta.get_field(name)
                self.assertTrue(field.null)

    def test_hajj_records_the_year_not_a_date_range(self):
        """Hajj is sold by year; the dated columns stay null on purpose."""
        booking = HajjBooking.objects.create(
            company=self.company,
            customer=self.customer,
            hajj_year='2026',
            package_name='Economy Hajj',
        )
        self.assertEqual(booking.hajj_year, '2026')
        self.assertIsNone(booking.start_date)
        self.assertIsNone(booking.end_date)
        self.assertEqual(booking.status, BookingStageChoices.INQUIRY)

    def test_hajj_year_column_holds_the_longest_expected_value(self):
        self.assertEqual(HajjBooking._meta.get_field('hajj_year').max_length, 9)

    def test_hajj_application_number_is_optional_and_indexed(self):
        field = HajjBooking._meta.get_field('application_number')
        self.assertTrue(field.blank)
        self.assertTrue(field.db_index)
        self.assertEqual(field.max_length, 100)

    def test_umrah_season_is_free_text(self):
        """Must hold values like 'Ramadan 2026', not just a year."""
        booking = UmrahBooking.objects.create(
            company=self.company,
            customer=self.customer,
            umrah_year_season='Ramadan 2026',
            package_name='Umrah Plus',
        )
        self.assertEqual(booking.umrah_year_season, 'Ramadan 2026')
        self.assertIsNone(booking.total_duration_nights)

    def test_tour_requires_a_destination_country(self):
        field = TourBooking._meta.get_field('destination_country')
        self.assertFalse(field.blank)

        booking = TourBooking.objects.create(
            company=self.company,
            customer=self.customer,
            tour_name='Turkey Highlights',
            destination_country='Turkey',
        )
        self.assertEqual(booking.destination_city, '')
        self.assertIsNone(booking.number_of_travelers)

    def test_visa_status_is_independent_of_stage(self):
        """A confirmed booking can still have a visa in process."""
        booking = HajjBooking.objects.create(
            company=self.company,
            customer=self.customer,
            hajj_year='2026',
            package_name='Economy Hajj',
            status=BookingStageChoices.CONFIRMED,
        )
        self.assertEqual(booking.visa_status, '')
        self.assertEqual(booking.status, BookingStageChoices.CONFIRMED)

    def test_str_outputs_are_human_readable(self):
        hotel = HotelBooking.objects.create(
            company=self.company,
            customer=self.customer,
            lead_guest_name='A Guest',
            hotel_name='Hilton Makkah',
            city='Makkah',
            room_type='Double',
        )
        transport = TransportBooking.objects.create(
            company=self.company,
            customer=self.customer,
            service_type='ZIYARAT',
            pickup_location='Hilton Makkah',
            dropoff_location='Masjid al-Haram',
            pickup_time='05:00',
            number_of_passengers=3,
            vehicle_type='Sedan',
        )
        package = Package.objects.create(company=self.company, name='Family Hajj')

        self.assertEqual(str(hotel), 'Hilton Makkah (Makkah)')
        self.assertEqual(str(transport), 'Ziyarat → Masjid al-Haram')
        self.assertEqual(str(package), 'Family Hajj')

    def test_choice_sets_are_the_specified_values(self):
        self.assertEqual(
            {value for value, _ in RefundStatusChoices.choices},
            {'NOT_REQUESTED', 'REQUESTED', 'PROCESSED', 'REJECTED', 'PARTIAL'},
        )
        self.assertEqual(
            {value for value, _ in CabinClassChoices.choices},
            {'ECONOMY', 'PREMIUM_ECONOMY', 'BUSINESS', 'FIRST'},
        )
        self.assertEqual(
            {value for value, _ in BookingStageChoices.choices},
            {'INQUIRY', 'BOOKED', 'CONFIRMED', 'COMPLETED', 'CANCELLED'},
        )


class MinimalRecordTests(TestCase):
    """Only the required fields - the lean record must actually be possible."""

    def setUp(self):
        self.company = make_company()
        self.customer = make_customer(self.company)

    def test_minimal_ticket(self):
        booking = TicketingBooking.objects.create(
            company=self.company,
            customer=self.customer,
            passenger_name='A Passenger',
            pnr='AAA111',
            airline='PIA',
            origin='KHI',
            destination='JED',
        )
        self.assertEqual(booking.booking_reference, '')
        self.assertEqual(booking.e_ticket_number, '')
        self.assertIsNone(booking.amount)
        self.assertIsNone(booking.sales_agent)
        self.assertEqual(booking.notes, '')
        self.assertEqual(booking.attachments.count(), 0)

    def test_minimal_hotel_and_transport(self):
        hotel = HotelBooking.objects.create(
            company=self.company,
            customer=self.customer,
            lead_guest_name='A Guest',
            hotel_name='Hilton Makkah',
            city='Makkah',
            room_type='Double',
        )
        transport = TransportBooking.objects.create(
            company=self.company,
            customer=self.customer,
            service_type='INTERCITY',
            pickup_location='Makkah',
            dropoff_location='Madinah',
            pickup_time='07:00',
            number_of_passengers=2,
            vehicle_type='Sedan',
        )

        self.assertEqual(hotel.country, '')
        self.assertEqual(hotel.occupancy_type, '')
        self.assertEqual(transport.lead_passenger_name, '')
        self.assertEqual(transport.supplier_vendor, '')

    def test_minimal_trip_records(self):
        hajj = HajjBooking.objects.create(
            company=self.company,
            customer=self.customer,
            hajj_year='2026',
            package_name='Economy Hajj',
        )
        umrah = UmrahBooking.objects.create(
            company=self.company,
            customer=self.customer,
            umrah_year_season='Ramadan 2026',
            package_name='Umrah Plus',
        )
        tour = TourBooking.objects.create(
            company=self.company,
            customer=self.customer,
            tour_name='Northern Pakistan',
            destination_country='Pakistan',
        )

        for record in (hajj, umrah, tour):
            with self.subTest(model=type(record).__name__):
                self.assertIsNone(record.package)
                self.assertEqual(record.currency, 'PKR')
                self.assertEqual(record.notes, '')
