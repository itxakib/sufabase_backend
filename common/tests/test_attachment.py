"""Schema-level tests for the generic ``common.Attachment`` model.

No views or serializers exist for attachments yet, so these tests cover the
parts that are already load-bearing: the contenttypes plumbing, tenant scoping,
PROTECT on the company FK, and the upload path.
"""

from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, models, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from common.models import Attachment
from common.tests.factories import make_attachment, make_company, make_user
from common.tests.mixins import MediaRootMixin
from tenant.models import Company


class AttachmentSchemaTests(MediaRootMixin, TestCase):
    def test_content_object_attaches_to_any_model(self):
        """The whole point of the generic FK: no column or table per host model."""
        company = make_company()
        user = make_user(company=company)

        on_company = make_attachment(company=company, target=company, name='voucher.pdf')
        on_user = make_attachment(company=company, target=user, name='cnic.pdf')

        self.assertEqual(on_company.content_object, company)
        self.assertEqual(on_user.content_object, user)
        self.assertNotEqual(on_company.content_type, on_user.content_type)

    def test_records_are_found_by_content_type_and_object_id(self):
        """Until a host model declares a GenericRelation, this is the way in."""
        company = make_company()
        user = make_user(company=company)
        other_user = make_user(company=company)
        mine = make_attachment(company=company, target=user)
        make_attachment(company=company, target=other_user, name='other.pdf')

        found = Attachment.objects.filter(
            content_type=ContentType.objects.get_for_model(user),
            object_id=user.pk,
        )

        self.assertEqual(list(found), [mine])

    def test_index_covers_the_content_type_and_object_id_lookup(self):
        indexed = [tuple(index.fields) for index in Attachment._meta.indexes]
        self.assertIn(('content_type', 'object_id'), indexed)

    def test_upload_path_groups_files_by_year_and_month(self):
        """Keeps a tenant's uploads browsable instead of one flat directory."""
        self.assertEqual(
            Attachment._meta.get_field('file').upload_to,
            'attachments/%Y/%m/',
        )

    def test_file_is_written_under_the_media_root(self):
        company = make_company()
        attachment = make_attachment(
            company=company,
            target=company,
            name='offer-letter.pdf',
        )

        self.assertTrue(attachment.file.storage.exists(attachment.file.name))
        self.assertTrue(attachment.file.name.startswith('attachments/'))
        self.assertTrue(attachment.file.name.endswith('offer-letter.pdf'))

    def test_doc_type_is_optional_but_never_null(self):
        """Module 01 has no document taxonomy; blank, not NULL, keeps queries simple."""
        field = Attachment._meta.get_field('doc_type')
        self.assertTrue(field.blank)
        self.assertFalse(field.null)

    def test_company_is_required(self):
        """A tenant-owned row can never exist without a tenant."""
        company = make_company()

        with self.assertRaises(IntegrityError), transaction.atomic():
            Attachment.objects.create(content_object=company, file='x.pdf')

    def test_company_fk_is_protected_and_accessor_follows_the_shared_pattern(self):
        field = Attachment._meta.get_field('company')
        self.assertIs(field.remote_field.on_delete, models.PROTECT)
        # The abstract base stores the raw pattern (see common tests); Django
        # interpolates it per concrete model, which is what keeps the accessor
        # unique now that several models hang off the same tenant.
        self.assertEqual(field.remote_field.related_name, 'common_attachment_set')
        self.assertEqual(Company.common_attachment_set.field, field)

    def test_deleting_a_company_with_attachments_is_protected(self):
        """One careless delete must not take a tenant's documents with it."""
        company = make_company()
        make_attachment(company=company, target=company)

        with self.assertRaises(ProtectedError):
            company.delete()

        self.assertTrue(Company.objects.filter(pk=company.pk).exists())

    def test_protection_is_scoped_to_the_company_being_deleted(self):
        """Protection is conditional, not a blanket block on deleting companies.

        A company that has never had a document uploaded must still delete
        cleanly - that is what proves the FK is doing the protecting, rather
        than something vetoing all deletes.
        """
        bare = make_company()
        other = make_company()
        make_attachment(company=other, target=other)

        bare.delete()

        self.assertFalse(Company.objects.filter(pk=bare.pk).exists())
        self.assertEqual(Attachment.objects.count(), 1)

    def test_company_is_never_implied_by_the_generic_lookup(self):
        """Selectors must filter ``company`` explicitly - this pins that down.

        ``content_type``/``object_id`` say nothing about the tenant, so a
        cross-tenant leak is one forgotten filter away. If ambient tenant
        scoping is ever introduced (thread-local, middleware, custom manager),
        this test fails and forces that decision to be made in the open.
        """
        company_a = make_company()
        company_b = make_company()
        user_a = make_user(company=company_a)
        user_b = make_user(company=company_b)
        attachment_a = make_attachment(company=company_a, target=user_a)
        make_attachment(company=company_b, target=user_b, name='b.pdf')

        self.assertEqual(
            Attachment.objects.filter(object_id__in=[user_a.pk, user_b.pk]).count(),
            2,
            'the generic lookup is not tenant-aware, so scoping is the selector\'s job',
        )
        self.assertEqual(
            list(Attachment.objects.filter(company=company_a)),
            [attachment_a],
        )

    def test_deleting_the_host_record_leaves_the_attachment_behind(self):
        """A documented consequence of generic FKs, not an endorsement.

        ``object_id`` is a plain integer, so no cascade fires when the host row
        is deleted and the attachment is left dangling. A cleanup step belongs in
        whatever service hard-deletes a host record - this test exists so that
        gap stays visible instead of being discovered in production.
        """
        company = make_company()
        user = make_user(company=company)
        attachment = make_attachment(company=company, target=user)

        user.delete()

        surviving = Attachment.objects.get(pk=attachment.pk)
        self.assertIsNone(surviving.content_object)
