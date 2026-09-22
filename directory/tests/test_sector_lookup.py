"""Tests for the sector lookup the directory filters are built from.

Exercised through the API rather than the query, because what can actually break
is the wiring: the action's URL, the tenant scope, and the shape the frontend
consumes. A unit test on the grouping would pass while ``/sectors/`` still
resolved to the detail route and answered 404.
"""

from rest_framework.test import APITestCase

from common.tests.factories import make_company, make_user
from common.tests.mixins import CompanyHeaderMixin
from directory.models import DirectoryBusinessActivity, DirectoryCompany

SECTORS_URL = '/api/v1/directory-companies/sectors/'
ACTIVITIES_URL = '/api/v1/directory-companies/activities/'
LIST_URL = '/api/v1/directory-companies/'


class DirectorySectorLookupTests(CompanyHeaderMixin, APITestCase):
    """``GET /api/v1/directory-companies/sectors/``."""

    def setUp(self):
        self.company = make_company(name='Alpha Travel', slug='alpha-travel')
        self.other_company = make_company(name='Beta Tours', slug='beta-tours')
        self.user = make_user(company=self.company, username='agent-1')
        self.client.force_authenticate(self.user)
        super().setUp()

        # Two sub-sectors under one sector, plus a row with no sub-sector at all —
        # that third row is what proves a sector's own count is not just the sum of
        # its children.
        self.agriculture_crops = self._company(
            'Crops Ltd', 'AGRICULTURE & HORTICULTURE', 'AGRICULTURAL CROPS & SEEDS'
        )
        self.agriculture_livestock = self._company(
            'Livestock Ltd', 'AGRICULTURE & HORTICULTURE', 'LIVESTOCK & POULTRY'
        )
        self.agriculture_unfiled = self._company(
            'Mixed Farm', 'AGRICULTURE & HORTICULTURE', ''
        )
        self.manufacturing = self._company('Steel Works', 'MANUFACTURING', 'STEEL')

        # A blank sector is not an option anybody can pick, and another tenant's
        # rows are not this tenant's vocabulary.
        self._company('No Sector Ltd', '', '')
        self._company(
            'Other Tenant Ltd', 'OTHER SECTOR', 'OTHER SUB', company=self.other_company
        )

    def _company(self, name, sector, sub_sector, company=None):
        return DirectoryCompany.objects.create(
            company=company or self.company,
            company_name=name,
            business_sector=sector,
            sub_sector=sub_sector,
        )

    def _sectors(self):
        response = self.client.get(SECTORS_URL)
        self.assertEqual(response.status_code, 200, response.data)
        return response.json()['data']

    def test_groups_sub_sectors_under_their_sector(self):
        sectors = {entry['value']: entry for entry in self._sectors()}

        self.assertEqual(sorted(sectors), ['AGRICULTURE & HORTICULTURE', 'MANUFACTURING'])
        self.assertEqual(
            [sub['value'] for sub in sectors['AGRICULTURE & HORTICULTURE']['sub_sectors']],
            ['AGRICULTURAL CROPS & SEEDS', 'LIVESTOCK & POULTRY'],
        )
        self.assertEqual(
            [sub['value'] for sub in sectors['MANUFACTURING']['sub_sectors']], ['STEEL']
        )

    def test_sector_count_includes_rows_with_no_sub_sector(self):
        sectors = {entry['value']: entry for entry in self._sectors()}

        self.assertEqual(sectors['AGRICULTURE & HORTICULTURE']['count'], 3)
        self.assertEqual(sectors['MANUFACTURING']['count'], 1)
        # ...while the child list still holds only the two real sub-sectors.
        self.assertEqual(len(sectors['AGRICULTURE & HORTICULTURE']['sub_sectors']), 2)

    def test_sub_sector_carries_its_own_count(self):
        sectors = {entry['value']: entry for entry in self._sectors()}
        subs = {sub['value']: sub for sub in sectors['AGRICULTURE & HORTICULTURE']['sub_sectors']}

        self.assertEqual(subs['AGRICULTURAL CROPS & SEEDS']['count'], 1)
        self.assertEqual(subs['LIVESTOCK & POULTRY']['label'], 'LIVESTOCK & POULTRY')

    def test_blank_sector_is_not_an_option(self):
        values = [entry['value'] for entry in self._sectors()]
        self.assertNotIn('', values)

    def test_another_tenants_sectors_are_not_offered(self):
        values = [entry['value'] for entry in self._sectors()]
        self.assertNotIn('OTHER SECTOR', values)

    def test_query_parameters_do_not_narrow_the_option_list(self):
        """A filter's own options must not shrink to what that filter matched."""
        response = self.client.get(SECTORS_URL, {'business_sector': 'MANUFACTURING'})
        self.assertEqual(response.status_code, 200)

        values = [entry['value'] for entry in response.json()['data']]
        self.assertEqual(sorted(values), ['AGRICULTURE & HORTICULTURE', 'MANUFACTURING'])

    def test_empty_directory_answers_an_empty_list(self):
        DirectoryCompany.objects.all().delete()
        self.assertEqual(self._sectors(), [])

    def test_requires_a_company_header(self):
        self.client.credentials()
        response = self.client.get(SECTORS_URL)
        self.assertEqual(response.status_code, 403)


