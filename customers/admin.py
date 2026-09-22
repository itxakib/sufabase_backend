from django.contrib import admin
from django.contrib.contenttypes.models import ContentType
from customers.models import Customer, Tag


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = (
        'full_name',
        'phone',
        'company',
        'stage',
        'record_status',
        'assigned_agent',
        'created_at',
    )
    list_filter = ('stage', 'record_status', 'company')
    search_fields = ('full_name', 'phone', 'email', 'cnic_number', 'passport_number')
    readonly_fields = ('created_at', 'updated_at', 'created_by', 'updated_by')

    def get_queryset(self, request):
        """Optimize: select related agent and prefetch tags."""
        return (
            super()
            .get_queryset(request)
            .select_related('company', 'assigned_agent')
            .prefetch_related('tags')
        )


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('name', 'color', 'company', 'created_at')
    list_filter = ('company',)
    search_fields = ('name',)
    readonly_fields = ('created_at', 'updated_at', 'created_by', 'updated_by')
