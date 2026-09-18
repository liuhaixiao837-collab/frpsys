from copy import deepcopy
from urllib.parse import urlsplit, urlunsplit

import requests


LLM_PROVIDER_DEFINITIONS = {
    'deepseek': {
        'name': '深度求索',
        'model': 'deepseek-v4',
        'base_url': 'https://api.deepseek.com/v1',
        'priority': 10,
        'description': 'DeepSeek 通用大语言模型服务。',
        'hosts': {'api.deepseek.com'},
    },
    'qwen': {
        'name': '通义千问',
        'model': 'qwen-plus',
        'base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
        'priority': 20,
        'description': '阿里云百炼通义千问模型服务。',
        'hosts': {'dashscope.aliyuncs.com'},
    },
    'glm': {
        'name': '智谱清言',
        'model': 'glm-4.5',
        'base_url': 'https://open.bigmodel.cn/api/paas/v4',
        'priority': 30,
        'description': '智谱 AI GLM 系列模型服务。',
        'hosts': {'open.bigmodel.cn'},
    },
    'kimi': {
        'name': '月之暗面',
        'model': 'kimi-k2-turbo-preview',
        'base_url': 'https://api.moonshot.cn/v1',
        'priority': 40,
        'description': 'Moonshot AI Kimi 系列模型服务。',
        'hosts': {'api.moonshot.cn'},
    },
    'openai': {
        'name': 'OpenAI',
        'model': 'gpt-5.6',
        'base_url': 'https://api.openai.com/v1',
        'priority': 50,
        'description': 'OpenAI GPT 系列模型服务。',
        'hosts': {'api.openai.com'},
    },
    'mimo': {
        'name': '小米 MiMo',
        'model': 'MiMo-V2.5',
        'base_url': 'https://api.xiaomimimo.com/v1',
        'priority': 60,
        'description': '小米 MiMo 系列模型服务。',
        'hosts': {'api.xiaomimimo.com'},
    },
}


class LlmConfigurationError(Exception):
    """表示 LLM 厂商配置缺失或不符合调用要求。"""


class LlmConnectionError(Exception):
    """表示 LLM 厂商网络、鉴权或模型检测失败。"""


def default_llm_settings():
    """返回六家内置 LLM 厂商的完整初始配置。"""
    providers = []
    for code, definition in LLM_PROVIDER_DEFINITIONS.items():
        providers.append({
            'name': definition['name'],
            'code': code,
            'model': definition['model'],
            'priority': definition['priority'],
            'enabled': False,
            'api_key': '',
            'base_url': definition['base_url'],
            'status': 'unchecked',
            'last_checked_at': '',
            'description': definition['description'],
        })
    return {'providers': providers}


def normalize_provider_base_url(code, value):
    """校验厂商官方 HTTPS 地址并返回去除尾斜杠的标准地址。"""
    definition = LLM_PROVIDER_DEFINITIONS.get(code)
    if not definition:
        raise ValueError('不支持的 LLM 厂商')
    text = str(value or definition['base_url']).strip()
    if len(text) > 500:
        raise ValueError('接口地址不能超过 500 个字符')
    parsed = urlsplit(text)
    if parsed.scheme != 'https' or not parsed.hostname:
        raise ValueError('接口地址必须是 HTTPS 完整地址')
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('接口地址不能包含凭据、查询参数或锚点')
    if parsed.hostname.lower() not in definition['hosts']:
        raise ValueError(f"{definition['name']}仅允许使用官方接口地址")
    path = parsed.path.rstrip('/')
    return urlunsplit(('https', parsed.netloc.lower(), path, '', ''))


def provider_for_code(settings_value, code):
    """从平台设置中读取指定厂商配置，不存在时返回空值。"""
    if not isinstance(settings_value, dict):
        return None
    providers = settings_value.get('providers', [])
    if not isinstance(providers, list):
        return None
    return next((item for item in providers if isinstance(item, dict) and item.get('code') == code), None)


def update_provider_status(settings_value, code, provider_status, checked_at):
    """复制 LLM 配置并更新单个厂商的检测状态和时间。"""
    updated = deepcopy(settings_value)
    provider = provider_for_code(updated, code)
    if not provider:
        raise LlmConfigurationError('请先保存该 LLM 厂商配置')
    provider['status'] = provider_status
    provider['last_checked_at'] = checked_at
    return updated


def test_llm_provider(provider):
    """按 OpenAI 兼容协议向指定厂商发送最小化连通性请求。"""
    if not isinstance(provider, dict):
        raise LlmConfigurationError('LLM 厂商配置不存在')
    code = str(provider.get('code') or '').strip().lower()
    if code not in LLM_PROVIDER_DEFINITIONS:
        raise LlmConfigurationError('不支持的 LLM 厂商')
    api_key = str(provider.get('api_key') or '').strip()
    model = str(provider.get('model') or '').strip()
    if not api_key or not model:
        raise LlmConfigurationError('请先填写 API Key 和模型名称')
    try:
        base_url = normalize_provider_base_url(code, provider.get('base_url'))
    except ValueError as exc:
        raise LlmConfigurationError(str(exc)) from exc

    payload = {
        'model': model,
        'messages': [{'role': 'user', 'content': 'Reply with OK only.'}],
        'temperature': 0,
    }
    if code == 'openai':
        payload['max_completion_tokens'] = 8
    else:
        payload['max_tokens'] = 8
    try:
        response = requests.post(
            f'{base_url}/chat/completions',
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            json=payload,
            timeout=(3.05, 15),
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise LlmConnectionError('连接模型服务失败，请检查网络和接口地址') from exc

    if response.status_code == 200:
        return True
    if response.status_code in {401, 403}:
        raise LlmConnectionError('模型服务鉴权失败，请检查 API Key')
    if response.status_code == 404:
        raise LlmConnectionError('模型或接口地址不可用，请检查模型名称')
    if response.status_code == 429:
        raise LlmConnectionError('模型服务额度不足或请求受限')
    raise LlmConnectionError('模型服务暂不可用，请稍后重试')
