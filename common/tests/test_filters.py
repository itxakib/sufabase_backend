"""Tests for the shared filter primitives in ``common.filters``.

Two of these are regression tests for bugs that were completely silent. Both are
worth keeping for that reason alone:

* The audit-timestamp filters were first declared on a plain mixin. django-filter
  only collects declared filters from bases that are themselves ``FilterSet``s, so
  all four were discarded - no error, no warning, nothing in the schema, and the
  source still looked correct.
* The tag endpoint's filters vanished from the generated schema, and its ``{id}``
  path parameter degraded to ``string``, because a ``NameError`` inside
  ``get_queryset`` aborted model derivation. Nothing failed; the docs were just
  quietly wrong.

The schema contract test at the bottom is the general defence: every filter a
filterset declares must appear as a documented query parameter on its endpoint.
"""

from datetime import timedelta

from django import forms
from django.test import TestCase
from django.utils import timezone
from django_filters import BooleanFilter
from rest_framework.test import APIRequestFactory, APITestCase

from common.filters import (
    AuditRangeFilterSet,
    InCharFilter,
    InNumberFilter,
    StrictBooleanField,
    StrictBooleanFilter,
    TenantAwareFilterSet,
)
from common.tests.factories import make_company, make_user
from customers.filters.customer import CustomerFilter
from customers.filters.tag import TagFilter
from customers.models import Customer, Tag
from tenant.filters.company import CompanyFilter
from tenant.models import Company
from users.filters.user import UserFilter

# Every filterset wired to a list endpoint, and the endpoint it documents.
FILTERSET_ENDPOINTS = {
    '/api/v1/customers/': CustomerFilter,
    '/api/v1/tags/': TagFilter,
    '/api/v1/users/': UserFilter,
    '/api/v1/companies/': CompanyFilter,
}

AUDIT_FILTER_NAMES = {'created_after', 'created_before', 'updated_after', 'updated_before'}


class InFilterTests(TestCase):
    """The comma-separated ``__in`` filters."""

    def setUp(self):
        self.company = make_company()
        self.vip = Tag.objects.create(company=self.company, name='VIP')
        self.umrah = Tag.objects.create(company=self.company, name='Umrah-2026')
        self.base = Customer.objects.filter(company=self.company)

    def test_single_id(self):
        filterset = CustomerFilter({'tags': str(self.vip.pk)}, queryset=self.base)
        self.assertTrue(filterset.is_valid(), filterset.errors)
        self.assertEqual(filterset.qs.count(), 0)

    def test_comma_separated_ids_are_parsed_as_a_list(self):
        filterset = CustomerFilter(
            {'tags': f'{self.vip.pk},{self.umrah.pk}'},
            queryset=self.base,
        )
        self.assertTrue(filterset.is_valid(), filterset.errors)
        self.assertEqual(filterset.form.cleaned_data['tags'], [self.vip.pk, self.umrah.pk])

    def test_a_non_numeric_value_is_a_validation_error_not_a_crash(self):
        filterset = CustomerFilter({'tags': 'not-an-id'}, queryset=self.base)
        self.assertFalse(filterset.is_valid())

    def test_char_in_filter_parses_choices(self):
        filterset = CustomerFilter({'stage_in': 'NEW,OLD'}, queryset=self.base)
        self.assertTrue(filterset.is_valid(), filterset.errors)
        self.assertEqual(filterset.form.cleaned_data['stage_in'], ['NEW', 'OLD'])

    def test_the_in_filters_really_use_the_in_lookup(self):
        """``BaseInFilter`` supplies the lookup.

        Without it the filter would compare a whole comma-joined string against a
        single column value and silently match nothing, which is the failure mode
        that makes ``?tags=1,2`` look like it works in a browser but return an
        empty page.
        """
        self.assertEqual(InNumberFilter().lookup_expr, 'in')
        self.assertEqual(InCharFilter().lookup_expr, 'in')


class AuditRangeFilterSetTests(TestCase):
    """The four timestamp filters every model can support."""

    def test_the_base_declares_all_four(self):
        self.assertEqual(set(AuditRangeFilterSet.base_filters), AUDIT_FILTER_NAMES)

    def test_every_project_filterset_keeps_them(self):
        """The mixin regression: a non-FilterSet base loses them silently."""
        for filterset in (UserFilter, CustomerFilter, TagFilter, CompanyFilter):
            with self.subTest(filterset=filterset.__name__):
                self.assertTrue(
                    AUDIT_FILTER_NAMES <= set(filterset.base_filters),
                    f'{filterset.__name__} is missing some audit range filters',
                )

    def test_created_after_actually_narrows_the_queryset(self):
        old = make_company()
        fresh = make_company()
        backdated = timezone.now() - timedelta(days=30)
        Company.objects.filter(pk=old.pk).update(created_at=backdated)

        cutoff = (timezone.now() - timedelta(days=1)).isoformat()
        filterset = CompanyFilter({'created_after': cutoff}, queryset=Company.objects.all())
        self.assertTrue(filterset.is_valid(), filterset.errors)

        self.assertNotIn(old, filterset.qs)
        self.assertIn(fresh, filterset.qs)

    def test_created_before_actually_narrows_the_queryset(self):
        old = make_company()
        fresh = make_company()
        Company.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=30))

        cutoff = (timezone.now() - timedelta(days=1)).isoformat()
        filterset = CompanyFilter({'created_before': cutoff}, queryset=Company.objects.all())
        self.assertTrue(filterset.is_valid(), filterset.errors)

        self.assertIn(old, filterset.qs)
        self.assertNotIn(fresh, filterset.qs)


