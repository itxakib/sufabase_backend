from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers

from catalog.models import PackageTemplate, PackageTemplateLine
from common.serializers import TenantScopedSerializerMixin


class PackageTemplateLineSerializer(serializers.ModelSerializer):
    """One spec line. The write payload is kind plus that kind's spec columns."""

    class Meta:
        model = PackageTemplateLine
        fields = [
            'id',
            'kind',
            'city',
            'room_type',
            'meal_plan',
            'nights',
            'cabin_class',
            'route',
            'vehicle_type',
        ]
        read_only_fields = ['id']

    def validate(self, attrs):
        attrs = super().validate(attrs)
        line = PackageTemplateLine()
        for name, value in attrs.items():
            setattr(line, name, value)
        try:
            line.clean()
        except DjangoValidationError as exc:
            if getattr(exc, 'error_dict', None):
                raise serializers.ValidationError(exc.message_dict) from exc
            raise serializers.ValidationError(exc.messages) from exc
        return attrs


class PackageTemplateSerializer(TenantScopedSerializerMixin, serializers.ModelSerializer):
    """Create and update a sellable package and its spec lines.

    ``lines`` replaces the whole set when it is sent. Omitting it on a partial
    update leaves the existing specs in place. A line never accepts booking
    fields — there are none on the model.
    """

    lines = PackageTemplateLineSerializer(many=True, required=False)

    class Meta:
        model = PackageTemplate
        fields = [
            'id',
            'name',
            'notes',
            'lines',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    @transaction.atomic
    def create(self, validated_data):
        lines = validated_data.pop('lines', [])
        template = super().create(validated_data)
        self._save_lines(template, lines)
        return template

    @transaction.atomic
    def update(self, instance, validated_data):
        lines = validated_data.pop('lines', serializers.empty)
        template = super().update(instance, validated_data)
        if lines is not serializers.empty:
            template.lines.all().delete()
            self._save_lines(template, lines)
        return template

    def _save_lines(self, template, lines):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        actor = user if user is not None and user.is_authenticated else None
        for line in lines:
            PackageTemplateLine.objects.create(
                template=template,
                company=template.company,
                created_by=actor,
                **line,
            )


class PackageTemplateListSerializer(serializers.ModelSerializer):
    """List row — name only, specs stay on the detail payload."""

    class Meta:
        model = PackageTemplate
        fields = ['id', 'name', 'notes', 'created_at']
        read_only_fields = fields