class DirectoryActivityFilterTests(CompanyHeaderMixin, APITestCase):
    """Sheet categories (Manufacturers, Importers, …) as a list filter."""

    def setUp(self):
        self.company = make_company(name='Alpha Travel', slug='alpha-travel')
        self.other_company = make_company(name='Beta Tours', slug='beta-tours')
        self.user = make_user(company=self.company, username='agent-1')
        self.client.force_authenticate(self.user)
        super().setUp()

        self.manufacturer = DirectoryCompany.objects.create(
            company=self.company,
            company_name='Agromax',
            business_sector='AGRICULTURE & HORTICULTURE',
            sub_sector='AGRICULTURAL CROPS & SEEDS',
        )
        self.importer = DirectoryCompany.objects.create(
            company=self.company,
            company_name='Steel Traders',
            business_sector='MANUFACTURING',
            sub_sector='STEEL',
        )
        DirectoryBusinessActivity.objects.create(
            company=self.company,
            directory_company=self.manufacturer,
            sheet_name='Manufacturers',
        )
        DirectoryBusinessActivity.objects.create(
            company=self.company,
            directory_company=self.importer,
            sheet_name='Importers',
        )
        other = DirectoryCompany.objects.create(
            company=self.other_company,
            company_name='Other Tenant Ltd',
            business_sector='OTHER SECTOR',
        )
        DirectoryBusinessActivity.objects.create(
            company=self.other_company,
            directory_company=other,
            sheet_name='Exporters',
        )

    def test_activities_lists_this_tenants_sheets(self):
        response = self.client.get(ACTIVITIES_URL)
        self.assertEqual(response.status_code, 200, response.data)
        payload = {row['value']: row['count'] for row in response.json()['data']}
        self.assertEqual(payload, {'Importers': 1, 'Manufacturers': 1})

    def test_query_parameters_do_not_narrow_activity_options(self):
        response = self.client.get(ACTIVITIES_URL, {'sheet_name': 'Manufacturers'})
        self.assertEqual(response.status_code, 200)
        values = [row['value'] for row in response.json()['data']]
        self.assertEqual(values, ['Importers', 'Manufacturers'])

    def test_sheet_name_filter_returns_only_that_category(self):
        response = self.client.get(LIST_URL, {'sheet_name': 'Importers'})
        self.assertEqual(response.status_code, 200, response.data)
        names = [row['company_name'] for row in response.json()['data']['results']]
        self.assertEqual(names, ['Steel Traders'])

    def test_sector_filter_still_matches_the_imported_sector(self):
        response = self.client.get(LIST_URL, {'business_sector': 'MANUFACTURING'})
        self.assertEqual(response.status_code, 200, response.data)
        names = [row['company_name'] for row in response.json()['data']['results']]
        self.assertEqual(names, ['Steel Traders'])
