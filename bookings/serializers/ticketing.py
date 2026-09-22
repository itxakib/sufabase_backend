from rest_framework import serializers

from bookings.models.ticketing import TicketingBooking
from bookings.status_rules import STATUS_REQUIRED_FIELDS
from common.serializers import StatusRequiredFieldsMixin, TenantScopedSerializerMixin
from customers.models import Customer
from customers.serializers import CustomerMiniSerializer
from users.models import User
from users.serializers import UserMiniSerializer


class TicketingBookingListSerializer(serializers.ModelSerializer):
    """Read-only list — nested mini serializers for every FK."""
    customer = CustomerMiniSerializer(read_only=True)
    sales_agent = UserMiniSerializer(read_only=True)

    class Meta:
        model = TicketingBooking
        fields = [
            "id", "customer", "booking_reference", "start_date", "end_date",
            "amount", "currency", "sales_agent", "status",
            "passenger_name", "airline", "flight_number", "origin",
            "destination", "cabin_class", "pnr", "ticket_issue_date",
            "created_at",
        ]
        read_only_fields = fields


class TicketingBookingSerializer(
    StatusRequiredFieldsMixin,
    TenantScopedSerializerMixin,
    serializers.ModelSerializer,
):
    """Create / update for an airline ticket record.

    ``pnr`` is only demanded from ``ISSUED`` onwards. A ticket is created at the
    moment it is sold; the PNR does not exist until it is issued, so requiring it
    up front would only ever collect a placeholder.
    """

    tenant_scoped_fields = {
        "customer": Customer,
        "sales_agent": User,
    }
    status_required_fields = STATUS_REQUIRED_FIELDS['TicketingBooking']

    class Meta:
        model = TicketingBooking
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
            # Ticketing-specific
            "passenger_name",
            "passenger_type",
            "pnr",
            "e_ticket_number",
            "airline",
            "flight_number",
            "trip_type",
            "origin",
            "destination",
            "departure_time",
            "arrival_time",
            "cabin_class",
            "baggage_allowance",
            "ticket_issue_date",
            "refund_status",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
