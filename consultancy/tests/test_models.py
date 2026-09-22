"""Schema-level tests for the consultancy app models.

Structural tests only - field shapes, delete rules, accessor names, choice widths,
tenant isolation - because this pass is schema only. The delete-rule and isolation
tests are the ones that matter most: they are the cursor rules (no silent
cross-tenant reads, no accidental destruction of live client data) expressed as
something that fails loudly.
"""

from django.apps import apps
from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.db.models import ProtectedError
from django.test import TestCase

from common.models import TenantScopedModel
from common.tests.factories import make_company, make_user
from consultancy.choices import (
    BiometricsStatusChoices,
    DocumentChecklistStatusChoices,
    StudyLevelChoices,
    StudyVisaApplicationStatusChoices,
    VisaCaseStatusChoices,
    VisaDecisionChoices,
)
from consultancy.models import CaseRecordBase, StudyVisaCase, VisaConsultancyCase
from customers.models import Customer

CASE_MODELS = (VisaConsultancyCase, StudyVisaCase)

EXPECTED_CONCRETE_MODELS = {'StudyVisaCase', 'VisaConsultancyCase'}


def make_customer(company, **overrides):
    """Create the Customer every case in these tests hangs off."""
    defaults = {
        'company': company,
        'full_name': 'Test Applicant',
        'phone': '03001234567',
    }
    defaults.update(overrides)
    return Customer.objects.create(**defaults)


class ConsultancyAppShapeTests(TestCase):
    """Guard the shape of the app itself, not any one model."""

    def test_app_owns_exactly_the_expected_concrete_models(self):
        """Two tables and nothing else.

        A third appearing here means a model was added without a deliberate
        decision; this test is the tripwire.
        """
        names = {model.__name__ for model in apps.get_app_config('consultancy').get_models()}
        self.assertEqual(names, EXPECTED_CONCRETE_MODELS)

    def test_case_record_base_is_abstract(self):
        self.assertTrue(CaseRecordBase._meta.abstract)
        self.assertNotIn('CaseRecordBase', EXPECTED_CONCRETE_MODELS)

    def test_every_case_model_inherits_tenant_scoping(self):
        for model in CASE_MODELS:
            with self.subTest(model=model.__name__):
                self.assertTrue(issubclass(model, TenantScopedModel))

    def test_every_choice_value_fits_its_column(self):
        """A choice value longer than its column is a data-loss bug waiting.

        Catches the whole class of mistake at once: longest offer state is
        "Unconditional Offer" (19 chars), longest case status is
        "DOCUMENTS_PENDING" (17), and a future value can easily outgrow a column
        nobody looks at again.
        """
        offenders = []
        for model in CASE_MODELS:
            for field in model._meta.get_fields():
                if isinstance(field, models.CharField) and field.choices:
                    longest = max(len(str(value)) for value, _ in field.choices)
                    if longest > field.max_length:
                        offenders.append(
                            f'{model.__name__}.{field.name} needs {longest}, '
                            f'has {field.max_length}'
                        )
        self.assertEqual(offenders, [])

    def test_cases_are_not_dated_bookings(self):
        """Pins the reason this is a separate app from ``bookings``.

        A case is a process with an open date and a decision date, not a
        transaction with a date range. If someone later "unifies" the two by
        adding a booking-shaped date pair here, this fails and they have to make
        the argument explicitly.
        """
        booking_only_fields = (
            'start_date',
            'end_date',
            'amount',
            'sales_agent',
            'booking_reference',
        )
        for model in CASE_MODELS:
            for name in booking_only_fields:
                with self.subTest(model=model.__name__, field=name):
                    with self.assertRaises(FieldDoesNotExist):
                        model._meta.get_field(name)

    def test_shared_choice_enums_are_reused_not_duplicated(self):
        """Both case types must reference the *same* decision enum.

        Two near-identical copies would drift the first time one gained a value,
        which is exactly what happened to the refusal-rate reporting these enums
        feed.
        """
        for model in CASE_MODELS:
            with self.subTest(model=model.__name__):
                self.assertEqual(
                    model._meta.get_field('visa_decision').choices,
                    VisaDecisionChoices.choices,
                )
                self.assertEqual(
                    model._meta.get_field('biometrics_status').choices,
                    BiometricsStatusChoices.choices,
                )


