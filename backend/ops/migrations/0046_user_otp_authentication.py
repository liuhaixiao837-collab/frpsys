from django.db import migrations, models

import data_security.fields


OTP_ACTION_CODE = 'page.admin_users.reset_otp'


def add_reset_otp_permission(apps, schema_editor):
    """为用户管理页面新增重置 OTP 操作并将已有策略默认补齐为拒绝。"""
    MenuNode = apps.get_model('ops', 'PermissionMenuNode')
    MenuAction = apps.get_model('ops', 'PermissionMenuAction')
    PermissionPolicy = apps.get_model('ops', 'PermissionPolicy')
    PermissionRule = apps.get_model('ops', 'PermissionRule')

    page = MenuNode.objects.get(code='page.admin_users.view')
    MenuAction.objects.update_or_create(
        page=page,
        code='reset_otp',
        defaults={
            'name': '重置 OTP',
            'sort_order': 50,
            'is_active': True,
        },
    )
    for policy in PermissionPolicy.objects.all().iterator():
        PermissionRule.objects.update_or_create(
            policy=policy,
            permission_code=OTP_ACTION_CODE,
            defaults={'effect': 'deny'},
        )


def remove_reset_otp_permission(apps, schema_editor):
    """回退时删除重置 OTP 操作及所有策略中对应的规则。"""
    MenuAction = apps.get_model('ops', 'PermissionMenuAction')
    PermissionRule = apps.get_model('ops', 'PermissionRule')

    PermissionRule.objects.filter(permission_code=OTP_ACTION_CODE).delete()
    MenuAction.objects.filter(page__code='page.admin_users.view', code='reset_otp').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('ops', '0045_platform_filing_settings'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='auth_version',
            field=models.PositiveIntegerField(default=0, help_text='认证版本号，重置 OTP 时递增以使已签发令牌失效。'),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='otp_bound_at',
            field=models.DateTimeField(blank=True, help_text='用户最近一次完成 OTP 绑定的时间。', null=True),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='otp_failed_attempts',
            field=models.PositiveSmallIntegerField(default=0, help_text='当前连续 OTP 验证失败次数。'),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='otp_last_timestep',
            field=models.BigIntegerField(blank=True, help_text='最后一次成功使用的 TOTP 时间步，用于防止口令重放。', null=True),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='otp_locked_until',
            field=models.DateTimeField(blank=True, help_text='OTP 验证锁定截止时间；为空表示未锁定。', null=True),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='otp_policy',
            field=models.CharField(choices=[('inherit', '跟随平台'), ('required', '强制启用'), ('exempt', '免于认证')], default='inherit', help_text='用户 OTP 策略：跟随平台、强制启用或免于认证。', max_length=16),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='otp_recovery_hashes',
            field=models.JSONField(blank=True, default=list, help_text='旧版 OTP 应急凭据摘要列表。'),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='otp_secret',
            field=data_security.fields.EncryptedCharField(blank=True, help_text='使用 SM4 加密保存的 TOTP Base32 种子，接口和日志禁止返回。', max_length=512),
        ),
        migrations.RunPython(add_reset_otp_permission, remove_reset_otp_permission),
    ]
