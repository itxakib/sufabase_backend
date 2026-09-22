"""Selector tests for the consultancy app."""

from django.test import TestCase

from common.tests.factories import make_company, make_user
from consultancy.choices import StudyVisaApplicationStatusChoices, VisaCaseStatusChoices
from consultancy.models import StudyVisaCase, VisaConsultancyCase
from consultancy.selectors.consultancy_selectors import (
    CASE_RECORD_RELATED,
    ConsultancySelector,
)
from customers.models import Customer


class ConsultancySelectorFixtureMixin:
    """Two visa cases and one study case, across two tenants."""

    def setUp(self):
        super().setUp()
        self.company = make_company()
        self.other_company = make_company()
        self.counselor = make_user(company=self.company)

        self.customer = Customer.objects.create(
            company=self.company,
            full_name='Ali Khan',
            phone='03001112223',
        )
        self.other_customer = Customer.objects.create(
            company=self.company,
            full_name='Sara Ahmed',
            phone='03219998887',
        )
        self.foreign_customer = Customer.objects.create(
            company=self.other_company,
            full_name='Foreign Customer',
            phone='03000000000',
        )

        base = {
            'company': self.company,
            'customer': self.customer,
            'assigned_counselor': self.counselor,
        }
        self.visa_case = VisaConsultancyCase.objects.create(
            destination_country='Schengen',
            visa_category='VISIT_TOURIST',
            status=VisaCaseStatusChoices.CONSULTATION,
            **base,
        )
        self.submitted_case = VisaConsultancyCase.objects.create(
            destination_country='UAE',
            visa_category='BUSINESS',
            status=VisaCaseStatusChoices.SUBMITTED,
            **base,
        )
        self.study_case = StudyVisaCase.objects.create(
            destination_country='United Kingdom',
            study_level='MASTERS',
            field_of_study='Data Science',
            preferred_intake='September 2026',
            institution='University of Manchester',
            status=StudyVisaApplicationStatusChoices.NOT_READY,
            **base,
        )
        # Same tenant, different customer.
        self.other_visa_case = VisaConsultancyCase.objects.create(
            company=self.company,
            customer=self.other_customer,
            assigned_counselor=self.counselor,
            destination_country='Turkey',
            visa_category='VISIT_TOURIST',
        )
        # Different tenant entirely.
        self.foreign_case = VisaConsultancyCase.objects.create(
            company=self.other_company,
            customer=self.foreign_customer,
            destination_country='Japan',
            visa_category='BUSINESS',
        )


class CaseSelectorScopingTests(ConsultancySelectorFixtureMixin, TestCase):
    def test_visa_cases_for_customer_returns_only_visa_cases(self):
        """The study case belongs to the same customer and must not appear."""
        self.assertEqual(
            set(ConsultancySelector.visa_cases_for_customer(self.customer)),
            {self.visa_case, self.submitted_case},
        )

    def test_study_visa_cases_for_customer_returns_only_study_cases(self):
        self.assertEqual(
            list(ConsultancySelector.study_visa_cases_for_customer(self.customer)),
            [self.study_case],
        )

    def test_visa_cases_for_customer_is_scoped_to_the_customer(self):
        self.assertEqual(
            list(ConsultancySelector.visa_cases_for_customer(self.other_customer)),
            [self.other_visa_case],
        )

    def test_visa_cases_for_customer_never_crosses_a_tenant(self):
        self.assertNotIn(
            self.foreign_case,
            list(ConsultancySelector.visa_cases_for_customer(self.customer)),
        )

    def test_visa_cases_for_company_returns_every_case_in_the_tenant(self):
        self.assertEqual(
            set(ConsultancySelector.visa_cases_for_company(self.company)),
            {self.visa_case, self.submitted_case, self.other_visa_case},
        )

    def test_visa_cases_for_company_filters_by_status(self):
        self.assertEqual(
            list(
                ConsultancySelector.visa_cases_for_company(
                    self.company,
                    status=VisaCaseStatusChoices.SUBMITTED,
                ),
            ),
            [self.submitted_case],
        )

    def test_an_absent_status_factor_is_not_applied(self):
        """``status=None`` means no status filter, not ``status IS NULL``."""
        self.assertEqual(
            ConsultancySelector.visa_cases_for_company(self.company).count(),
            3,
        )

    def test_study_visa_cases_for_company_is_the_symmetric_accessor(self):
        self.assertEqual(
            list(ConsultancySelector.study_visa_cases_for_company(self.company)),
            [self.study_case],
        )

    def test_study_visa_cases_for_company_filters_by_status(self):
        self.assertEqual(
            list(
                ConsultancySelector.study_visa_cases_for_company(
                    self.company,
                    status=StudyVisaApplicationStatusChoices.NOT_READY,
                ),
            ),
            [self.study_case],
        )

    def test_for_company_works_for_both_case_models(self):
        for model in (VisaConsultancyCase, StudyVisaCase):
            with self.subTest(model=model.__name__):
                self.assertIsNotNone(
                    ConsultancySelector.for_company(model, self.company).count(),
                )
        self.assertIn('assigned_counselor', CASE_RECORD_RELATED)


class CaseSelectorEagerLoadingTests(ConsultancySelectorFixtureMixin, TestCase):
    def test_a_case_list_costs_no_extra_queries_when_relations_are_touched(self):
        cases = list(ConsultancySelector.visa_cases_for_company(self.company))

        self.assertGreater(len(cases), 1, 'the test needs more than one case')

        with self.assertNumQueries(0):
            for case in cases:
                case.company.name
                case.customer.full_name
                case.assigned_counselor.username

    def test_a_customer_scoped_case_list_applies_the_same_loading(self):
        cases = list(ConsultancySelector.visa_cases_for_customer(self.customer))

        with self.assertNumQueries(0):
            for case in cases:
                case.customer.full_name
                case.assigned_counselor.username

    def test_a_case_without_a_counselor_still_renders_without_a_query(self):
        """A null FK is resolved in Python, so an unassigned case costs nothing."""
        case = ConsultancySelector.visa_cases_for_company(self.company).filter(
            pk=self.other_visa_case.pk,
        ).first()
        case.assigned_counselor = None
        case.save(update_fields=['assigned_counselor'])

        reloaded = ConsultancySelector.for_company(
            VisaConsultancyCase,
            self.company,
        ).get(pk=case.pk)

        with self.assertNumQueries(0):
            self.assertIsNone(reloaded.assigned_counselor)
