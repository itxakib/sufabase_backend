"""Tests for the status-conditional required fields.

These are **data-driven from the rules table** (`bookings/status_rules.py`): every
class below builds its cases by iterating `STATUS_REQUIRED_FIELDS`, so adding a
rule automatically adds the tests that prove all three enforcement layers honour
it. The alternative — hand-writing one test per rule — is how a rule ends up in
the table, in the serializer and in the docstring but not in the database.

Three layers are covered, because each catches a different mistake:

* the **database constraint** is the one that cannot be bypassed, so it is tested
  by attempting a real `INSERT` and expecting an `IntegrityError`;
* the **model's `clean()`** is what gives Django admin a usable error, tested
  through `full_clean()`;
* the **serializer** is what the frontend sees, tested over HTTP for both create
  and partial update.
"""

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APITestCase

from bookings import status_rules
from bookings.choices import BookingStageChoices
from bookings.models import (
    HajjBooking,
    HotelBooking,
    TicketingBooking,
    TourBooking,
    TransportBooking,
    UmrahBooking,
)
from common.tests.factories import make_company, make_user
from common.tests.mixins import CompanyHeaderMixin
from customers.models import Customer


def rule_cases():
    """Yield ``(model, field, status)`` for every rule in the shared table."""
    for model_name, rules in status_rules.STATUS_REQUIRED_FIELDS.items():
        model = apps.get_model('bookings', model_name)
        for status, fields in rules.items():
            for field in fields:
                yield model, field, str(status)


def minimal_fields(model, value_for=None):
    """The smallest set of required fields for ``model``, minus the conditional ones.

    Deliberately excludes every field named in the rules table: these tests are
    about what the status demands, so the base record has to be otherwise valid.
    """
    value_for = value_for or {}
    if model is TicketingBooking:
        fields = {
            'passenger_name': 'A Passenger',
            'airline': 'PIA',
            'origin': 'LHE',
            'destination': 'JED',
        }
    elif model is HotelBooking:
        fields = {'hotel_name': 'Hilton Makkah', 'city': 'Makkah', 'room_type': 'Double'}
    elif model is TransportBooking:
        fields = {
            'service_type': 'ZIYARAT',
            'pickup_location': 'Makkah',
            'dropoff_location': 'Madinah',
            'number_of_passengers': 4,
            'vehicle_type': 'Hiace',
        }
    elif model is TourBooking:
        fields = {'tour_name': 'Northern Tour', 'destination_country': 'Pakistan'}
    elif model is HajjBooking:
        fields = {'hajj_year': '2026', 'package_name': 'Economy Hajj'}
    elif model is UmrahBooking:
        fields = {'umrah_year_season': 'Ramadan 2026', 'package_name': 'Economy Umrah'}
    else:  # pragma: no cover - a new rule on a model with no builder is a test bug
        raise AssertionError(f'No minimal-field builder for {model.__name__}')
    fields.update(value_for)
    return fields


