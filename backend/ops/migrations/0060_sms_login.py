import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.utils import timezone


DEFAULT_TEMPLATE_CONTENT = '验证码为${code}，有效期30s，请及时登录。'


def configure_sms_login(apps, schema_editor):
    """补齐短信登录设置、模板预览并回填唯一手机号国密索引。"""
    import hmac

    SystemSetting = apps.get_model('ops', 'SystemSetting')
    UserProfile = apps.get_model('ops', 'UserProfile')

    login_setting = SystemSetting.objects.filter(key='security.login').first()
    if login_setting:
        value = dict(login_setting.value or {})
        value.setdefault('sms_login_enabled', False)
        value.setdefault('sms_failure_limit', 5)
        value.setdefault('sms_lock_minutes', 20)
        login_setting.value = value
        login_setting.save(update_fields=['value', 'updated_at'])

    notification = SystemSetting.objects.filter(key='notification.delivery').first()
    if notification:
        value = dict(notification.value or {})
        sms = dict(value.get('sms') or {})
        sms.setdefault('template_content', DEFAULT_TEMPLATE_CONTENT)
        value['sms'] = sms
        notification.value = value
        notification.save(update_fields=['value', 'updated_at'])

    key = str(settings.SMS_SECURITY_KEY).encode('utf-8')
    seen = set()
    for profile in UserProfile.objects.exclude(phone='').iterator():
        phone = ''.join(character for character in str(profile.phone or '').strip() if character not in {' ', '-'})
        if phone.startswith('+86'):
            phone = phone[3:]
        elif phone.startswith('0086'):
            phone = phone[4:]
        if len(phone) != 11 or not phone.isdigit():
            continue
        message = f'taichu-bastion:phone-lookup:v1:{phone}'.encode('utf-8')
        lookup_hash = hmac.new(key, message, 'sm3').hexdigest()
        if lookup_hash in seen:
            raise RuntimeError('检测到重复手机号，请先处理后重新执行迁移')
        seen.add(lookup_hash)
        profile.phone = phone
        profile.phone_lookup_hash = lookup_hash
        profile.save(update_fields=['phone', 'phone_lookup_hash', 'updated_at'])


def restore_sms_login_settings(apps, schema_editor):
    """回滚时移除本迁移增加的短信登录配置键。"""
    SystemSetting = apps.get_model('ops', 'SystemSetting')
    login_setting = SystemSetting.objects.filter(key='security.login').first()
    if login_setting:
        value = dict(login_setting.value or {})
        for field in ('sms_login_enabled', 'sms_failure_limit', 'sms_lock_minutes'):
            value.pop(field, None)
        login_setting.value = value
        login_setting.save(update_fields=['value', 'updated_at'])
    notification = SystemSetting.objects.filter(key='notification.delivery').first()
    if notification:
        value = dict(notification.value or {})
        sms = dict(value.get('sms') or {})
        sms.pop('template_content', None)
        value['sms'] = sms
        notification.value = value
        notification.save(update_fields=['value', 'updated_at'])


class Migration(migrations.Migration):

    dependencies = [
        ('ops', '0059_remove_permission_report_page'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='phone_lookup_hash',
            field=models.CharField(blank=True, help_text='使用带密钥 SM3-HMAC 生成的手机号查询索引，不保存手机号明文。', max_length=64, null=True, unique=True),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='sms_failed_attempts',
            field=models.PositiveSmallIntegerField(default=0, help_text='短信验证码当前连续输入错误次数。'),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='sms_locked_until',
            field=models.DateTimeField(blank=True, help_text='短信验证码验证锁定截止时间；为空表示未锁定。', null=True),
        ),
        migrations.CreateModel(
            name='SmsDispatchRecord',
            fields=[
                ('id', models.BigAutoField(auto_created=True, help_text='数据库主键。', primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(default=timezone.now, help_text='记录创建时间。')),
                ('updated_at', models.DateTimeField(auto_now=True, help_text='记录最后更新时间。')),
                ('recipient_hash', models.CharField(db_index=True, help_text='接收手机号的 SM3-HMAC 查询索引。', max_length=64)),
                ('purpose', models.CharField(choices=[('login', '短信登录'), ('test', '渠道测试')], help_text='本次短信发送的业务用途。', max_length=16)),
                ('status', models.CharField(choices=[('pending', '发送中'), ('sent', '已发送'), ('failed', '发送失败')], default='pending', help_text='网关发送处理状态。', max_length=16)),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='SmsLoginChallenge',
            fields=[
                ('id', models.BigAutoField(auto_created=True, help_text='数据库主键。', primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(default=timezone.now, help_text='记录创建时间。')),
                ('updated_at', models.DateTimeField(auto_now=True, help_text='记录最后更新时间。')),
                ('token_hash', models.CharField(help_text='短信挑战随机令牌的 SM3-HMAC 摘要。', max_length=64, unique=True)),
                ('phone_lookup_hash', models.CharField(db_index=True, help_text='接收手机号的 SM3-HMAC 查询索引。', max_length=64)),
                ('code_hash', models.CharField(help_text='六位短信验证码与挑战令牌组合后的 SM3-HMAC 摘要。', max_length=64)),
                ('ip_address', models.GenericIPAddressField(help_text='挑战绑定的真实客户端 IP 地址。')),
                ('client_nonce_hash', models.CharField(help_text='浏览器会话随机值的 SM3-HMAC 摘要。', max_length=64)),
                ('expires_at', models.DateTimeField(help_text='短信验证码严格失效时间。')),
                ('consumed_at', models.DateTimeField(blank=True, help_text='挑战成功使用或主动失效的时间。', null=True)),
                ('user', models.ForeignKey(blank=True, help_text='手机号对应的用户；匿名一致性挑战为空。', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='sms_login_challenges', to='auth.user')),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.AddIndex(
            model_name='smsdispatchrecord',
            index=models.Index(fields=['recipient_hash', 'status', 'created_at'], name='ops_sms_dispatch_limit_idx'),
        ),
        migrations.AddIndex(
            model_name='smsloginchallenge',
            index=models.Index(fields=['phone_lookup_hash', 'expires_at'], name='ops_sms_challenge_phone_idx'),
        ),
        migrations.AddIndex(
            model_name='smsloginchallenge',
            index=models.Index(fields=['user', 'consumed_at'], name='ops_sms_challenge_user_idx'),
        ),
        migrations.RunPython(configure_sms_login, restore_sms_login_settings),
    ]
