"""Shared base for every dated, bookable service record in the bookings app."""

from django.contrib.contenttypes.fields import GenericRelation
from django.db import models

from bookings import status_rules
from common.models import TenantScopedModel


class ServiceRecordBase(TenantScopedModel):
    """Shared shape for every dated, bookable service (Hajj, Umrah, Tour,
    Ticketing, Hotel, Transport).

    This exists so the seven concrete booking models do not each re-declare the
    same five or six columns. Everything common to "a thing a customer bought
    from us for a date" lives here; only genuinely service-specific fields live
    on the subclasses.

    ``start_date``/``end_date`` are reused per service line rather than each
    getting its own named pair: Tour and Ticketing use them as departure/return,
    Hotel as check-in/check-out, Transport as the pickup date. Hajj and Umrah
    leave them null because those are sold by year/season, not by date - the
    year lives on the trip record itself. Four extra column pairs would buy
    nothing but ambiguity about which pair is authoritative.

    Tenant scoping comes from ``TenantScopedModel``: ``company`` is required and
    PROTECT, so a booking can never exist without a tenant and a company cannot
    be deleted while it holds bookings.

    ``customer`` is PROTECT as well, and that is a deliberate choice over
    CASCADE. A booking is live client business data that cannot be recovered once
    wiped, so ``customer.delete()`` must fail loudly with ProtectedError while
    booking history exists rather than silently taking that history with it. The
    realistic deletion triggers in a CRM - merging a duplicate, correcting a
    wrong entry, an erasure request - are all cases where somebody should decide
    explicitly what happens to the bookings. Retire a customer with
    ``record_status = ARCHIVED`` instead.

    ``sales_agent`` is SET_NULL rather than PROTECT: it is an assignment, not
    part of the record's identity, and leaving a company unable to remove a
    departing staff member because of an old booking would be the wrong trade.
    The booking survives, the assignment simply becomes unassigned.

    ``attachments`` is a ``GenericRelation`` onto ``common.Attachment``, which is
    how every "Documents"/"Voucher"/"Scanned copy" field on every service sheet
    is covered by one mechanism instead of a separate attachment table per model.

    Note what is deliberately *not* stored: nothing here duplicates
    ``created_at``/``updated_at``/``created_by``/``updated_by`` (inherited from
    ``BaseModel`` via ``TenantScopedModel``), and calculated values such as
    "number of nights" or "customer ID/link" are never columns - the nights are
    derivable from ``start_date``/``end_date`` and belong in a selector, and the
    customer link *is* the ``customer`` FK.
    """

    customer = models.ForeignKey(
        'customers.Customer',
        related_name='%(class)s_set',
        on_delete=models.PROTECT,
    )
    booking_reference = models.CharField(max_length=100, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    currency = models.CharField(max_length=6, default='PKR')
    sales_agent = models.ForeignKey(
        'users.User',
        null=True,
        blank=True,
        related_name='%(app_label)s_%(class)s_agent',
        on_delete=models.SET_NULL,
    )
    notes = models.TextField(blank=True)
    attachments = GenericRelation('common.Attachment')

    class Meta:
        abstract = True

    def clean(self):
        """Enforce the status-conditional required fields, where any apply.

        Django runs this from ``full_clean()``, so Django admin and ModelForms
        report a field-level error instead of letting the model's
        ``CheckConstraint`` raise an ``IntegrityError`` on save. The rule itself
        lives in ``bookings/status_rules.py`` so the admin, the API and the
        database all read one table.

        A no-op for models with no entry there (Hajj, Umrah, Tour, Ticketing at
        ``RESERVED``, ...): their statuses never demand a field that could be
        unknown at sale time.
        """
        super().clean()
        status_rules.check_instance(self)
