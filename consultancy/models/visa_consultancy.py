from django.db import models

from consultancy.choices import (
    BiometricsStatusChoices,
    DocumentChecklistStatusChoices,
    PassportCollectionStatusChoices,
    VisaCaseStatusChoices,
    VisaCategoryChoices,
    VisaDecisionChoices,
)
from consultancy.models.base import CaseRecordBase


class VisaConsultancyCase(CaseRecordBase):
    """A general (non-study) visa consultancy case.

    Covers visit/tourist, business, family, transit and work visas - one model
    rather than five, because the *workflow* is identical across them and only
    ``visa_category`` changes which checklist and fee apply. Five models would be
    five copies of the same twenty columns.

    ``intended_travel_date`` is separate from the case dates on the base: it is
    what the *client* wants, and the planning question ("is there time?") is asked
    long before anything is submitted. It is nullable because plenty of cases are
    exploratory.

    The status chain has three parallel tracks that move independently, which is
    why each is its own field rather than being folded into ``status``:

    * ``document_checklist_status`` - is the client's pack ready?
    * ``biometrics_status`` - is enrolment done?
    * ``passport_collection_status`` - is the passport back in the client's hands?

    ``visa_valid_from``/``visa_valid_until`` are kept because the visa's validity
    is frequently *not* what the client asked for (a 30-day single-entry instead of
    a multi-entry year visa), and staff need that recorded to advise correctly
    next time. ``application_tracking_reference`` and ``embassy_vac`` exist so
    anyone can answer "where is it" without opening a document.
    """

    visa_category = models.CharField(
        max_length=20,
        choices=VisaCategoryChoices.choices,
    )
    purpose_of_travel = models.CharField(max_length=255, blank=True)
    intended_travel_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=VisaCaseStatusChoices.choices,
        default=VisaCaseStatusChoices.CONSULTATION,
    )
    # Free text, not an FK: the same embassy is named half a dozen ways by staff,
    # and the counterparty is an external government body that will never be a
    # SUFABASE record.
    embassy_vac = models.CharField(max_length=255, blank=True)
    application_tracking_reference = models.CharField(max_length=100, blank=True)
    application_submission_date = models.DateField(null=True, blank=True)
    appointment_date = models.DateField(null=True, blank=True)
    biometrics_status = models.CharField(
        max_length=15,
        choices=BiometricsStatusChoices.choices,
        blank=True,
    )
    document_checklist_status = models.CharField(
        max_length=15,
        choices=DocumentChecklistStatusChoices.choices,
        default=DocumentChecklistStatusChoices.NOT_STARTED,
    )
    visa_decision = models.CharField(
        max_length=15,
        choices=VisaDecisionChoices.choices,
        blank=True,
    )
    visa_valid_from = models.DateField(null=True, blank=True)
    visa_valid_until = models.DateField(null=True, blank=True)
    passport_collection_status = models.CharField(
        max_length=15,
        choices=PassportCollectionStatusChoices.choices,
        blank=True,
    )

    def __str__(self):
        # Deliberately does not touch ``customer``: this is called for every row
        # in admin list views, and dereferencing the FK here would be one query
        # per row.
        return f'{self.get_visa_category_display()} to {self.destination_country}'
