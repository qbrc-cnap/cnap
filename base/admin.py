from django.contrib import admin

from .models import Resource, Issue

class ResourceAdmin(admin.ModelAdmin):
    list_display = ('name', 'path', 'source')
    list_editable = ('path', 'source')
    list_display_links = ('name',)


class IssueAdmin(admin.ModelAdmin):
    list_display = ('message', 'time')

admin.site.register(Resource, ResourceAdmin)
admin.site.register(Issue, IssueAdmin)

