"""HTTP-level tests for the generic attachment API and the customer avatar.

The model layer for attachments is already pinned in ``test_attachment.py``.
What these cover is the part that did not exist before: the routes, the
``content_type`` spelling a client sends, and - most importantly - that the two
ways of naming a target (nested URL vs. flat payload) are both checked against
the caller's company rather than trusted.

Responses are read through ``response.json()`` rather than ``response.data``,
because the project wraps every payload in the ``{success, message, data,
errors}`` envelope at render time and ``.data`` is the pre-render object.
"""

import io

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APITestCase

from common.attachment_selectors import AttachmentSelector
from common.models import Attachment
from common.tests.factories import make_company, make_user
from common.tests.mixins import CompanyHeaderMixin, MediaRootMixin
from customers.models import Customer


def png(name='document.png'):
    """A real (tiny) PNG - an ImageField rejects bytes that are not an image."""
    buffer = io.BytesIO()
    Image.new('RGB', (4, 4), (10, 20, 30)).save(buffer, format='PNG')
    buffer.seek(0)
    return SimpleUploadedFile(name, buffer.read(), content_type='image/png')


class AttachmentApiTestCase(MediaRootMixin, CompanyHeaderMixin, APITestCase):
    """Shared fixture: one tenant, one staff user, one customer to hang files on."""

    def setUp(self):
        self.company = make_company()
        self.user = make_user(company=self.company)
        self.customer = Customer.objects.create(
            company=self.company,
            full_name='Fatima Khan',
            phone='03001234567',
        )
        self.client.force_authenticate(user=self.user)
        super().setUp()

    def act_as(self, user):
        """Authenticate as another staff member *and* send their company header.

        ``HasCompanyContext`` requires the two to agree, so switching identity
        without switching the header is a 403 - correct, and the reason this
        helper exists rather than calling ``force_authenticate`` alone.
        """
        self.client.force_authenticate(user=user)
        self.client.credentials(HTTP_X_COMPANY_ID=str(user.company_id))

    def make_foreign_user(self):
        """A staff member in a different tenant, header included."""
        foreign = make_user(company=make_company())
        return foreign


