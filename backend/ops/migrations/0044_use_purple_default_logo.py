from django.db import migrations


OLD_DEFAULT_LOGO_URL = '/assets/brand/logo.png'
PURPLE_DEFAULT_LOGO_URL = '/assets/brand/logo.svg'


def use_purple_default_logo(apps, schema_editor):
    SystemSetting = apps.get_model('ops', 'SystemSetting')
    platform_setting = SystemSetting.objects.filter(key='platform').first()
    if platform_setting is None:
        SystemSetting.objects.create(
            key='platform',
            value={'name': 'Ongrid', 'logo_url': PURPLE_DEFAULT_LOGO_URL},
        )
        return
    value = platform_setting.value if isinstance(platform_setting.value, dict) else {}
    if not value.get('logo_url') or value.get('logo_url') == OLD_DEFAULT_LOGO_URL:
        platform_setting.value = {**value, 'logo_url': PURPLE_DEFAULT_LOGO_URL}
        platform_setting.save(update_fields=['value', 'updated_at'])


def restore_blue_default_logo(apps, schema_editor):
    SystemSetting = apps.get_model('ops', 'SystemSetting')
    platform_setting = SystemSetting.objects.filter(key='platform').first()
    if platform_setting is None:
        return
    value = platform_setting.value if isinstance(platform_setting.value, dict) else {}
    if value.get('logo_url') == PURPLE_DEFAULT_LOGO_URL:
        platform_setting.value = {**value, 'logo_url': OLD_DEFAULT_LOGO_URL}
        platform_setting.save(update_fields=['value', 'updated_at'])


class Migration(migrations.Migration):
    dependencies = [
        ('ops', '0043_password_expiry_and_default_logo'),
    ]

    operations = [
        migrations.RunPython(use_purple_default_logo, restore_blue_default_logo),
    ]
