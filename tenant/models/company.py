"""The Company model - the tenant itself.

This app owns exactly one responsibility: describing a company as a business
entity. Tenant *enforcement* (middleware, managers, mixins) belongs in
``common``; Module 07 adds platform-level billing/plan limits on top.
"""

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify

from common.models import BaseModel


def validate_timezone(value):
    """Reject timezone names the stdlib cannot resolve."""
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValidationError(
            'Unknown timezone: %(tz)s',
            params={'tz': value},
        ) from exc


class Company(BaseModel):
    """A tenant on the SUFABASE platform.

    Deliberately NOT tenant-scoped: a company cannot belong to a company, so
    this model inherits ``BaseModel`` rather than ``TenantScopedModel``.

    Deletion policy: every tenant-owned model FKs to this model with PROTECT
    (see ``common.models.TenantScopedModel``), as does ``users.User.company``.
    ``company.delete()`` therefore raises ProtectedError for as long as any
    staff account or tenant data exists. That is intentional: clearing a
    company's data is a deliberate, explicit process, never an accident.

    To take a tenant out of service, set ``is_active = False`` - that is the
    supported path and leaves all data intact and recoverable.
    """

    class Plan(models.TextChoices):
        """Placeholder for Module 07 billing/plan limits - no enforcement here."""

        STANDARD = 'standard', 'Standard'
        PREMIUM = 'premium', 'Premium'
        ENTERPRISE = 'enterprise', 'Enterprise'

    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(
        max_length=255,
        unique=True,
        blank=True,
        help_text='URL-safe identifier. Generated from the name when left blank.',
    )
    legal_name = models.CharField(
        max_length=255,
        blank=True,
        help_text='Registered legal entity, if it differs from the display name.',
    )
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=32, blank=True)
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    # TODO: confirm with frontend - free-text country or ISO-3166 alpha-2 code?
    country = models.CharField(max_length=100, blank=True)

    # ── Fields added for frontend settings panel ────────────────────────────
    registration_number = models.CharField(max_length=100, blank=True)
    tax_number = models.CharField(max_length=100, blank=True)
    website = models.URLField(max_length=255, blank=True)
    address_line1 = models.CharField(max_length=255, blank=True)
    address_line2 = models.CharField(max_length=255, blank=True)
    state = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    currency = models.CharField(max_length=6, default='PKR')
    logo_url = models.URLField(max_length=500, blank=True)
    # TODO: confirm with client whether companies need per-region timezones or
    # whether one platform timezone is enough.
    timezone = models.CharField(
        max_length=64,
        default='UTC',
        validators=[validate_timezone],
    )
    plan = models.CharField(
        max_length=20,
        choices=Plan.choices,
        default=Plan.STANDARD,
    )
    onboarded_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When the tenant went live - distinct from created_at.',
    )
    is_active = models.BooleanField(
        default=True,
        help_text='Set to False to take a tenant out of service without deleting data.',
    )

    class Meta:
        verbose_name = 'company'
        verbose_name_plural = 'companies'
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            # TODO: Module 07 (company onboarding) should handle the case where
            # two differently-named companies slugify to the same value.
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
