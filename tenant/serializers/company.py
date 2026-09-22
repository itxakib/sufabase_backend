from rest_framework import serializers

from tenant.models import Company


class CompanySerializer(serializers.ModelSerializer):
    """Read serializer for a tenant profile.

    Every field is read-only: Module 01 exposes the staff-visible company
    directory, and creating or editing a company is Module 07 (platform admin)
    work. ``created_by``/``updated_by`` are intentionally not exposed, and no
    field-level masking is applied - masking is Module 02's concern.
    """

    class Meta:
        model = Company
        fields = (
            'id', 'name', 'slug', 'legal_name',
            'registration_number', 'tax_number',
            'contact_email', 'contact_phone', 'website',
            'address', 'address_line1', 'address_line2',
            'city', 'state', 'postal_code', 'country',
            'currency', 'timezone', 'logo_url',
            'plan', 'is_active', 'onboarded_at',
            'created_at', 'updated_at',
        )
        read_only_fields = fields


class SettingsCompanySerializer(serializers.ModelSerializer):
    """Settings-panel serializer for the authenticated user's own company.

    Maps frontend field names (email, phone, address_line1) to model fields
    (contact_email, contact_phone, address). Only the user's own company is
    editable — the view filters by request.company.
    """

    # Map frontend names to model fields
    email = serializers.EmailField(source='contact_email', required=False)
    phone = serializers.CharField(source='contact_phone', required=False)
    address_line1 = serializers.CharField(required=False)

    class Meta:
        model = Company
        fields = (
            'id', 'name', 'legal_name', 'slug',
            'registration_number', 'tax_number',
            'email', 'phone', 'website',
            'address_line1', 'address_line2',
            'city', 'state', 'postal_code', 'country',
            'currency', 'timezone', 'logo_url',
        )
        read_only_fields = ('id', 'slug')
