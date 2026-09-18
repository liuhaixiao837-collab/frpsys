from django.db import migrations, models
import django.utils.timezone


DEFAULT_LOGO_URL = '/assets/brand/logo.png'


def add_password_expiry_defaults(apps, schema_editor):
    """补齐密码有效期和默认 Logo 的平台配置。"""
    SystemSetting = apps.get_model('ops', 'SystemSetting')
    password_setting = SystemSetting.objects.filter(key='security.password_policy').first()
    if password_setting:
        value = password_setting.value if isinstance(password_setting.value, dict) else {}
        if 'max_age_days' not in value:
            password_setting.value = {**value, 'max_age_days': 30}
            password_setting.save(update_fields=['value', 'updated_at'])
    platform_setting, _created = SystemSetting.objects.get_or_create(
        key='platform',
        defaults={
            'organization': None,
            'value': {'name': 'Ongrid', 'logo_url': DEFAULT_LOGO_URL},
            'description': '平台基础品牌配置',
        },
    )
    value = platform_setting.value if isinstance(platform_setting.value, dict) else {}
    if not value.get('logo_url'):
        platform_setting.value = {**value, 'logo_url': DEFAULT_LOGO_URL}
        platform_setting.save(update_fields=['value', 'updated_at'])


def remove_password_expiry_defaults(apps, schema_editor):
    """回退密码有效期默认配置，保留用户可能已经上传的 Logo。"""
    SystemSetting = apps.get_model('ops', 'SystemSetting')
    password_setting = SystemSetting.objects.filter(key='security.password_policy').first()
    if password_setting and isinstance(password_setting.value, dict):
        value = dict(password_setting.value)
        value.pop('max_age_days', None)
        password_setting.value = value
        password_setting.save(update_fields=['value', 'updated_at'])


class Migration(migrations.Migration):

    dependencies = [
        ('ops', '0042_enable_slider_captcha'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='password_changed_at',
            field=models.DateTimeField(default=django.utils.timezone.now, help_text='用户最近一次修改密码或管理员解锁重置周期的时间。'),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='password_expired_locked',
            field=models.BooleanField(default=False, help_text='是否因密码超过有效期被系统自动禁用。'),
        ),
        migrations.RunPython(add_password_expiry_defaults, remove_password_expiry_defaults),
    ]
