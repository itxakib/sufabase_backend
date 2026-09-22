"""Schema-level tests for the customers app models."""

from django.db import IntegrityError, transaction
from django.test import TestCase

from common.tests.factories import make_company, make_user
from customers.choices import RecordStatusChoices, StageChoices
from customers.models import Customer, Tag


class TagModelTests(TestCase):
    def test_str_returns_name(self):
        company = make_company()
        tag = Tag.objects.create(company=company, name='VIP', color='#ff0000')
        self.assertEqual(str(tag), 'VIP')

    def test_color_is_optional(self):
        field = Tag._meta.get_field('color')
        self.assertTrue(field.blank)
        self.assertFalse(field.null)

    def test_unique_together_per_company(self):
        """Two companies can have a tag with the same name; one company cannot."""
        company_a = make_company()
        company_b = make_company()
        Tag.objects.create(company=company_a, name='VIP')

        # Different company, same name — allowed
        Tag.objects.create(company=company_b, name='VIP')

        # Same company, same name — blocked
        with self.assertRaises(IntegrityError), transaction.atomic():
            Tag.objects.create(company=company_a, name='VIP')

    def test_name_max_length(self):
        field = Tag._meta.get_field('name')
        self.assertEqual(field.max_length, 50)


class CustomerModelTests(TestCase):
    def setUp(self):
        self.company = make_company()

    def test_str_returns_full_name(self):
        customer = Customer.objects.create(
            company=self.company,
            full_name='Hanan Abdul',
            phone='03001234567',
        )
        self.assertEqual(str(customer), 'Hanan Abdul')

    def test_phone_is_required(self):
        """phone has no blank=True, so it cannot be empty."""
        field = Customer._meta.get_field('phone')
        self.assertFalse(field.blank)

    def test_phone_is_indexed(self):
        """phone is the most common lookup — it must be indexed."""
        field = Customer._meta.get_field('phone')
        self.assertTrue(field.db_index)

    def test_company_phone_index_exists(self):
        """Composite index for the common 'company + phone' query path."""
        indexed = [tuple(idx.fields) for idx in Customer._meta.indexes]
        self.assertIn(('company', 'phone'), indexed)

    def test_defaults_are_correct(self):
        customer = Customer.objects.create(
            company=self.company,
            full_name='Test',
            phone='03001234567',
        )
        self.assertEqual(customer.stage, StageChoices.NEW)
        self.assertEqual(customer.record_status, RecordStatusChoices.ACTIVE)

    def test_stage_choices_are_valid(self):
        field = Customer._meta.get_field('stage')
        self.assertEqual(field.max_length, 10)
        valid = {c[0] for c in StageChoices.choices}
        self.assertEqual(valid, {'NEW', 'OLD'})

    def test_record_status_choices_are_valid(self):
        field = Customer._meta.get_field('record_status')
        self.assertEqual(field.max_length, 10)
        valid = {c[0] for c in RecordStatusChoices.choices}
        self.assertEqual(valid, {'ACTIVE', 'INACTIVE', 'ARCHIVED'})

    def test_assigned_agent_can_be_null(self):
        """Not every customer needs an assigned agent — it's nullable."""
        field = Customer._meta.get_field('assigned_agent')
        self.assertTrue(field.null)

    def test_assigned_agent_set_null_on_delete(self):
        """Deleting an agent must not cascade-delete customers."""
        from django.db import models as django_models
        field = Customer._meta.get_field('assigned_agent')
        self.assertIs(field.remote_field.on_delete, django_models.SET_NULL)

    def test_attachments_generic_relation(self):
        """The reverse accessor exists for common.Attachment queries."""
        customer = Customer.objects.create(
            company=self.company,
            full_name='With Attachments',
            phone='03001234567',
        )
        self.assertEqual(customer.attachments.count(), 0)

    def test_tags_many_to_many(self):
        """Tags can be attached via M2M."""
        tag = Tag.objects.create(company=self.company, name='VIP')
        customer = Customer.objects.create(
            company=self.company,
            full_name='Tagged',
            phone='03001234567',
        )
        customer.tags.add(tag)
        self.assertEqual(customer.tags.count(), 1)

    def test_blank_fields_are_truly_blank(self):
        """A lean record should be possible — only company, full_name, phone."""
        customer = Customer.objects.create(
            company=self.company,
            full_name='Minimal',
            phone='03001234567',
        )
        self.assertEqual(customer.father_husband_name, '')
        self.assertEqual(customer.email, '')
        self.assertEqual(customer.passport_number, '')
        self.assertEqual(customer.profession, '')
        self.assertEqual(customer.customer_source, '')
        self.assertEqual(customer.emergency_contact_name, '')
        self.assertEqual(customer.family_group_reference, '')

    def test_inherits_tenant_scoped(self):
        """Customer must be tenant-scoped (company FK from TenantScopedModel)."""
        from common.models import TenantScopedModel
        self.assertTrue(issubclass(Customer, TenantScopedModel))
