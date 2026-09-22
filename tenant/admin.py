from django.contrib import admin

from tenant.models import Company


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'plan', 'is_active', 'onboarded_at', 'created_at')
    list_filter = ('is_active', 'plan', 'country')
    search_fields = ('name', 'slug', 'legal_name', 'contact_email', 'contact_phone')
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('created_by', 'updated_by', 'created_at', 'updated_at')
    date_hierarchy = 'created_at'

    def has_delete_permission(self, request, obj=None):
        # Deleting a company is a deliberate Module 07 process, not an admin
        # action: every tenant-owned row FKs here with PROTECT, so a careless
        # click fails noisily rather than wiping a tenant's live data.
        return False
