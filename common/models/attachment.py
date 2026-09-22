"""Generic document/file attachment, usable by any model in any module."""

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from common.models.tenant_scoped import TenantScopedModel


class Attachment(TenantScopedModel):
    """A file attached to any other record, without a FK per host model.

    The contenttypes framework is what keeps this decoupled: a CNIC copy on a
    Customer, a voucher on a booking and a scanned passport on a case all land
    in this one table, and adding a fourth host model later costs zero schema
    change here. The alternative - one attachment table per host model, or a
    column per possible owner - would mean a new table (and a new upload
    pipeline) for every module that needs documents.

    Tenant scoping applies exactly as it does to every other tenant-owned model:
    ``company`` comes from ``TenantScopedModel``, it is required and PROTECT.
    Generic FKs make it tempting to believe the attachment is scoped by whatever
    it hangs off, but it is not - ``content_type``/``object_id`` say nothing
    about the tenant, so a selector must filter ``company`` explicitly, like
    every other selector in this project (no thread-locals, no ambient magic).

    Two consequences of generic FKs worth knowing (both Module 02+ concerns, not
    schema bugs):

    * Deleting a host record does not delete its attachments - ``object_id`` is
      a plain integer, so no cascade fires and the rows are left dangling. A
      cleanup service is needed when a host row is hard-deleted.
    * Nothing here stops an attachment from claiming company A while pointing at
      company B's record. The writing service owns that check.
    """

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    # Grouped by year/month so a tenant's uploads stay browsable on disk instead
    # of piling into one flat directory.
    file = models.FileField(upload_to='attachments/%Y/%m/')

    # Free text, e.g. "CNIC copy", "Offer letter", "Voucher". Module 02 may turn
    # this into controlled vocabularies per company; a CharField keeps Module 01
    # from guessing at a taxonomy that does not exist yet.
    doc_type = models.CharField(max_length=100, blank=True)

    class Meta:
        indexes = [
            # The lookup every consumer performs: "attachments for this row".
            models.Index(
                fields=['content_type', 'object_id'],
                name='common_attachment_ct_obj_idx',
            ),
        ]

    def __str__(self):
        return f'{self.doc_type or "Attachment"} ({self.file.name})'
