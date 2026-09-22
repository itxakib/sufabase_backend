from rest_framework.test import APIClient, APITestCase

from common.tests.factories import make_company, make_user
from common.tests.mixins import CompanyHeaderMixin
from tenant.models import Company

COMPANIES_URL = '/api/v1/companies/'


class CompanyApiTests(CompanyHeaderMixin, APITestCase):
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
        self.staff = make_user(company=self.alpha)
        self.client.force_authenticate(self.staff)
        self.client.credentials(HTTP_X_COMPANY_ID=str(self.alpha.pk))

    def names(self, response):
        return {row['name'] for row in response.data['results']}

    def test_requires_authentication(self):
        self.assertEqual(APIClient().get(COMPANIES_URL).status_code, 401)

    def test_lists_companies(self):
        response = self.client.get(COMPANIES_URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.names(response), {'Alpha Travel', 'Beta Tours'})

    def test_filters_by_is_active_plan_and_country(self):
        response = self.client.get(COMPANIES_URL, {'is_active': True})
        self.assertEqual(self.names(response), {'Alpha Travel'})

        response = self.client.get(COMPANIES_URL, {'plan': Company.Plan.PREMIUM})
        self.assertEqual(self.names(response), {'Alpha Travel'})

        response = self.client.get(COMPANIES_URL, {'country': 'AE'})
        self.assertEqual(self.names(response), {'Beta Tours'})

    def test_searches_by_name_and_slug(self):
        response = self.client.get(COMPANIES_URL, {'search': 'beta-tours'})
        self.assertEqual(self.names(response), {'Beta Tours'})

        response = self.client.get(COMPANIES_URL, {'search': 'Alpha'})
        self.assertEqual(self.names(response), {'Alpha Travel'})

    def test_retrieves_a_single_company(self):
        response = self.client.get(f'{COMPANIES_URL}{self.alpha.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['slug'], 'alpha-travel')
        self.assertEqual(response.data['plan'], Company.Plan.PREMIUM)

    def test_is_read_only(self):
        payload = {'name': 'Gamma Ltd', 'slug': 'gamma-ltd'}
        self.assertEqual(self.client.post(COMPANIES_URL, payload, format='json').status_code, 405)
        self.assertEqual(
            self.client.patch(f'{COMPANIES_URL}{self.alpha.pk}/', payload, format='json').status_code,
            405,
        )
        self.assertEqual(self.client.delete(f'{COMPANIES_URL}{self.alpha.pk}/').status_code, 405)
        self.assertEqual(Company.objects.count(), 2)

    def test_audit_columns_are_not_exposed(self):
        response = self.client.get(f'{COMPANIES_URL}{self.alpha.pk}/')
        for field in ('created_by', 'updated_by'):
            self.assertNotIn(field, response.data)
