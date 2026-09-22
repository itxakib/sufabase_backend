"""ViewSets for the consultancy app — visa and study-visa case workflows.

These are case-flow services, not dated bookings — the filter fields
reflect the document/checklist/decision chain rather than date ranges.
"""

from common.attachment_views import AttachmentActionsMixin
from common.viewsets import TenantScopedViewSetMixin
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets

from consultancy.models import StudyVisaCase, VisaConsultancyCase
from consultancy.serializers import (
    StudyVisaCaseListSerializer,
    StudyVisaCaseSerializer,
    VisaConsultancyCaseListSerializer,
    VisaConsultancyCaseSerializer,
)


class VisaConsultancyCaseViewSet(AttachmentActionsMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """General (non-study) visa consultancy cases — visit, business, family,
    transit, or work."""

    queryset = VisaConsultancyCase.objects.select_related('customer', 'assigned_counselor').all()

    def get_serializer_class(self):
        if self.action == 'list':
            return VisaConsultancyCaseListSerializer
        return VisaConsultancyCaseSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["status", "customer", "visa_category", "visa_decision"]
    search_fields = [
        "destination_country",
        "application_tracking_reference",
        "embassy_vac",
        "customer__full_name",
        "customer__phone",
    ]
    ordering_fields = ["visa_category", "status", "case_open_date", "decision_date", "created_at", "updated_at"]
    ordering = ["-created_at"]


class StudyVisaCaseViewSet(AttachmentActionsMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """Study-visa / education-consultancy cases — course/institution
    application through to visa decision."""

    queryset = StudyVisaCase.objects.select_related('customer', 'assigned_counselor').all()

    def get_serializer_class(self):
        if self.action == 'list':
            return StudyVisaCaseListSerializer
        return StudyVisaCaseSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["status", "customer", "study_level", "visa_decision"]
    search_fields = [
        "institution",
        "field_of_study",
        "destination_country",
        "visa_tracking_reference",
        "customer__full_name",
        "customer__phone",
    ]
    ordering_fields = ["study_level", "status", "case_open_date", "decision_date", "created_at", "updated_at"]
    ordering = ["-created_at"]
