"""Generic cross-reference between two service records of any type."""

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from common.models.tenant_scoped import TenantScopedModel


class ServiceLink(TenantScopedModel):
    """A directional link between two records of any type, in any module.

    Example: a HajjBooking linked to the TicketingBooking that was raised for
    the same traveller. Those two models live in different modules and neither
    should import the other, so a per-pair join table would couple modules
    together and grow multiplicatively with every new service type. Two generic
    FKs instead let one table express "A is linked to B" for every pair that
    will ever exist.

    Direction is meaningful: ``from_object`` -> ``to_object``. The "Linked X
    Record" field in the UI is optional and hidden by default, so records are
    created without a link and gain one later - which is exactly why this is a
    separate table rather than a column on either side.

    Tenant scoping comes from ``TenantScopedModel``: ``company`` is required and
    PROTECT, and selectors must filter it explicitly. Note the model does *not*
    check that ``from_object`` and ``to_object`` belong to the same company -
    generic FKs cannot be enforced at the schema level. Both ends living in
    ``self.company`` is a rule the writing service must apply.
    """

    from_content_type = models.ForeignKey(
        ContentType,
        related_name='+',
        on_delete=models.CASCADE,
    )
    from_object_id = models.PositiveBigIntegerField()
    from_object = GenericForeignKey('from_content_type', 'from_object_id')

    to_content_type = models.ForeignKey(
        ContentType,
        related_name='+',
        on_delete=models.CASCADE,
    )
    to_object_id = models.PositiveBigIntegerField()
    to_object = GenericForeignKey('to_content_type', 'to_object_id')

    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        indexes = [
            # Both directions are queried: "what does this record point at" and
            # "what points at this record".
            models.Index(
                fields=['from_content_type', 'from_object_id'],
                name='common_servicelink_from_idx',
            ),
            models.Index(
                fields=['to_content_type', 'to_object_id'],
                name='common_servicelink_to_idx',
            ),
        ]

    def __str__(self):
        return f'{self.from_content_type.model}#{self.from_object_id} -> {self.to_content_type.model}#{self.to_object_id}'
