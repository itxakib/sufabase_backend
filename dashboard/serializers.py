"""Serializers for the dashboard summary endpoint."""

from rest_framework import serializers


class ServiceTotalSerializer(serializers.Serializer):
    """One row in the service_totals array."""
    service_type = serializers.CharField()
    count = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)


class UpcomingDepartureSerializer(serializers.Serializer):
    """One row in the upcoming_departures array."""
    id = serializers.IntegerField()
    service_type = serializers.CharField()
    customer_name = serializers.CharField()
    destination = serializers.CharField()
    start_date = serializers.DateField()
    booking_reference = serializers.CharField()
    status = serializers.CharField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)


class RecentActivitySerializer(serializers.Serializer):
    """One row in the recent_activity array."""
    id = serializers.IntegerField()
    service_type = serializers.CharField()
    customer_name = serializers.CharField()
    action = serializers.CharField()
    description = serializers.CharField()
    timestamp = serializers.DateTimeField()


class DashboardSummarySerializer(serializers.Serializer):
    """Top-level dashboard summary response."""
    total_customers = serializers.IntegerField()
    new_customers_this_month = serializers.IntegerField()
    total_revenue = serializers.DecimalField(max_digits=14, decimal_places=2)
    currency = serializers.CharField()
    service_totals = ServiceTotalSerializer(many=True)
    upcoming_departures = UpcomingDepartureSerializer(many=True)
    recent_activity = RecentActivitySerializer(many=True)
