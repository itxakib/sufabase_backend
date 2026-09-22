"""ViewSets for the customers app — thin: parse request → selector → serialize.

Filtering and search are declarative, so the views carry no query logic of their
own: ``CustomerFilter``/``TagFilter`` own the filter contract for HTTP callers
and the selectors own the same query logic for everything else.

Company scoping is handled by ``TenantScopedViewSetMixin`` via the
``X-Company-ID`` header — the mixin filters the base queryset by
``request.company`` and stamps audit fields on save.
"""

import csv
import io
from datetime import datetime

from common.attachment_views import AttachmentActionsMixin
from common.viewsets import TenantScopedViewSetMixin
from django.http import HttpResponse
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from customers.filters.customer import CustomerFilter
from customers.filters.tag import TagFilter
from customers.models import Customer, Tag
from customers.serializers.customer import (
    CustomerDetailSerializer,
    CustomerListSerializer,
    CustomerWriteSerializer,
    TagSerializer,
)

# CSV column header → model field name mapping.
# Fields listed here are the ONLY ones importable via CSV.
# company / created_by / updated_by are never CSV columns.
CSV_FIELD_MAP = {
    'full_name': 'full_name',
    'father_husband_name': 'father_husband_name',
    'gender': 'gender',
    'date_of_birth': 'date_of_birth',
    'cnic_number': 'cnic_number',
    'cnic_expiry_date': 'cnic_expiry_date',
    'passport_number': 'passport_number',
    'passport_issue_date': 'passport_issue_date',
    'passport_expiry_date': 'passport_expiry_date',
    'nationality': 'nationality',
    'marital_status': 'marital_status',
    'phone': 'phone',
    'whatsapp_number': 'whatsapp_number',
    'alt_phone': 'alt_phone',
    'email': 'email',
    'country': 'country',
    'city': 'city',
    'location_area': 'location_area',
    'sub_location': 'sub_location',
    'complete_address': 'complete_address',
    'profession': 'profession',
    'business_type': 'business_type',
    'company_name': 'company_name',
    'designation': 'designation',
    'business_address': 'business_address',
    'business_contact_number': 'business_contact_number',
    'customer_source': 'customer_source',
    'referred_by': 'referred_by',
    'preferred_contact_method': 'preferred_contact_method',
    'preferred_language': 'preferred_language',
    'notes': 'notes',
    'stage': 'stage',
    'record_status': 'record_status',
    'marketing_contact_permission': 'marketing_contact_permission',
    'emergency_contact_name': 'emergency_contact_name',
    'emergency_contact_relationship': 'emergency_contact_relationship',
    'emergency_contact_number': 'emergency_contact_number',
    'family_group_reference': 'family_group_reference',
    'tags': 'tags',
}

# Fields where an empty CSV cell should become None (NULL), not ''.
NULLABLE_DATE_FIELDS = {
    'date_of_birth', 'cnic_expiry_date', 'passport_issue_date', 'passport_expiry_date',
}

# Fields whose values must match a TextChoices set.
CHOICE_FIELDS = {
    'stage': {c[0] for c in Customer._meta.get_field('stage').choices},
    'record_status': {c[0] for c in Customer._meta.get_field('record_status').choices},
}



