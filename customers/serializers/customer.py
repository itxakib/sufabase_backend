from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from common.serializers import TenantScopedSerializerMixin
from customers.models import Customer, Tag
from users.models import User
from users.serializers import UserMiniSerializer


class TagSerializer(serializers.ModelSerializer):
    """Tag — names and colours, company-scoped.

    The ``unique_together = (company, name)`` constraint is enforced here
    (not just at DB level) so duplicate names return a clean 400 instead of
    an IntegrityError 500.  ``company`` is not a serializer field — it's
    stamped by ``perform_create`` — so we validate manually against the
    requesting user's company.
    """

    class Meta:
        model = Tag
        fields = ["id", "name", "color"]
        read_only_fields = ["id"]

    def validate_name(self, value):
        """Check uniqueness of (company, name) at serializer level."""
        request = self.context.get("request")
        company = None
        if request:
            company = getattr(request, "company", None)
            if company is None:
                user = getattr(request, "user", None)
                if user and user.is_authenticated:
                    company = getattr(user, "company", None)
        if company is not None:
            qs = Tag.objects.filter(company=company, name=value)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    "A tag with this name already exists for your company."
                )
        return value


class CustomerMiniSerializer(serializers.ModelSerializer):
    """Minimal customer representation — used nested inside booking/
    consultancy list serializers so the frontend sees a name instead of
    a bare integer ID.  Six fields only, zero extra queries.  Read-only.

    ``avatar`` is included despite the "minimal" name: a booking row and a
    customer row render the same person, and an avatar that appears on one
    screen and disappears on the next reads as a bug rather than as a lean
    payload.  It is a stored URL on the row, so it costs no extra query.
    """

    class Meta:
        model = Customer
        fields = ["id", "avatar", "full_name", "phone", "city", "stage"]
        read_only_fields = fields


class CustomerListSerializer(serializers.ModelSerializer):
    """Lightweight — the customer table/list view.

    Eight fields only: enough to render a scanable list, not the 56-field
    detail page.  Tags are nested for display, ``stage`` and ``record_status``
    are choice labels rather than raw values.
    """

    tags = TagSerializer(many=True, read_only=True)

    class Meta:
        model = Customer
        fields = [
            "id",
            "avatar",
            "full_name",
            "phone",
            "city",
            "profession",
            "stage",
            "record_status",
            "tags",
        ]
        read_only_fields = ["id"]


class CustomerDetailSerializer(serializers.ModelSerializer):
    """Full profile — every field plus derived service_summary.

    ``service_summary`` calls the selector, which costs 8 fixed queries.
    That is fine for a single-record detail view and deliberately not on the
    list serializer — calling it once per row would be 8 × N queries.
    """

    tags = TagSerializer(many=True, read_only=True)
    assigned_agent = UserMiniSerializer(read_only=True)
    service_summary = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = [
            # Identity
            "id",
            "avatar",
            "full_name",
            "father_husband_name",
            "gender",
            "date_of_birth",
            "cnic_number",
            "cnic_expiry_date",
            "passport_number",
            "passport_issue_date",
            "passport_expiry_date",
            "nationality",
            "marital_status",
            # Contact
            "phone",
            "whatsapp_number",
            "alt_phone",
            "email",
            # Location
            "country",
            "city",
            "location_area",
            "sub_location",
            "complete_address",
            # Professional
            "profession",
            "business_type",
            "company_name",
            "designation",
            "business_address",
            "business_contact_number",
            # CRM meta
            "customer_source",
            "referred_by",
            "preferred_contact_method",
            "preferred_language",
            "assigned_agent",
            "notes",
            # Status
            "stage",
            "record_status",
            # Marketing
            "marketing_contact_permission",
            # Emergency
            "emergency_contact_name",
            "emergency_contact_relationship",
            "emergency_contact_number",
            # Relations
            "family_group_reference",
            "tags",
            "service_summary",
            # Inherited
            "company",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "company",
            "created_at",
            "updated_at",
        ]

    @extend_schema_field({
        "type": "object",
        "description": "Per-service record counts (hajj, umrah, tour, ticketing, hotel, transport, visa_consultancy, study_visa).",
        "properties": {
            "hajj": {"type": "integer"},
            "umrah": {"type": "integer"},
            "tour": {"type": "integer"},
            "ticketing": {"type": "integer"},
            "hotel": {"type": "integer"},
            "transport": {"type": "integer"},
            "visa_consultancy": {"type": "integer"},
            "study_visa": {"type": "integer"},
        },
    })
    def get_service_summary(self, obj):
        """Derived counts — the 8 service totals deliberately never stored
        as columns on Customer."""
        from customers.selectors.customer_selectors import CustomerSelector

        return CustomerSelector.service_summary(obj)




class CustomerWriteSerializer(TenantScopedSerializerMixin, serializers.ModelSerializer):
    """Create / update.

    ``company``, ``created_by``, ``updated_by`` are never writable fields —
    the view stamps them from ``request.user.company`` / ``request.user``.
    Using ``exclude`` as a safety net: if a future field is added to
    Customer, it becomes writable by default, which is the safer default than
    silently ignoring it.
    """

    tenant_scoped_fields = {
        "assigned_agent": User,
        "tags": Tag,
    }
    tags = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Tag.objects.none(), required=False
    )

    class Meta:
        model = Customer
        exclude = ["company", "created_by", "updated_by"]
        read_only_fields = ["id", "created_at", "updated_at"]






# Backward-compatible alias — the existing view imports this name directly
CustomerSerializer = CustomerDetailSerializer
