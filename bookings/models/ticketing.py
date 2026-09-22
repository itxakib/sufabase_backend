from django.db import models

from bookings.choices import (
    CabinClassChoices,
    PassengerTypeChoices,
    RefundStatusChoices,
    TicketStatusChoices,
    TripTypeChoices,
)
from bookings.models.base import ServiceRecordBase


class TicketingBooking(ServiceRecordBase):
    """An airline ticket record - one customer, one journey.

    ``start_date``/``end_date`` are the departure and return dates, so a
    round-trip is a single row rather than two. ``refund_status`` is tracked
    separately from ``status`` because a cancelled ticket can still be awaiting
    money back, and that outstanding balance is exactly what finance chases.

    Kept independent of ``Package`` rather than nested inside it: a ticket can be
    sold on its own, and when it is part of a Hajj/Umrah/Tour trip the
    composition is recorded on the ``Package`` that points at this row.

    ``pnr`` is ``blank=True`` even though an issued ticket always has one: a
    ticket is created at the moment it is *sold*, and the PNR does not exist
    until it is *issued*. It becomes required at ``ISSUED``/``REISSUED`` -- see
    ``bookings/status_rules.py`` and the ``CheckConstraint`` in ``Meta`` below,
    which is the same rule stated in the database so it cannot be bypassed.
    """

    passenger_name = models.CharField(max_length=255)
    passenger_type = models.CharField(
        max_length=10,
        choices=PassengerTypeChoices.choices,
        blank=True,
    )
    pnr = models.CharField(max_length=20, blank=True)
    e_ticket_number = models.CharField(max_length=50, blank=True)
    airline = models.CharField(max_length=100)
    flight_number = models.CharField(max_length=20, blank=True)
    trip_type = models.CharField(
        max_length=15,
        choices=TripTypeChoices.choices,
        blank=True,
    )
    origin = models.CharField(max_length=100)
    destination = models.CharField(max_length=100)
    departure_time = models.TimeField(null=True, blank=True)
    arrival_time = models.TimeField(null=True, blank=True)
    cabin_class = models.CharField(
        max_length=20,
        choices=CabinClassChoices.choices,
        blank=True,
    )
    baggage_allowance = models.CharField(max_length=100, blank=True)
    ticket_issue_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=15,
        choices=TicketStatusChoices.choices,
        default=TicketStatusChoices.RESERVED,
    )
    refund_status = models.CharField(
        max_length=15,
        choices=RefundStatusChoices.choices,
        blank=True,
    )

    class Meta:
        constraints = [
            # The database half of `status_rules`. Keep the status list in step
            # with STATUS_REQUIRED_FIELDS['TicketingBooking'] -
            # `test_constraints_match_the_rules_table` fails if they drift.
            models.CheckConstraint(
                condition=(
                    ~models.Q(status__in=['ISSUED', 'REISSUED'])
                    | ~models.Q(pnr='')
                ),
                name='ticketing_pnr_required_once_issued',
            ),
        ]

    def __str__(self):
        return self.pnr or f'Ticket #{self.pk}'
