from django.db import models

from bookings.choices import BookingStageChoices, TourTypeChoices
from bookings.models.base import ServiceRecordBase


class TourBooking(ServiceRecordBase):
    """A customer's tour package booking, domestic or international.

    Unlike Hajj and Umrah this record does use ``start_date``/``end_date`` - a
    tour has a real departure and return date - and ``number_of_travelers``
    because tours are priced per head.

    ``destination_country`` is required because "where are they going" is the
    primary way staff search and group tours; ``destination_city`` is optional
    because a multi-city tour has no single answer at this level (the per-leg
    detail belongs on the itinerary and on the component bookings).

    ``itinerary_summary`` is a short free-text description for the booking desk,
    not a structured itinerary - a real day-by-day itinerary is a document, and
    ``attachments`` already covers uploading one.

    ``tour_type`` drives whether visa/passport work is needed, which is why it is
    a field rather than a label on the tour name.
    """

    tour_name = models.CharField(max_length=255)
    tour_type = models.CharField(
        max_length=15,
        choices=TourTypeChoices.choices,
        blank=True,
    )
    destination_country = models.CharField(max_length=100)
    destination_city = models.CharField(max_length=100, blank=True)
    number_of_travelers = models.PositiveIntegerField(null=True, blank=True)
    package_name = models.CharField(max_length=255, blank=True)
    status = models.CharField(
        max_length=15,
        choices=BookingStageChoices.choices,
        default=BookingStageChoices.INQUIRY,
    )
    itinerary_summary = models.TextField(blank=True)
    package = models.ForeignKey(
        'bookings.Package',
        null=True,
        blank=True,
        related_name='tour_trips',
        on_delete=models.SET_NULL,
    )

    def __str__(self):
        return f'{self.tour_name} ({self.destination_country})'
