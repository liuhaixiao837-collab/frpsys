from django.db import migrations


LOCK_DEFAULTS = {
    'login_failure_limit': 5,
    'login_lock_minutes': 30,
    'otp_failure_limit': 5,
    'otp_lock_minutes': 20,
}
LEGACY_MASKED_KEYS = ('password_failure_limit', 'password_lock_minutes')


def add_login_lock_policy(apps, schema_editor):
    """为现有登录设置补充密码和 OTP 错误锁定默认策略。"""
    SystemSetting = apps.get_model('ops', 'SystemSetting')
    for setting in SystemSetting.objects.filter(key='security.login').iterator():
        value = dict(setting.value) if isinstance(setting.value, dict) else {}
        for key in LEGACY_MASKED_KEYS:
            value.pop(key, None)
        for key, default in LOCK_DEFAULTS.items():
            value.setdefault(key, default)
        setting.value = value
        setting.save(update_fields=['value', 'updated_at'])


def remove_login_lock_policy(apps, schema_editor):
    """回退时仅移除本迁移增加的登录锁定策略字段。"""
    SystemSetting = apps.get_model('ops', 'SystemSetting')
    for setting in SystemSetting.objects.filter(key='security.login').iterator():
        value = dict(setting.value) if isinstance(setting.value, dict) else {}
        for key in LOCK_DEFAULTS:
            value.pop(key, None)
        setting.value = value
        setting.save(update_fields=['value', 'updated_at'])


class Migration(migrations.Migration):

    dependencies = [
        ('ops', '0046_user_otp_authentication'),
    ]

    operations = [
        migrations.RunPython(add_login_lock_policy, remove_login_lock_policy),
    ]
