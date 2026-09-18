from django.apps import AppConfig


class OpsConfig(AppConfig):
    """注册平台核心模型及权限缓存失效信号。"""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ops'
    verbose_name = '平台核心'

    def ready(self):
        """初始化实例 ID，并注册管理员约束及权限缓存失效信号。"""
        from django.contrib.auth.models import User
        from django.db.models.signals import post_delete, post_save, pre_save

        from .models import PermissionMenuAction, PermissionMenuNode, PermissionPolicy, PermissionRule
        from .permission_service import clear_permission_cache
        from .services.instance_identity import initialize_instance_identity
        from .services.system_admin import enforce_system_admin_invariant

        initialize_instance_identity()

        def clear_permission_cache_receiver(**kwargs):
            """响应权限相关模型变更并清空缓存。"""
            clear_permission_cache()

        def enforce_system_admin_receiver(sender, instance, **kwargs):
            """在用户写入数据库前阻止产生第二个超级管理员或修改 admin 身份。"""
            enforce_system_admin_invariant(instance)

        pre_save.connect(
            enforce_system_admin_receiver,
            sender=User,
            dispatch_uid='ops.enforce_system_admin.save',
        )

        for model in (PermissionMenuNode, PermissionMenuAction, PermissionPolicy, PermissionRule):
            post_save.connect(clear_permission_cache_receiver, sender=model, dispatch_uid=f'ops.clear_permission_cache.{model.__name__}.save')
            post_delete.connect(clear_permission_cache_receiver, sender=model, dispatch_uid=f'ops.clear_permission_cache.{model.__name__}.delete')
