from django.db import models

from common.models.base import BaseModel


class TenantScopedModel(BaseModel):
    """Base for every tenant-owned model in every module app.

    Applies to ``users.User`` and to every future module model (leads, quotes,
    campaigns, ...) - any row that belongs to exactly one company.

    ``company`` is required, so a tenant-owned row can never exist without a
    tenant.

    It is PROTECT, never CASCADE. A company holds live client business data
    (leads, quotes, bookings, outreach logs, campaign records) that cannot be
    recovered once wiped, so ``company.delete()`` must fail loudly with
    ProtectedError until that data has been cleared deliberately. A CASCADE here
    would turn one careless admin click - or one future script - into an
    unrecoverable, silent, cross-tenant data loss.

    The intended way to take a tenant out of service is
    ``Company.is_active = False``. Hard-deleting a company is a deliberate
    process that clears its tenant data first; that friction is the design, not
    an obstacle. Module 07 owns the platform-admin purge workflow.

    The reverse accessor is ``company.<app_label>_<model>_set`` (e.g.
    ``company.users_user_set``) - the pattern keeps accessor names unique across
    every model that inherits this base.
    """

    company = models.ForeignKey(
        'tenant.Company',
        on_delete=models.PROTECT,
        related_name='%(app_label)s_%(class)s_set',
    )

    class Meta:
        abstract = True
