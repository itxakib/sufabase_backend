"""Project-wide DRF exception handler.

Two jobs:

1. Turn Django's **protected-delete** errors into a `409` that says what blocked
   the delete. Every tenant-owned model is PROTECT-ed on ``company`` and
   ``ServiceRecordBase``/``CaseRecordBase`` are PROTECT-ed on ``customer``, by
   explicit client decision - live business data must fail loudly rather than
   disappear. Django raises ``ProtectedError`` for that, DRF has no handler for
   it, and without this mapping the client sees a generic `500
   {"detail": "Internal server error"}`: the protection works, but the reason is
   invisible to the frontend and to whoever is trying to delete the row.
   ``RestrictedError`` (the ``RESTRICT`` variant) is handled identically.

2. Guarantee the body is **always JSON**, including for exceptions nothing
   handled. Django's debug page is HTML, and a frontend calling
   ``response.json()`` on an HTML error page gets a parse crash instead of a
   message. The traceback is still logged, so nothing is hidden from developers -
   it is just not sent to the client.
"""

import logging
from collections import Counter

from django.db.models import ProtectedError, RestrictedError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)

# What ProtectedError/RestrictedError call the collection they carry.
_BLOCKER_ATTRS = ('protected_objects', 'restricted_objects')


def _blocking_records(exc):
    """``{model_name: count}`` for whatever blocked the delete.

    Read defensively: the attribute name differs between ``ProtectedError`` and
    ``RestrictedError``, and a raised class could carry neither (a custom
    subclass with a different signature). An empty dict is a fine answer - the
    status code and the human message are what the client acts on.
    """
    for attr in _BLOCKER_ATTRS:
        objects = getattr(exc, attr, None)
        if objects is not None:
            return dict(Counter(type(obj).__name__ for obj in objects))
    return {}


def _protected_response(exc):
    """`409 Conflict` naming the records that must be cleared first."""
    blockers = _blocking_records(exc)
    if blockers:
        summary = ', '.join(
            f'{name} ({count})' for name, count in sorted(blockers.items())
        )
        detail = (
            'This record cannot be deleted because other records depend on it. '
            f'Blocking records: {summary}. '
            'Deactivate or archive it instead, or clear those records first.'
        )
    else:
        detail = (
            'This record cannot be deleted because other records depend on it. '
            'Deactivate or archive it instead, or clear those records first.'
        )

    return Response(
        {'detail': detail, 'blocking_records': blockers},
        status=status.HTTP_409_CONFLICT,
    )


def custom_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is not None:
        return response

    if isinstance(exc, (ProtectedError, RestrictedError)):
        return _protected_response(exc)

    # Unhandled exception - a bug, not a validation error. Log the traceback so
    # it is visible in the server console, and still answer with JSON so the
    # client's error handling does not have to cope with an HTML page.
    view = context.get('view')
    logger.error(
        'Unhandled exception in %s',
        type(view).__name__ if view else 'view',
        exc_info=exc,
    )
    return Response(
        {'detail': 'Internal server error'},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
