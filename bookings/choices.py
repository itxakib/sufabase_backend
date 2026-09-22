"""Choice enumerations for the bookings app.

Choices live in their own module rather than being inlined as tuples on each
model field, per the project-wide convention (see ``customers/choices.py``).
Views, serializers, filters, reports and tests can then import the full set of
valid options without importing the models themselves.

Some values are shared on purpose and some are not:

* Hajj, Umrah and Tour all run on ``BookingStageChoices`` so one pipeline report
  can read across all three service lines.
* Ticketing, Hotel and Transport each get their own status flow, because their
  real-world lifecycles genuinely differ - a ticket can be refunded and a hotel
  stay cannot, and collapsing them into one enum would only hide that.
"""

from django.db import models


class BookingStageChoices(models.TextChoices):
    """Shared commercial pipeline for Hajj, Umrah and Tour records.

    INQUIRY is the default: a record is created the moment a customer asks about
    a trip, before any money or commitment exists. BOOKED means the customer has
    committed and a booking reference exists; CONFIRMED means the supplier side
    is locked in (visa, seat, room). COMPLETED is the terminal success state used
    for retention and repeat-sale reporting; CANCELLED is the terminal failure
    state and must never be treated as COMPLETED in revenue reporting.
    """

    INQUIRY = 'INQUIRY', 'Inquiry'
    BOOKED = 'BOOKED', 'Booked'
    CONFIRMED = 'CONFIRMED', 'Confirmed'
    COMPLETED = 'COMPLETED', 'Completed'
    CANCELLED = 'CANCELLED', 'Cancelled'


class VisaStatusChoices(models.TextChoices):
    """Where the customer's visa application stands.

    Tracked separately from the booking stage because the two move independently:
    a booking can be CONFIRMED while the visa is still IN_PROCESS, and a visa
    PROBLEM does not by itself cancel the booking. Left blank rather than
    defaulted, because "not started" and "not applicable" (domestic tours) are
    different answers and only a human knows which applies.
    """

    NOT_APPLIED = 'NOT_APPLIED', 'Not Applied'
    IN_PROCESS = 'IN_PROCESS', 'In Process'
    ISSUED = 'ISSUED', 'Issued'
    PROBLEM = 'PROBLEM', 'Rejected / Problem'


class QurbaniArrangementChoices(models.TextChoices):
    """How the Hajj/Umrah Qurbani obligation is being handled.

    INCLUDED means it is part of the package price; ARRANGED means the company
    arranges it but it is billed or handled separately; NOT_APPLICABLE covers
    seasons and packages where it does not arise.
    """

    INCLUDED = 'INCLUDED', 'Included'
    ARRANGED = 'ARRANGED', 'Arranged'
    NOT_APPLICABLE = 'NOT_APPLICABLE', 'Not Applicable'


class TourTypeChoices(models.TextChoices):
    """Whether a tour stays inside the country or crosses a border.

    Drives different paperwork (domestic tours need no visa or passport) and
    different supplier sets, so it is a field rather than a free-text label.
    """

    DOMESTIC = 'DOMESTIC', 'Domestic'
    INTERNATIONAL = 'INTERNATIONAL', 'International'


class TicketStatusChoices(models.TextChoices):
    """Lifecycle of an airline ticket.

    RESERVED is the default: a PNR is held but not yet paid for, and it is the
    state where the seat can still be lost. ISSUED means the ticket is paid and
    ticketed. REISSUED covers a voluntary change (date/route) on an already
    issued ticket, which is distinct from a refund because money stays with the
    airline. REFUNDED is the terminal state of a cancelled-and-credited ticket.
    """

    RESERVED = 'RESERVED', 'Reserved'
    ISSUED = 'ISSUED', 'Issued'
    REISSUED = 'REISSUED', 'Reissued'
    CANCELLED = 'CANCELLED', 'Cancelled'
    REFUNDED = 'REFUNDED', 'Refunded'


class TripTypeChoices(models.TextChoices):
    """Journey shape. MULTI covers multi-city itineraries and multi-leg journeys
    that neither ONE_WAY nor ROUND_TRIP describes honestly."""

    ONE_WAY = 'ONE_WAY', 'One-way'
    ROUND_TRIP = 'ROUND_TRIP', 'Round-trip'
    MULTI = 'MULTI', 'Multi-city / Multi-leg'