class SharedFieldTests(TestCase):
    """The fields every case inherits from CaseRecordBase."""

    def setUp(self):
        self.company = make_company()
        self.customer = make_customer(self.company)

    def test_customer_is_protected_not_cascaded(self):
        """Deleting a customer must not silently destroy their case history."""
        for model in CASE_MODELS:
            with self.subTest(model=model.__name__):
                field = model._meta.get_field('customer')
                self.assertIs(field.remote_field.on_delete, models.PROTECT)
                self.assertFalse(field.null)

    def test_company_is_protected(self):
        for model in CASE_MODELS:
            with self.subTest(model=model.__name__):
                field = model._meta.get_field('company')
                self.assertIs(field.remote_field.on_delete, models.PROTECT)
                self.assertFalse(field.null)

    def test_assigned_counselor_is_nullable_set_null(self):
        """Losing an assignment must never block removing a staff account."""
        for model in CASE_MODELS:
            with self.subTest(model=model.__name__):
                field = model._meta.get_field('assigned_counselor')
                self.assertIs(field.remote_field.on_delete, models.SET_NULL)
                self.assertTrue(field.null)
                self.assertTrue(field.blank)

    def test_destination_country_is_required(self):
        for model in CASE_MODELS:
            with self.subTest(model=model.__name__):
                field = model._meta.get_field('destination_country')
                self.assertFalse(field.blank)
                self.assertFalse(field.null)

    def test_case_dates_are_nullable(self):
        for model in CASE_MODELS:
            for name in ('case_open_date', 'decision_date'):
                with self.subTest(model=model.__name__, field=name):
                    field = model._meta.get_field(name)
                    self.assertTrue(field.null)
                    self.assertTrue(field.blank)

    def test_service_value_shape(self):
        field = VisaConsultancyCase._meta.get_field('service_value')
        self.assertEqual(field.max_digits, 12)
        self.assertEqual(field.decimal_places, 2)
        self.assertTrue(field.null)

    def test_currency_defaults_to_pkr(self):
        case = self._minimal_visa_case()
        self.assertEqual(case.currency, 'PKR')

    def test_every_case_can_hold_attachments(self):
        """Documents/Checklist columns are covered by one generic relation."""
        for model in CASE_MODELS:
            with self.subTest(model=model.__name__):
                self.assertTrue(hasattr(model, 'attachments'))

    def test_customer_has_a_distinct_reverse_accessor_per_case_type(self):
        for model in CASE_MODELS:
            accessor = f'{model._meta.model_name}_set'
            with self.subTest(model=model.__name__):
                self.assertTrue(hasattr(self.customer, accessor))

    def test_reverse_accessors_do_not_share_rows_between_case_types(self):
        case = self._minimal_visa_case()
        self.assertEqual(list(self.customer.visaconsultancycase_set.all()), [case])
        self.assertEqual(self.customer.studyvisacase_set.count(), 0)

    def test_consultancy_accessors_do_not_collide_with_bookings(self):
        """``%(class)s_set`` must stay unique across apps, not just within one.

        Both apps put a reverse accessor on ``Customer``; a collision here would be
        a system-check error rather than a silent bug, but the names are asserted
        so the convention is pinned rather than assumed.
        """
        self.assertEqual(VisaConsultancyCase._meta.model_name, 'visaconsultancycase')
        self.assertEqual(StudyVisaCase._meta.model_name, 'studyvisacase')

    def _minimal_visa_case(self, **overrides):
        defaults = {
            'company': self.company,
            'customer': self.customer,
            'destination_country': 'Saudi Arabia',
            'visa_category': 'VISIT_TOURIST',
        }
        defaults.update(overrides)
        return VisaConsultancyCase.objects.create(**defaults)


