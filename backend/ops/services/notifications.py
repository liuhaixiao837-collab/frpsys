"""平台邮件与多服务商验证码短信发送服务。"""

import base64
import hashlib
import hmac
import html
import json
import time
import uuid
from datetime import datetime, timedelta, timezone as datetime_timezone
from urllib.parse import quote

import requests
from django.core.mail import EmailMultiAlternatives
from django.core.mail.backends.smtp import EmailBackend
from django.db import transaction
from django.utils import timezone

from ..models import SmsDispatchRecord, SystemSetting
from .phone_identity import phone_lookup_hash


ALIYUN_SMS_ENDPOINT = 'https://dysmsapi.aliyuncs.com/'
TENCENT_SMS_ENDPOINT = 'https://sms.tencentcloudapi.com'
BAIDU_SMS_ENDPOINT = 'https://smsv3.bj.baidubce.com/api/v3/sendSms'
UPYUN_SMS_ENDPOINT = 'https://sms-api.upyun.com/api/messages'
QINIU_SMS_ENDPOINT = 'https://sms.qiniuapi.com/v1/message/single'
YUNPIAN_SMS_ENDPOINT = 'https://sms.yunpian.com/v2/sms/tpl_single_send.json'
NETEASE_SMS_ENDPOINT = 'https://api.netease.im/sms/sendtemplate.action'
NOTIFICATION_TIMEOUT_SECONDS = 10

SMS_PROVIDER_NAMES = {
    'aliyun': '阿里云',
    'tencent': '腾讯云',
    'baidu': '百度云',
    'upyun': '又拍云',
    'qiniu': '七牛云',
    'yunpian': '云片网',
    'netease': '网易云信',
}

SMS_PROVIDER_REQUIRED_FIELDS = {
    'aliyun': ('access_key_id', 'access_key_secret', 'sign_name', 'template_code'),
    'tencent': ('secret_id', 'secret_key', 'sdk_app_id', 'sign_name', 'template_code'),
    'baidu': ('access_key_id', 'access_key_secret', 'signature_id', 'template_code'),
    'upyun': ('authorization_token', 'template_code'),
    'qiniu': ('access_key_id', 'access_key_secret', 'template_code'),
    'yunpian': ('api_key', 'template_code'),
    'netease': ('app_key', 'app_secret', 'template_code'),
}


class NotificationConfigurationError(ValueError):
    """表示通知渠道尚未启用或配置不完整。"""


class NotificationSendError(RuntimeError):
    """表示已配置渠道连接或第三方发送失败。"""


class NotificationRateLimitError(NotificationSendError):
    """表示同一手机号已经达到短信网关动态发送上限。"""


def notification_delivery_settings():
    """读取数据库中已解密的通知渠道配置。

    返回：包含邮件与短信配置的字典；未配置时返回空字典。
    副作用：只读取数据库，不记录或返回任何凭据给客户端。
    """
    setting = SystemSetting.objects.filter(key='notification.delivery').first()
    return setting.value if setting and isinstance(setting.value, dict) else {}


def platform_name():
    """读取测试通知中使用的平台名称。

    返回：基础设置中的平台名称，未配置时返回 Ongrid。
    副作用：只读取数据库。
    """
    setting = SystemSetting.objects.filter(key='platform').first()
    value = setting.value if setting and isinstance(setting.value, dict) else {}
    return str(value.get('name') or 'Ongrid').strip()[:120] or 'Ongrid'


def _required_channel(config, fields, channel_label):
    """校验测试发送所需的渠道开关和必填字段。

    参数：`config` 为渠道配置，`fields` 为必填键，`channel_label` 为错误提示名称。
    返回：通过校验的原配置字典；配置不可用时抛出安全错误。
    """
    if not isinstance(config, dict) or not config.get('enabled'):
        raise NotificationConfigurationError(f'{channel_label}尚未启用，请先完成配置并保存')
    if any(not str(config.get(field) or '').strip() for field in fields):
        raise NotificationConfigurationError(f'{channel_label}配置不完整，请补充必填项后再测试')
    return config


