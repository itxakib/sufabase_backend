"""Manager for the custom staff user model.

Signatures mirror ``django.contrib.auth.models.UserManager`` (``username,
email, password``) so ``createsuperuser`` and Django's auth forms keep working
unchanged.
"""

from django.contrib.auth.base_user import BaseUserManager


class CustomUserManager(BaseUserManager):
    """Creates staff users. No tenant logic lives here."""

    use_in_migrations = True

    def _create_user(self, username, email, password, **extra_fields):
        if not username:
            raise ValueError('The username must be set')
        if extra_fields.get('company') is None:
            # company is required by TenantScopedModel; fail with a clear message
            # instead of letting the database raise an IntegrityError on save.
            raise ValueError('A staff user must belong to a company (company=<Company>).')
        email = self.normalize_email(email)
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(username, email, password, **extra_fields)

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'admin')
        # No default company is invented here on purpose: a superuser must be
        # attached to a real tenant explicitly. Cross-tenant platform admins are
        # Module 07 work.

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self._create_user(username, email, password, **extra_fields)
