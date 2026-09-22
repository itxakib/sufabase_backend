from rest_framework import serializers

from bookings.models.package import Package
from bookings.models.tour import TourBooking
from bookings.serializers.package import PackageMiniSerializer
from common.serializers import TenantScopedSerializerMixin
from customers.models import Customer
from customers.serializers import CustomerMiniSerializer
from users.models import User
from users.serializers import UserMiniSerializer


class TourBookingListSerializer(serializers.ModelSerializer):
    """Read-only list — nested mini serializers for every FK."""
    customer = CustomerMiniSerializer(read_only=True)
    sales_agent = UserMiniSerializer(read_only=True)
    package = PackageMiniSerializer(read_only=True)

    class Meta:
        model = TourBooking
        fields = [
            "id", "customer", "booking_reference", "start_date", "end_date",
            "amount", "currency", "sales_agent", "status",
            "tour_name", "tour_type", "destination_country", "destination_city",
            "package_name", "package", "created_at",
        ]
        read_only_fields = fields


class TourBookingSerializer(TenantScopedSerializerMixin, serializers.ModelSerializer):
    """Create / update for a tour service record.

    ``package`` is company-scoped like the other two FKs - see the note on
    ``HajjBookingSerializer`` for why that is not optional.
    """

    tenant_scoped_fields = {
        "customer": Customer,
        "sales_agent": User,
        "package": Package,
    }

    class Meta:
        model = TourBooking
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
            # Tour-specific
            "tour_name",
            "tour_type",
            "destination_country",
            "destination_city",
            "number_of_travelers",
            "package_name",
            "itinerary_summary",
            "package",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