def _test_email_content(name):
    """生成不依赖外部资源的测试邮件正文。

    参数：`name` 为平台名称。
    返回：邮件主题、纯文本正文和使用内联样式的 HTML 正文。
    """
    safe_name = html.escape(name)
    sent_at = timezone.localtime().strftime('%Y-%m-%d %H:%M:%S')
    subject = f'【{name}】通知渠道测试'
    text_body = (
        f'这是平台名称「{name}」的测试邮件，用于验证 SMTP 通知渠道是否可以正常发送。\n\n'
        f'平台名称：{name}\n发送时间：{sent_at}\n状态：配置验证成功\n\n'
        '此邮件由平台管理员手动触发，无需回复。'
    )
    html_body = f'''<!doctype html>
<html lang="zh-CN">
<body style="margin:0;padding:0;background:#f3f6fa;color:#172033;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Microsoft YaHei',Arial,sans-serif;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f3f6fa;padding:32px 12px;">
    <tr><td align="center">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:600px;background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;box-shadow:0 8px 24px rgba(15,23,42,.06);">
        <tr><td style="height:4px;background:#2563eb;"></td></tr>
        <tr><td style="padding:30px 34px 18px;">
          <div style="font-size:12px;font-weight:700;color:#2563eb;">通知渠道测试</div>
          <h1 style="margin:9px 0 0;font-size:22px;line-height:1.4;color:#172033;">SMTP 配置验证成功</h1>
        </td></tr>
        <tr><td style="padding:0 34px 24px;">
          <p style="margin:0;color:#526176;font-size:14px;line-height:1.8;">这是平台名称「{safe_name}」的测试邮件，用于验证 SMTP 通知渠道是否可以正常发送。</p>
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-top:22px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;">
            <tr><td style="padding:14px 16px;color:#64748b;font-size:13px;width:92px;">平台名称</td><td style="padding:14px 16px;color:#172033;font-size:13px;font-weight:600;">{safe_name}</td></tr>
            <tr><td style="padding:0 16px 14px;color:#64748b;font-size:13px;">发送时间</td><td style="padding:0 16px 14px;color:#172033;font-size:13px;">{sent_at}</td></tr>
            <tr><td style="padding:0 16px 14px;color:#64748b;font-size:13px;">验证状态</td><td style="padding:0 16px 14px;color:#15803d;font-size:13px;font-weight:600;">配置验证成功</td></tr>
          </table>
        </td></tr>
        <tr><td style="padding:17px 34px;background:#f8fafc;border-top:1px solid #e2e8f0;color:#7b8798;font-size:12px;line-height:1.6;">此邮件由平台管理员手动触发，无需回复。</td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>'''
    return subject, text_body, html_body


def send_test_email(recipient):
    """使用已保存 SMTP 配置发送平台测试邮件。

    参数：`recipient` 为已经过接口校验的收件邮箱。
    返回：邮件后端成功接受消息时返回真；失败时抛出安全错误。
    副作用：连接外部 SMTP 服务并发送一封邮件。
    """
    config = _required_channel(
        notification_delivery_settings().get('email'),
        ('smtp_host', 'smtp_port', 'sender_email', 'username', 'password'),
        '发件箱邮箱',
    )
    security = str(config.get('security') or 'ssl').lower()
    connection = EmailBackend(
        host=config['smtp_host'],
        port=int(config['smtp_port']),
        username=config['username'],
        password=config['password'],
        use_tls=security == 'starttls',
        use_ssl=security == 'ssl',
        timeout=NOTIFICATION_TIMEOUT_SECONDS,
        fail_silently=False,
    )
    subject, text_body, html_body = _test_email_content(platform_name())
    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=config['sender_email'],
        to=[recipient],
        connection=connection,
    )
    message.attach_alternative(html_body, 'text/html')
    try:
        if message.send() != 1:
            raise NotificationSendError('测试邮件发送失败，请检查 SMTP 配置和网络连接')
    except NotificationSendError:
        raise
    except Exception as exc:
        raise NotificationSendError('测试邮件发送失败，请检查 SMTP 配置和网络连接') from exc
    return True


