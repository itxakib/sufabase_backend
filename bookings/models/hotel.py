from django.db import models

from bookings.choices import (
    HotelStatusChoices,
    MealPlanChoices,
    OccupancyTypeChoices,
)
from bookings.models.base import ServiceRecordBase


class HotelBooking(ServiceRecordBase):
    """A hotel stay record - one reservation, one room block, one stay window.

    ``start_date``/``end_date`` are check-in and check-out, so the number of
    nights is derived rather than stored (a stored night count is a second source
    of truth that drifts the moment someone edits a date). ``cancellation_deadline``
    is kept because hotel suppliers impose real deadlines after which a
    cancellation is charged, and staff need that date visible up front.

    ``supplier_agent`` is free text rather than an FK: the counterparty is
    frequently an external agency or a hotel sales contact who will never be a
    SUFABASE user, and forcing them into ``users.User`` would be wrong.

    ``lead_guest_name`` is ``blank=True`` because a group booking goes in before
    the rooming list exists. It becomes required at ``CONFIRMED``/``COMPLETED``,
    where a stay provably has a named guest - see ``bookings/status_rules.py``.
    ``room_type`` stays required at every status: it is what the room is priced
    on, so a quote cannot be produced without it.
    """

    lead_guest_name = models.CharField(max_length=255, blank=True)
    hotel_name = models.CharField(max_length=255)
    country = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=100)
    number_of_rooms = models.PositiveIntegerField(null=True, blank=True)
    room_type = models.CharField(max_length=100)
    occupancy_type = models.CharField(
        max_length=15,
        choices=OccupancyTypeChoices.choices,
        blank=True,
    )
    number_of_guests = models.PositiveIntegerField(null=True, blank=True)
    meal_plan = models.CharField(
        max_length=15,
        choices=MealPlanChoices.choices,
        blank=True,
    )
    confirmation_number = models.CharField(max_length=100, blank=True)
    status = models.CharField(
        max_length=15,
        choices=HotelStatusChoices.choices,
        default=HotelStatusChoices.INQUIRY,
    )
    supplier_agent = models.CharField(max_length=255, blank=True)
    cancellation_deadline = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            # The database half of `status_rules` - `test_constraints_match_the_
            # rules_table` fails if this drifts from the table there.
            models.CheckConstraint(
                condition=(
                    ~models.Q(status__in=['CONFIRMED', 'COMPLETED'])
                    | ~models.Q(lead_guest_name='')
                ),
                name='hotel_lead_guest_required_once_confirmed',
            ),
        ]

    def __str__(self):
        return f'{self.hotel_name} ({self.city})'
