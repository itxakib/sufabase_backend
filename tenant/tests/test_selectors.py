from django.test import TestCase

from common.tests.factories import make_company
from tenant.models import Company
from tenant.selectors.company_selectors import CompanySelector


class CompanySelectorTests(TestCase):
    def setUp(self):
        self.alpha = make_company(
            name='Alpha Travel',
            slug='alpha-travel',
            plan=Company.Plan.PREMIUM,
            country='SA',
        )
        self.beta = make_company(
            name='Beta Tours',
            slug='beta-tours',
            country='AE',
            is_active=False,
        )

    def test_list_companies_returns_everything_ordered_by_name(self):
        self.assertEqual(list(CompanySelector.list_companies()), [self.alpha, self.beta])

    def test_get_active_excludes_inactive_tenants(self):
        self.assertEqual(list(CompanySelector.get_active()), [self.alpha])

    def test_filters_by_is_active_plan_and_country(self):
        self.assertEqual(list(CompanySelector.list_companies(is_active=True)), [self.alpha])
        self.assertEqual(
            list(CompanySelector.list_companies(plan=Company.Plan.PREMIUM)),
            [self.alpha],
        )
        # country matches case-insensitively
        self.assertEqual(list(CompanySelector.list_companies(country='ae')), [self.beta])

    def test_search_matches_name_slug_and_legal_name(self):
        self.assertEqual(list(CompanySelector.list_companies(search='alpha')), [self.alpha])
        self.assertEqual(list(CompanySelector.list_companies(search='beta-tours')), [self.beta])
        self.alpha.legal_name = 'Alpha Travel Group LLC'
        self.alpha.save(update_fields=['legal_name'])
        self.assertEqual(list(CompanySelector.list_companies(search='Group LLC')), [self.alpha])

    def test_get_by_id_and_slug(self):
        self.assertEqual(CompanySelector.get_by_id(self.alpha.pk), self.alpha)
        self.assertEqual(CompanySelector.get_by_slug('beta-tours'), self.beta)

    def test_missing_company_raises_does_not_exist(self):
        with self.assertRaises(Company.DoesNotExist):
            CompanySelector.get_by_slug('does-not-exist')
        with self.assertRaises(Company.DoesNotExist):
            CompanySelector.get_by_id(999999)
