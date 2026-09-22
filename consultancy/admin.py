"""Django admin registration for the consultancy app.

Django admin is currently the only write path in SUFABASE (the module APIs are
read-only), so both case models are registered here. The two share one admin base
class for the fields ``CaseRecordBase`` provides, and each adds only the columns
specific to its own case type.
"""

from django.contrib import admin

from consultancy.models import StudyVisaCase, VisaConsultancyCase


class CaseRecordAdmin(admin.ModelAdmin):
    """Shared admin config for the two ``CaseRecordBase`` subclasses.

    Never registered itself - it has no model.

    ``customer`` and ``assigned_counselor`` are autocomplete rather than plain
    selects: both tables grow without bound in a live CRM, and rendering every
    customer into a dropdown is the classic way an admin page stops loading.
    ``customer__*`` in ``search_fields`` is the workflow that matters - "find this
    person's cases".

    ``date_hierarchy`` is on ``case_open_date`` because that is the axis cases are
    actually worked and reported on (cases opened this month), unlike a booking's
    departure date.
    """

    list_display = (
        'customer',
        'company',
        'destination_country',
        'case_open_date',
        'decision_date',
        'service_value',
        'currency',
        'status',
        'assigned_counselor',
    )
    list_filter = ('company', 'status')
    search_fields = (
        'customer__full_name',
        'customer__phone',
        'destination_country',
    )
    autocomplete_fields = ('customer', 'assigned_counselor')
    list_select_related = ('company', 'customer', 'assigned_counselor')
    readonly_fields = ('created_at', 'updated_at', 'created_by', 'updated_by')
    date_hierarchy = 'case_open_date'


@admin.register(VisaConsultancyCase)
class VisaConsultancyCaseAdmin(CaseRecordAdmin):
    list_display = CaseRecordAdmin.list_display + (
        'visa_category',
        'embassy_vac',
        'visa_decision',
    )
    search_fields = CaseRecordAdmin.search_fields + (
        'purpose_of_travel',
        'embassy_vac',
        'application_tracking_reference',
    )
    # Every one of these is a filter staff actually reach for, because each is a
    # different queue of work rather than a different label on the same queue.
    list_filter = (
        'company',
        'status',
        'visa_category',
        'visa_decision',
        'document_checklist_status',
        'biometrics_status',
        'passport_collection_status',
    )


@admin.register(StudyVisaCase)
class StudyVisaCaseAdmin(CaseRecordAdmin):
    list_display = CaseRecordAdmin.list_display + (
        'institution',
        'study_level',
        'institution_application_status',
        'visa_decision',
    )
    search_fields = CaseRecordAdmin.search_fields + (
        'institution',
        'field_of_study',
        'institution_reference',
        'enrolment_reference',
        'visa_tracking_reference',
    )
    list_filter = (
        'company',
        'status',
        'study_level',
        'institution_application_status',
        'offer_acceptance_status',
        'academic_documents_status',
        'financial_evidence_status',
        'biometrics_status',
        'medical_tb_status',
        'visa_decision',
    )
