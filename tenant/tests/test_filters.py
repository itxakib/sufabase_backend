"""Filter and search tests for the company (tenant) directory endpoint."""

from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from common.tests.factories import make_company, make_user
from common.tests.mixins import CompanyHeaderMixin
from tenant.models import Company

COMPANIES_URL = '/api/v1/companies/'


class CompanyFilterApiTests(CompanyHeaderMixin, APITestCase):
    def setUp(self):
        self.alpha = make_company(
            name='Alpha Travel',
            slug='alpha-travel',
            plan=Company.Plan.PREMIUM,
            country='SA',
            city='Riyadh',
            contact_email='hello@alpha.test',
            onboarded_at=timezone.now(),
        )
        self.beta = make_company(
            name='Beta Tours',
            slug='beta-tours',
            country='AE',
            city='Dubai',
            is_active=False,
        )
        self.gamma = make_company(
            name='Gamma Holidays',
            slug='gamma-holidays',
            plan=Company.Plan.ENTERPRISE,
            country='SA',
            city='Jeddah',
            onboarded_at=timezone.now(),
        )

        self.staff = make_user(company=self.alpha)
        self.client.force_authenticate(self.staff)
        self.client.credentials(HTTP_X_COMPANY_ID=str(self.alpha.pk))

    def get(self, **params):
        return self.client.get(COMPANIES_URL, params)

    def names(self, response):
        return {row['name'] for row in response.data['results']}

    # ── Identity ─────────────────────────────────────────────────────────────
    def test_lists_every_company(self):
        self.assertEqual(self.names(self.get()), {'Alpha Travel', 'Beta Tours', 'Gamma Holidays'})

    def test_filters_by_name_substring(self):
        self.assertEqual(self.names(self.get(name='trav')), {'Alpha Travel'})

    def test_exact_name_requires_the_whole_value(self):
        self.assertEqual(self.names(self.get(name_exact='Alpha Travel')), {'Alpha Travel'})
        self.assertEqual(self.names(self.get(name_exact='alpha')), set())

    def test_filters_by_slug(self):
        self.assertEqual(self.names(self.get(slug='beta-tours')), {'Beta Tours'})

    # ── Location and contact ─────────────────────────────────────────────────
    def test_filters_by_country(self):
        self.assertEqual(self.names(self.get(country='SA')), {'Alpha Travel', 'Gamma Holidays'})

    def test_filters_by_city_substring(self):
        self.assertEqual(self.names(self.get(city='dub')), {'Beta Tours'})

    def test_filters_by_contact_email(self):
        self.assertEqual(self.names(self.get(contact_email='alpha.test')), {'Alpha Travel'})

    # ── Commercial state ─────────────────────────────────────────────────────
    def test_filters_by_plan(self):
        self.assertEqual(self.names(self.get(plan=Company.Plan.PREMIUM)), {'Alpha Travel'})

    def test_filters_by_a_list_of_plans(self):
        self.assertEqual(
            self.names(self.get(plan_in='premium,enterprise')),
            {'Alpha Travel', 'Gamma Holidays'},
        )

    def test_excludes_a_list_of_plans(self):
        self.assertEqual(
            self.names(self.get(plan_not='standard')),
            {'Alpha Travel', 'Gamma Holidays'},
        )

    def test_an_invalid_plan_is_a_400(self):
        self.assertEqual(self.get(plan='platinum').status_code, 400)

    def test_filters_by_is_active(self):
        self.assertEqual(self.names(self.get(is_active='true')), {'Alpha Travel', 'Gamma Holidays'})
        self.assertEqual(self.names(self.get(is_active='false')), {'Beta Tours'})

    def test_an_invalid_boolean_is_a_400(self):
        self.assertEqual(self.get(is_active='yes').status_code, 400)

    # ── Onboarding ───────────────────────────────────────────────────────────
    def test_filters_companies_that_never_went_live(self):
        """Created but never onboarded - the stuck-in-setup list.

        Distinct from ``is_active=false``: Beta is the only one here with no
        onboarded_at, and the two states answer different questions.
        """
        self.assertEqual(self.names(self.get(onboarded='false')), {'Beta Tours'})

    def test_filters_onboarded_companies(self):
        self.assertEqual(self.names(self.get(onboarded='true')), {'Alpha Travel', 'Gamma Holidays'})

    def test_filters_by_onboarding_window(self):
        yesterday = (timezone.now() - timedelta(days=1)).isoformat()
        tomorrow = (timezone.now() + timedelta(days=1)).isoformat()

        self.assertEqual(self.names(self.get(onboarded_after=yesterday)), {'Alpha Travel', 'Gamma Holidays'})
        self.assertEqual(self.names(self.get(onboarded_after=tomorrow)), set())
        self.assertEqual(self.names(self.get(onboarded_before=tomorrow)), {'Alpha Travel', 'Gamma Holidays'})

    # ── Timestamps, search and ordering ──────────────────────────────────────
    def test_created_after_excludes_backdated_companies(self):
        Company.objects.filter(pk=self.beta.pk).update(
            created_at=timezone.now() - timedelta(days=30),
        )
        cutoff = (timezone.now() - timedelta(days=1)).isoformat()

        self.assertEqual(self.names(self.get(created_after=cutoff)), {'Alpha Travel', 'Gamma Holidays'})

    def test_created_before_keeps_only_backdated_companies(self):
        Company.objects.filter(pk=self.beta.pk).update(
            created_at=timezone.now() - timedelta(days=30),
        )
        cutoff = (timezone.now() - timedelta(days=1)).isoformat()

        self.assertEqual(self.names(self.get(created_before=cutoff)), {'Beta Tours'})

    def test_search_spans_the_contact_and_location_columns(self):
        for term, expected in (
            ('hello@alpha.test', {'Alpha Travel'}),
            ('Dubai', {'Beta Tours'}),
            ('beta-tours', {'Beta Tours'}),
        ):
            with self.subTest(term=term):
                self.assertEqual(self.names(self.get(search=term)), expected)

    def test_ordering_by_name_ascending_and_descending(self):
        ascending = [row['name'] for row in self.get(ordering='name').data['results']]
        descending = [row['name'] for row in self.get(ordering='-name').data['results']]

        self.assertEqual(ascending, ['Alpha Travel', 'Beta Tours', 'Gamma Holidays'])
        self.assertEqual(descending, ['Gamma Holidays', 'Beta Tours', 'Alpha Travel'])

    def test_filters_combine_with_and(self):
        self.assertEqual(self.names(self.get(country='SA', is_active='true')), {'Alpha Travel', 'Gamma Holidays'})
        self.assertEqual(self.names(self.get(country='SA', plan=Company.Plan.PREMIUM)), {'Alpha Travel'})
