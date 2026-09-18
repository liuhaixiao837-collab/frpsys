from django.db import migrations


IP_LOCK_DEFAULTS = {
    'ip_failure_limit': 20,
    'ip_lock_minutes': 30,
}


def add_ip_login_lock_policy(apps, schema_editor):
    """为现有登录设置补充独立的来源 IP 防暴力锁定策略。"""
    SystemSetting = apps.get_model('ops', 'SystemSetting')
    for setting in SystemSetting.objects.filter(key='security.login').iterator():
        value = dict(setting.value) if isinstance(setting.value, dict) else {}
        for key, default in IP_LOCK_DEFAULTS.items():
            value.setdefault(key, default)
        setting.value = value
        setting.save(update_fields=['value', 'updated_at'])


def remove_ip_login_lock_policy(apps, schema_editor):
    """回退时仅移除独立的来源 IP 锁定策略字段。"""
    SystemSetting = apps.get_model('ops', 'SystemSetting')
    for setting in SystemSetting.objects.filter(key='security.login').iterator():
        value = dict(setting.value) if isinstance(setting.value, dict) else {}
        for key in IP_LOCK_DEFAULTS:
            value.pop(key, None)
        setting.value = value
        setting.save(update_fields=['value', 'updated_at'])


class Migration(migrations.Migration):

    dependencies = [
        ('ops', '0047_login_lock_policy'),
    ]

    operations = [
        migrations.RunPython(add_ip_login_lock_policy, remove_ip_login_lock_policy),
    ]
