from rest_framework import serializers

from consultancy.models.study_visa import StudyVisaCase
from common.serializers import TenantScopedSerializerMixin
from customers.models import Customer
from customers.serializers import CustomerMiniSerializer
from users.models import User
from users.serializers import UserMiniSerializer


class StudyVisaCaseListSerializer(serializers.ModelSerializer):
    """Read-only list — nested mini serializers for every FK."""
    customer = CustomerMiniSerializer(read_only=True)
    assigned_counselor = UserMiniSerializer(read_only=True)

    class Meta:
        model = StudyVisaCase
        fields = [
            "id", "customer", "destination_country", "case_open_date",
            "decision_date", "service_value", "assigned_counselor", "status",
            "study_level", "institution", "visa_decision", "created_at",
        ]
        read_only_fields = fields


class StudyVisaCaseSerializer(TenantScopedSerializerMixin, serializers.ModelSerializer):
    """Create / update for a study-visa case."""

    tenant_scoped_fields = {
        "customer": Customer,
        "assigned_counselor": User,
    }

    class Meta:
        model = StudyVisaCase
        fields = [
            "id",
            "customer",
            "destination_country",
            "case_open_date",
            "decision_date",
            "service_value",
            "currency",
            "assigned_counselor",
            "notes",
            "created_at",
            "updated_at",
            # Study-specific
            "study_level",
            "field_of_study",
            "preferred_intake",
            "institution",
            "institution_application_status",
            "institution_reference",
            "offer_acceptance_status",
            "course_start_date",
            "tuition_fee",
            "tuition_deposit_paid",
            "highest_qualification",
            "english_test_type",
            "english_test_score",
            "academic_documents_status",
            "sop_status",
            "financial_evidence_status",
            "enrolment_reference_type",
            "enrolment_reference",
            "status",
            "visa_tracking_reference",
            "visa_application_date",
            "biometrics_status",
            "medical_tb_status",
            "visa_decision",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
