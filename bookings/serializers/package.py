from rest_framework import serializers

from bookings.models.hotel import HotelBooking
from bookings.models.package import Package, PackageComponent
from bookings.models.ticketing import TicketingBooking
from bookings.models.transport import TransportBooking
from catalog.models import PackageTemplate
from common.serializers import TenantScopedSerializerMixin

_COMPONENT_FIELDS = ('hotel_booking', 'ticketing_booking', 'transport_booking')


class PackageMiniSerializer(serializers.ModelSerializer):
    """Minimal package representation — id + name only, for trip list rows."""

    class Meta:
        model = Package
        fields = ['id', 'name']
        read_only_fields = fields


class PackageComponentReadSerializer(serializers.ModelSerializer):
    """A link row as the package detail returns it. Not a write shape."""

    label = serializers.SerializerMethodField()

    class Meta:
        model = PackageComponent
        fields = [
            'id',
            'hotel_booking',
            'ticketing_booking',
            'transport_booking',
            'label',
        ]
        read_only_fields = fields

    def get_label(self, obj):
        booking = obj.component
        return str(booking) if booking is not None else ''


class PackageSerializer(TenantScopedSerializerMixin, serializers.ModelSerializer):
    """Create and update a trip bundle.

    ``components`` is read-only. Linking a booking is
    ``POST /api/v1/package-components/`` with an id. This serializer does not
    create hotel, ticket, or transport rows.
    """

    components = PackageComponentReadSerializer(many=True, read_only=True)
    tenant_scoped_fields = {
        'template': PackageTemplate,
    }

    class Meta:
        model = Package
        fields = [
            'id',
            'name',
            'notes',
            'template',
            'components',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'components', 'created_at', 'updated_at']

    def validate_template(self, template):
        if template is None:
            return template
        company = self.instance.company if self.instance is not None else self._get_company()
        if company is not None and template.company_id != company.pk:
            raise serializers.ValidationError(
                'This template belongs to a different company than the package.'
            )
        return template


class PackageComponentSerializer(TenantScopedSerializerMixin, serializers.ModelSerializer):
    """Link an existing booking into a package.

    Each of the three booking fields is a primary key. A nested booking object
    is rejected by the pk field, and this serializer never creates a booking.
    """

    tenant_scoped_fields = {
        'package': Package,
        'hotel_booking': HotelBooking,
        'ticketing_booking': TicketingBooking,
        'transport_booking': TransportBooking,
    }

    class Meta:
        model = PackageComponent
        fields = [
            'id',
            'package',
            'hotel_booking',
            'ticketing_booking',
            'transport_booking',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, attrs):
        attrs = super().validate(attrs)
        chosen = [self._resolved(attrs, name) for name in _COMPONENT_FIELDS]
        if sum(item is not None for item in chosen) != 1:
            raise serializers.ValidationError(
                'Exactly one of hotel_booking / ticketing_booking / transport_booking must be set.'
            )
        package = self._resolved(attrs, 'package')
        booking = next(item for item in chosen if item is not None)
        if package is not None and booking.company_id != package.company_id:
            raise serializers.ValidationError(
                'This booking belongs to a different company than the package.'
            )
        return attrs

    def _resolved(self, attrs, name):
        if name in attrs:
            return attrs[name]
        if self.instance is not None:
            return getattr(self.instance, name)
        return None