class TenantAwareFilterSetTests(TestCase):
    """The company a filter method sees comes from the request, not the query string."""

    def setUp(self):
        self.company = make_company()
        self.user = make_user(company=self.company)

    def _filterset(self, request=None):
        return CustomerFilter({}, queryset=Customer.objects.none(), request=request)

    def test_company_comes_from_the_authenticated_user(self):
        request = APIRequestFactory().get('/')
        request.user = self.user
        self.assertEqual(self._filterset(request).company, self.company)

    def test_company_is_none_without_a_request(self):
        """No request means no tenant - filters must handle that, not assume one."""
        self.assertIsNone(self._filterset().company)

    def test_company_is_none_for_an_anonymous_request(self):
        request = APIRequestFactory().get('/')
        self.assertIsNone(self._filterset(request).company)

    def test_the_base_is_a_filterset_so_subclasses_inherit_its_filters(self):
        self.assertTrue(issubclass(TenantAwareFilterSet, AuditRangeFilterSet))


class StrictBooleanFilterTests(TestCase):
    """A bad boolean must be a 400, never a silently unfiltered list."""

    def test_the_plain_boolean_filter_is_the_trap_this_replaces(self):
        """Documents exactly why ``StrictBooleanFilter`` exists.

        django-filter's ``BooleanFilter`` uses ``NullBooleanField``, which maps an
        unrecognised value to ``None`` - and django-filter reads ``None`` as
        "parameter absent". The filter is skipped and the caller gets every row
        with a 200, which is the worst possible answer: wrong data, success
        status, nothing to notice.
        """
        self.assertIsNone(forms.NullBooleanField().to_python('maybe'))
        self.assertIsNot(StrictBooleanFilter.field_class, forms.NullBooleanField)

    def test_accepted_spellings(self):
        field = StrictBooleanField()
        for raw, expected in (
            ('true', True),
            ('TRUE', True),
            ('True', True),
            ('1', True),
            (' false', False),
            ('False', False),
            ('0', False),
        ):
            with self.subTest(raw=raw):
                self.assertIs(field.to_python(raw), expected)

    def test_rejected_spellings_raise_a_validation_error(self):
        """``yes``/``no`` are rejected on purpose: guessing at them is how a
        filter starts answering a question nobody asked."""
        field = StrictBooleanField()
        for raw in ('maybe', 'yes', 'no', 'on', 'off', '2', 'null'):
            with self.subTest(raw=raw):
                with self.assertRaises(forms.ValidationError):
                    field.to_python(raw)

    def test_an_empty_value_means_absent_not_invalid(self):
        """``?is_active=`` is ignored, matching every other filter in the API."""
        field = StrictBooleanField()
        self.assertIsNone(field.to_python(''))
        self.assertIsNone(field.to_python('   '))
        self.assertIsNone(field.to_python(None))

    def test_python_bools_pass_through(self):
        field = StrictBooleanField()
        self.assertIs(field.to_python(True), True)
        self.assertIs(field.to_python(False), False)

    def test_no_filterset_in_the_project_uses_the_plain_boolean_filter(self):
        """Guard: adding ``BooleanFilter`` anywhere reopens the silent-200 bug."""
        offenders = []
        for filterset in FILTERSET_ENDPOINTS.values():
            for name, declared in filterset.base_filters.items():
                if isinstance(declared, BooleanFilter) and not isinstance(
                    declared, StrictBooleanFilter,
                ):
                    offenders.append(f'{filterset.__name__}.{name}')

        self.assertEqual(offenders, [], f'use StrictBooleanFilter instead: {offenders}')


class SchemaDocumentsEveryFilterTests(APITestCase):
    """The generated docs must describe the API that actually exists.

    This is the drift guard. Every previous way a filter has gone missing in this
    project was silent - a discarded mixin, an exception swallowed during schema
    generation - so the check is mechanical rather than trusting the source.
    """

    def schema(self):
        response = self.client.get('/api/schema/', HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, 200)
        return response.json()

    def query_params(self, spec, path):
        operations = spec['paths'][path]
        return {
            parameter['name']
            for operation in operations.values()
            for parameter in operation.get('parameters', [])
            if parameter['in'] == 'query'
        }

    def test_every_declared_filter_appears_as_a_query_parameter(self):
        spec = self.schema()

        for path, filterset in FILTERSET_ENDPOINTS.items():
            with self.subTest(path=path):
                documented = self.query_params(spec, path)
                missing = set(filterset.base_filters) - documented
                self.assertEqual(
                    missing,
                    set(),
                    f'{filterset.__name__} declares filters the docs do not mention: '
                    f'{sorted(missing)}',
                )

    def test_detail_path_parameters_are_typed_integers(self):
        """They degrade to ``string`` whenever queryset introspection fails.

        That is not cosmetic: a generated client built from ``string`` sends an
        unencoded path segment and the request 404s.
        """
        spec = self.schema()

        for path in ('/api/v1/customers/{id}/', '/api/v1/tags/{id}/', '/api/v1/users/{id}/'):
            with self.subTest(path=path):
                params = [
                    parameter
                    for operation in spec['paths'][path].values()
                    for parameter in operation.get('parameters', [])
                    if parameter['in'] == 'path'
                ]
                self.assertTrue(params, f'{path} documents no path parameter')
                for parameter in params:
                    self.assertEqual(parameter['schema']['type'], 'integer')

    def test_search_and_ordering_are_documented_on_every_list_endpoint(self):
        spec = self.schema()

        for path in FILTERSET_ENDPOINTS:
            with self.subTest(path=path):
                documented = self.query_params(spec, path)
                self.assertIn('search', documented)
                self.assertIn('ordering', documented)