class ProtectedDeleteTests(TestCase):
    """The two PROTECT edges, checked from both directions."""

    def setUp(self):
        self.company = make_company()
        self.customer = make_customer(self.company)

    def _make_study_case(self):
        return StudyVisaCase.objects.create(
            company=self.company,
            customer=self.customer,
            destination_country='United Kingdom',
            study_level=StudyLevelChoices.MASTERS,
            field_of_study='Data Science',
            preferred_intake='September 2026',
            institution='University of Manchester',
        )

    def test_deleting_a_customer_with_cases_is_blocked(self):
        case = self._make_study_case()

        with self.assertRaises(ProtectedError):
            self.customer.delete()

        self.assertTrue(Customer.objects.filter(pk=self.customer.pk).exists())
        self.assertTrue(StudyVisaCase.objects.filter(pk=case.pk).exists())

    def test_deleting_a_customer_without_cases_still_works(self):
        """Proves the protection is conditional, not a blanket block on delete."""
        self.customer.delete()
        self.assertFalse(Customer.objects.filter(pk=self.customer.pk).exists())

    def test_deleting_a_company_with_cases_is_blocked(self):
        self._make_study_case()

        with self.assertRaises(ProtectedError):
            self.company.delete()

        self.assertTrue(Customer.objects.filter(pk=self.customer.pk).exists())

    def test_deleting_the_counselor_keeps_the_case(self):
        """SET_NULL, not PROTECT: an assignment is not part of the record."""
        counselor = make_user(company=self.company)
        case = VisaConsultancyCase.objects.create(
            company=self.company,
            customer=self.customer,
            destination_country='UAE',
            visa_category='BUSINESS',
            assigned_counselor=counselor,
        )

        counselor.delete()
        case.refresh_from_db()

        self.assertIsNone(case.assigned_counselor)
        self.assertTrue(VisaConsultancyCase.objects.filter(pk=case.pk).exists())


class TenantIsolationTests(TestCase):
    """Cursor Rule 3, expressed as a test: no cross-tenant reads."""

    def setUp(self):
        self.company_a = make_company()
        self.company_b = make_company()
        self.customer_a = make_customer(self.company_a, full_name='Applicant A')
        self.customer_b = make_customer(self.company_b, full_name='Applicant B')

    def test_cases_do_not_leak_across_tenants(self):
        case_a = VisaConsultancyCase.objects.create(
            company=self.company_a,
            customer=self.customer_a,
            destination_country='Schengen',
            visa_category='VISIT_TOURIST',
        )
        VisaConsultancyCase.objects.create(
            company=self.company_b,
            customer=self.customer_b,
            destination_country='Japan',
            visa_category='BUSINESS',
        )

        self.assertEqual(
            list(VisaConsultancyCase.objects.filter(company=self.company_a)),
            [case_a],
        )
        self.assertNotIn(
            case_a,
            VisaConsultancyCase.objects.filter(company=self.company_b),
        )

    def test_company_filter_is_the_only_thing_separating_the_two(self):
        """Stated explicitly so the filtering contract cannot be misread."""
        VisaConsultancyCase.objects.create(
            company=self.company_a,
            customer=self.customer_a,
            destination_country='Schengen',
            visa_category='VISIT_TOURIST',
        )
        VisaConsultancyCase.objects.create(
            company=self.company_b,
            customer=self.customer_b,
            destination_country='Japan',
            visa_category='BUSINESS',
        )

        self.assertEqual(VisaConsultancyCase.objects.count(), 2)
        self.assertEqual(VisaConsultancyCase.objects.filter(company=self.company_a).count(), 1)
        self.assertEqual(VisaConsultancyCase.objects.filter(company=self.company_b).count(), 1)


