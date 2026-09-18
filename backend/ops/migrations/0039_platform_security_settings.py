from django.db import migrations


DEFAULT_SETTINGS = {
    'security': (
        {'session_timeout': 1800},
        '平台会话安全设置',
    ),
    'security.login_whitelist': (
        {'enabled': False, 'entries': []},
        '登录来源 IP 白名单',
    ),
    'security.password_policy': (
        {
            'min_length': 8,
            'require_uppercase': True,
            'require_lowercase': True,
            'require_number': True,
            'require_special': True,
            'exclude_username': True,
        },
        '平台用户密码复杂度策略',
    ),
    'security.login': (
        {
            'captcha_enabled': True,
            'slider_captcha_enabled': False,
            'otp_enabled': False,
        },
        '平台登录认证设置',
    ),
    'locale.timezone': (
        {'timezone': 'Asia/Shanghai'},
        '平台统一时区设置',
    ),
}


def add_platform_security_settings(apps, schema_editor):
    """补充平台设置五个 Tab 所需的默认数据库配置。"""
    SystemSetting = apps.get_model('ops', 'SystemSetting')
    for key, (value, description) in DEFAULT_SETTINGS.items():
        SystemSetting.objects.get_or_create(
            key=key,
            defaults={
                'organization': None,
                'value': value,
                'description': description,
            },
        )


def remove_platform_security_settings(apps, schema_editor):
    """回退时只删除本迁移新增的安全设置键。"""
    SystemSetting = apps.get_model('ops', 'SystemSetting')
    SystemSetting.objects.filter(
        key__in=[
            'security.login_whitelist',
            'security.password_policy',
            'security.login',
            'locale.timezone',
        ],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('ops', '0038_add_menu_order_page'),
    ]

    operations = [
        migrations.RunPython(add_platform_security_settings, remove_platform_security_settings),
    ]
