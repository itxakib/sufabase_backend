"""One serializer pair covering attachments for *every* host model.

Because ``common.Attachment`` is generic, the API needs exactly one serializer
rather than one per module: the same shape uploads a CNIC scan onto a Customer,
a voucher onto a Hajj booking and a contract onto a Package.
"""

import os

from django.contrib.contenttypes.models import ContentType
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from common.models import Attachment
from users.serializers import UserMiniSerializer


@extend_schema_field({'type': 'string', 'example': 'customers.customer'})
class ContentTypeField(serializers.Field):
    """Reads and writes a ``ContentType`` as the string ``"app_label.model"``.

    The API could expose the raw ``ContentType`` primary key, but those ids come
    from Django's own ``django_content_type`` table: they are an implementation
    detail, they differ between databases, and nothing about ``"31"`` tells a
    frontend developer what they are attaching to. ``"customers.customer"`` is
    stable, self-describing and pasteable into a frontend constant.
    """

    default_error_messages = {
        'invalid': 'Expected "app_label.model" (for example "customers.customer"), got "{value}".',
        'unknown': 'Unknown content type "{value}".',
    }

    def to_representation(self, value):
        return f'{value.app_label}.{value.model}'

    def to_internal_value(self, data):
        if not isinstance(data, str) or '.' not in data:
            self.fail('invalid', value=data)
        app_label, _, model = data.partition('.')
        try:
            return ContentType.objects.get_by_natural_key(
                app_label.strip().lower(), model.strip().lower(),
            )
        except ContentType.DoesNotExist:
            self.fail('unknown', value=data)


class AttachmentSerializer(serializers.ModelSerializer):
    """A single attached file, generic across every host model.

    Two ways to use it, and the difference matters:

    * **Nested** (``POST /api/v1/hajj/7/attachments/``) - the host record comes
      from the URL. The view passes it in ``context['target']``, and
      ``content_type``/``object_id`` are filled in server-side. A client cannot
      attach a file to a record it did not address, which is why this is the
      documented path for the frontend. On update they are ignored entirely -
      an attachment cannot be moved to another record.
    * **Flat** (``POST /api/v1/attachments/``) - the payload carries
      ``content_type`` and ``object_id`` itself, for bulk or scripted uploads.

    In both cases the target is re-checked against the caller's company before
    anything is written: without that, knowing another tenant's record id would
    be enough to staple a file onto their customer.

    ``company`` / ``created_by`` / ``updated_by`` are never accepted from the
    client. ``file`` accepts a multipart upload on write and returns a URL on
    read, so the frontend renders ``<img src={file}>`` / ``<a href={file}>``
    directly.
    """

    content_type = ContentTypeField(required=False)
    object_id = serializers.IntegerField(required=False)
    uploaded_by = UserMiniSerializer(source='created_by', read_only=True)
    file_name = serializers.SerializerMethodField()
    file_size = serializers.SerializerMethodField()
    target_label = serializers.SerializerMethodField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # ``file`` is required to create, but an existing row always has one, so
        # a PATCH that only renames ``doc_type`` must not be forced to re-upload
        # the document.
        if self.instance is not None:
            self.fields['file'].required = False

    class Meta:
        model = Attachment
        fields = [
            'id',
            'content_type',
            'object_id',
            'target_label',
            'doc_type',
            'file',
            'file_name',
            'file_size',
            'uploaded_by',
            'created_at',
        ]
        read_only_fields = [
            'id',
            'target_label',
            'file_name',
            'file_size',
            'uploaded_by',
            'created_at',
        ]

    # ── Representation helpers ───────────────────────────────────────────────

    def get_file_name(self, obj) -> str:
        return os.path.basename(obj.file.name) if obj.file else ''

    def get_file_size(self, obj) -> int | None:
        """Size in bytes, or null when the file is missing from storage.

        ``FileField.size`` touches storage, and a row whose file was deleted
        out-of-band (or lives on a bucket that is briefly unreachable) must not
        turn an attachment list into a 500.
        """
        try:
            return obj.file.size
        except (OSError, ValueError):
            return None

    def get_target_label(self, obj) -> str:
        """Human-readable name of the host record, for cross-record listings.

        Needed on the flat listing, where attachments from many different models
        are mixed together and the frontend has no other way to say *what* a
        file belongs to. It is harmless on the nested listing too (every row
        shares one host) but must not cost a query per row, which is exactly
        what ``content_object`` does on a generic FK.

        The cache is keyed on ``(content_type_id, object_id)`` and lives on the
        serializer instance, so a nested list of 50 documents for one booking
        resolves its host **once**, and a flat page of 50 documents resolves at
        most one query per distinct host record - not one per attachment.
        """
        cache = getattr(self, '_target_label_cache', None)
        if cache is None:
            cache = self._target_label_cache = {}
        key = (obj.content_type_id, obj.object_id)
        if key not in cache:
            target = obj.content_object
            cache[key] = str(target) if target is not None else ''
        return cache[key]

    # ── Validation ───────────────────────────────────────────────────────────

    def _get_company(self):
        """The caller's tenant, from ``request.company`` (middleware) or the
        user itself - identical resolution order to ``TenantScopedViewSetMixin``
        so a view and its serializer can never disagree about the tenant."""
        request = self.context.get('request')
        if request is None:
            return None
        company = getattr(request, 'company', None)
        if company is not None:
            return company
        user = getattr(request, 'user', None)
        if user is None or not user.is_authenticated:
            return None
        return getattr(user, 'company', None)

    def validate(self, attrs):
        target = self.context.get('target')
        company = self._get_company()

        if self.instance is not None:
            # An existing attachment's target is immutable. Re-pointing a file at
            # a different record would need the same company check as creation,
            # and moving a document between records is meant to look like what it
            # is - a delete and a fresh upload - so it leaves an audit trail
            # instead of silently rewriting where a document belongs.
            #
            # Dropping the keys (rather than 400-ing when they are absent) is
            # what lets the frontend send ``PATCH {"doc_type": "Voucher"}``, the
            # one edit that is actually useful here, without resending an
            # identity it cannot change anyway.
            attrs.pop('content_type', None)
            attrs.pop('object_id', None)
            return attrs

        if target is not None:
            # Nested route: the host record is whatever the URL resolved to,
            # already company-scoped by the ViewSet's queryset. The payload is
            # not allowed to override it.
            attrs['content_type'] = ContentType.objects.get_for_model(
                target, for_concrete_model=False,
            )
            attrs['object_id'] = target.pk
            return attrs

        content_type = attrs.get('content_type')
        object_id = attrs.get('object_id')

        if content_type is None:
            raise serializers.ValidationError(
                {'content_type': 'This field is required.'},
            )
        if object_id is None:
            raise serializers.ValidationError(
                {'object_id': 'This field is required.'},
            )

        model_cls = content_type.model_class()
        if model_cls is None:
            raise serializers.ValidationError(
                {'content_type': f'"{content_type}" is not a concrete model.'},
            )
        if not hasattr(model_cls, 'attachments'):
            raise serializers.ValidationError({
                'content_type': (
                    f'"{content_type.app_label}.{content_type.model}" does not '
                    'support attachments.'
                ),
            })

        candidates = model_cls._default_manager.filter(pk=object_id)
        if company is not None:
            candidates = candidates.filter(company=company)
        if not candidates.exists():
            raise serializers.ValidationError({
                'object_id': (
                    f'No {content_type.model} with id {object_id} exists in '
                    'your company.'
                ),
            })

        return attrs
