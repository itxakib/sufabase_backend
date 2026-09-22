from django.contrib import admin
from directory.models import (
    DirectoryCompany,
    DirectoryBusinessActivity,
    ImportBatch,
    ImportRowIssue,
)


@admin.register(DirectoryCompany)
class DirectoryCompanyAdmin(admin.ModelAdmin):
    list_display = [
        'membership_number', 'company_name', 'contact_person',
        'business_sector', 'email', 'phone',
    ]
    search_fields = ['company_name', 'membership_number', 'email', 'contact_person']
    list_filter = ['business_sector', 'membership_type']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(DirectoryBusinessActivity)
class DirectoryBusinessActivityAdmin(admin.ModelAdmin):
    list_display = ['company', 'sheet_name', 'sr_no']
    list_filter = ['sheet_name']
    search_fields = ['company__company_name', 'company__membership_number']


@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'filename', 'status',
        'total_rows', 'companies_created', 'issues_count',
        'triggered_by', 'created_at',
    ]
    list_filter = ['status']
    readonly_fields = [
        'total_rows', 'companies_created', 'companies_updated',
        'activities_created', 'issues_count', 'error_message',
        'created_at', 'completed_at',
    ]


@admin.register(ImportRowIssue)
class ImportRowIssueAdmin(admin.ModelAdmin):
    list_display = [
        'batch', 'sheet_name', 'row_number', 'membership_number',
        'field_name', 'issue_type', 'message',
    ]
    list_filter = ['issue_type', 'sheet_name']
    search_fields = ['membership_number', 'message']
