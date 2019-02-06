from django.contrib import admin

from transfer.models import Transfer

class TransferAdmin(admin.ModelAdmin):
    list_display = ('destination')

admin.site.register(Transfer, TransferAdmin)
