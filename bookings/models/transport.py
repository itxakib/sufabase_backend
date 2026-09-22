from django.db import models

from bookings.choices import (
    TransportServiceTypeChoices,
    TransportStatusChoices,
    TripTypeChoices,
)
from bookings.models.base import ServiceRecordBase


class TransportBooking(ServiceRecordBase):
    """A ground transport service record - one vehicle job for one date.

    ``start_date``/``end_date`` carry the pickup date (end is the return date for
    a trip that runs across days), while ``pickup_time`` is separate.

    ``pickup_time`` is nullable because it is routinely settled after the vehicle
    is booked - the time is confirmed once the flight is, or the day before. It
    becomes required at ``DRIVER_ASSIGNED``/``COMPLETED``: nobody can be sent to
    collect anyone without knowing when. ``vehicle_type`` and
    ``number_of_passengers`` stay required at every status, because they are what
    the job is priced on.

    ``number_of_passengers`` and ``number_of_vehicles`` are both required-ish
    numbers rather than derived, because they are what the supplier prices on and
    neither can be inferred from the customer record.

    ``flight_number_arrival_ref`` is what makes airport pickups workable in
    practice: the driver needs the inbound flight to track delays, and it is free
    text because the flight may belong to a ticket booked outside this system.

    Driver name/contact are intentionally absent for now - the spec marks them
    optional, and DRIVER_ASSIGNED already records that the operational handover
    happened. Add the driver fields when SUFA actually wants driver records here.
    """

    lead_passenger_name = models.CharField(max_length=255, blank=True)
    service_type = models.CharField(
        max_length=20,
        choices=TransportServiceTypeChoices.choices,
    )
    trip_type = models.CharField(
        max_length=15,
        choices=TripTypeChoices.choices,
        blank=True,
    )
    pickup_location = models.CharField(max_length=255)
    dropoff_location = models.CharField(max_length=255)
    pickup_time = models.TimeField(null=True, blank=True)
    number_of_passengers = models.PositiveIntegerField()
    vehicle_type = models.CharField(max_length=100)
    number_of_vehicles = models.PositiveIntegerField(null=True, blank=True)
    supplier_vendor = models.CharField(max_length=255, blank=True)
    flight_number_arrival_ref = models.CharField(max_length=50, blank=True)
    status = models.CharField(
        max_length=20,
        choices=TransportStatusChoices.choices,
        default=TransportStatusChoices.INQUIRY,
    )

    class Meta:
        constraints = [
            # The database half of `status_rules` - `test_constraints_match_the_
            # rules_table` fails if this drifts from the table there.
            models.CheckConstraint(
                condition=(
                    ~models.Q(status__in=['DRIVER_ASSIGNED', 'COMPLETED'])
                    | models.Q(pickup_time__isnull=False)
                ),
                name='transport_pickup_time_required_once_assigned',
            ),
        ]

    def __str__(self):
        return f'{self.get_service_type_display()} → {self.dropoff_location}'
