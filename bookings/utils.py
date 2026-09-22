"""Booking reference number generation.

Format: ``{PREFIX}-{YEAR}-{SEQ}``

- PREFIX: 2-letter service code (HJ, UM, TR, TK, HT, TP)
- YEAR: 4-digit year
- SEQ: 6-digit zero-padded sequential number per company per year

The sequence resets each calendar year.  Generation happens in the view's
``perform_create``, immediately before the INSERT.

**Not concurrency-safe, and deliberately so for now.** Two simultaneous creates
for the same company can both read the same max and compute the same next
reference: nothing here takes a lock, there is no ``transaction.atomic()`` around
the read-then-write, and ``booking_reference`` carries no unique constraint. At
SUFA's write volume that is not reachable in practice, and the value is a
human-facing label rather than a key - nothing joins on it. Making it airtight
needs a DB uniqueness constraint plus a retry, or a dedicated sequence table;
that is a deliberate later decision, not something to guess at here.

An earlier version of this docstring claimed the read and the insert were
atomic. They are not, and a duplicate would be saved silently rather than
rejected - there is no constraint to reject it.
"""

from django.db.models import Max, Q
import re


PREFIX_MAP = {
    'HajjBooking': 'HJ',
    'UmrahBooking': 'UM',
    'TourBooking': 'TR',
    'TicketingBooking': 'TK',
    'HotelBooking': 'HT',
    'TransportBooking': 'TP',
}


def generate_booking_reference(model_class, company, year=None):
    """Return the next booking reference for a company + year.

    Example output: ``HJ-2026-000001``

    If the model class is not in ``PREFIX_MAP``, returns an empty string
    (caller should fall back to letting the user provide one manually).
    """
    from django.utils import timezone

    prefix = PREFIX_MAP.get(model_class.__name__)
    if not prefix:
        return ''

    if year is None:
        year = timezone.now().year

    # Find the highest SEQ number for this company + year + prefix.
    # booking_reference format: XX-YYYY-NNNNNN
    pattern = f'{prefix}-{year}-'
    last = (
        model_class.objects.filter(
            company=company,
            booking_reference__startswith=pattern,
        )
        .aggregate(max_ref=Max('booking_reference'))
        .get('max_ref')
    )

    if last:
        # Extract the numeric part after the last dash
        match = re.search(r'-(\d+)$', last)
        seq = int(match.group(1)) + 1 if match else 1
    else:
        seq = 1

    return f'{prefix}-{year}-{seq:06d}'
