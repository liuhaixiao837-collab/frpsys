from django.contrib import admin

from .models import AuditLog


admin.site.register(AuditLog)
