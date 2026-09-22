from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from users.models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Admin for the custom staff user: exposes company, role, phone, and audit fields."""

    list_display = ('username', 'email', 'company', 'role', 'is_active', 'is_staff')
    list_filter = ('role', 'is_active', 'is_staff', 'is_superuser', 'company')
    search_fields = ('username', 'email', 'first_name', 'last_name', 'phone')
    ordering = ('username',)
    readonly_fields = ('created_by', 'updated_by', 'created_at', 'updated_at')

    fieldsets = DjangoUserAdmin.fieldsets + (
        ('SUFABASE', {'fields': ('company', 'role', 'phone')}),
        ('Audit', {'fields': ('created_by', 'updated_by', 'created_at', 'updated_at')}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ('SUFABASE', {'fields': ('company', 'role', 'phone')}),
    )
