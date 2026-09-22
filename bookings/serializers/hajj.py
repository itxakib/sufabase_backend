from rest_framework import serializers

from bookings.models.hajj import HajjBooking
from bookings.models.package import Package
from bookings.serializers.package import PackageMiniSerializer
from common.serializers import TenantScopedSerializerMixin
from customers.models import Customer
from customers.serializers import CustomerMiniSerializer
from users.models import User
from users.serializers import UserMiniSerializer


class HajjBookingListSerializer(serializers.ModelSerializer):
    """Read-only list — nested mini serializers for every FK."""
    customer = CustomerMiniSerializer(read_only=True)
    sales_agent = UserMiniSerializer(read_only=True)
    package = PackageMiniSerializer(read_only=True)

    class Meta:
        model = HajjBooking
        fields = [
            "id", "customer", "booking_reference", "start_date", "end_date",
            "amount", "currency", "sales_agent", "status", "hajj_year", "application_number",
            "package_name", "group_name", "departure_city", "visa_status",
            "package", "created_at",
        ]
        read_only_fields = fields


class HajjBookingSerializer(TenantScopedSerializerMixin, serializers.ModelSerializer):
    """Create / update for a Hajj service record.

    ``customer``, ``sales_agent`` and ``package`` are restricted to the
    requesting company's own rows by the mixin.  ``company`` / ``created_by`` /
    ``updated_by`` are never writable.

    ``package`` belongs in that list for the same reason the other two do, and it
    used to be missing: the link is written from a client-supplied id, so without
    the scoping a crafted payload could point this booking at another company's
    package.  It is covered by ``PackageCompositionApiTests``.
    """

    tenant_scoped_fields = {
        "customer": Customer,
        "sales_agent": User,
        "package": Package,
    }

    class Meta:
        model = HajjBooking
        fields = [
            "id",
            "customer",
            "booking_reference",
            "start_date",
            "end_date",
            "amount",
            "currency",
            "sales_agent",
            "status",
            "notes",
            "created_at",
            "updated_at",
            # Hajj-specific
            "hajj_year",
            "application_number",
            "package_name",
            "package_type",
            "stay_in_ksa_days",
            "group_name",
            "departure_city",
            "visa_status",
            "maktab_service_provider",
            "qurbani_arrangement",
            "room_type",
            "package",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