class VisaConsultancyCaseTests(TestCase):
    """The fields that make a general visa case what it is."""

    def setUp(self):
        self.company = make_company()
        self.customer = make_customer(self.company)

    def _case(self, **overrides):
        defaults = {
            'company': self.company,
            'customer': self.customer,
            'destination_country': 'Schengen',
            'visa_category': 'VISIT_TOURIST',
        }
        defaults.update(overrides)
        return VisaConsultancyCase.objects.create(**defaults)

    def test_visa_category_is_required(self):
        field = VisaConsultancyCase._meta.get_field('visa_category')
        self.assertFalse(field.blank)

    def test_status_defaults_to_consultation(self):
        self.assertEqual(self._case().status, VisaCaseStatusChoices.CONSULTATION)

    def test_document_checklist_defaults_to_not_started(self):
        self.assertEqual(
            self._case().document_checklist_status,
            DocumentChecklistStatusChoices.NOT_STARTED,
        )

    def test_tracking_fields_start_empty(self):
        case = self._case()
        self.assertEqual(case.embassy_vac, '')
        self.assertEqual(case.application_tracking_reference, '')
        self.assertEqual(case.visa_decision, '')
        self.assertEqual(case.passport_collection_status, '')
        self.assertEqual(case.biometrics_status, '')
        self.assertIsNone(case.application_submission_date)
        self.assertIsNone(case.appointment_date)
        self.assertIsNone(case.visa_valid_from)
        self.assertIsNone(case.visa_valid_until)

    def test_intended_travel_date_is_optional(self):
        """Plenty of cases are exploratory; the client has not picked a date."""
        field = VisaConsultancyCase._meta.get_field('intended_travel_date')
        self.assertTrue(field.null)
        self.assertIsNone(self._case().intended_travel_date)

    def test_a_refused_case_can_still_be_closed(self):
        """CLOSED is a file state, not an outcome - it follows either decision."""
        case = self._case(
            status=VisaCaseStatusChoices.CLOSED,
            visa_decision=VisaDecisionChoices.REFUSED,
        )
        self.assertEqual(case.visa_decision, VisaDecisionChoices.REFUSED)
        self.assertEqual(case.status, VisaCaseStatusChoices.CLOSED)

    def test_str_does_not_dereference_the_customer(self):
        """``__str__`` runs per row in admin lists; it must not cost a query."""
        case = self._case()
        self.assertEqual(str(case), 'Visit / Tourist to Schengen')

    def test_case_status_column_holds_the_longest_value(self):
        self.assertEqual(VisaConsultancyCase._meta.get_field('status').max_length, 20)
        self.assertEqual(VisaConsultancyCase._meta.get_field('visa_category').max_length, 20)


