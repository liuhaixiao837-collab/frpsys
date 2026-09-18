from django.db import migrations


DEFAULT_NOTIFICATION_DELIVERY = {
    'email': {
        'enabled': False,
        'smtp_host': '',
        'smtp_port': 465,
        'security': 'ssl',
        'sender_email': '',
        'username': '',
        'password': '',
        'recipient_limit_per_minute': 5,
        'recipient_limit_per_hour': 100,
        'recipient_limit_per_day': 500,
    },
    'sms': {
        'enabled': False,
        'provider': 'aliyun',
        'access_key_id': '',
        'access_key_secret': '',
        'sign_name': '',
        'template_code': '',
        'recipient_limit_per_minute': 1,
        'recipient_limit_per_hour': 10,
        'recipient_limit_per_day': 50,
    },
}


def create_notification_delivery_setting(apps, schema_editor):
    """创建邮件和阿里云短信通知渠道的默认配置。"""
    SystemSetting = apps.get_model('ops', 'SystemSetting')
    SystemSetting.objects.get_or_create(
        key='notification.delivery',
        defaults={
            'organization': None,
            'value': DEFAULT_NOTIFICATION_DELIVERY,
            'description': '平台邮件与短信通知渠道配置',
        },
    )


def remove_notification_delivery_setting(apps, schema_editor):
    """回退迁移时只删除通知渠道配置。"""
    SystemSetting = apps.get_model('ops', 'SystemSetting')
    SystemSetting.objects.filter(key='notification.delivery').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('ops', '0052_license_time_guard'),
    ]

    operations = [
        migrations.RunPython(create_notification_delivery_setting, remove_notification_delivery_setting),
    ]
