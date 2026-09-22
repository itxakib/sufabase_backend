"""Selectors for the consultancy app.

Same contract as every other selector in this project: ``company`` or ``customer``
is always an explicit parameter, and the queries come from
``common.selectors.TenantScopedSelector`` so the tenant filter is written once.
"""

from consultancy.models import StudyVisaCase, VisaConsultancyCase
from common.selectors import TenantScopedSelector

#: Relations every ``CaseRecordBase`` subclass needs eagerly loaded. Both case
#: types share these three foreign keys, so a case list that adds a fourth relation
#: must add it here or it starts issuing a query per row.
CASE_RECORD_RELATED = ('company', 'customer', 'assigned_counselor')


class ConsultancySelector:
    """Lookup and query logic for the two case models."""

    @staticmethod
    def for_company(model_cls, company, **filters):
        """Company-scoped cases of ``model_cls``, with relations loaded."""
        return TenantScopedSelector.for_company(
            model_cls,
            company,
            select_related=CASE_RECORD_RELATED,
            **filters,
        )

    @staticmethod
    def for_customer(model_cls, customer, **filters):
        """One customer's cases of a given type, relations loaded."""
        return TenantScopedSelector.for_customer(
            model_cls,
            customer,
            select_related=CASE_RECORD_RELATED,
            **filters,
        )

    @staticmethod
    def visa_cases_for_customer(customer):
        """This customer's general (non-study) visa cases."""
        return ConsultancySelector.for_customer(VisaConsultancyCase, customer)

    @staticmethod
    def study_visa_cases_for_customer(customer):
        """This customer's study-visa cases."""
        return ConsultancySelector.for_customer(StudyVisaCase, customer)

    @staticmethod
    def visa_cases_for_company(company, status=None):
        """This tenant's visa cases, optionally at one pipeline status.

        ``status`` is an exact match on ``VisaCaseStatusChoices`` - the case queue
        a counselor works from. Free-text or range filtering is the API layer's
        job (``consultancy/filters/``), not this selector's: a selector answers
        "these rows", and every extra keyword here is another thing to test.
        """
        filters = {'status': status} if status else {}
        return ConsultancySelector.for_company(VisaConsultancyCase, company, **filters)

    @staticmethod
    def study_visa_cases_for_company(company, status=None):
        """This tenant's study-visa cases, optionally at one pipeline status.

        The symmetric counterpart to :meth:`visa_cases_for_company`. It is not in
        the original selector spec, but without it study cases have no
        company-scoped entry point at all, and callers would fall back to importing
        the model and hand-writing the filter - which is the thing this layer
        exists to prevent.
        """
        filters = {'status': status} if status else {}
        return ConsultancySelector.for_company(StudyVisaCase, company, **filters)
