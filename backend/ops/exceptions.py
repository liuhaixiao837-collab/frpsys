from rest_framework.views import exception_handler


def ongrid_exception_handler(exc, context):
    """将后端异常转换为统一且用户友好的接口错误结构。

    参数：`exc` 表示该步骤所需的exc 参数；`context` 表示该步骤所需的context 参数。
    返回：返回该业务步骤生成、查询或校验后的结果。
    副作用：不直接修改持久化数据。
    """
    response = exception_handler(exc, context)
    if response is None:
        return response

    detail = response.data
    if isinstance(detail, dict) and set(detail.keys()) == {'detail'}:
        message = detail['detail']
    else:
        message = detail
    response.data = {
        'status': response.status_code,
        'detail': message,
        'path': context.get('request').path if context.get('request') else '',
    }
    return response