class DatabaseConstraintTests(TestCase):
    """The layer nothing can bypass: a real INSERT that must be rejected."""

    def setUp(self):
        self.company = make_company()
        self.customer = Customer.objects.create(
            company=self.company, full_name='A Customer', phone='03001234567',
        )

    def _make(self, model, **overrides):
        return model.objects.create(
            company=self.company,
            customer=self.customer,
            **{**minimal_fields(model), **overrides},
        )

    def test_every_rule_has_a_database_constraint(self):
        """A rule in the table with no constraint is the drift this catches."""
        for model, field, status in rule_cases():
            with self.subTest(model=model.__name__, field=field, status=status):
                # A blank value plus the demanding status must be refused by the
                # database itself, not just by the API.
                blank = '' if field != 'pickup_time' else None
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        self._make(model, status=status, **{field: blank})

    def test_every_status_the_rule_does_not_list_accepts_a_blank(self):
        """The whole point: a sale-stage record is valid without the value.

        Derived from the table and the model's own choices, so a status added to
        the enum later is covered automatically — including the case where
        someone adds one to the table by mistake and this stops passing.
        """
        for model, field, _demanding in rule_cases():
            demanding = {
                status for name, name_field, status in rule_cases()
                if name is model and name_field == field
            }
            blank = '' if field != 'pickup_time' else None
            for status, _label in model._meta.get_field('status').choices:
                if str(status) in demanding:
                    continue
                with self.subTest(model=model.__name__, field=field, status=status):
                    record = self._make(model, status=str(status), **{field: blank})
                    self.assertTrue(record.pk)

    def test_a_filled_value_is_accepted_at_the_demanding_status(self):
        value_for = {'pickup_time': '06:30:00'}
        for model, field, status in rule_cases():
            with self.subTest(model=model.__name__, field=field, status=status):
                record = self._make(
                    model, status=status, **{field: value_for.get(field, 'FILLED IN')},
                )
                self.assertTrue(record.pk)

    def test_the_constraint_does_not_over_reach(self):
        """A model with no rules must stay createable with its conditional field blank."""
        # Tour has a `status` and no rules; nothing about it should be conditional.
        self.assertNotIn('TourBooking', status_rules.STATUS_REQUIRED_FIELDS)
        tour = self._make(TourBooking, status=BookingStageChoices.COMPLETED)
        self.assertTrue(tour.pk)
        # And Hajj, which has a `status` the enum reserves no rules for either.
        hajj = self._make(HajjBooking, status=BookingStageChoices.COMPLETED)
        self.assertTrue(hajj.pk)


class ModelCleanTests(TestCase):
    """Django admin's path: `full_clean()` must report a field-level error."""

    def setUp(self):
        self.company = make_company()
        self.customer = Customer.objects.create(
            company=self.company, full_name='A Customer', phone='03001234567',
        )

    def test_full_clean_rejects_a_missing_field_at_the_demanding_status(self):
        for model, field, status in rule_cases():
            with self.subTest(model=model.__name__, field=field, status=status):
                record = model(
                    company=self.company,
                    customer=self.customer,
                    status=status,
                    **minimal_fields(model),
                )
                with self.assertRaises(ValidationError) as caught:
                    record.full_clean()
                self.assertIn(field, caught.exception.message_dict)

    def test_full_clean_passes_before_that_status(self):
        ticket = TicketingBooking(
            company=self.company,
            customer=self.customer,
            status='RESERVED',
            pnr='',
            **minimal_fields(TicketingBooking),
        )

        ticket.full_clean()  # must not raise
        ticket.save()
        self.assertEqual(ticket.pnr, '')

    def test_the_error_message_says_which_status_demands_it(self):
        """A bare "This field is required" would not explain *when* it is needed."""
        ticket = TicketingBooking(status='ISSUED', pnr='')

        with self.assertRaises(ValidationError) as caught:
            status_rules.check_instance(ticket)

        self.assertIn('ISSUED', caught.exception.message_dict['pnr'][0])

    def test_the_helper_is_a_no_op_for_a_model_with_no_rules(self):
        """Hajj has an entry-less table slot, not a missing one - must not raise."""
        hajj = HajjBooking(
            company=self.company, customer=self.customer, status='CONFIRMED',
            hajj_year='2026', package_name='Economy Hajj',
        )

        status_rules.check_instance(hajj)  # must not raise

        self.assertEqual(status_rules.required_fields_for('HajjBooking', 'CONFIRMED'), ())
        self.assertEqual(status_rules.required_fields_for('NoSuchModel', 'ANY'), ())