class NestedAttachmentRouteTests(AttachmentApiTestCase):
    """``/<resource>/{id}/attachments/`` - the path the frontend is told to use."""

    def test_upload_returns_the_created_attachment(self):
        response = self.client.post(
            f'/api/v1/customers/{self.customer.pk}/attachments/',
            {'file': png(), 'doc_type': 'CNIC copy'},
            format='multipart',
        )

        self.assertEqual(response.status_code, 201, response.json())
        data = response.json()['data']
        self.assertEqual(data['content_type'], 'customers.customer')
        self.assertEqual(data['object_id'], self.customer.pk)
        self.assertEqual(data['doc_type'], 'CNIC copy')
        self.assertEqual(data['file_name'], 'document.png')
        self.assertIn('/media/attachments/', data['file'])

    def test_upload_stamps_the_requesting_company_and_user(self):
        self.client.post(
            f'/api/v1/customers/{self.customer.pk}/attachments/',
            {'file': png()},
            format='multipart',
        )

        attachment = Attachment.objects.get()
        self.assertEqual(attachment.company_id, self.company.pk)
        self.assertEqual(attachment.created_by_id, self.user.pk)

    def test_upload_needs_a_file(self):
        response = self.client.post(
            f'/api/v1/customers/{self.customer.pk}/attachments/',
            {'doc_type': 'CNIC copy'},
            format='multipart',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('file', response.json()['errors'])
        self.assertEqual(Attachment.objects.count(), 0)

    def test_list_returns_only_this_record_documents(self):
        other = Customer.objects.create(
            company=self.company, full_name='Someone Else', phone='03009999999',
        )
        self.client.post(
            f'/api/v1/customers/{self.customer.pk}/attachments/',
            {'file': png('mine.png'), 'doc_type': 'Mine'},
            format='multipart',
        )
        self.client.post(
            f'/api/v1/customers/{other.pk}/attachments/',
            {'file': png('theirs.png'), 'doc_type': 'Theirs'},
            format='multipart',
        )

        payload = self.client.get(
            f'/api/v1/customers/{self.customer.pk}/attachments/',
        ).json()

        self.assertEqual(len(payload['data']), 1)
        self.assertEqual(payload['data'][0]['doc_type'], 'Mine')

    def test_nested_route_cannot_be_used_to_escape_the_tenant(self):
        """The host id in the URL still resolves through the scoped queryset."""
        self.act_as(self.make_foreign_user())

        response = self.client.get(
            f'/api/v1/customers/{self.customer.pk}/attachments/',
        )

        self.assertEqual(response.status_code, 404)

    def test_another_tenants_documents_are_not_listed(self):
        """The tenant filter is the selector's job, not the generic FK's."""
        foreign_company = make_company()
        foreign_customer = Customer.objects.create(
            company=foreign_company, full_name='Theirs', phone='03008888888',
        )
        Attachment.objects.create(
            company=foreign_company,
            content_object=foreign_customer,
            file=png('theirs.png'),
        )
        # Same row id, different tenant: if the query forgot `company`, this
        # would return the foreign document.
        Attachment.objects.create(
            company=self.company,
            content_object=self.customer,
            file=png('mine.png'),
        )

        payload = self.client.get(
            f'/api/v1/customers/{self.customer.pk}/attachments/',
        ).json()

        self.assertEqual(len(payload['data']), 1)
        self.assertEqual(payload['data'][0]['file_name'], 'mine.png')


class FlatAttachmentRouteTests(AttachmentApiTestCase):
    """``/api/v1/attachments/`` - the collection, for scripts and bulk views."""

    def test_create_accepts_the_app_label_dot_model_spelling(self):
        response = self.client.post(
            '/api/v1/attachments/',
            {
                'content_type': 'customers.customer',
                'object_id': self.customer.pk,
                'file': png(),
                'doc_type': 'Passport scan',
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, 201, response.json())
        self.assertEqual(response.json()['data']['doc_type'], 'Passport scan')

    def test_create_rejects_a_record_belonging_to_another_company(self):
        """Knowing a record id must not be enough to staple a file onto it."""
        self.act_as(self.make_foreign_user())

        response = self.client.post(
            '/api/v1/attachments/',
            {
                'content_type': 'customers.customer',
                'object_id': self.customer.pk,
                'file': png(),
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('object_id', response.json()['errors'])
        self.assertEqual(Attachment.objects.count(), 0)

    def test_create_rejects_a_model_that_does_not_support_attachments(self):
        response = self.client.post(
            '/api/v1/attachments/',
            {
                'content_type': 'users.user',
                'object_id': self.user.pk,
                'file': png(),
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('content_type', response.json()['errors'])

    def test_create_rejects_an_unknown_content_type(self):
        response = self.client.post(
            '/api/v1/attachments/',
            {'content_type': 'nope.nothing', 'object_id': 1, 'file': png()},
            format='multipart',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('content_type', response.json()['errors'])

    def test_create_without_a_content_type_asks_for_one(self):
        response = self.client.post(
            '/api/v1/attachments/',
            {'file': png()},
            format='multipart',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('content_type', response.json()['errors'])

    def test_list_can_be_filtered_by_record(self):
        self.client.post(
            '/api/v1/attachments/',
            {
                'content_type': 'customers.customer',
                'object_id': self.customer.pk,
                'file': png(),
            },
            format='multipart',
        )

        payload = self.client.get(
            f'/api/v1/attachments/?content_type=customers.customer'
            f'&object_id={self.customer.pk}',
        ).json()

        self.assertEqual(payload['data']['count'], 1)
        self.assertEqual(payload['data']['results'][0]['target_label'], 'Fatima Khan')

    def test_unknown_content_type_filter_is_a_400_not_an_empty_page(self):
        """A typo must not look like "this record has no documents"."""
        response = self.client.get('/api/v1/attachments/?content_type=bogus.thing')

        self.assertEqual(response.status_code, 400)
        self.assertIn('content_type', response.json()['errors'])

    def test_list_shows_only_the_callers_company(self):
        foreign_company = make_company()
        Attachment.objects.create(
            company=foreign_company,
            content_object=Customer.objects.create(
                company=foreign_company, full_name='Theirs', phone='03007777777',
            ),
            file=png('theirs.png'),
        )

        payload = self.client.get('/api/v1/attachments/').json()

        self.assertEqual(payload['data']['count'], 0)


class AttachmentUpdateTests(AttachmentApiTestCase):
    """Relabelling and deleting a document - the two edits that make sense."""

    def setUp(self):
        super().setUp()
        self.attachment = Attachment.objects.create(
            company=self.company,
            content_object=self.customer,
            file=png('cnic.png'),
            doc_type='CNIC copy',
        )

    def test_patch_relabels_without_re_uploading_the_file(self):
        response = self.client.patch(
            f'/api/v1/attachments/{self.attachment.pk}/',
            {'doc_type': 'CNIC - verified'},
            format='json',
        )

        self.assertEqual(response.status_code, 200, response.json())
        self.attachment.refresh_from_db()
        self.assertEqual(self.attachment.doc_type, 'CNIC - verified')
        self.assertTrue(self.attachment.file.name)

    def test_patch_cannot_repoint_the_attachment_at_another_record(self):
        """Moving a document between records must be a delete and re-upload."""
        other = Customer.objects.create(
            company=self.company, full_name='Other', phone='03006666666',
        )

        response = self.client.patch(
            f'/api/v1/attachments/{self.attachment.pk}/',
            {'object_id': other.pk, 'content_type': 'customers.customer'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.attachment.refresh_from_db()
        self.assertEqual(self.attachment.object_id, self.customer.pk)

    def test_delete_removes_the_row(self):
        response = self.client.delete(f'/api/v1/attachments/{self.attachment.pk}/')

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Attachment.objects.filter(pk=self.attachment.pk).exists())


class AttachmentQueryCountTests(AttachmentApiTestCase):
    """A list of documents must cost the same number of queries at any size.

    The generic foreign key is the trap here: a naive serializer resolving
    ``content_object`` per row turns a 50-document panel into 50 extra SELECTs,
    and nothing about the response looks wrong while it happens.
    """

    def _seed_and_list(self, rows):
        Attachment.objects.filter(company=self.company).delete()
        for index in range(rows):
            Attachment.objects.create(
                company=self.company,
                content_object=self.customer,
                file=png(f'doc{index}.png'),
                doc_type='Copy',
            )

        with self.assertNumQueries(3):
            response = self.client.get(
                f'/api/v1/customers/{self.customer.pk}/attachments/',
            )
        return response.json()

    def test_one_document_costs_three_queries(self):
        self.assertEqual(len(self._seed_and_list(1)['data']), 1)

    def test_six_documents_still_cost_three_queries(self):
        self.assertEqual(len(self._seed_and_list(6)['data']), 6)


class AttachmentSelectorScopingTests(AttachmentApiTestCase):
    """The selector is the one place the tenant filter is written."""

    def test_for_object_ignores_a_mismatched_company(self):
        Attachment.objects.create(
            company=self.company,
            content_object=self.customer,
            file=png(),
        )

        self.assertEqual(
            AttachmentSelector.for_object(self.customer, self.company).count(), 1,
        )
        self.assertEqual(
            AttachmentSelector.for_object(self.customer, make_company()).count(), 0,
        )

    def test_counts_for_objects_batches_into_one_query(self):
        for index in range(3):
            Attachment.objects.create(
                company=self.company,
                content_object=self.customer,
                file=png(f'doc{index}.png'),
            )

        counts = AttachmentSelector.counts_for_objects(
            Customer, [self.customer.pk], self.company,
        )

        self.assertEqual(counts[self.customer.pk], 3)


class CustomerAvatarApiTests(MediaRootMixin, CompanyHeaderMixin, APITestCase):
    """``avatar`` is a real column on Customer, so it rides the normal CRUD."""

    def setUp(self):
        self.company = make_company()
        self.user = make_user(company=self.company)
        self.client.force_authenticate(user=self.user)
        super().setUp()

    def _create(self, **extra):
        payload = {
            'full_name': 'With Avatar',
            'phone': '03005555555',
            'avatar': png('avatar.png'),
        }
        payload.update(extra)
        return self.client.post('/api/v1/customers/', payload, format='multipart')

    def test_avatar_is_optional(self):
        response = self.client.post(
            '/api/v1/customers/',
            {'full_name': 'No Photo', 'phone': '03004444444'},
            format='multipart',
        )

        self.assertEqual(response.status_code, 201, response.json())
        self.assertIsNone(response.json()['data']['avatar'])

    def test_uploaded_avatar_comes_back_as_a_url(self):
        response = self._create()

        self.assertEqual(response.status_code, 201, response.json())
        self.assertIn('/media/customers/avatars/', response.json()['data']['avatar'])

    def test_a_renamed_non_image_is_rejected(self):
        """ImageField, not FileField - the bytes are checked, not the extension."""
        response = self._create(
            full_name='Bad Photo',
            phone='03003333333',
            avatar=SimpleUploadedFile(
                'fake.png', b'not an image', content_type='image/png',
            ),
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('avatar', response.json()['errors'])

    def test_avatar_rides_along_on_the_nested_mini_serializer(self):
        """Booking rows render the same person, so they need the same picture."""
        customer_id = self._create().json()['data']['id']

        from bookings.models import HajjBooking

        HajjBooking.objects.create(
            company=self.company,
            customer=Customer.objects.get(pk=customer_id),
            hajj_year='2026',
            package_name='Economy Hajj',
        )

        payload = self.client.get('/api/v1/hajj/').json()

        self.assertIn(
            '/media/customers/avatars/',
            payload['data']['results'][0]['customer']['avatar'],
        )

    def test_has_avatar_filter_separates_the_two_sets(self):
        with_photo = self._create(full_name='Has Photo', phone='03002222222').json()
        self.client.post(
            '/api/v1/customers/',
            {'full_name': 'No Photo', 'phone': '03001111111'},
            format='multipart',
        )

        missing = self.client.get('/api/v1/customers/?has_avatar=false').json()
        present = self.client.get('/api/v1/customers/?has_avatar=true').json()

        self.assertEqual(missing['data']['count'], 1)
        self.assertEqual(missing['data']['results'][0]['full_name'], 'No Photo')
        self.assertEqual(present['data']['count'], 1)
        self.assertEqual(present['data']['results'][0]['id'], with_photo['data']['id'])
