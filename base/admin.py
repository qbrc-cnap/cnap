from django.contrib import admin

from .models import Resource

class ResourceAdmin(admin.ModelAdmin):
    list_display = ('name', 'path', 'source')
    list_editable = ('name', 'path', 'source')

admin.site.register(Resource, ResourceAdmin)
