from django.contrib import admin

from transfer_app.models import Transfer, FailedTransfer

class TransferAdmin(admin.ModelAdmin):
    list_display = ('destination',)

class FailedTransferAdmin(admin.ModelAdmin):
    list_display = ('was_download','intended_path', 'resource_name')


admin.site.register(Transfer, TransferAdmin)
admin.site.register(FailedTransfer, FailedTransferAdmin)