def _aliyun_percent_encode(value):
    """按阿里云 RPC 规范编码签名参数。

    参数：`value` 为待编码参数值。
    返回：保留波浪号且空格编码为百分号形式的字符串。
    """
    return quote(str(value), safe='~')


def _aliyun_signature(parameters, access_key_secret):
    """计算阿里云短信 RPC 请求的 HMAC-SHA1 签名。

    参数：`parameters` 为不含 Signature 的公共和业务参数，`access_key_secret` 为密钥。
    返回：Base64 编码后的阿里云请求签名。
    """
    canonical_query = '&'.join(
        f'{_aliyun_percent_encode(key)}={_aliyun_percent_encode(parameters[key])}'
        for key in sorted(parameters)
    )
    string_to_sign = f'POST&%2F&{_aliyun_percent_encode(canonical_query)}'
    digest = hmac.new(
        f'{access_key_secret}&'.encode('utf-8'),
        string_to_sign.encode('utf-8'),
        hashlib.sha1,
    ).digest()
    return base64.b64encode(digest).decode('ascii')


def _json_body(value):
    """将短信请求体编码为稳定、紧凑的 UTF-8 JSON。"""
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def _hmac_sha256(key, value):
    """返回 HMAC-SHA256 原始摘要，供云厂商签名链复用。"""
    return hmac.new(key, value.encode('utf-8'), hashlib.sha256).digest()


def _safe_provider_code(value):
    """过滤第三方错误码，避免手机号或响应正文进入平台错误信息。"""
    code = str(value or '').strip()
    allowed = code and len(code) <= 80 and all(character.isalnum() or character in '._-' for character in code)
    return code if allowed else 'UNKNOWN'


def _required_sms_config(config):
    """按服务商验证运行时发送所需配置并返回规范化服务商代码。"""
    if not isinstance(config, dict) or not config.get('enabled'):
        raise NotificationConfigurationError('短信网关尚未启用，请先完成配置并保存')
    provider = str(config.get('provider') or 'aliyun').strip().lower()
    fields = SMS_PROVIDER_REQUIRED_FIELDS.get(provider)
    if not fields:
        raise NotificationConfigurationError('短信服务商不受支持，请重新保存短信网关配置')
    if any(not str(config.get(field) or '').strip() for field in fields):
        raise NotificationConfigurationError(f'{SMS_PROVIDER_NAMES[provider]}短信配置不完整，请补充必填项后再测试')
    return provider


