from rest_framework import serializers


LOCAL_ASSET_PREFIXES = ('/assets/', '/uploads/')


def normalize_local_asset_path(value, *, raise_error=False):
    """校验并规范化本地静态资源路径，拒绝外网地址。

    参数：`value` 表示待处理的输入值；`raise_error` 表示该步骤所需的raise_error 参数。
    返回：返回该业务步骤生成、查询或校验后的结果。
    副作用：不直接修改持久化数据。
    """
    path = str(value or '').strip()
    if not path:
        return ''
    valid = (
        path.startswith(LOCAL_ASSET_PREFIXES)
        and not path.startswith('//')
        and '\\' not in path
        and '..' not in path.split('/')
    )
    if valid:
        return path
    if raise_error:
        raise serializers.ValidationError('只能使用 /assets/ 或 /uploads/ 下的本地资源路径，禁止引用外网地址')
    return ''