class CabinClassChoices(models.TextChoices):
    """Airline cabin class. PREMIUM_ECONOMY is separate from ECONOMY because it
    prices differently and is a common upgrade upsell."""

    ECONOMY = 'ECONOMY', 'Economy'
    PREMIUM_ECONOMY = 'PREMIUM_ECONOMY', 'Premium Economy'
    BUSINESS = 'BUSINESS', 'Business'
    FIRST = 'FIRST', 'First'


class PassengerTypeChoices(models.TextChoices):
    """Passenger category, which drives fare and seat rules (infants often share
    an adult's seat and carry no baggage allowance of their own)."""

    ADULT = 'ADULT', 'Adult'
    CHILD = 'CHILD', 'Child'
    INFANT = 'INFANT', 'Infant'


class RefundStatusChoices(models.TextChoices):
    """Where a refund claim stands, tracked separately from ticket status because
    a ticket can be CANCELLED while the money is still outstanding.

    PARTIAL exists because airline penalties and partial credits are the norm,
    not the exception.
    """

    NOT_REQUESTED = 'NOT_REQUESTED', 'Not Requested'
    REQUESTED = 'REQUESTED', 'Requested'
    PROCESSED = 'PROCESSED', 'Processed'
    REJECTED = 'REJECTED', 'Rejected'
    PARTIAL = 'PARTIAL', 'Partial'


class HotelStatusChoices(models.TextChoices):
    """Lifecycle of a hotel stay record, kept deliberately parallel to
    ``BookingStageChoices`` but with PENDING instead of BOOKED - a hotel booking
    is either an inquiry, awaiting supplier confirmation, or it is not."""

    INQUIRY = 'INQUIRY', 'Inquiry'
    PENDING = 'PENDING', 'Pending'
    CONFIRMED = 'CONFIRMED', 'Confirmed'
    COMPLETED = 'COMPLETED', 'Completed'
    CANCELLED = 'CANCELLED', 'Cancelled'


class OccupancyTypeChoices(models.TextChoices):
    """How many people share one room. SHARING is distinct from QUAD because it
    means an unspecified number of same-gender roommates (the common Hajj/Umrah
    option), not a fixed four."""

    SINGLE = 'SINGLE', 'Single'
    DOUBLE = 'DOUBLE', 'Double'
    TRIPLE = 'TRIPLE', 'Triple'
    QUAD = 'QUAD', 'Quad'
    SHARING = 'SHARING', 'Sharing'


class MealPlanChoices(models.TextChoices):
    """Board basis, which is a pricing line in every hotel quote."""

    ROOM_ONLY = 'ROOM_ONLY', 'Room Only'
    BREAKFAST = 'BREAKFAST', 'Breakfast'
    HALF_BOARD = 'HALF_BOARD', 'Half Board'
    FULL_BOARD = 'FULL_BOARD', 'Full Board'


class TransportServiceTypeChoices(models.TextChoices):
    """Which ground-transport product this record is.

    ZIYARAT is its own type rather than a LOCAL_TRANSFER because it is a sold,
    priced religious-travel service in this business, not incidental movement.
    """

    AIRPORT_TRANSFER = 'AIRPORT_TRANSFER', 'Airport Transfer'
    HOTEL_TRANSFER = 'HOTEL_TRANSFER', 'Hotel Transfer'
    INTERCITY = 'INTERCITY', 'Intercity'
    LOCAL_TRANSFER = 'LOCAL_TRANSFER', 'Local Transfer'
    ZIYARAT = 'ZIYARAT', 'Ziyarat'
    SHUTTLE = 'SHUTTLE', 'Shuttle'
    PRIVATE_VEHICLE = 'PRIVATE_VEHICLE', 'Private Vehicle'


class TransportStatusChoices(models.TextChoices):
    """Lifecycle of a transport job, including the two states a vehicle booking
    needs and a flight does not: DRIVER_ASSIGNED (the operational handover) and
    NO_SHOW (the customer never appeared - a billable event, and not the same
    thing as CANCELLED)."""

    INQUIRY = 'INQUIRY', 'Inquiry'
    PENDING = 'PENDING', 'Pending'
    CONFIRMED = 'CONFIRMED', 'Confirmed'
    DRIVER_ASSIGNED = 'DRIVER_ASSIGNED', 'Driver Assigned'
    COMPLETED = 'COMPLETED', 'Completed'
    CANCELLED = 'CANCELLED', 'Cancelled'
    NO_SHOW = 'NO_SHOW', 'No-show'