def _send_aliyun_sms(config, phone, code):
    """调用阿里云 SendSms，并仅传递 code 模板变量。"""
    parameters = {
        'AccessKeyId': config['access_key_id'],
        'Action': 'SendSms',
        'Format': 'JSON',
        'PhoneNumbers': phone,
        'RegionId': 'cn-hangzhou',
        'SignName': config['sign_name'],
        'SignatureMethod': 'HMAC-SHA1',
        'SignatureNonce': uuid.uuid4().hex,
        'SignatureVersion': '1.0',
        'TemplateCode': config['template_code'],
        'TemplateParam': _json_body({'code': code}),
        'Timestamp': datetime.now(datetime_timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'Version': '2017-05-25',
    }
    parameters['Signature'] = _aliyun_signature(parameters, config['access_key_secret'])
    response = requests.post(ALIYUN_SMS_ENDPOINT, data=parameters, timeout=NOTIFICATION_TIMEOUT_SECONDS)
    payload = response.json()
    result_code = payload.get('Code') if isinstance(payload, dict) else ''
    return response.ok and result_code == 'OK', result_code


def _tencent_authorization(secret_id, secret_key, timestamp, payload):
    """按腾讯云 TC3-HMAC-SHA256 规范生成短信请求认证头。"""
    host = 'sms.tencentcloudapi.com'
    date = datetime.fromtimestamp(timestamp, datetime_timezone.utc).strftime('%Y-%m-%d')
    canonical_headers = f'content-type:application/json; charset=utf-8\nhost:{host}\n'
    signed_headers = 'content-type;host'
    canonical_request = '\n'.join((
        'POST', '/', '', canonical_headers, signed_headers,
        hashlib.sha256(payload.encode('utf-8')).hexdigest(),
    ))
    credential_scope = f'{date}/sms/tc3_request'
    string_to_sign = '\n'.join((
        'TC3-HMAC-SHA256', str(timestamp), credential_scope,
        hashlib.sha256(canonical_request.encode('utf-8')).hexdigest(),
    ))
    secret_date = _hmac_sha256(f'TC3{secret_key}'.encode('utf-8'), date)
    secret_service = hmac.new(secret_date, b'sms', hashlib.sha256).digest()
    secret_signing = hmac.new(secret_service, b'tc3_request', hashlib.sha256).digest()
    signature = hmac.new(secret_signing, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()
    return (
        f'TC3-HMAC-SHA256 Credential={secret_id}/{credential_scope}, '
        f'SignedHeaders={signed_headers}, Signature={signature}'
    )


def _send_tencent_sms(config, phone, code):
    """调用腾讯云 SendSms，并把 code 作为唯一模板参数。"""
    body = _json_body({
        'PhoneNumberSet': [f'+86{phone}'],
        'SmsSdkAppId': config['sdk_app_id'],
        'SignName': config['sign_name'],
        'TemplateId': config['template_code'],
        'TemplateParamSet': [code],
    })
    timestamp = int(time.time())
    headers = {
        'Authorization': _tencent_authorization(
            config['secret_id'], config['secret_key'], timestamp, body,
        ),
        'Content-Type': 'application/json; charset=utf-8',
        'Host': 'sms.tencentcloudapi.com',
        'X-TC-Action': 'SendSms',
        'X-TC-Region': 'ap-guangzhou',
        'X-TC-Timestamp': str(timestamp),
        'X-TC-Version': '2021-01-11',
    }
    response = requests.post(
        TENCENT_SMS_ENDPOINT, data=body.encode('utf-8'), headers=headers,
        timeout=NOTIFICATION_TIMEOUT_SECONDS,
    )
    payload = response.json()
    result = payload.get('Response', {}) if isinstance(payload, dict) else {}
    error = result.get('Error') if isinstance(result, dict) else None
    statuses = result.get('SendStatusSet') if isinstance(result, dict) else None
    status_code = statuses[0].get('Code') if isinstance(statuses, list) and statuses else ''
    error_code = error.get('Code') if isinstance(error, dict) else status_code
    return response.ok and not error and status_code == 'Ok', error_code


def _baidu_authorization(access_key_id, access_key_secret, timestamp):
    """按百度 BCE Auth v1 规范生成短信 API Authorization。"""
    host = 'smsv3.bj.baidubce.com'
    expiration = 1800
    auth_prefix = f'bce-auth-v1/{access_key_id}/{timestamp}/{expiration}'
    canonical_headers = f'host:{host}\nx-bce-date:{quote(timestamp, safe="")}'
    canonical_request = '\n'.join((
        'POST', '/api/v3/sendSms', '', canonical_headers,
    ))
    signing_key = hmac.new(
        access_key_secret.encode('utf-8'), auth_prefix.encode('utf-8'), hashlib.sha256,
    ).hexdigest()
    signature = hmac.new(
        signing_key.encode('utf-8'), canonical_request.encode('utf-8'), hashlib.sha256,
    ).hexdigest()
    return f'{auth_prefix}/host;x-bce-date/{signature}'


def _send_baidu_sms(config, phone, code):
    """调用百度云 SMS v3，并只提交 code 内容变量。"""
    body = _json_body({
        'mobile': phone,
        'signatureId': config['signature_id'],
        'template': config['template_code'],
        'contentVar': {'code': code},
    })
    timestamp = datetime.now(datetime_timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    headers = {
        'Authorization': _baidu_authorization(
            config['access_key_id'], config['access_key_secret'], timestamp,
        ),
        'Content-Type': 'application/json; charset=utf-8',
        'Host': 'smsv3.bj.baidubce.com',
        'x-bce-date': timestamp,
    }
    response = requests.post(
        BAIDU_SMS_ENDPOINT, data=body.encode('utf-8'), headers=headers,
        timeout=NOTIFICATION_TIMEOUT_SECONDS,
    )
    payload = response.json()
    result_code = payload.get('code') if isinstance(payload, dict) else ''
    return response.ok and str(result_code) in {'0', '1000'}, result_code


def _send_upyun_sms(config, phone, code):
    """按又拍云模板短信 API 发送单个 code 位置变量。"""
    response = requests.post(
        UPYUN_SMS_ENDPOINT,
        data={'mobile': phone, 'template_id': config['template_code'], 'vars': code},
        headers={'Authorization': config['authorization_token']},
        timeout=NOTIFICATION_TIMEOUT_SECONDS,
    )
    payload = response.json() if response.content else {}
    result_code = payload.get('code') if isinstance(payload, dict) else response.status_code
    return response.ok, result_code


def _qiniu_authorization(access_key_id, access_key_secret, body):
    """按七牛管理 API v2 规范签名短信 JSON 请求。"""
    signing_data = (
        'POST /v1/message/single\n'
        'Host: sms.qiniuapi.com\n'
        'Content-Type: application/json\n\n'
        f'{body}'
    )
    digest = hmac.new(
        access_key_secret.encode('utf-8'), signing_data.encode('utf-8'), hashlib.sha1,
    ).digest()
    encoded = base64.urlsafe_b64encode(digest).decode('ascii').rstrip('=')
    return f'Qiniu {access_key_id}:{encoded}'


def _send_qiniu_sms(config, phone, code):
    """调用七牛云单条模板短信接口，并仅提交 code 参数。"""
    body = _json_body({
        'template_id': config['template_code'],
        'mobile': phone,
        'parameters': {'code': code},
    })
    headers = {
        'Authorization': _qiniu_authorization(
            config['access_key_id'], config['access_key_secret'], body,
        ),
        'Content-Type': 'application/json',
    }
    response = requests.post(
        QINIU_SMS_ENDPOINT, data=body.encode('utf-8'), headers=headers,
        timeout=NOTIFICATION_TIMEOUT_SECONDS,
    )
    payload = response.json() if response.content else {}
    if isinstance(payload, dict):
        result_code = payload.get('error') or payload.get('code') or response.status_code
    else:
        result_code = response.status_code
    return response.ok, result_code


def _send_yunpian_sms(config, phone, code):
    """调用云片模板短信 API，把 code 映射到模板的 #code# 变量。"""
    response = requests.post(
        YUNPIAN_SMS_ENDPOINT,
        data={
            'apikey': config['api_key'],
            'mobile': phone,
            'tpl_id': config['template_code'],
            'tpl_value': f'#code#={code}',
        },
        timeout=NOTIFICATION_TIMEOUT_SECONDS,
    )
    payload = response.json()
    result_code = payload.get('code') if isinstance(payload, dict) else ''
    return response.ok and str(result_code) == '0', result_code


def _send_netease_sms(config, phone, code):
    """调用网易云信模板短信 API，把 code 作为唯一模板参数。"""
    nonce = uuid.uuid4().hex
    current_time = str(int(time.time()))
    checksum = hashlib.sha1(
        f"{config['app_secret']}{nonce}{current_time}".encode('utf-8'),
    ).hexdigest()
    response = requests.post(
        NETEASE_SMS_ENDPOINT,
        data={
            'templateid': config['template_code'],
            'mobiles': _json_body([phone]),
            'params': _json_body([code]),
        },
        headers={
            'AppKey': config['app_key'],
            'Nonce': nonce,
            'CurTime': current_time,
            'CheckSum': checksum,
            'Content-Type': 'application/x-www-form-urlencoded;charset=utf-8',
        },
        timeout=NOTIFICATION_TIMEOUT_SECONDS,
    )
    payload = response.json()
    result_code = payload.get('code') if isinstance(payload, dict) else ''
    return response.ok and str(result_code) == '200', result_code


SMS_SENDERS = {
    'aliyun': _send_aliyun_sms,
    'tencent': _send_tencent_sms,
    'baidu': _send_baidu_sms,
    'upyun': _send_upyun_sms,
    'qiniu': _send_qiniu_sms,
    'yunpian': _send_yunpian_sms,
    'netease': _send_netease_sms,
}


@transaction.atomic
def _reserve_sms_dispatch(phone, purpose):
    """按数据库最新短信策略原子预占一次发送额度。

    参数：`phone` 为标准手机号；`purpose` 为 login 或 test。
    返回：待发送记录和行锁内读取的短信网关配置。
    副作用：锁定 notification.delivery 并新增一条不含手机号的发送记录。
    """
    setting = SystemSetting.objects.select_for_update().filter(key='notification.delivery').first()
    delivery = setting.value if setting and isinstance(setting.value, dict) else {}
    config = delivery.get('sms')
    provider = _required_sms_config(config)
    config = {**config, 'provider': provider}
    recipient_hash = phone_lookup_hash(phone)
    now = timezone.now()
    windows = (
        ('recipient_limit_per_minute', '每分钟', now - timedelta(minutes=1)),
        ('recipient_limit_per_hour', '每小时', now - timedelta(hours=1)),
        ('recipient_limit_per_day', '每天', now - timedelta(days=1)),
    )
    for field, label, threshold in windows:
        try:
            limit = max(1, int(config.get(field) or 1))
        except (TypeError, ValueError):
            limit = 1
        used = SmsDispatchRecord.objects.filter(
            recipient_hash=recipient_hash,
            status__in=['pending', 'sent'],
            created_at__gte=threshold,
        ).count()
        if used >= limit:
            raise NotificationRateLimitError(f'该手机号短信发送次数已达到{label}上限，请稍后再试')
    record = SmsDispatchRecord.objects.create(
        recipient_hash=recipient_hash,
        purpose=purpose,
        status='pending',
    )
    return record, config


def send_sms(phone, template_parameters, purpose):
    """使用已保存的服务商模板发送验证码短信。

    参数：`phone` 为标准手机号；`template_parameters` 为模板变量；`purpose` 为发送用途。
    返回：短信服务商接受请求时返回真；失败时只抛出不含敏感上下文的错误。
    副作用：占用动态发送额度、调用当前短信服务商接口并更新发送状态。
    """
    record, config = _reserve_sms_dispatch(phone, purpose)
    provider = config['provider']
    provider_name = SMS_PROVIDER_NAMES[provider]
    code = str((template_parameters or {}).get('code') or '').strip()
    if not code:
        record.status = 'failed'
        record.save(update_fields=['status', 'updated_at'])
        raise NotificationConfigurationError('短信验证码不能为空')
    try:
        success, provider_code = SMS_SENDERS[provider](config, phone, code)
    except (requests.RequestException, ValueError) as exc:
        record.status = 'failed'
        record.save(update_fields=['status', 'updated_at'])
        raise NotificationSendError(f'{provider_name}短信发送失败，请检查网络连接和短信配置') from exc
    if not success:
        record.status = 'failed'
        record.save(update_fields=['status', 'updated_at'])
        safe_code = _safe_provider_code(provider_code)
        raise NotificationSendError(
            f'{provider_name}短信发送失败（{safe_code}），请检查签名、模板、账号权限和余额',
        )
    record.status = 'sent'
    record.save(update_fields=['status', 'updated_at'])
    return True


def send_test_sms(phone):
    """使用登录模板和固定演示变量发送测试短信。

    参数：`phone` 为标准化后的中国大陆手机号。
    返回：当前服务商接受短信时返回真。
    副作用：调用统一短信发送服务并占用该手机号的动态发送额度。
    """
    return send_sms(phone, {'code': '123456'}, 'test')


def send_login_sms(phone, code):
    """使用当前短信服务商的登录模板发送一次六位验证码。

    参数：`phone` 为标准手机号；`code` 为仅本次挑战使用的六位验证码。
    返回：当前服务商接受短信时返回真。
    副作用：调用统一短信发送服务并产生短信费用，不保存或记录验证码。
    """
    return send_sms(phone, {'code': str(code)}, 'login')
