from rest_framework import serializers

from consultancy.models.visa_consultancy import VisaConsultancyCase
from common.serializers import TenantScopedSerializerMixin
from customers.models import Customer
from customers.serializers import CustomerMiniSerializer
from users.models import User
from users.serializers import UserMiniSerializer


class VisaConsultancyCaseListSerializer(serializers.ModelSerializer):
    """Read-only list — nested mini serializers for every FK."""
    customer = CustomerMiniSerializer(read_only=True)
    assigned_counselor = UserMiniSerializer(read_only=True)

    class Meta:
        model = VisaConsultancyCase
        fields = [
            "id", "customer", "destination_country", "case_open_date",
            "decision_date", "service_value", "assigned_counselor", "status",
            "visa_category", "visa_decision", "created_at",
        ]
        read_only_fields = fields


class VisaConsultancyCaseSerializer(TenantScopedSerializerMixin, serializers.ModelSerializer):
    """Create / update for a visa consultancy case."""

    tenant_scoped_fields = {
        "customer": Customer,
        "assigned_counselor": User,
    }

    class Meta:
        model = VisaConsultancyCase
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
            # Visa-specific
            "visa_category",
            "purpose_of_travel",
            "intended_travel_date",
            "status",
            "embassy_vac",
            "application_tracking_reference",
            "application_submission_date",
            "appointment_date",
            "biometrics_status",
            "document_checklist_status",
            "visa_decision",
            "visa_valid_from",
            "visa_valid_until",
            "passport_collection_status",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
