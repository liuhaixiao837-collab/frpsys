from django.db import migrations


DEFAULT_FILING = {
    'icp_record': '冀ICP备2026010543号-3',
    'icp_url': 'https://beian.miit.gov.cn/',
    'public_security_record': '冀公网安备13310102000221号',
    'public_security_url': 'http://www.beian.gov.cn/portal/registerSystemInfo?recordcode=13310102000221',
}


def create_platform_filing(apps, schema_editor):
    SystemSetting = apps.get_model('ops', 'SystemSetting')
    SystemSetting.objects.get_or_create(
        key='platform.filing',
        organization_id=None,
        defaults={
            'value': DEFAULT_FILING,
            'description': '登录页工信部与公安部备案信息',
        },
    )


def remove_platform_filing(apps, schema_editor):
    SystemSetting = apps.get_model('ops', 'SystemSetting')
    SystemSetting.objects.filter(key='platform.filing', organization_id=None).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('ops', '0044_use_purple_default_logo'),
    ]

    operations = [
        migrations.RunPython(create_platform_filing, remove_platform_filing),
    ]
