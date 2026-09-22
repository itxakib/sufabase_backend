from rest_framework import serializers

from bookings.models.hotel import HotelBooking
from bookings.status_rules import STATUS_REQUIRED_FIELDS
from common.serializers import StatusRequiredFieldsMixin, TenantScopedSerializerMixin
from customers.models import Customer
from customers.serializers import CustomerMiniSerializer
from users.models import User
from users.serializers import UserMiniSerializer


class HotelBookingListSerializer(serializers.ModelSerializer):
    """Read-only list — nested mini serializers for every FK."""
    customer = CustomerMiniSerializer(read_only=True)
    sales_agent = UserMiniSerializer(read_only=True)

    class Meta:
        model = HotelBooking
        fields = [
            "id", "customer", "booking_reference", "start_date", "end_date",
            "amount", "currency", "sales_agent", "status",
            "hotel_name", "city", "country", "room_type", "lead_guest_name",
            "confirmation_number", "created_at",
        ]
        read_only_fields = fields


class HotelBookingSerializer(
    StatusRequiredFieldsMixin,
    TenantScopedSerializerMixin,
    serializers.ModelSerializer,
):
    """Create / update for a hotel stay record.

    ``lead_guest_name`` is only demanded from ``CONFIRMED`` onwards — a group
    booking is taken before the rooming list exists.
    """

    tenant_scoped_fields = {
        "customer": Customer,
        "sales_agent": User,
    }
    status_required_fields = STATUS_REQUIRED_FIELDS['HotelBooking']

    class Meta:
        model = HotelBooking
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
            # Hotel-specific
            "lead_guest_name",
            "hotel_name",
            "country",
            "city",
            "number_of_rooms",
            "room_type",
            "occupancy_type",
            "number_of_guests",
            "meal_plan",
            "confirmation_number",
            "supplier_agent",
            "cancellation_deadline",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
