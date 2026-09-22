from django.db import models

from common.models.audit import AuditModel
from common.models.time_stamped import TimeStampedModel


class BaseModel(TimeStampedModel, AuditModel):
    """Default base for models that are NOT tenant-owned.

    Used by ``tenant.Company``: a company cannot belong to a company, so it gets
    timestamps and audit attribution but no tenant link.
    """

    class Meta:
        abstract = True
