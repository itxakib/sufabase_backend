from django.contrib.contenttypes.fields import GenericRelation
from django.core.exceptions import ValidationError
from django.db import models

from bookings.choices import CabinClassChoices, MealPlanChoices
from catalog.choices import TemplateLineKind
from common.models import TenantScopedModel

#: Spec columns that belong to each line kind. Anything outside the set for the
#: line's kind must stay empty — a hotel spec does not carry a cabin or a vehicle.
_FIELDS_FOR_KIND = {
    TemplateLineKind.HOTEL: ('city', 'room_type', 'meal_plan', 'nights'),
    TemplateLineKind.FLIGHT: ('cabin_class', 'route'),
    TemplateLineKind.TRANSPORT: ('vehicle_type',),
}
_ALL_SPEC_FIELDS = tuple(
    dict.fromkeys(name for names in _FIELDS_FOR_KIND.values() for name in names)
)


def _is_filled(line, name):
    value = getattr(line, name)
    if name == 'nights':
        return value is not None
    return bool(value)


def _empty_q(name):
    if name == 'nights':
        return models.Q(nights__isnull=True)
    return models.Q(**{name: ''})


def _filled_q(name):
    return ~_empty_q(name)


def _kind_matches_fields(kind):
    """A line of ``kind`` has exactly that kind's spec columns filled."""
    required = _FIELDS_FOR_KIND[kind]
    check = models.Q(kind=kind)
    for name in _ALL_SPEC_FIELDS:
        check &= _filled_q(name) if name in required else _empty_q(name)
    return check


class PackageTemplate(TenantScopedModel):
    """A sellable package defined before anyone is booked.

    This is the catalog item ("Economy Hajj — quad, economy, coaster"). It
    stores a name, spec lines, and optional paperwork (brochure, itinerary,
    quote). It has no price, no customer, and none of the facts that appear
    only once a supplier booking exists: ticket number, guest name, passenger
    counts.

    Template documents stay on the catalogue item. They are not copied onto a
    trip bundle when staff pick this template as "sold from".

    The trip that was actually sold is ``bookings.Package``. That bundle may
    point here, and deleting this template only unlinks those bundles.
    """

    name = models.CharField(max_length=255)
    notes = models.TextField(blank=True)
    attachments = GenericRelation('common.Attachment')

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Package template'

    def __str__(self):
        return self.name


class PackageTemplateLine(TenantScopedModel):
    """One spec inside a sellable package.

    Several lines of the same kind are normal: Makkah and Madinah, an outbound
    flight and a return flight. ``kind`` decides which columns are meaningful.
    The other columns stay blank so a hotel line cannot quietly become a
    ticket.
    """

    template = models.ForeignKey(
        PackageTemplate,
        on_delete=models.CASCADE,
        related_name='lines',
    )
    kind = models.CharField(max_length=10, choices=TemplateLineKind.choices)

    city = models.CharField(max_length=100, blank=True)
    room_type = models.CharField(max_length=100, blank=True)
    meal_plan = models.CharField(
        max_length=20,
        choices=MealPlanChoices.choices,
        blank=True,
    )
    nights = models.PositiveIntegerField(null=True, blank=True)

    cabin_class = models.CharField(
        max_length=20,
        choices=CabinClassChoices.choices,
        blank=True,
    )
    route = models.CharField(max_length=100, blank=True)

    vehicle_type = models.CharField(max_length=100, blank=True)

    class Meta:
        verbose_name = 'Package template line'
        ordering = ['id']
        constraints = [
            models.CheckConstraint(
                condition=(
                    _kind_matches_fields(TemplateLineKind.HOTEL)
                    | _kind_matches_fields(TemplateLineKind.FLIGHT)
                    | _kind_matches_fields(TemplateLineKind.TRANSPORT)
                ),
                name='spec_line_fields_match_kind',
            ),
        ]

    def clean(self):
        errors = {}
        required = _FIELDS_FOR_KIND.get(self.kind, ())
        if not required:
            errors['kind'] = 'Choose a hotel, flight, or transport line.'
        for name in required:
            if not _is_filled(self, name):
                errors[name] = f'Required on a {self.kind.lower()} line.'
        for name in _ALL_SPEC_FIELDS:
            if name not in required and _is_filled(self, name):
                errors[name] = f'Does not belong on a {self.kind.lower()} line.'
        if self.company_id and self.template_id and self.company_id != self.template.company_id:
            errors['company'] = 'A spec line must belong to the same company as its template.'
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        if self.kind == TemplateLineKind.HOTEL:
            return f'{self.city} — {self.room_type}'
        if self.kind == TemplateLineKind.FLIGHT:
            return f'{self.route} ({self.cabin_class})'
        return self.vehicle_type or 'Transport'
