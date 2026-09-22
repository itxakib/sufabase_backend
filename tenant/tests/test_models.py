from django.core.exceptions import ValidationError
from django.db.models import ProtectedError
from django.test import TestCase

from common.tests.factories import make_company, make_user
from tenant.models import Company


class CompanyModelTests(TestCase):
    def test_slug_is_generated_from_the_name_when_blank(self):
        company = make_company(name='SUFA International', slug='')
        self.assertEqual(company.slug, 'sufa-international')

    def test_explicit_slug_is_preserved(self):
        company = make_company(slug='sufa')
        self.assertEqual(company.slug, 'sufa')

    def test_field_defaults(self):
        company = make_company(slug='')
        self.assertEqual(company.plan, Company.Plan.STANDARD)
        self.assertEqual(company.timezone, 'UTC')
        self.assertTrue(company.is_active)
        self.assertIsNone(company.onboarded_at)
        self.assertIsNotNone(company.created_at)
        self.assertIsNotNone(company.updated_at)

    def test_onboarded_at_is_distinct_from_created_at(self):
        company = make_company(slug='')
        self.assertIsNone(company.onboarded_at)
        self.assertIsNotNone(company.created_at)

    def test_timezone_validator_accepts_real_zones(self):
        company = make_company(slug='', timezone='Asia/Riyadh')
        company.full_clean(exclude=['created_by', 'updated_by'])

    def test_timezone_validator_rejects_unknown_zones(self):
        company = make_company(slug='')
        company.timezone = 'Mars/Olympus_Mons'
        with self.assertRaises(ValidationError) as ctx:
            company.full_clean(exclude=['created_by', 'updated_by'])
        self.assertIn('timezone', ctx.exception.error_dict)

    def test_company_cannot_be_hard_deleted_while_staff_reference_it(self):
        """The whole point of PROTECT: accidental deletes fail loudly."""
        company = make_company(slug='')
        make_user(company=company)

        with self.assertRaises(ProtectedError):
            company.delete()

        self.assertTrue(Company.objects.filter(pk=company.pk).exists())

    def test_bare_company_can_still_be_deleted(self):
        """PROTECT is conditional - it must not block genuine cleanup."""
        company = make_company(slug='')
        company.delete()
        self.assertFalse(Company.objects.filter(pk=company.pk).exists())

    def test_deactivating_a_tenant_is_the_supported_retirement_path(self):
        company = make_company(slug='')
        make_user(company=company)

        company.is_active = False
        company.save(update_fields=['is_active'])

        self.assertFalse(Company.objects.get(pk=company.pk).is_active)
