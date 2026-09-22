"""Tests for the project-wide exception handling contract.

Two guarantees are pinned here, both of which the frontend depends on:

* a **protected** delete is a `409` that names what blocked it, not a `500`; and
* **every** error body is JSON, including one produced by an unhandled bug.
"""

from django.db.models import ProtectedError
from django.test import TestCase
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.test import APITestCase

from bookings.models import HajjBooking
from common.exception_handler import custom_exception_handler
from common.tests.factories import make_company, make_user
from common.tests.mixins import CompanyHeaderMixin
from customers.models import Customer


class ProtectedDeleteTests(CompanyHeaderMixin, APITestCase):
    """``DELETE`` on a record that other rows point at is a `409`, not a `500`."""

    def setUp(self):
        self.company = make_company()
        self.user = make_user(company=self.company)
        self.customer = Customer.objects.create(
            company=self.company, full_name='Blocked Customer', phone='03001112222',
        )
        self.client.force_authenticate(user=self.user)
        super().setUp()

    def test_deleting_a_customer_with_bookings_is_a_conflict(self):
        HajjBooking.objects.create(
            company=self.company,
            customer=self.customer,
            hajj_year='2026',
            package_name='Economy Hajj',
        )

        response = self.client.delete(f'/api/v1/customers/{self.customer.pk}/')

        self.assertEqual(response.status_code, 409)
        body = response.json()
        self.assertFalse(body['success'])
        self.assertEqual(
            body['message'], 'Cannot delete: other records depend on this one',
        )
        self.assertEqual(body['errors']['blocking_records'], {'HajjBooking': 1})
        # Still there - the failed delete changed nothing.
        self.assertTrue(Customer.objects.filter(pk=self.customer.pk).exists())

    def test_the_conflict_names_the_dependent_model(self):
        """The whole point of the 409 is telling the user what to clear."""
        HajjBooking.objects.create(
            company=self.company,
            customer=self.customer,
            hajj_year='2026',
            package_name='Economy Hajj',
        )

        detail = self.client.delete(
            f'/api/v1/customers/{self.customer.pk}/',
        ).json()['errors']['detail']

        self.assertIn('HajjBooking', detail)
        self.assertIn('archive', detail)

    def test_deleting_a_customer_without_bookings_still_works(self):
        """The protection must be conditional, not a blanket block."""
        response = self.client.delete(f'/api/v1/customers/{self.customer.pk}/')

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Customer.objects.filter(pk=self.customer.pk).exists())


class ExceptionHandlerContractTests(TestCase):
    """Direct tests of the handler, without going through HTTP."""

    def _handle(self, exc):
        return custom_exception_handler(exc, {'view': None, 'request': None})

    def test_drf_exceptions_are_passed_through_untouched(self):
        """A 404 must keep DRF's own detail message, not a generic one."""
        response = self._handle(NotFound())

        self.assertIsInstance(response, Response)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data, {'detail': 'Not found.'})

    def test_drf_validation_errors_keep_their_field_map(self):
        """The frontend renders these next to inputs - shape must survive."""
        response = self._handle(ValidationError({'phone': ['This field is required.']}))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {'phone': ['This field is required.']})

    def test_unhandled_exceptions_become_json_not_html(self):
        """A bug must not break the client's response parsing."""
        response = self._handle(RuntimeError('kaboom'))

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.data, {'detail': 'Internal server error'})
        # The real message is never leaked to the client.
        self.assertNotIn('kaboom', str(response.data))

    def test_protected_error_without_carried_objects_still_maps_to_409(self):
        """Falls back to the generic wording rather than blowing up."""
        response = self._handle(ProtectedError('protected', []))

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data['blocking_records'], {})
