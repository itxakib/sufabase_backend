"""CSV import that opens a Hajj booking from an application id and a passport."""

from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase

from bookings.models import HajjBooking
from common.tests.factories import make_company, make_user
from common.tests.mixins import CompanyHeaderMixin
from customers.models import Customer

IMPORT_URL = '/api/v1/hajj/import/'
TEMPLATE_URL = '/api/v1/hajj/import-template/'


def _csv(text):
    return SimpleUploadedFile('hajj.csv', text.encode('utf-8'), content_type='text/csv')


class HajjApplicationImportTests(CompanyHeaderMixin, APITestCase):
    def setUp(self):
        self.company = make_company(name='Alpha Travel', slug='alpha-travel')
        self.other = make_company(name='Beta Tours', slug='beta-tours')
        self.user = make_user(company=self.company, username='hajj-importer')
        self.client.force_authenticate(self.user)
        super().setUp()
        self.customer = Customer.objects.create(
            company=self.company,
            full_name='Ahmed Khan',
            phone='03001234567',
            passport_number='AB1234567',
        )

    def test_template_is_the_two_columns(self):
        response = self.client.get(TEMPLATE_URL)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertTrue(body.startswith('application_number,passport_number'))
        self.assertIn('AB1234567', body)

    def test_matching_passport_creates_a_hajj_booking(self):
        response = self.client.post(
            IMPORT_URL,
            {'file': _csv('application_number,passport_number\nHAJJ-99,AB1234567\n'), 'hajj_year': '2026'},
            format='multipart',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['created'], 1)
        booking = HajjBooking.objects.get()
        self.assertEqual(booking.customer_id, self.customer.pk)
        self.assertEqual(booking.application_number, 'HAJJ-99')
        self.assertEqual(booking.hajj_year, '2026')
        self.assertEqual(booking.package_name, 'Hajj 2026')
        self.assertTrue(booking.booking_reference.startswith('HJ-'))

    def test_passport_match_ignores_spaces_and_case(self):
        self.customer.passport_number = 'ab 1234567'
        self.customer.save(update_fields=['passport_number'])
        response = self.client.post(
            IMPORT_URL,
            {'file': _csv('Passport Number,Hajj Application ID\nAB-1234567,APP-1\n'), 'hajj_year': '2027'},
            format='multipart',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['created'], 1)
        self.assertEqual(HajjBooking.objects.get().application_number, 'APP-1')

    def test_unknown_passport_is_reported_and_creates_nothing(self):
        response = self.client.post(
            IMPORT_URL,
            {'file': _csv('application_number,passport_number\nHAJJ-1,ZZ9999999\n'), 'hajj_year': '2026'},
            format='multipart',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['created'], 0)
        self.assertEqual(response.data['errors'][0]['row'], 1)
        self.assertIn('No customer', response.data['errors'][0]['errors']['passport_number'])
        self.assertFalse(HajjBooking.objects.exists())

    def test_another_tenants_passport_is_not_a_match(self):
        Customer.objects.create(
            company=self.other,
            full_name='Other Person',
            phone='03007654321',
            passport_number='ZZ9999999',
        )
        response = self.client.post(
            IMPORT_URL,
            {'file': _csv('application_number,passport_number\nHAJJ-1,ZZ9999999\n'), 'hajj_year': '2026'},
            format='multipart',
        )
        self.assertEqual(response.data['created'], 0)
        self.assertFalse(HajjBooking.objects.exists())

    def test_importing_the_same_application_again_skips_it(self):
        payload = {'file': _csv('application_number,passport_number\nHAJJ-99,AB1234567\n'), 'hajj_year': '2026'}
        first = self.client.post(IMPORT_URL, payload, format='multipart')
        self.assertEqual(first.data['created'], 1)
        payload['file'] = _csv('application_number,passport_number\nHAJJ-99,AB1234567\n')
        second = self.client.post(IMPORT_URL, payload, format='multipart')
        self.assertEqual(second.data['created'], 0)
        self.assertEqual(second.data['skipped'], 1)
        self.assertEqual(HajjBooking.objects.count(), 1)

    def test_missing_columns_reject_the_file(self):
        response = self.client.post(
            IMPORT_URL,
            {'file': _csv('name,phone\nAhmed,0300\n'), 'hajj_year': '2026'},
            format='multipart',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('application_number', response.data['detail'])
