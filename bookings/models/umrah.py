from django.db import models

from bookings.choices import BookingStageChoices, VisaStatusChoices
from bookings.models.base import ServiceRecordBase


class UmrahBooking(ServiceRecordBase):
    """A customer's Umrah service record for one year or season.

    Umrah runs year-round and is sold by season rather than a fixed date, which
    is why ``umrah_year_season`` is free text (it has to hold things like
    "Ramadan 2026" or "Shawwal 1447") and why ``start_date``/``end_date`` are
    left null on the trip record. ``total_duration_nights`` is the commercially
    meaningful duration.

    ``room_occupancy_type`` is free text rather than reusing
    ``OccupancyTypeChoices`` because at this level staff record the package's
    advertised sharing basis ("quad sharing", "triple with child"), which does
    not always map cleanly onto a single fixed occupancy value. The per-hotel
    truth lives on the ``HotelBooking`` rows in the package.

    ``visa_status`` is independent of ``status`` for the same reason as Hajj:
    Umrah visas are routinely still in process on a confirmed booking.
    """

    umrah_year_season = models.CharField(max_length=50)
    package_name = models.CharField(max_length=255)
    package_category = models.CharField(max_length=100, blank=True)
    total_duration_nights = models.PositiveIntegerField(null=True, blank=True)
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
    room_occupancy_type = models.CharField(max_length=100, blank=True)
    package = models.ForeignKey(
        'bookings.Package',
        null=True,
        blank=True,
        related_name='umrah_trips',
        on_delete=models.SET_NULL,
    )

    def __str__(self):
        return f'Umrah {self.umrah_year_season} - {self.package_name}'
