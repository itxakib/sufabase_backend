"""Shared models for every SUFABASE module app.

One model per file - ``time_stamped.py``, ``audit.py``, ``base.py``,
``tenant_scoped.py``, ``attachment.py`` and ``service_link.py`` - so each one
can grow on its own.

Two kinds of thing live here:

* Abstract bases (``TimeStampedModel``, ``AuditModel``, ``BaseModel``,
  ``TenantScopedModel``) - no tables, no migrations, inherited by every module.
* Two concrete generic models (``Attachment``, ``ServiceLink``) that any other
  model can hang off through the contenttypes framework. They live in ``common``
  rather than in a module app precisely because no single module owns them: a
  booking, a customer and a case can all carry the same attachments and links.

Import from ``common.models`` (the re-exports here); that is the public import
path, so this physical layout can change without touching any call site or
migration.
"""

from common.models.attachment import Attachment
from common.models.audit import AuditModel
from common.models.base import BaseModel
from common.models.service_link import ServiceLink
from common.models.tenant_scoped import TenantScopedModel
from common.models.time_stamped import TimeStampedModel

__all__ = [
    'Attachment',
    'AuditModel',
    'BaseModel',
    'ServiceLink',
    'TenantScopedModel',
    'TimeStampedModel',
]
