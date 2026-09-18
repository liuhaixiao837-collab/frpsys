from django.db import migrations


EMAIL_RATE_LIMITS = {
    'recipient_limit_per_minute': 5,
    'recipient_limit_per_hour': 100,
    'recipient_limit_per_day': 500,
}
SMS_RATE_LIMITS = {
    'recipient_limit_per_minute': 1,
    'recipient_limit_per_hour': 10,
    'recipient_limit_per_day': 50,
}


def add_notification_recipient_rate_limits(apps, schema_editor):
    """为现有邮件和短信配置补齐单一接收方频率策略。"""
    SystemSetting = apps.get_model('ops', 'SystemSetting')
    setting = SystemSetting.objects.filter(key='notification.delivery').first()
    if not setting or not isinstance(setting.value, dict):
        return
    value = dict(setting.value)
    email = dict(value.get('email') or {})
    sms = dict(value.get('sms') or {})
    for field, default in EMAIL_RATE_LIMITS.items():
        email.setdefault(field, default)
    for field, default in SMS_RATE_LIMITS.items():
        sms.setdefault(field, default)
    value['email'] = email
    value['sms'] = sms
    setting.value = value
    setting.save(update_fields=['value', 'updated_at'])


def remove_notification_recipient_rate_limits(apps, schema_editor):
    """回滚时仅移除新增频率字段并保留原通知渠道配置。"""
    SystemSetting = apps.get_model('ops', 'SystemSetting')
    setting = SystemSetting.objects.filter(key='notification.delivery').first()
    if not setting or not isinstance(setting.value, dict):
        return
    value = dict(setting.value)
    for channel_name in ('email', 'sms'):
        channel = dict(value.get(channel_name) or {})
        for field in EMAIL_RATE_LIMITS:
            channel.pop(field, None)
        value[channel_name] = channel
    setting.value = value
    setting.save(update_fields=['value', 'updated_at'])


class Migration(migrations.Migration):

    dependencies = [
        ('ops', '0054_notification_test_permissions'),
    ]

    operations = [
        migrations.RunPython(
            add_notification_recipient_rate_limits,
            remove_notification_recipient_rate_limits,
        ),
    ]
