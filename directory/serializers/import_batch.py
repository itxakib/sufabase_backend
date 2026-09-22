from rest_framework import serializers
from directory.models import ImportBatch, ImportRowIssue, DirectoryBusinessActivity


class ImportRowIssueSerializer(serializers.ModelSerializer):
    """Row-level issue shown in the batch detail view."""
    class Meta:
        model = ImportRowIssue
        fields = [
            'id', 'sheet_name', 'row_number', 'membership_number',
            'field_name', 'issue_type', 'raw_value', 'message',
        ]


class DirectoryBusinessActivitySerializer(serializers.ModelSerializer):
    """Activity row nested inside company detail."""
    class Meta:
        model = DirectoryBusinessActivity
        fields = ['id', 'sheet_name', 'sr_no']


class ImportBatchSerializer(serializers.ModelSerializer):
    """Batch list/detail — shows progress and summary counts."""
    issues = ImportRowIssueSerializer(many=True, read_only=True)

    class Meta:
        model = ImportBatch
        fields = [
            'id', 'filename', 'status',
            'total_rows', 'companies_created', 'companies_updated',
            'activities_created', 'issues_count', 'error_message', 'triggered_by',
            'issues', 'created_at', 'completed_at',
        ]
        read_only_fields = fields


class ImportUploadSerializer(serializers.Serializer):
    """File upload — accepts an XLS file and optional batch name."""
    file = serializers.FileField()
    batch_name = serializers.CharField(max_length=255, required=False, default='')

    def validate_file(self, value):
        """Allow only .xls and .xlsx files, cap at 50 MB."""
        import os
        ext = os.path.splitext(value.name)[1].lower()
        if ext not in ('.xls', '.xlsx'):
            raise serializers.ValidationError(
                f'Unsupported file type "{ext}". Only .xls and .xlsx are accepted.',
            )
        if value.size > 50 * 1024 * 1024:
            raise serializers.ValidationError(
                f'File too large ({value.size / 1024 / 1024:.1f} MB). Max is 50 MB.',
            )
        return value