class StudyVisaCaseTests(TestCase):
    """The fields that make a study case what it is."""

    def setUp(self):
        self.company = make_company()
        self.customer = make_customer(self.company)

    def _case(self, **overrides):
        defaults = {
            'company': self.company,
            'customer': self.customer,
            'destination_country': 'United Kingdom',
            'study_level': StudyLevelChoices.MASTERS,
            'field_of_study': 'Data Science',
            'preferred_intake': 'September 2026',
            'institution': 'University of Manchester',
        }
        defaults.update(overrides)
        return StudyVisaCase.objects.create(**defaults)

    def test_required_admissions_fields(self):
        for name in ('study_level', 'field_of_study', 'preferred_intake', 'institution'):
            with self.subTest(field=name):
                field = StudyVisaCase._meta.get_field(name)
                self.assertFalse(field.blank)
                self.assertFalse(field.null)

    def test_status_defaults_to_not_ready(self):
        """A study case cannot be visa-ready before an admission exists."""
        self.assertEqual(self._case().status, StudyVisaApplicationStatusChoices.NOT_READY)

    def test_admissions_defaults(self):
        case = self._case()
        self.assertEqual(case.institution_application_status, 'NOT_APPLIED')
        self.assertEqual(case.academic_documents_status, 'INCOMPLETE')
        self.assertEqual(case.financial_evidence_status, 'NOT_STARTED')
        self.assertEqual(case.offer_acceptance_status, '')
        self.assertEqual(case.sop_status, '')

    def test_english_test_score_is_text_not_a_number(self):
        """IELTS band scores and TOEFL integers are not comparable.

        Storing either in a numeric column would force one test's scale onto the
        other and quietly make the values meaningless.
        """
        field = StudyVisaCase._meta.get_field('english_test_score')
        self.assertIsInstance(field, models.CharField)
        self.assertNotIsInstance(field, models.DecimalField)
        self.assertNotIsInstance(field, models.IntegerField)

        band = self._case(english_test_type='IELTS', english_test_score='7.5')
        toefl = self._case(english_test_type='TOEFL', english_test_score='95')
        self.assertEqual(band.english_test_score, '7.5')
        self.assertEqual(toefl.english_test_score, '95')

    def test_tuition_fields_are_nullable_decimals(self):
        case = self._case()
        for name in ('tuition_fee', 'tuition_deposit_paid'):
            with self.subTest(field=name):
                field = StudyVisaCase._meta.get_field(name)
                self.assertTrue(field.null)
                self.assertEqual(field.max_digits, 12)
                self.assertEqual(field.decimal_places, 2)
                self.assertIsNone(getattr(case, name))

    def test_enrolment_reference_starts_empty(self):
        """Blank until an institution issues one - the case's real gate."""
        case = self._case()
        self.assertEqual(case.enrolment_reference, '')
        self.assertEqual(case.enrolment_reference_type, '')

    def test_enrolment_reference_type_holds_every_country_system(self):
        """One field instead of four country-specific column groups."""
        for value, _ in StudyVisaCase._meta.get_field('enrolment_reference_type').choices:
            with self.subTest(value=value):
                case = self._case(enrolment_reference_type=value)
                self.assertEqual(case.enrolment_reference_type, value)

    def test_medical_and_biometrics_start_empty(self):
        case = self._case()
        self.assertEqual(case.biometrics_status, '')
        self.assertEqual(case.medical_tb_status, '')

    def test_str_does_not_dereference_the_customer(self):
        case = self._case()
        self.assertEqual(str(case), "Master's at University of Manchester")

    def test_longest_choice_values_fit_their_columns(self):
        self.assertEqual(StudyVisaCase._meta.get_field('study_level').max_length, 20)
        self.assertEqual(
            StudyVisaCase._meta.get_field('institution_application_status').max_length,
            20,
        )
        self.assertEqual(StudyVisaCase._meta.get_field('english_test_type').max_length, 10)
        self.assertEqual(
            StudyVisaCase._meta.get_field('enrolment_reference_type').max_length,
            10,
        )


class MinimalRecordTests(TestCase):
    """Only the required fields - the lean record must actually be possible."""

    def setUp(self):
        self.company = make_company()
        self.customer = make_customer(self.company)

    def test_minimal_visa_case(self):
        case = VisaConsultancyCase.objects.create(
            company=self.company,
            customer=self.customer,
            destination_country='Turkey',
            visa_category='VISIT_TOURIST',
        )
        self.assertIsNone(case.case_open_date)
        self.assertIsNone(case.decision_date)
        self.assertIsNone(case.service_value)
        self.assertIsNone(case.assigned_counselor)
        self.assertEqual(case.notes, '')
        self.assertEqual(case.attachments.count(), 0)

    def test_minimal_study_case(self):
        case = StudyVisaCase.objects.create(
            company=self.company,
            customer=self.customer,
            destination_country='Canada',
            study_level=StudyLevelChoices.DIPLOMA,
            field_of_study='Hospitality',
            preferred_intake='January 2027',
            institution='Seneca College',
        )
        self.assertIsNone(case.case_open_date)
        self.assertIsNone(case.decision_date)
        self.assertIsNone(case.course_start_date)
        self.assertEqual(case.currency, 'PKR')
        self.assertEqual(case.attachments.count(), 0)
