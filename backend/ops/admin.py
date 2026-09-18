from django.contrib import admin

from . import models


admin.site.register([
    models.Organization,
    models.Role,
    models.UserProfile,
    models.PermissionMenuNode,
    models.PermissionMenuAction,
    models.PermissionPolicy,
    models.PermissionRule,
    models.SystemSetting,
])
