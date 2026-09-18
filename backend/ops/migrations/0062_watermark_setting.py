from django.db import migrations


DEFAULT_WATERMARK = {
    'enabled': False,
    'content_type': 'username_ip',
    'custom_text': '',
    'layout': 'tiled',
    'show_time': True,
    'font_size': 14,
    'font_weight': 500,
    'color': '#64748b',
    'opacity': 0.14,
    'rotate': -24,
    'horizontal_gap': 220,
    'vertical_gap': 140,
}


def add_watermark_setting(apps, schema_editor):
    """新增默认关闭的工作台全局水印配置。"""
    SystemSetting = apps.get_model('ops', 'SystemSetting')
    SystemSetting.objects.get_or_create(
        key='security.watermark',
        defaults={
            'organization': None,
            'value': DEFAULT_WATERMARK,
            'description': '平台工作台全局水印设置',
        },
    )


def remove_watermark_setting(apps, schema_editor):
    """回退迁移时删除水印配置。"""
    SystemSetting = apps.get_model('ops', 'SystemSetting')
    SystemSetting.objects.filter(key='security.watermark').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('ops', '0061_log_export_permissions'),
    ]

    operations = [
        migrations.RunPython(add_watermark_setting, remove_watermark_setting),
    ]
