from rest_framework import serializers

from bookings.models.package import Package
from bookings.models.umrah import UmrahBooking
from bookings.serializers.package import PackageMiniSerializer
from common.serializers import TenantScopedSerializerMixin
from customers.models import Customer
from customers.serializers import CustomerMiniSerializer
from users.models import User
from users.serializers import UserMiniSerializer


class UmrahBookingListSerializer(serializers.ModelSerializer):
    """Read-only list — nested mini serializers for every FK."""
    customer = CustomerMiniSerializer(read_only=True)
    sales_agent = UserMiniSerializer(read_only=True)
    package = PackageMiniSerializer(read_only=True)

    class Meta:
        model = UmrahBooking
        fields = [
            "id", "customer", "booking_reference", "start_date", "end_date",
            "amount", "currency", "sales_agent", "status",
            "umrah_year_season", "package_name", "visa_status", "package", "created_at",
        ]
        read_only_fields = fields


class UmrahBookingSerializer(TenantScopedSerializerMixin, serializers.ModelSerializer):
    """Create / update for an Umrah service record.

    ``package`` is company-scoped like the other two FKs - see the note on
    ``HajjBookingSerializer`` for why that is not optional.
    """

    tenant_scoped_fields = {
        "customer": Customer,
        "sales_agent": User,
        "package": Package,
    }

    class Meta:
        model = UmrahBooking
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
            # Umrah-specific
            "umrah_year_season",
            "package_name",
            "package_category",
            "total_duration_nights",
            "visa_status",
            "room_occupancy_type",
            "package",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
