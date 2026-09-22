"""Trip bundle: real hotel, ticket and transport rows for one trip.

The sellable spec ("quad sharing, economy, coaster") is ``catalog.PackageTemplate``.
This model is the bundle assembled once those parts have actually been booked.
It links the booking rows. It does not copy their guest names, ticket numbers,
or the template's room type and cabin.
"""

from django.contrib.contenttypes.fields import GenericRelation
from django.core.exceptions import ValidationError
from django.db import models

from common.models import TenantScopedModel


class Package(TenantScopedModel):
    """One bundle for one actual trip.

    Created when staff assemble the hotel, ticket and transport rows booked for
    a customer's Hajj, Umrah or Tour. ``template`` is optional: a bundle can be
    assembled without a catalog item, and deleting the catalog item only clears
    the link.

    ``attachments`` holds paperwork for the whole trip (consolidated itinerary,
    group visa list). Each component booking keeps its own documents.
    """

    name = models.CharField(
        max_length=255,
        help_text="Label for this booked bundle, e.g. 'Family of 4 — Hajj July 2026'.",
    )
    notes = models.TextField(blank=True)
    template = models.ForeignKey(
        'catalog.PackageTemplate',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='bundles',
    )
    attachments = GenericRelation('common.Attachment')

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Package'

    def clean(self):
        if (
            self.template_id
            and self.company_id
            and self.template.company_id != self.company_id
        ):
            raise ValidationError({
                'template': 'This template belongs to a different company than the package.',
            })

    def __str__(self):
        return self.name


class PackageComponent(TenantScopedModel):
    """One real booking inside a package.

    Exactly one of ``hotel_booking``, ``ticketing_booking`` and
    ``transport_booking`` is set. The foreign keys are explicit so the link is
    a real join. Creating a component never creates a booking — it points at a
    row that already exists.
    """

    package = models.ForeignKey(
        Package,
        on_delete=models.CASCADE,
        related_name='components',
    )
    hotel_booking = models.ForeignKey(
        'bookings.HotelBooking',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='package_components',
    )
    ticketing_booking = models.ForeignKey(
        'bookings.TicketingBooking',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='package_components',
    )
    transport_booking = models.ForeignKey(
        'bookings.TransportBooking',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='package_components',
    )

    class Meta:
        verbose_name = 'Package component'
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        hotel_booking__isnull=False,
                        ticketing_booking__isnull=True,
                        transport_booking__isnull=True,
                    )
                    | models.Q(
                        hotel_booking__isnull=True,
                        ticketing_booking__isnull=False,
                        transport_booking__isnull=True,
                    )
                    | models.Q(
                        hotel_booking__isnull=True,
                        ticketing_booking__isnull=True,
                        transport_booking__isnull=False,
                    )
                ),
                name='exactly_one_component_type_set',
            ),
            models.UniqueConstraint(
                fields=['package', 'hotel_booking'],
                condition=models.Q(hotel_booking__isnull=False),
                name='uniq_package_hotel_booking',
            ),
            models.UniqueConstraint(
                fields=['package', 'ticketing_booking'],
                condition=models.Q(ticketing_booking__isnull=False),
                name='uniq_package_ticketing_booking',
            ),
            models.UniqueConstraint(
                fields=['package', 'transport_booking'],
                condition=models.Q(transport_booking__isnull=False),
                name='uniq_package_transport_booking',
            ),
        ]

    def clean(self):
        set_count = sum(
            bool(pk)
            for pk in (
                self.hotel_booking_id,
                self.ticketing_booking_id,
                self.transport_booking_id,
            )
        )
        if set_count != 1:
            raise ValidationError(
                'Exactly one of hotel_booking / ticketing_booking / transport_booking must be set.'
            )
        if self.company_id and self.package_id and self.company_id != self.package.company_id:
            raise ValidationError({
                'company': 'A component must belong to the same company as its package.',
            })
        booking = self.component
        if (
            booking is not None
            and self.package_id
            and booking.company_id != self.package.company_id
        ):
            raise ValidationError(
                'This booking belongs to a different company than the package.'
            )

    @property
    def component(self):
        """Whichever of the three bookings is actually set."""
        return self.hotel_booking or self.ticketing_booking or self.transport_booking

    def __str__(self):
        booking = self.component
        label = str(booking) if booking is not None else 'unlinked'
        return f'{self.package.name} — {label}'
