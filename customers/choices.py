"""Choice enumerations for the customers app.

Choices live in their own module rather than being inlined as tuples on each
model field. This keeps model files readable and lets any view, serializer,
test or management command import the full set of valid options in one place
without importing the models themselves.
"""

from django.db import models


class StageChoices(models.TextChoices):
    """CRM pipeline stage: how far along is this customer in the sales cycle?

    NEW (default) is assigned the moment any channel — WhatsApp, phone, walk-in,
    web form — creates a row. The status changes to OLD once the customer has
    completed at least one service booking, at which point the sales focus shifts
    from acquisition to retention and upsell.
    """

    NEW = 'NEW', 'New'
    OLD = 'OLD', 'Old'


class RecordStatusChoices(models.TextChoices):
    """Lifecycle status of the customer record itself, distinct from the CRM stage.

    ACTIVE is the default and means the record is current and editable.
    INACTIVE is a soft-suspension: the row stays visible for historical lookups
    but is excluded from default list views and search results. ARCHIVED is a
    stronger version of INACTIVE: it means the record was deliberately shelved
    (GDPR withdrawal, duplicate merge, account closure) and should only surface
    in explicit admin/bulk-recovery contexts.
    """

    ACTIVE = 'ACTIVE', 'Active'
    INACTIVE = 'INACTIVE', 'Inactive'
    ARCHIVED = 'ARCHIVED', 'Archived'
