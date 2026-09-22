"""Shared base for the case-workflow services in the consultancy app."""

from django.contrib.contenttypes.fields import GenericRelation
from django.db import models

from common.models import TenantScopedModel


class CaseRecordBase(TenantScopedModel):
    """Shared shape for case-workflow services (Visa Consultancy, Study Visa).

    **Why this is a separate app from ``bookings``.** The two look similar from a
    distance - both hang off ``Customer``, both are company-scoped, both are
    something a client paid for - but they are different shapes of work, and
    merging them would mean one table where half the columns are null for half the
    rows:

    * A booking is a *dated* transaction. It has a departure and a return, or a
      check-in and a check-out, and its state is mostly about that window
      (``RESERVED`` → ``ISSUED``).
    * A case is a *process*. It has no single date range at all; it has a
      ``case_open_date`` and a ``decision_date``, and what happens between them is
      a long chain - documents, submission, biometrics, decision - whose length
      depends on an embassy, not on us. ``starts_date``/``end_date`` would be
      meaningless here, which is why ``CaseRecordBase`` has neither.

    ``case_open_date`` and ``decision_date`` are two separate nullable dates
    rather than one range because the duration between them is a first-class
    business metric (how long does a visa actually take, per category and per
    embassy) and because a case legitimately has an open date with no decision yet
    for months.

    Tenant scoping comes from ``TenantScopedModel``: ``company`` is required and
    PROTECT, so a case can never exist without a tenant and a company cannot be
    deleted while it holds cases.

    ``customer`` is PROTECT, matching ``bookings.ServiceRecordBase``. A case is
    live client business data with a paper trail - submissions, decisions,
    refusals - that cannot be reconstructed once wiped, so ``customer.delete()``
    must fail loudly with ProtectedError while cases exist. Retire a customer with
    ``record_status = ARCHIVED`` instead.

    ``assigned_counselor`` is SET_NULL for the same reason as ``sales_agent`` on a
    booking: it is an assignment, not part of the record's identity, and a
    departing staff member must never be un-deletable because of an old case. The
    case survives; the assignment simply becomes unassigned.

    ``attachments`` is a ``GenericRelation`` onto ``common.Attachment``, which is
    how every "Documents"/"Checklist"/"Scanned copy" item on the consultancy sheets
    is covered by one mechanism instead of a table per case type. It is also worth
    noting that a document checklist *status* is a column here while the documents
    themselves are attachments - the status is what gets filtered and reported on,
    the files are the evidence behind it.

    Deliberately not stored: ``created_at``/``updated_at``/``created_by``/
    ``updated_by`` (inherited from ``BaseModel``), and any calculated value such as
    "days open" or "days to decision" - those derive from the two dates and belong
    in a selector, not in a column that goes stale overnight.
    """

    customer = models.ForeignKey(
        'customers.Customer',
        related_name='%(class)s_set',
        on_delete=models.PROTECT,
    )
    destination_country = models.CharField(max_length=100)
    case_open_date = models.DateField(null=True, blank=True)
    decision_date = models.DateField(null=True, blank=True)
    service_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    currency = models.CharField(max_length=6, default='PKR')
    assigned_counselor = models.ForeignKey(
        'users.User',
        null=True,
        blank=True,
        related_name='%(app_label)s_%(class)s_counselor',
        on_delete=models.SET_NULL,
    )
    notes = models.TextField(blank=True)
    attachments = GenericRelation('common.Attachment')

    class Meta:
        abstract = True
