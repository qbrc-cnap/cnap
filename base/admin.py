from django.contrib import admin

from .models import Resource

class ResourceAdmin(admin.ModelAdmin):
    list_display = ('name', 'path', 'source')
    list_editable = ('path', 'source')
    list_display_links = ('name',)

admin.site.register(Resource, ResourceAdmin)
