from common.models import TenantScopedModel
from django.db import models


class Tag(TenantScopedModel):
    """A free-form label that can be attached to customers for filtering and
    segmentation (e.g. "VIP", "Hajj-2026", "Referral-Partner").

    Tags are company-scoped: each tenant maintains its own vocabulary. The
    unique_together constraint on (company, name) prevents a single company from
    creating two tags with the same text, while allowing two different companies
    to use the same label independently.
    """

    name = models.CharField(max_length=50)
    color = models.CharField(max_length=7, blank=True)

    class Meta:
        unique_together = ('company', 'name')

    def __str__(self):
        return self.name
