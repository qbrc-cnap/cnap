from django.contrib import admin

from .models import Resource, Issue, AvailableZones, CurrentZone

class ResourceAdmin(admin.ModelAdmin):
    list_display = ('name', 'path', 'source')
    list_editable = ('path', 'source')
    list_display_links = ('name',)


class IssueAdmin(admin.ModelAdmin):
    list_display = ('message', 'time')


class AvailableZonesAdmin(admin.ModelAdmin):
    list_display = ('cloud_environment', 'zone')
    list_editable = ('zone',)


class CurrentZoneAdmin(admin.ModelAdmin):
    list_display = ('zone',)


admin.site.register(Resource, ResourceAdmin)
admin.site.register(Issue, IssueAdmin)
admin.site.register(AvailableZones, AvailableZonesAdmin)
admin.site.register(CurrentZone, CurrentZoneAdmin)
