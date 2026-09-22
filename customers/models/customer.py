from common.models import TenantScopedModel
from customers.choices import StageChoices, RecordStatusChoices
from django.contrib.contenttypes.fields import GenericRelation
from django.db import models


class Customer(TenantScopedModel):
    """A single customer identity shared across every SUFABASE service line
    (Hajj, Umrah, Tour, Ticketing, Hotel, Visa Consultancy, Study Visa, Transport).

    This is the canonical "who is this person" record. Service-specific data
    (booking references, payment records, ticket numbers) lives in the module
    that owns the service; Customer holds the identity and contact information
    that every module needs but none of them should duplicate.

    ``customer_since`` is intentionally omitted: ``created_at`` (inherited from
    BaseModel) already answers "when did this relationship start". If SUFA needs
    a manually-editable date (e.g. for backfilling historical join dates), it
    should be added as a separate field on a case-by-case basis — that is a
    business decision, not a schema decision.
    """

    # ── Identity ─────────────────────────────────────────────────────────────
    # Profile picture. Nullable on purpose: staff create a customer in seconds
    # (often by phone, mid-call) and should never be blocked on an image upload.
    # ImageField rather than FileField so Django validates the bytes are an
    # actual image at upload time instead of accepting a renamed .exe.
    avatar = models.ImageField(upload_to='customers/avatars/%Y/%m/', null=True, blank=True)
    full_name = models.CharField(max_length=255)
    father_husband_name = models.CharField(max_length=255, blank=True)
    gender = models.CharField(max_length=20, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    cnic_number = models.CharField(max_length=20, blank=True)
    cnic_expiry_date = models.DateField(null=True, blank=True)
    passport_number = models.CharField(max_length=30, blank=True)
    passport_issue_date = models.DateField(null=True, blank=True)
    passport_expiry_date = models.DateField(null=True, blank=True)
    nationality = models.CharField(max_length=100, blank=True)
    marital_status = models.CharField(max_length=20, blank=True)

    # ── Contact ──────────────────────────────────────────────────────────────
    phone = models.CharField(max_length=20, db_index=True)
    whatsapp_number = models.CharField(max_length=20, blank=True)
    alt_phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)

    # ── Location ─────────────────────────────────────────────────────────────
    country = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=100, blank=True)
    location_area = models.CharField(max_length=100, blank=True)
    sub_location = models.CharField(max_length=100, blank=True)
    complete_address = models.TextField(blank=True)

    # ── Professional ─────────────────────────────────────────────────────────
    profession = models.CharField(max_length=100, blank=True)
    business_type = models.CharField(max_length=100, blank=True)
    company_name = models.CharField(max_length=255, blank=True)
    designation = models.CharField(max_length=100, blank=True)
    business_address = models.TextField(blank=True)
    business_contact_number = models.CharField(max_length=20, blank=True)

    # ── CRM meta ─────────────────────────────────────────────────────────────
    customer_source = models.CharField(max_length=50, blank=True)
    referred_by = models.CharField(max_length=255, blank=True)
    preferred_contact_method = models.CharField(max_length=30, blank=True)
    preferred_language = models.CharField(max_length=30, blank=True)
    assigned_agent = models.ForeignKey(
        'users.User',
        null=True,
        blank=True,
        related_name='assigned_customers',
        on_delete=models.SET_NULL,
    )
    notes = models.TextField(blank=True)

    # ── Status ───────────────────────────────────────────────────────────────
    stage = models.CharField(
        max_length=10,
        choices=StageChoices.choices,
        default=StageChoices.NEW,
    )
    record_status = models.CharField(
        max_length=10,
        choices=RecordStatusChoices.choices,
        default=RecordStatusChoices.ACTIVE,
    )

    # ── Marketing ────────────────────────────────────────────────────────────
    marketing_contact_permission = models.CharField(max_length=10, blank=True)

    # ── Emergency ────────────────────────────────────────────────────────────
    emergency_contact_name = models.CharField(max_length=255, blank=True)
    emergency_contact_relationship = models.CharField(max_length=50, blank=True)
    emergency_contact_number = models.CharField(max_length=20, blank=True)

    # ── Relations ────────────────────────────────────────────────────────────
    family_group_reference = models.CharField(max_length=255, blank=True)
    tags = models.ManyToManyField('customers.Tag', blank=True, related_name='customers')
    attachments = GenericRelation('common.Attachment')

    class Meta:
        indexes = [models.Index(fields=['company', 'phone'])]

    def __str__(self):
        return self.full_name
