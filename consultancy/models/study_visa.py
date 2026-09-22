from django.db import models

from consultancy.choices import (
    AcademicDocumentsStatusChoices,
    BiometricsStatusChoices,
    EnglishTestTypeChoices,
    EnrolmentReferenceTypeChoices,
    FinancialEvidenceStatusChoices,
    InstitutionApplicationStatusChoices,
    MedicalTBStatusChoices,
    OfferAcceptanceStatusChoices,
    SOPStatusChoices,
    StudyLevelChoices,
    StudyVisaApplicationStatusChoices,
    VisaDecisionChoices,
)
from consultancy.models.base import CaseRecordBase


class StudyVisaCase(CaseRecordBase):
    """A study-visa / education-consultancy case.

    The defining difference from ``VisaConsultancyCase`` is that most of this case
    happens *before* any visa exists: the client has to be admitted to an
    institution first, and the visa application cannot even be lodged without an
    enrolment reference. That is why ``status`` cannot leave NOT_READY until
    ``enrolment_reference`` is populated - the admission pipeline is the bulk of
    the work, and modelling it as a footnote would hide where cases actually stall.

    Country flexibility comes from ``enrolment_reference_type`` plus
    ``destination_country`` on the base rather than from four country-specific
    column groups (CAS/CoE/I-20/LOA): one reference field and one type is enough
    to know which country's system the case sits in, and it does not need a
    migration per destination SUFA adds later.

    The three readiness tracks are separate fields because they block different
    things and are owned by different people:

    * ``academic_documents_status`` and ``sop_status`` - the applicant's side.
    * ``financial_evidence_status`` - usually a parent or sponsor, and the most
      common cause of a study visa refusal.
    * ``medical_tb_status`` - required by several destinations, arranged with a
      clinic, and on nobody else's critical path.

    ``tuition_fee`` and ``tuition_deposit_paid`` are both kept because the deposit
    is what unlocks the enrolment reference at most institutions, so "what is
    outstanding" is a real question this model has to answer. ``course_start_date``
    exists because it, not the visa, is the real deadline the whole case is racing.
    """

    study_level = models.CharField(
        max_length=20,
        choices=StudyLevelChoices.choices,
    )
    field_of_study = models.CharField(max_length=255)
    preferred_intake = models.CharField(max_length=100)
    institution = models.CharField(max_length=255)
    institution_application_status = models.CharField(
        max_length=20,
        choices=InstitutionApplicationStatusChoices.choices,
        default=InstitutionApplicationStatusChoices.NOT_APPLIED,
    )
    institution_reference = models.CharField(max_length=100, blank=True)
    offer_acceptance_status = models.CharField(
        max_length=15,
        choices=OfferAcceptanceStatusChoices.choices,
        blank=True,
    )
    course_start_date = models.DateField(null=True, blank=True)
    tuition_fee = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    tuition_deposit_paid = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    highest_qualification = models.CharField(max_length=255, blank=True)

    # Text, not a number: IELTS reports band scores like "7.5" while TOEFL uses a
    # different integer scale entirely, so a single numeric column would be both
    # lossy and misleading about comparability between tests.
    english_test_type = models.CharField(
        max_length=10,
        choices=EnglishTestTypeChoices.choices,
        blank=True,
    )
    english_test_score = models.CharField(max_length=20, blank=True)

    academic_documents_status = models.CharField(
        max_length=15,
        choices=AcademicDocumentsStatusChoices.choices,
        default=AcademicDocumentsStatusChoices.INCOMPLETE,
    )
    sop_status = models.CharField(
        max_length=15,
        choices=SOPStatusChoices.choices,
        blank=True,
    )
    financial_evidence_status = models.CharField(
        max_length=15,
        choices=FinancialEvidenceStatusChoices.choices,
        default=FinancialEvidenceStatusChoices.NOT_STARTED,
    )

    enrolment_reference_type = models.CharField(
        max_length=10,
        choices=EnrolmentReferenceTypeChoices.choices,
        blank=True,
    )
    enrolment_reference = models.CharField(max_length=100, blank=True)

    status = models.CharField(
        max_length=20,
        choices=StudyVisaApplicationStatusChoices.choices,
        default=StudyVisaApplicationStatusChoices.NOT_READY,
    )
    visa_tracking_reference = models.CharField(max_length=100, blank=True)
    visa_application_date = models.DateField(null=True, blank=True)
    biometrics_status = models.CharField(
        max_length=15,
        choices=BiometricsStatusChoices.choices,
        blank=True,
    )
    medical_tb_status = models.CharField(
        max_length=15,
        choices=MedicalTBStatusChoices.choices,
        blank=True,
    )
    visa_decision = models.CharField(
        max_length=15,
        choices=VisaDecisionChoices.choices,
        blank=True,
    )

    def __str__(self):
        # See VisaConsultancyCase.__str__: no FK dereference in a hot path.
        return f'{self.get_study_level_display()} at {self.institution}'
