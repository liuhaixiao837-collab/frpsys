import re
from copy import deepcopy

from django.db.models import Max, Prefetch


ROOT_MENU_ORDER_KEY = '__root__'


def catalog_signature():
    """返回随数据库菜单或操作变化而变化的权限目录缓存签名。

    参数：无。
    返回：返回该业务步骤生成、查询或校验后的结果。
    副作用：只读取数据库，不修改持久化数据。
    """
    from .models import PermissionMenuAction, PermissionMenuNode

    node_stats = PermissionMenuNode.objects.aggregate(updated=Max('updated_at'))
    action_stats = PermissionMenuAction.objects.aggregate(updated=Max('updated_at'))
    return (
        PermissionMenuNode.objects.count(),
        node_stats['updated'].isoformat() if node_stats['updated'] else '',
        PermissionMenuAction.objects.count(),
        action_stats['updated'].isoformat() if action_stats['updated'] else '',
    )
def _node_payload(node):
    """把数据库菜单节点转换为前端和权限策略共用的结构。"""
    return {
        'code': node.code,
        'name': node.name,
        'path': node.path,
        'icon': node.icon,
        'sidebar': node.sidebar,
        'aliases': node.aliases if isinstance(node.aliases, list) else [],
        'actions': [
            {
                'code': action.code,
                'name': action.name,
            }
            for action in node.actions.all() if action.is_active
        ],
        'children': [],
    }


def catalog_tree():
    """从数据库读取启用节点和操作并组装菜单树。"""
    from .models import PermissionMenuAction, PermissionMenuNode

    action_queryset = PermissionMenuAction.objects.filter(is_active=True).order_by('sort_order', 'id')
    nodes = list(
        PermissionMenuNode.objects.filter(is_active=True)
        .prefetch_related(Prefetch('actions', queryset=action_queryset))
        .order_by('sort_order', 'id')
    )
    payload_by_id = {node.id: _node_payload(node) for node in nodes}
    groups = []
    for node in nodes:
        payload = payload_by_id[node.id]
        if node.parent_id and node.parent_id in payload_by_id:
            payload_by_id[node.parent_id]['children'].append(payload)
        elif node.node_type == 'group':
            groups.append({
                'code': payload['code'],
                'name': payload['name'],
                'icon': payload['icon'],
                'path': payload['path'],
                'pages': payload['children'],
            })
    return deepcopy(groups)


def _sort_by_codes(items, codes):
    """按个人代码顺序排列同级菜单，并把后续新增项接在默认顺序末尾。

    参数：`items` 表示同级菜单数据；`codes` 表示用户保存的菜单代码顺序。
    返回：返回应用个人偏好后的同级菜单列表。
    副作用：不直接修改持久化数据。
    """
    positions = {code: index for index, code in enumerate(codes or [])}
    defaults = {item['code']: index for index, item in enumerate(items)}
    return sorted(items, key=lambda item: (positions.get(item['code'], len(positions) + defaults[item['code']])))


def navigation_tree_for_user(user):
    """返回应用当前用户一级和各级子菜单排序偏好的数据库导航树。

    参数：`user` 表示请求导航的平台用户，匿名用户使用数据库默认顺序。
    返回：返回仅调整同级展示顺序后的导航树。
    副作用：只读取数据库，不修改持久化数据。
    """
    tree = catalog_tree()
    if not user or not getattr(user, 'is_authenticated', False):
        return tree
    from .models import UserMenuOrderPreference

    preference = UserMenuOrderPreference.objects.filter(user=user).first()
    order_data = preference.order_data if preference and isinstance(preference.order_data, dict) else {}

    def sort_children(parent_code, children):
        """递归应用指定父级下的个人菜单顺序。"""
        ordered = _sort_by_codes(children, order_data.get(parent_code, []))
        for child in ordered:
            child['children'] = sort_children(child['code'], child.get('children', []))
        return ordered

    tree = _sort_by_codes(tree, order_data.get(ROOT_MENU_ORDER_KEY, []))
    for group in tree:
        group['pages'] = sort_children(group['code'], group.get('pages', []))
    return tree


def menu_order_items_for_user(user):
    """返回当前用户有权访问并可在排序页面调整的层级菜单数据。

    参数：`user` 表示读取排序偏好的平台用户。
    返回：超级管理员返回全部启用菜单；普通用户只返回有效权限覆盖的主菜单和子菜单。
    副作用：只读取数据库，不修改持久化数据。
    """
    from .permission_service import effective_permission_codes, is_permission_admin

    allowed_codes = None if is_permission_admin(user) else set(effective_permission_codes(user))

    def page_item(page):
        """递归过滤无权访问的页面，并精简为排序页面需要的字段。

        参数：`page` 表示数据库导航树中的当前页面或子菜单节点。
        返回：有权访问时返回排序节点，无权访问或无可见子项时返回空值。
        副作用：不修改导航树或用户偏好。
        """
        if allowed_codes is not None and page['code'] not in allowed_codes:
            return None
        children = [
            child_item
            for child in page.get('children', [])
            if (child_item := page_item(child)) is not None
        ]
        if page['code'].startswith('menu.') and not children:
            return None
        return {
            'code': page['code'],
            'name': page['name'],
            'children': children,
        }

    items = []
    for group in navigation_tree_for_user(user):
        if allowed_codes is not None and group['code'] not in allowed_codes:
            continue
        children = [
            item
            for page in group.get('pages', [])
            if (item := page_item(page)) is not None
        ]
        if not children:
            continue
        items.append({
            'code': group['code'],
            'name': group['name'],
            'children': children,
        })
    return items


