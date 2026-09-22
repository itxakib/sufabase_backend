"""Which fields a status starts demanding.

**The problem this solves.** A component record is created at the moment it is
*sold*, not the moment it is *delivered*. At that point some of its fields
provably cannot be known yet:

* a PNR does not exist until the ticket is issued - yet ``status`` defaults to
  ``RESERVED``, the very state that means "not issued yet";
* the exact pickup time for an airport transfer is routinely learned the night
  before, not at booking;
* a group hotel booking may have no guest name until the rooming list arrives.

Making those fields unconditionally required forces staff to type a placeholder
(``"PENDING"`` into a PNR column), and a placeholder is worse than an empty
field: it is indistinguishable from real data forever after, so nobody can tell
which tickets actually need chasing.

**The rule instead:** a field is required once the record reaches the status
where it must exist. A ``RESERVED`` ticket is valid without a PNR; an ``ISSUED``
one is not.

``STATUS_REQUIRED_FIELDS`` below is the single source of truth, read by all
three enforcement layers so they cannot disagree:

* ``ServiceRecordBase.clean()`` -> Django admin and ModelForms, via
  :func:`check_instance`
* ``StatusRequiredFieldsMixin`` in ``common/serializers.py`` -> the API, which
  takes the relevant dict straight out of this table onto the serializer class
* the ``CheckConstraint`` in each affected model's ``Meta`` -> the database
  itself, which is the layer nothing can bypass
  (``bookings/tests/test_models.py`` asserts those constraints still agree with
  this table, so drift is a failing test rather than a silent hole)

**What is deliberately *not* here.** Fields that determine the *price* stay
required at every status, because you cannot quote without them: ``room_type``,
``vehicle_type``, ``number_of_passengers``, ``origin``, ``destination``,
``airline``, ``passenger_name``. ``confirmation_number`` is also absent on
purpose - plenty of small hotels and guesthouses never issue one, and demanding
it would block a legitimate confirmed stay.
"""

from django.core.exceptions import ValidationError

from bookings.choices import (
    HotelStatusChoices,
    TicketStatusChoices,
    TransportStatusChoices,
)

# model class name -> {status: (fields that become required at that status,)}
#
# Keyed by class name rather than the class itself, so this module never imports
# the models - the models import *this*, and a cycle here would break app loading.
STATUS_REQUIRED_FIELDS = {
    'TicketingBooking': {
        # An issued ticket without a booking reference cannot exist: the PNR is
        # what the airline filed that ticket under.
        TicketStatusChoices.ISSUED: ('pnr',),
        TicketStatusChoices.REISSUED: ('pnr',),
    },
    'HotelBooking': {
        # A confirmed stay has a named guest - the hotel was given one in order
        # to hold the room.
        HotelStatusChoices.CONFIRMED: ('lead_guest_name',),
        HotelStatusChoices.COMPLETED: ('lead_guest_name',),
    },
    'TransportBooking': {
        # Note the status: a vehicle can be booked before the pickup time is
        # settled, but nobody can be sent to collect anyone without knowing when.
        TransportStatusChoices.DRIVER_ASSIGNED: ('pickup_time',),
        TransportStatusChoices.COMPLETED: ('pickup_time',),
    },
}


def is_missing(value):
    """``None`` and ``''`` both mean "not filled in" across this codebase.

    Text fields are ``blank=True`` (empty string) and the one datetime field is
    ``null=True``, so a single check has to cover both spellings.
    """
    return value is None or value == ''


def required_fields_for(model_name, status):
    """The fields this status demands - possibly empty, never ``None``."""
    # ``status`` may arrive as a TextChoices member or a plain string depending
    # on the caller; they compare equal and hash the same, so one lookup works
    # for both.
    return STATUS_REQUIRED_FIELDS.get(model_name, {}).get(status, ())


def statuses_requiring(model_name, field):
    """Which statuses demand ``field`` - used to build the DB constraints."""
    return [
        status
        for status, fields in STATUS_REQUIRED_FIELDS.get(model_name, {}).items()
        if field in fields
    ]


def check_instance(instance):
    """Validate a model instance in place, raising ``ValidationError`` if short.

    Called from ``ServiceRecordBase.clean()``, which Django runs on
    ``full_clean()`` - so Django admin and ModelForms report a field-level error
    instead of letting the model's ``CheckConstraint`` raise an
    ``IntegrityError`` on save.

    Note the limit: Django does **not** call ``clean()`` from ``save()``, so a
    bare ``obj.save()`` in a script still reaches the DB layer - where the
    constraint catches it. Same rule, harsher error.
    """
    model_name = type(instance).__name__
    status = getattr(instance, 'status', None)
    missing = {
        field: status_required_message(status)
        for field in required_fields_for(model_name, status)
        if is_missing(getattr(instance, field, None))
    }
    if missing:
        raise ValidationError(missing)


def status_required_message(status):
    """The user-facing wording, kept identical across the model and API layers."""
    return f'This field is required once status is "{status}".'
