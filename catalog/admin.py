"""Admin for sellable package specs.

Lines are typed on the template. This screen does not create hotel, ticket,
or transport bookings.
"""

from django.contrib import admin

from catalog.models import PackageTemplate, PackageTemplateLine


class PackageTemplateLineInline(admin.TabularInline):
    model = PackageTemplateLine
    extra = 0
    exclude = ('company', 'created_by', 'updated_by')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(PackageTemplate)
class PackageTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'created_at')
    list_filter = ('company',)
    search_fields = ('name',)
    readonly_fields = ('created_at', 'updated_at', 'created_by', 'updated_by')
    inlines = [PackageTemplateLineInline]

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for obj in formset.deleted_objects:
            obj.delete()
        for obj in instances:
            if isinstance(obj, PackageTemplateLine):
                obj.company = form.instance.company
            obj.save()
        formset.save_m2m()
