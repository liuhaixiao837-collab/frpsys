from django.db import migrations


def enable_slider_captcha(apps, schema_editor):
    """为现有平台登录配置默认启用图形拖拽验证。"""
    SystemSetting = apps.get_model('ops', 'SystemSetting')
    for setting in SystemSetting.objects.filter(key='security.login'):
        value = dict(setting.value) if isinstance(setting.value, dict) else {}
        value['slider_captcha_enabled'] = True
        value.setdefault('captcha_enabled', True)
        value.setdefault('otp_enabled', False)
        setting.value = value
        setting.save(update_fields=['value', 'updated_at'])


def disable_slider_captcha(apps, schema_editor):
    """回退迁移时恢复图形拖拽验证的默认关闭状态。"""
    SystemSetting = apps.get_model('ops', 'SystemSetting')
    for setting in SystemSetting.objects.filter(key='security.login'):
        value = dict(setting.value) if isinstance(setting.value, dict) else {}
        value['slider_captcha_enabled'] = False
        setting.value = value
        setting.save(update_fields=['value', 'updated_at'])


class Migration(migrations.Migration):

    dependencies = [
        ('ops', '0041_access_license_and_system_status'),
    ]

    operations = [
        migrations.RunPython(enable_slider_captcha, disable_slider_captcha),
    ]