class StatusRuleApiTests(CompanyHeaderMixin, APITestCase):
    """What the frontend actually experiences."""

    def setUp(self):
        self.company = make_company()
        self.user = make_user(company=self.company)
        self.customer = Customer.objects.create(
            company=self.company, full_name='Ahmed Khan', phone='03001234567',
        )
        self.client.force_authenticate(user=self.user)
        super().setUp()

    def post(self, path, payload):
        return self.client.post(path, payload, format='json')

    def patch(self, path, payload):
        return self.client.patch(path, payload, format='json')

    def ticket_payload(self, **overrides):
        payload = {
            'customer': self.customer.pk, 'passenger_name': 'Ahmed Khan',
            'airline': 'PIA', 'origin': 'LHE', 'destination': 'JED',
        }
        payload.update(overrides)
        return payload

    # ── Ticketing ────────────────────────────────────────────────────────────

    def test_a_reserved_ticket_can_be_sold_without_a_pnr(self):
        response = self.post('/api/v1/ticketing/', self.ticket_payload())

        self.assertEqual(response.status_code, 201, response.json())
        self.assertEqual(response.json()['data']['pnr'], '')
        self.assertEqual(response.json()['data']['status'], 'RESERVED')

    def test_an_issued_ticket_cannot_be_sold_without_a_pnr(self):
        response = self.post(
            '/api/v1/ticketing/', self.ticket_payload(status='ISSUED'),
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('pnr', response.json()['errors'])
        self.assertIn('ISSUED', response.json()['errors']['pnr'][0])
        self.assertEqual(TicketingBooking.objects.count(), 0)

    def test_a_ticket_can_be_issued_once_the_pnr_is_recorded(self):
        created = self.post('/api/v1/ticketing/', self.ticket_payload()).json()['data']

        response = self.patch(
            f"/api/v1/ticketing/{created['id']}/",
            {'pnr': 'ABC123', 'status': 'ISSUED'},
        )

        self.assertEqual(response.status_code, 200, response.json())
        self.assertEqual(response.json()['data']['pnr'], 'ABC123')

    def test_issuing_a_pnr_less_ticket_is_refused(self):
        """The partial-update direction: status changes, the PNR is still absent."""
        created = self.post('/api/v1/ticketing/', self.ticket_payload()).json()['data']

        response = self.patch(
            f"/api/v1/ticketing/{created['id']}/", {'status': 'ISSUED'},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('pnr', response.json()['errors'])

    def test_recording_the_pnr_alone_does_not_demand_the_ticket_be_issued(self):
        """The rule is one-directional: the status demands the field, not the reverse."""
        created = self.post('/api/v1/ticketing/', self.ticket_payload()).json()['data']

        response = self.patch(
            f"/api/v1/ticketing/{created['id']}/", {'pnr': 'ABC123'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['status'], 'RESERVED')

    def test_the_price_determining_fields_are_still_always_required(self):
        """`airline`, `origin`, `destination` are needed to quote - not conditional."""
        for field in ('airline', 'origin', 'destination', 'passenger_name'):
            with self.subTest(field=field):
                payload = self.ticket_payload()
                payload.pop(field)
                response = self.post('/api/v1/ticketing/', payload)
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.json()['errors'])

    # ── Hotel ────────────────────────────────────────────────────────────────

    def hotel_payload(self, **overrides):
        payload = {
            'customer': self.customer.pk, 'hotel_name': 'Hilton Makkah',
            'city': 'Makkah', 'room_type': 'Double',
        }
        payload.update(overrides)
        return payload

    def test_a_group_booking_can_be_taken_without_a_guest_name(self):
        response = self.post('/api/v1/hotels/', self.hotel_payload())

        self.assertEqual(response.status_code, 201, response.json())
        self.assertEqual(response.json()['data']['lead_guest_name'], '')
        self.assertEqual(response.json()['data']['status'], 'INQUIRY')

    def test_confirming_a_stay_without_a_guest_name_is_refused(self):
        created = self.post('/api/v1/hotels/', self.hotel_payload()).json()['data']

        response = self.patch(
            f"/api/v1/hotels/{created['id']}/", {'status': 'CONFIRMED'},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('lead_guest_name', response.json()['errors'])

    def test_confirming_with_a_guest_name_succeeds(self):
        created = self.post(
            '/api/v1/hotels/',
            self.hotel_payload(lead_guest_name='Ahmed Khan', status='CONFIRMED'),
        )

        self.assertEqual(created.status_code, 201, created.json())

    def test_room_type_is_always_required_because_it_is_priced_on(self):
        payload = self.hotel_payload()
        payload.pop('room_type')

        response = self.post('/api/v1/hotels/', payload)

        self.assertEqual(response.status_code, 400)
        self.assertIn('room_type', response.json()['errors'])

    # ── Transport ────────────────────────────────────────────────────────────

    def transport_payload(self, **overrides):
        payload = {
            'customer': self.customer.pk, 'service_type': 'AIRPORT_TRANSFER',
            'pickup_location': 'JED', 'dropoff_location': 'Makkah',
            'number_of_passengers': 4, 'vehicle_type': 'Hiace',
        }
        payload.update(overrides)
        return payload

    def test_a_transfer_can_be_booked_before_the_pickup_time_is_known(self):
        response = self.post('/api/v1/transport/', self.transport_payload())

        self.assertEqual(response.status_code, 201, response.json())
        self.assertIsNone(response.json()['data']['pickup_time'])

    def test_assigning_a_driver_without_a_pickup_time_is_refused(self):
        created = self.post('/api/v1/transport/', self.transport_payload()).json()['data']

        response = self.patch(
            f"/api/v1/transport/{created['id']}/", {'status': 'DRIVER_ASSIGNED'},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('pickup_time', response.json()['errors'])

    def test_setting_the_time_and_the_status_together_succeeds(self):
        created = self.post('/api/v1/transport/', self.transport_payload()).json()['data']

        response = self.patch(
            f"/api/v1/transport/{created['id']}/",
            {'pickup_time': '06:30:00', 'status': 'DRIVER_ASSIGNED'},
        )

        self.assertEqual(response.status_code, 200, response.json())

    def test_confirming_a_vehicle_does_not_yet_demand_the_time(self):
        """CONFIRMED means the vehicle is booked, not that dispatch is scheduled."""
        created = self.post('/api/v1/transport/', self.transport_payload()).json()['data']

        response = self.patch(
            f"/api/v1/transport/{created['id']}/", {'status': 'CONFIRMED'},
        )

        self.assertEqual(response.status_code, 200, response.json())


class UnaffectedModelsTests(CompanyHeaderMixin, APITestCase):
    """Models outside the rules table must behave exactly as before."""

    def setUp(self):
        self.company = make_company()
        self.user = make_user(company=self.company)
        self.customer = Customer.objects.create(
            company=self.company, full_name='Ahmed Khan', phone='03001234567',
        )
        self.client.force_authenticate(user=self.user)
        super().setUp()

    def test_hajj_still_creates_at_any_stage_without_an_extra_field(self):
        for status, _label in BookingStageChoices.choices:
            with self.subTest(status=status):
                response = self.client.post('/api/v1/hajj/', {
                    'customer': self.customer.pk, 'hajj_year': '2026',
                    'package_name': 'Economy Hajj', 'status': status,
                }, format='json')

                self.assertEqual(response.status_code, 201, response.json())

    def test_umrah_and_tour_are_unaffected(self):
        umrah = self.client.post('/api/v1/umrah/', {
            'customer': self.customer.pk, 'umrah_year_season': 'Ramadan 2026',
            'package_name': 'Economy Umrah', 'status': 'CONFIRMED',
        }, format='json')
        tour = self.client.post('/api/v1/tours/', {
            'customer': self.customer.pk, 'tour_name': 'Northern Tour',
            'destination_country': 'Pakistan', 'status': 'CONFIRMED',
        }, format='json')

        self.assertEqual(umrah.status_code, 201, umrah.json())
        self.assertEqual(tour.status_code, 201, tour.json())