def navigation_payload_for_user(user):
    """返回应用个人排序后的数据库导航接口载荷。

    参数：`user` 表示当前请求用户。
    返回：返回导航菜单及数据库来源标识。
    副作用：只读取数据库，不修改持久化数据。
    """
    return {'items': navigation_tree_for_user(user), 'source': 'database'}


def _iter_pages(pages, parents=None):
    """深度遍历页面节点并同时返回父级权限链。"""
    for page in pages:
        chain = [*(parents or []), page['code']]
        yield page, chain
        yield from _iter_pages(page.get('children', []), chain)


def _iter_permissions(groups):
    """把菜单树展开为菜单、页面和操作权限清单。"""
    for group in groups:
        yield {'code': group['code'], 'name': group['name'], 'type': 'menu', 'path': ''}
        for page, _chain in _iter_pages(group['pages'], [group['code']]):
            item_type = 'menu' if page['code'].startswith('menu.') else 'page'
            yield {'code': page['code'], 'name': page['name'], 'type': item_type, 'path': page.get('path', '')}
            prefix = page['code'].removesuffix('.view')
            for action in page.get('actions', []):
                yield {
                    'code': f'{prefix}.{action["code"]}',
                    'name': f'{page["name"]}-{action["name"]}',
                    'type': 'action',
                    'path': page.get('path', ''),
                }


def iter_permissions():
    """迭代当前数据库目录中的全部有效权限。"""
    yield from _iter_permissions(catalog_tree())


def all_permission_codes():
    """返回当前数据库目录中的全部有效权限代码。"""
    return [item['code'] for item in iter_permissions()]


def _path_matches(configured_path, requested_path):
    """匹配静态路由或包含动态参数的配置路由。"""
    configured = (configured_path or '').rstrip('/') or '/'
    requested = (requested_path or '').rstrip('/') or '/'
    if ':' in configured:
        pattern = re.sub(r':[A-Za-z_][A-Za-z0-9_]*', r'[^/]+', re.escape(configured).replace(r'\:', ':'))
        return bool(re.fullmatch(pattern, requested))
    return requested == configured or (configured != '/' and requested.startswith(f'{configured}/'))


def page_code_for_path(path):
    """按最长路由匹配规则查找前端路径对应的页面权限。"""
    if not path:
        return ''
    best = ''
    best_len = -1
    for group in catalog_tree():
        for page, _chain in _iter_pages(group['pages'], [group['code']]):
            if page['code'].startswith('menu.'):
                continue
            candidates = [page.get('path', '')] + [alias.get('path', '') for alias in page.get('aliases', [])]
            for candidate in candidates:
                if candidate and _path_matches(candidate, path) and len(candidate) > best_len:
                    best = page['code']
                    best_len = len(candidate)
    return best


def parent_codes_for_permission(code):
    """返回权限项所属的菜单组权限代码。"""
    if not code:
        return []
    page_code = code
    if not code.endswith('.view'):
        parts = code.split('.')
        if len(parts) > 2:
            page_code = '.'.join(parts[:-1]) + '.view'
    for group in catalog_tree():
        for page, chain in _iter_pages(group['pages'], [group['code']]):
            if page['code'] == page_code or page['code'] == code:
                return [item for item in chain[:-1] if item.startswith('menu.')]
    return []


def required_codes_for_page(page_code):
    """返回访问页面必须同时具备的菜单组和页面权限。"""
    if not page_code:
        return []
    return [*parent_codes_for_permission(page_code), page_code]


def required_codes_for_permission(code):
    """返回指定权限代码对应的菜单、页面和操作完整权限链。"""
    if not code:
        return []
    permission = next((item for item in iter_permissions() if item['code'] == code), None)
    if not permission:
        return []
    if permission['type'] == 'action':
        parts = code.split('.')
        page_code = '.'.join(parts[:-1]) + '.view'
        return [*required_codes_for_page(page_code), code]
    return [*parent_codes_for_permission(code), code]


def action_code(page_code, action):
    """由页面权限和操作名生成完整操作权限代码。"""
    if not page_code:
        return ''
    return f'{page_code.removesuffix(".view")}.{action}'


def catalog_payload():
    """返回菜单树、平铺权限和数据来源标识。"""
    tree = catalog_tree()
    flat = list(_iter_permissions(tree))
    return {
        'items': tree,
        'flat': flat,
        'all_codes': [item['code'] for item in flat],
        'source': 'database',
    }
