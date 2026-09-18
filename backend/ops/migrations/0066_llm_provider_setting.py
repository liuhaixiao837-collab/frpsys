from django.db import migrations


DEFAULT_PROVIDERS = [
    {
        'name': '深度求索', 'code': 'deepseek', 'model': 'deepseek-v4', 'priority': 10,
        'enabled': False, 'api_key': '', 'base_url': 'https://api.deepseek.com/v1',
        'status': 'unchecked', 'last_checked_at': '', 'description': 'DeepSeek 通用大语言模型服务。',
    },
    {
        'name': '通义千问', 'code': 'qwen', 'model': 'qwen-plus', 'priority': 20,
        'enabled': False, 'api_key': '', 'base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
        'status': 'unchecked', 'last_checked_at': '', 'description': '阿里云百炼通义千问模型服务。',
    },
    {
        'name': '智谱清言', 'code': 'glm', 'model': 'glm-4.5', 'priority': 30,
        'enabled': False, 'api_key': '', 'base_url': 'https://open.bigmodel.cn/api/paas/v4',
        'status': 'unchecked', 'last_checked_at': '', 'description': '智谱 AI GLM 系列模型服务。',
    },
    {
        'name': '月之暗面', 'code': 'kimi', 'model': 'kimi-k2-turbo-preview', 'priority': 40,
        'enabled': False, 'api_key': '', 'base_url': 'https://api.moonshot.cn/v1',
        'status': 'unchecked', 'last_checked_at': '', 'description': 'Moonshot AI Kimi 系列模型服务。',
    },
    {
        'name': 'OpenAI', 'code': 'openai', 'model': 'gpt-5.6', 'priority': 50,
        'enabled': False, 'api_key': '', 'base_url': 'https://api.openai.com/v1',
        'status': 'unchecked', 'last_checked_at': '', 'description': 'OpenAI GPT 系列模型服务。',
    },
    {
        'name': '小米 MiMo', 'code': 'mimo', 'model': 'MiMo-V2.5', 'priority': 60,
        'enabled': False, 'api_key': '', 'base_url': 'https://api.xiaomimimo.com/v1',
        'status': 'unchecked', 'last_checked_at': '', 'description': '小米 MiMo 系列模型服务。',
    },
]


def create_llm_setting(apps, schema_editor):
    """为升级后的平台创建六家内置 LLM 厂商初始配置。"""
    SystemSetting = apps.get_model('ops', 'SystemSetting')
    SystemSetting.objects.get_or_create(
        key='llm.providers',
        defaults={
            'value': {'providers': DEFAULT_PROVIDERS},
            'description': '平台大语言模型厂商配置',
        },
    )


def remove_llm_setting(apps, schema_editor):
    """回滚迁移时移除由本迁移创建的 LLM 设置。"""
    SystemSetting = apps.get_model('ops', 'SystemSetting')
    SystemSetting.objects.filter(key='llm.providers').delete()


class Migration(migrations.Migration):
    dependencies = [('ops', '0065_platform_tools_page')]

    operations = [migrations.RunPython(create_llm_setting, remove_llm_setting)]