class CustomerViewSet(AttachmentActionsMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """The customer directory, scoped to the authenticated user's company.

    Company scoping comes from ``TenantScopedViewSetMixin`` (``request.company``
    via the ``X-Company-ID`` header), never from the query string.

    Search deliberately covers scalar columns only. Adding ``tags__name`` to
    ``search_fields`` would make DRF's search cross the tag join, and a customer
    with two matching tags would come back twice — the pagination ``count``
    would then disagree with the rows actually returned. Tag matching is
    available as ``?tag_name=`` and ``?tags=``, which de-duplicate properly.
    """

    queryset = Customer.objects.select_related('assigned_agent').all()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = CustomerFilter
    search_fields = [
        "full_name",
        "father_husband_name",
        "phone",
        "whatsapp_number",
        "alt_phone",
        "email",
        "cnic_number",
        "passport_number",
        "city",
        "location_area",
        "sub_location",
        "company_name",
        "profession",
        "designation",
        "customer_source",
        "referred_by",
        "family_group_reference",
        "emergency_contact_name",
        "assigned_agent__username",
        # TextField substring match — sequential scan, no index possible.
        # Worth it: "which customer mentioned X" is a real question.
        "notes",
    ]
    ordering_fields = [
        "full_name",
        "phone",
        "city",
        "country",
        "stage",
        "record_status",
        "date_of_birth",
        "passport_expiry_date",
        "created_at",
        "updated_at",
        "assigned_agent__username",
    ]
    ordering = ["full_name"]

    def get_serializer_class(self):
        if self.action == "list":
            return CustomerListSerializer
        if self.action in ("create", "update", "partial_update"):
            return CustomerWriteSerializer
        return CustomerDetailSerializer

    # ── CSV template download ────────────────────────────────────────────────
    @action(detail=False, methods=['get'], url_path='template')
    def template(self, request):
        """Download a blank CSV template with all importable customer fields.

        Returns a CSV file with headers matching the model field names and
        one example row showing the expected format.
        """
        buf = io.StringIO()
        writer = csv.writer(buf)

        # Header row
        headers = list(CSV_FIELD_MAP.keys())
        writer.writerow(headers)

        # Example row — shows format for every column
        example = {
            'full_name': 'Ahmed Khan',
            'phone': '03001234567',
            'gender': 'Male',
            'date_of_birth': '1990-05-15',
            'cnic_number': '35202-1234567-1',
            'passport_number': 'AB1234567',
            'nationality': 'Pakistani',
            'marital_status': 'Married',
            'city': 'Lahore',
            'country': 'Pakistan',
            'profession': 'Doctor',
            'email': 'ahmed@example.com',
            'whatsapp_number': '03001234567',
            'stage': 'NEW',
            'record_status': 'ACTIVE',
            'tags': 'VIP, Hajj-2026',
        }
        writer.writerow([example.get(h, '') for h in headers])

        response = HttpResponse(buf.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="customer_import_template.csv"'
        return response

    # ── Bulk CSV upload ──────────────────────────────────────────────────────
    @action(detail=False, methods=['post'], url_path='bulk-upload')
    def bulk_upload(self, request):
        """Import customers from a CSV file.

        Accepts a ``file`` field (multipart/form-data).  Each row is validated
        independently — valid rows are created, invalid rows are reported back
        with the row number, field name, and reason.

        Required fields: ``full_name``, ``phone``.
        All other fields are optional — empty cells become blank/null.
        Date fields accept ``YYYY-MM-DD`` format.
        ``tags`` is a comma-separated list of tag names (e.g. ``VIP, Hajj-2026``).
        """
        uploaded = request.FILES.get('file')
        if not uploaded:
            return Response(
                {'detail': 'No file provided. Send a CSV file as the "file" field.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Read CSV
        try:
            decoded = uploaded.read().decode('utf-8-sig')  # handles BOM
            reader = csv.DictReader(io.StringIO(decoded))
        except UnicodeDecodeError:
            return Response(
                {'detail': 'File must be UTF-8 encoded.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not reader.fieldnames:
            return Response(
                {'detail': 'CSV file is empty or has no headers.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate headers
        missing_required = []
        for required_field in ('full_name', 'phone'):
            if required_field not in reader.fieldnames:
                missing_required.append(required_field)
        if missing_required:
            return Response(
                {
                    'detail': f'Missing required columns: {", ".join(missing_required)}. '
                    'Download the template for the correct headers.',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        company = self._resolve_company()
        errors = []
        customers_to_create = []
        tag_names_to_collect = []  # (row_index, tag_name_strings)
        row_index = 0

        for row in reader:
            row_index += 1
            row_errors = {}
            customer_data = {}

            for csv_header, model_field in CSV_FIELD_MAP.items():
                raw_value = (row.get(csv_header) or '').strip()

                # Required fields
                if model_field in ('full_name', 'phone') and not raw_value:
                    row_errors[csv_header] = f'{csv_header} is required.'
                    continue

                # Empty → skip (model defaults apply)
                if not raw_value:
                    continue

                # Date fields
                if model_field in NULLABLE_DATE_FIELDS:
                    try:
                        customer_data[model_field] = datetime.strptime(raw_value, '%Y-%m-%d').date()
                    except ValueError:
                        row_errors[csv_header] = f'Invalid date format. Use YYYY-MM-DD, got: {raw_value}'
                    continue

                # Choice fields
                if model_field in CHOICE_FIELDS:
                    if raw_value not in CHOICE_FIELDS[model_field]:
                        valid = ', '.join(sorted(CHOICE_FIELDS[model_field]))
                        row_errors[csv_header] = f'Invalid value "{raw_value}". Must be one of: {valid}'
                    else:
                        customer_data[model_field] = raw_value
                    continue

                # Tags — comma-separated, collected for later M2M assignment
                if model_field == 'tags':
                    tag_names_to_collect.append((row_index, raw_value))
                    continue

                # Everything else — plain string
                customer_data[model_field] = raw_value

            if row_errors:
                errors.append({'row': row_index, 'errors': row_errors})
                continue

            # Check required fields made it through
            for required_field in ('full_name', 'phone'):
                if required_field not in customer_data:
                    row_errors[required_field] = f'{required_field} is required.'

            if row_errors:
                errors.append({'row': row_index, 'errors': row_errors})
                continue

            customers_to_create.append((row_index, customer_data))

        # Bulk-create customers
        created_customers = []
        if customers_to_create:
            objs = []
            for row_idx, data in customers_to_create:
                obj = Customer(
                    company=company,
                    created_by=request.user,
                    **data,
                )
                objs.append(obj)
            created_customers = Customer.objects.bulk_create(objs)

        # Assign tags (M2M — must happen after bulk_create)
        tags_assigned = 0
        for row_idx, tag_str in tag_names_to_collect:
            tag_names = [t.strip() for t in tag_str.split(',') if t.strip()]
            if not tag_names:
                continue
            # Get-or-create tags for this company
            tag_objs = []
            for name in tag_names:
                tag_obj, _ = Tag.objects.get_or_create(
                    company=company, name=name,
                    defaults={'name': name},
                )
                tag_objs.append(tag_obj)
            # Find the corresponding customer (same order as created)
            idx = row_idx - 1
            if idx < len(created_customers):
                created_customers[idx].tags.set(tag_objs)
                tags_assigned += len(tag_objs)

        return Response({
            'total_rows': row_index,
            'created': len(created_customers),
            'errors': errors,
            'tags_created_or_linked': tags_assigned,
        })




class TagViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """The tag vocabulary, scoped to the authenticated user's company."""

    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = TagFilter
    search_fields = ["name", "color"]
    ordering_fields = ["name", "color", "created_at", "updated_at"]
    ordering = ["name"]
