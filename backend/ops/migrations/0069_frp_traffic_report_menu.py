from django.db import migrations


GROUP_CODE = 'menu.security.frp'
PAGE_CODE = 'page.security.frp_traffic_reports.view'


def add_traffic_report_menu(apps, schema_editor):
    MenuNode = apps.get_model('ops', 'PermissionMenuNode')
    MenuPreference = apps.get_model('ops', 'UserMenuOrderPreference')
    PermissionPolicy = apps.get_model('ops', 'PermissionPolicy')
    PermissionRule = apps.get_model('ops', 'PermissionRule')

    group = MenuNode.objects.filter(code=GROUP_CODE).first()
    if not group:
        return
    MenuNode.objects.update_or_create(
        code=PAGE_CODE,
        defaults={
            'parent': group,
            'node_type': 'page',
            'name': '流量报表',
            'path': '/security/frp/traffic-reports',
            'icon': 'Activity',
            'sidebar': True,
            'aliases': [],
            'sort_order': 6,
            'is_active': True,
        },
    )
    for policy in PermissionPolicy.objects.all().iterator():
        PermissionRule.objects.update_or_create(
            policy=policy,
            permission_code=PAGE_CODE,
            defaults={'effect': 'deny'},
        )
    for preference in MenuPreference.objects.all().iterator():
        source = dict(preference.order_data) if isinstance(preference.order_data, dict) else {}
        order = source.get(GROUP_CODE, [])
        if not isinstance(order, list):
            order = []
        if PAGE_CODE not in order:
            source[GROUP_CODE] = [*order, PAGE_CODE]
            preference.order_data = source
            preference.save(update_fields=['order_data', 'updated_at'])


def remove_traffic_report_menu(apps, schema_editor):
    MenuNode = apps.get_model('ops', 'PermissionMenuNode')
    MenuPreference = apps.get_model('ops', 'UserMenuOrderPreference')
    PermissionRule = apps.get_model('ops', 'PermissionRule')
    PermissionRule.objects.filter(permission_code=PAGE_CODE).delete()
    MenuNode.objects.filter(code=PAGE_CODE).delete()
    for preference in MenuPreference.objects.all().iterator():
        source = dict(preference.order_data) if isinstance(preference.order_data, dict) else {}
        source[GROUP_CODE] = [code for code in source.get(GROUP_CODE, []) if code != PAGE_CODE]
        preference.order_data = source
        preference.save(update_fields=['order_data', 'updated_at'])


class Migration(migrations.Migration):
    dependencies = [('ops', '0068_frp_reveal_permissions')]
    operations = [migrations.RunPython(add_traffic_report_menu, remove_traffic_report_menu)]
