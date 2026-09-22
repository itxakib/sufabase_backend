from rest_framework import serializers

from bookings.models.transport import TransportBooking
from bookings.status_rules import STATUS_REQUIRED_FIELDS
from common.serializers import StatusRequiredFieldsMixin, TenantScopedSerializerMixin
from customers.models import Customer
from customers.serializers import CustomerMiniSerializer
from users.models import User
from users.serializers import UserMiniSerializer


class TransportBookingListSerializer(serializers.ModelSerializer):
    """Read-only list — nested mini serializers for every FK."""
    customer = CustomerMiniSerializer(read_only=True)
    sales_agent = UserMiniSerializer(read_only=True)

    class Meta:
        model = TransportBooking
        fields = [
            "id", "customer", "booking_reference", "start_date", "end_date",
            "amount", "currency", "sales_agent", "status",
            "service_type", "pickup_location", "dropoff_location",
            "vehicle_type", "lead_passenger_name", "created_at",
        ]
        read_only_fields = fields


class TransportBookingSerializer(
    StatusRequiredFieldsMixin,
    TenantScopedSerializerMixin,
    serializers.ModelSerializer,
):
    """Create / update for a ground transport record.

    ``pickup_time`` is only demanded from ``DRIVER_ASSIGNED`` onwards — the time
    is settled after the vehicle is booked, but nobody can be dispatched without
    it.
    """

    tenant_scoped_fields = {
        "customer": Customer,
        "sales_agent": User,
    }
    status_required_fields = STATUS_REQUIRED_FIELDS['TransportBooking']

    class Meta:
        model = TransportBooking
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
            # Transport-specific
            "lead_passenger_name",
            "service_type",
            "trip_type",
            "pickup_location",
            "dropoff_location",
            "pickup_time",
            "number_of_passengers",
            "vehicle_type",
            "number_of_vehicles",
            "supplier_vendor",
            "flight_number_arrival_ref",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
