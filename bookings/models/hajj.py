from django.db import models

from bookings.choices import (
    BookingStageChoices,
    QurbaniArrangementChoices,
    VisaStatusChoices,
)
from bookings.models.base import ServiceRecordBase


class HajjBooking(ServiceRecordBase):
    """A customer's Hajj service record for one Hajj year.

    Hajj is sold by year, not by date, which is why ``hajj_year`` is required
    while ``start_date``/``end_date`` are left null - a Hajj package spans a
    multi-week window set by the lunar calendar, and pinning a single departure
    and return date on the trip record would be a guess. ``stay_in_ksa_days``
    captures the package duration that actually matters commercially.

    ``visa_status`` is tracked independently of ``status`` because a booking can
    be confirmed while the Hajj visa is still in process - a normal and often
    long-running state for this service line.

    ``package`` is SET_NULL with ``related_name='hajj_trips'``: it is an optional
    link to the booked bundle, and losing it should never block deleting the
    package. Umrah and Tour use their own reverse names so the three do not clash.
    """

    hajj_year = models.CharField(max_length=9)
    # Ministry/chamber-issued identifier, separate from our booking reference.
    # It may not exist yet when an inquiry is recorded.
    application_number = models.CharField(max_length=100, blank=True, db_index=True)
    package_name = models.CharField(max_length=255)
    package_type = models.CharField(max_length=100, blank=True)
    stay_in_ksa_days = models.PositiveIntegerField(null=True, blank=True)
    group_name = models.CharField(max_length=100, blank=True)
    departure_city = models.CharField(max_length=100, blank=True)
    status = models.CharField(
        max_length=15,
        choices=BookingStageChoices.choices,
        default=BookingStageChoices.INQUIRY,
    )
    visa_status = models.CharField(
        max_length=15,
        choices=VisaStatusChoices.choices,
        blank=True,
    )
    maktab_service_provider = models.CharField(max_length=255, blank=True)
    qurbani_arrangement = models.CharField(
        max_length=20,
        choices=QurbaniArrangementChoices.choices,
        blank=True,
    )
    room_type = models.CharField(max_length=100, blank=True)
    package = models.ForeignKey(
        'bookings.Package',
        null=True,
        blank=True,
        related_name='hajj_trips',
        on_delete=models.SET_NULL,
    )

    def __str__(self):
        return f'Hajj {self.hajj_year} - {self.package_name}'
