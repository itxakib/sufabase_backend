import os
import tempfile

from django.db.models import Count
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from common.viewsets import TenantScopedViewSetMixin
from directory.choices import ImportStatusChoices
from directory.filters import DirectoryCompanyFilter
from directory.models import DirectoryBusinessActivity, DirectoryCompany, ImportBatch
from directory.serializers import (
    DirectoryActivityOptionSerializer,
    DirectoryCompanyDetailSerializer,
    DirectoryCompanyListSerializer,
    DirectorySectorSerializer,
    ImportBatchSerializer,
    ImportUploadSerializer,
)
from directory.services import DirectoryImportService


class DirectoryCompanyViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    # The activity count groups the query, and a GROUP BY query ignores the
    # model's default ordering. Without an explicit order, page 1 of a 30k-row
    # directory is not stable between requests.
    queryset = DirectoryCompany.objects.annotate(
        activity_count=Count('activities', distinct=True),
    ).order_by('company_name', 'pk')
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = DirectoryCompanyFilter
    search_fields = [
        'company_name', 'contact_person', 'membership_number',
        'email', 'phone', 'product_line', 'address',
    ]
    ordering_fields = ['company_name', 'created_at', 'membership_number']

    def get_serializer_class(self):
        if self.action == 'list':
            return DirectoryCompanyListSerializer
        return DirectoryCompanyDetailSerializer

    @extend_schema(
        responses=DirectorySectorSerializer(many=True),
        summary='Sector and sub-sector values, for the list filters',
    )
    # `pagination_class=None` and `filter_backends=[]` are load-bearing, not
    # cosmetic. The company list is paginated and filterable, and drf-spectacular
    # derives the schema from those class attributes: without the overrides the
    # generated frontend type would claim a `{count, results}` envelope and
    # advertise filter parameters the action never reads. A filter's option list is
    # a complete vocabulary, not a filtered page of rows.
    @action(detail=False, methods=['get'], pagination_class=None, filter_backends=[])
    def sectors(self, request):
        """GET /api/v1/directory-companies/sectors/

        Every distinct ``business_sector`` in this company's directory, each with
        the ``sub_sector`` values recorded beneath it, so the frontend can offer
        two cascading selects instead of two free-text boxes.

        Why this reads the data instead of declaring an enum: the sector names
        come from the chamber's own workbook, and future exports may rename or add
        them. A ``choices=`` list would reject a value the importer writes, so
        ``directory/choices.py`` deliberately does not restrict them. The lookup
        therefore stays correct across imports with no migration.

        Deliberately *not* narrowed by the request's query parameters. A filter's
        own option list must not shrink to the rows that filter already matched,
        or picking one sector would hide every other one. It is still tenant-
        scoped, and it is unaffected by the class-level annotation below.
        """
        # `self.get_queryset()` carries an `activity_count` annotation. An
        # annotation joins the SELECT and the GROUP BY, which would collapse the
        # (sector, sub_sector) pairs into one row per company instead of one row
        # per pair. The tenant-scoped manager is used directly for that reason —
        # `_resolve_company` is the mixin's own resolver, so the scoping rule
        # still lives in exactly one place.
        rows = (
            DirectoryCompany.objects.filter(company=self._resolve_company())
            .exclude(business_sector='')
            .values('business_sector', 'sub_sector')
            .annotate(count=Count('id'))
            .order_by('business_sector', 'sub_sector')
        )

        grouped: dict[str, dict] = {}
        for row in rows:
            sector = grouped.setdefault(
                row['business_sector'],
                {
                    'value': row['business_sector'],
                    'label': row['business_sector'],
                    'count': 0,
                    'sub_sectors': [],
                },
            )
            sector['count'] += row['count']

            # A sector can hold rows with no sub-sector at all. They stay out of
            # the child list — an empty option would filter on the empty string —
            # and are still reachable by choosing the sector alone.
            if row['sub_sector']:
                sector['sub_sectors'].append({
                    'value': row['sub_sector'],
                    'label': row['sub_sector'],
                    'count': row['count'],
                })

        return Response(DirectorySectorSerializer(grouped.values(), many=True).data)

    @extend_schema(
        responses=DirectoryActivityOptionSerializer(many=True),
        summary='Sheet categories, for the activity filter',
    )
    @action(detail=False, methods=['get'], pagination_class=None, filter_backends=[], url_path='activities')
    def activities(self, request):
        """GET /api/v1/directory-companies/activities/

        Distinct chamber sheets (Manufacturers, Importers, Exporters, Traders,
        Services) recorded as business activities, with a count of companies on
        each. The list filter ``?sheet_name=`` uses these values.

        Not narrowed by the request's query parameters, for the same reason as
        ``sectors``: picking Manufacturers must not hide Importers.
        """
        rows = (
            DirectoryBusinessActivity.objects.filter(company=self._resolve_company())
            .exclude(sheet_name='')
            .values('sheet_name')
            .annotate(count=Count('id'))
            .order_by('sheet_name')
        )
        payload = [
            {'value': row['sheet_name'], 'label': row['sheet_name'], 'count': row['count']}
            for row in rows
        ]
        return Response(DirectoryActivityOptionSerializer(payload, many=True).data)


class ImportBatchViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = ImportBatch.objects.all()
    serializer_class = ImportBatchSerializer
    http_method_names = ['get', 'post', 'head', 'options']  # read-only except upload

    def get_queryset(self):
        return super().get_queryset().prefetch_related('issues')

    def get_parser_classes(self):
        if self.action == 'upload':
            return [MultiPartParser(), FormParser()]
        return super().get_parser_classes()

    @action(detail=False, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def upload(self, request):
        """Upload an XLS/XLSX directory workbook for import.

        The import runs synchronously (no Celery in this project). For a
        46k-row LCCI file this takes ~30-60 seconds — the frontend should
        show a loading spinner and poll the batch detail endpoint.
        """
        upload_serializer = ImportUploadSerializer(data=request.data)
        upload_serializer.is_valid(raise_exception=True)

        file_obj = upload_serializer.validated_data['file']
        # Authentication runs after middleware for JWT requests, so the
        # middleware-owned `request.company` can be None even with a valid
        # X-Company-ID header. The tenant mixin resolves that case from the
        # authenticated user; use it for every write in this custom action.
        company = self._resolve_company()
        if company is None:
            return Response(
                {'detail': 'A valid company context is required.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Save to a temp file so xlrd can open it (xlrd needs a file path,
        # not a Django InMemoryUploadedFile).
        with tempfile.NamedTemporaryFile(
            suffix=os.path.splitext(file_obj.name)[1],
            delete=False,
        ) as tmp:
            for chunk in file_obj.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name

        try:
            # Pre-flight validation — structural check before touching the DB.
            ok, error = DirectoryImportService.validate_workbook(tmp_path)
            if not ok:
                return Response(
                    {'detail': error},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Create the batch in PROCESSING state.
            from django.utils import timezone as tz
            batch = ImportBatch.objects.create(
                company=company,
                triggered_by=request.user,
                filename=file_obj.name,
                status=ImportStatusChoices.PROCESSING,
                started_at=tz.now(),
            )

            # Run the import (synchronous, transactional).
            DirectoryImportService.import_workbook(
                batch=batch,
                file_path=tmp_path,
                company=company,
            )

            batch.refresh_from_db()
            batch.status = ImportStatusChoices.COMPLETED
            batch.save(update_fields=['status'])

            return Response(
                ImportBatchSerializer(batch).data,
                status=status.HTTP_201_CREATED,
            )

        except Exception as exc:
            # Mark the batch as failed so the UI shows something useful.
            if 'batch' in locals():
                batch.status = ImportStatusChoices.FAILED
                batch.error_message = str(exc)[:1000]
                from django.utils import timezone as _tz
                batch.completed_at = _tz.now()
                batch.save(update_fields=['status', 'error_message', 'completed_at'])
            return Response(
                {'detail': f'Import failed: {exc}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        finally:
            os.unlink(tmp_path)
