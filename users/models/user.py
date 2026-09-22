"""The custom staff user model (Module 01)."""

from django.contrib.auth.models import AbstractUser
from django.db import models

from common.models import TenantScopedModel
from users.managers import CustomUserManager


class User(AbstractUser, TenantScopedModel):
    """A SUFABASE staff account.

    Tenant-scoped via ``TenantScopedModel``, so ``company`` is a *required*
    PROTECT FK inherited from the shared base - every staff account belongs to
    exactly one company, and no user can exist without one. The reverse
    accessor is ``company.users_user_set``.

    Consequence worth knowing: there is no such thing as a tenant-less user
    anymore, so a platform-level superuser must belong to a company. Genuine
    cross-tenant platform administration is Module 07 (``saas_admin``) work.

    ``company`` is PROTECT, so deleting a company fails loudly (ProtectedError)
    rather than silently destroying staff accounts. Retire a tenant with
    ``Company.is_active = False``.

    ``role`` is a plain placeholder field for Module 02, which will replace it
    with real roles/permissions on top of this. Nothing in this app branches on
    it - there are no RBAC checks in Module 01.
    """

    class Role(models.TextChoices):
        ADMIN = 'admin', 'Admin'
        MANAGER = 'manager', 'Manager'
        AGENT = 'agent', 'Agent'

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.AGENT,
        help_text='Placeholder for Module 02 - no permission logic reads this yet.',
    )
    phone = models.CharField(max_length=20, blank=True)

    objects = CustomUserManager()

    # 'company' is prompted for by `createsuperuser`, since it is required.
    REQUIRED_FIELDS = ['email', 'company']

    class Meta:
        # Explicit, not inherited: AbstractUser.Meta is abstract=True, and
        # inheriting it would leave this model abstract with no table.
        ordering = ['username']
        verbose_name = 'user'
        verbose_name_plural = 'users'

    def __str__(self):
        return self.username
