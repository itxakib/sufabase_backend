"""Catalog templates store specs only, and never a booked guest or ticket."""

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APITestCase

from bookings.models import Package
from catalog.models import PackageTemplate, PackageTemplateLine
from common.tests.factories import make_attachment, make_company, make_user
from common.tests.mixins import CompanyHeaderMixin, MediaRootMixin


def hotel_line(**overrides):
    payload = {
        'kind': 'HOTEL',
        'city': 'Makkah',
        'room_type': 'Quad',
        'meal_plan': 'BREAKFAST',
        'nights': 5,
    }
    payload.update(overrides)
    return payload


class PackageTemplateModelTests(TestCase):
    def setUp(self):
        self.company = make_company()
        self.template = PackageTemplate.objects.create(company=self.company, name='Economy Hajj')

    def test_a_hotel_line_saves_with_specs_only(self):
        line = PackageTemplateLine(
            company=self.company,
            template=self.template,
            **hotel_line(),
        )
        line.full_clean()
        line.save()

        self.assertEqual(line.city, 'Makkah')
        self.assertEqual(line.room_type, 'Quad')
        stored = {field.name for field in PackageTemplateLine._meta.local_fields}
        self.assertTrue({
            'pnr', 'lead_guest_name', 'passenger_name', 'number_of_adults', 'price',
        }.isdisjoint(stored))

    def test_a_hotel_line_cannot_carry_a_cabin_or_a_vehicle(self):
        line = PackageTemplateLine(
            company=self.company,
            template=self.template,
            **hotel_line(cabin_class='ECONOMY', vehicle_type='Coaster'),
        )

        with self.assertRaises(ValidationError) as caught:
            line.full_clean()

        self.assertIn('cabin_class', caught.exception.message_dict)
        self.assertIn('vehicle_type', caught.exception.message_dict)

    def test_a_flight_line_requires_cabin_and_route(self):
        line = PackageTemplateLine(
            company=self.company,
            template=self.template,
            kind='FLIGHT',
            cabin_class='ECONOMY',
            route='LHE-JED',
        )
        line.full_clean()
        line.save()
        self.assertEqual(self.template.lines.count(), 1)

    def test_the_database_rejects_a_mixed_line(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PackageTemplateLine.objects.create(
                    company=self.company,
                    template=self.template,
                    kind='TRANSPORT',
                    vehicle_type='Coaster',
                    city='Makkah',
                )

    def test_deleting_a_template_deletes_its_lines_and_unlinks_bundles(self):
        PackageTemplateLine.objects.create(
            company=self.company, template=self.template, **hotel_line(),
        )
        bundle = Package.objects.create(
            company=self.company, name='Ahmed July', template=self.template,
        )

        self.template.delete()
        bundle.refresh_from_db()

        self.assertIsNone(bundle.template)
        self.assertTrue(Package.objects.filter(pk=bundle.pk).exists())
        self.assertEqual(PackageTemplateLine.objects.count(), 0)

    def test_a_bundle_cannot_point_at_another_companys_template(self):
        other = make_company()
        bundle = Package(company=other, name='Wrong tenant', template=self.template)

        with self.assertRaises(ValidationError) as caught:
            bundle.full_clean()

        self.assertIn('template', caught.exception.message_dict)

    def test_a_template_can_hold_attachments(self):
        self.assertTrue(hasattr(PackageTemplate, 'attachments'))
        attachment = make_attachment(
            company=self.company,
            target=self.template,
            name='brochure.pdf',
            doc_type='Brochure',
        )
        self.assertEqual(list(self.template.attachments.all()), [attachment])


class PackageTemplateApiTests(CompanyHeaderMixin, APITestCase):
    def setUp(self):
        self.company = make_company()
        self.user = make_user(company=self.company)
        self.client.force_authenticate(user=self.user)
        super().setUp()

    def test_create_accepts_spec_lines_and_no_guest_data(self):
        response = self.client.post('/api/v1/package-templates/', {
            'name': 'Ramadan Umrah',
            'notes': 'Quad sharing, economy, coaster',
            'lines': [
                hotel_line(),
                {'kind': 'FLIGHT', 'cabin_class': 'ECONOMY', 'route': 'LHE-JED'},
                {'kind': 'TRANSPORT', 'vehicle_type': 'Coaster'},
            ],
        }, format='json')

        self.assertEqual(response.status_code, 201, response.json())
        data = response.json()['data']
        self.assertEqual(len(data['lines']), 3)
        self.assertNotIn('pnr', data)
        self.assertNotIn('lead_guest_name', data)
        self.assertNotIn('price', data)

    def test_a_hotel_line_with_a_cabin_is_rejected(self):
        response = self.client.post('/api/v1/package-templates/', {
            'name': 'Bad line',
            'lines': [hotel_line(cabin_class='BUSINESS')],
        }, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(PackageTemplate.objects.count(), 0)

    def test_omitting_lines_on_patch_keeps_them(self):
        created = self.client.post('/api/v1/package-templates/', {
            'name': 'Keep lines',
            'lines': [hotel_line()],
        }, format='json').json()['data']

        updated = self.client.patch(
            f"/api/v1/package-templates/{created['id']}/",
            {'name': 'Renamed'},
            format='json',
        ).json()['data']

        self.assertEqual(updated['name'], 'Renamed')
        self.assertEqual(len(updated['lines']), 1)

    def test_another_tenants_template_is_not_readable(self):
        created = self.client.post('/api/v1/package-templates/', {
            'name': 'Ours',
        }, format='json').json()['data']
        outsider = make_user(company=make_company())
        self.client.force_authenticate(user=outsider)
        self.client.credentials(HTTP_X_COMPANY_ID=str(outsider.company_id))

        response = self.client.get(f"/api/v1/package-templates/{created['id']}/")

        self.assertEqual(response.status_code, 404)


class PackageTemplateAttachmentApiTests(MediaRootMixin, CompanyHeaderMixin, APITestCase):
    def setUp(self):
        self.company = make_company()
        self.user = make_user(company=self.company)
        self.client.force_authenticate(user=self.user)
        super().setUp()
        self.template = PackageTemplate.objects.create(
            company=self.company, name='Baku medium',
        )

    def test_upload_attaches_a_file_to_the_template(self):
        response = self.client.post(
            f'/api/v1/package-templates/{self.template.pk}/attachments/',
            {
                'file': SimpleUploadedFile('itinerary.pdf', b'%PDF-1.4 test'),
                'doc_type': 'Itinerary',
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, 201, response.json())
        data = response.json()['data']
        self.assertEqual(data['content_type'], 'catalog.packagetemplate')
        self.assertEqual(data['object_id'], self.template.pk)
        self.assertEqual(data['doc_type'], 'Itinerary')
        self.assertEqual(data['file_name'], 'itinerary.pdf')
        self.assertEqual(self.template.attachments.count(), 1)

    def test_list_returns_files_for_this_template_only(self):
        other = PackageTemplate.objects.create(company=self.company, name='Other')
        make_attachment(company=self.company, target=self.template, name='ours.pdf')
        make_attachment(company=self.company, target=other, name='theirs.pdf')

        response = self.client.get(
            f'/api/v1/package-templates/{self.template.pk}/attachments/',
        )

        self.assertEqual(response.status_code, 200, response.json())
        names = {row['file_name'] for row in response.json()['data']}
        self.assertEqual(names, {'ours.pdf'})
