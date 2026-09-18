from rest_framework.permissions import BasePermission, SAFE_METHODS

from .permission_catalog import action_code, page_code_for_path, required_codes_for_page
from .permission_service import has_permission, is_permission_admin


API_PAGE_ALIASES = [
    ('/users', 'page.admin_users.view'),
    ('/roles', 'page.admin_users.view'),
    ('/orgs', 'page.admin_departments.view'),
    ('/departments', 'page.admin_departments.view'),
    ('/permission-policies', 'page.permission_policies.view'),
    ('/permission-catalog', 'page.permission_policies.view'),
    ('/user-logs', 'page.logs.users.view'),
    ('/system-logs', 'page.logs.system.view'),
    ('/system-settings', 'page.settings.view'),
    ('/system-tools', 'page.system_tools.view'),
    ('/settings', 'page.settings.view'),
    ('/security/frp/servers', 'page.security.frp_servers.view'),
    ('/security/frp/agents', 'page.security.frp_agents.view'),
    ('/security/frp/proxies', 'page.security.frp_proxies.view'),
    ('/security/frp/heartbeats', 'page.security.frp_agents.view'),
    ('/security/frp/audits', 'page.security.frp_audits.view'),
    ('/security/frp/reports', 'page.security.frp_reports.view'),
    ('/security/frp/traffic-reports', 'page.security.frp_traffic_reports.view'),
]


def user_organization(user):
    """返回当前用户档案中的所属组织。"""
    profile = getattr(user, 'profile', None)
    return getattr(profile, 'organization', None) if profile else None


class RoleBasedPermission(BasePermission):
    """按数据库权限策略校验平台页面访问和具体业务操作。"""

    message = '没有该功能权限，请联系管理员在用户管理的权限策略中授权。'

    def _normalized_path(self, request):
        """移除 API 前缀和末尾斜线，得到稳定的权限匹配路径。"""
        path = getattr(request, 'path', '')
        if path.startswith('/api/v1'):
            path = path.removeprefix('/api/v1')
        return path.rstrip('/') or '/'

    def _page_code(self, request, view):
        """根据显式声明、接口别名和数据库路由定位页面权限。"""
        explicit = getattr(view, 'permission_code', '')
        if explicit:
            return explicit
        path = self._normalized_path(request)
        for prefix, code in sorted(API_PAGE_ALIASES, key=lambda item: len(item[0]), reverse=True):
            if path == prefix or path.startswith(f'{prefix}/'):
                return code
        return page_code_for_path(path)

    def _setting_write_action(self, request, view):
        """区分按键写入平台设置时的新增和编辑操作。"""
        category = (getattr(view, 'kwargs', {}) or {}).get('category')
        key = (getattr(view, 'kwargs', {}) or {}).get('key')
        if not category or not key:
            return 'update'
        from .models import SystemSetting
        return 'update' if SystemSetting.objects.filter(key=f'{category}.{key}').exists() else 'create'

    def _action_name(self, request, view):
        """把平台 DRF 动作和自定义接口转换为数据库操作权限代码。"""
        action = (getattr(view, 'action', '') or '').replace('-', '_')
        path = self._normalized_path(request)

        if path.startswith('/system-settings/') and path.endswith('/reveal'):
            return 'reveal'
        if path == '/system-settings/platform/logo-upload':
            return 'update'
        if path == '/system-settings/notification/test/email':
            return 'test_email'
        if path == '/system-settings/notification/test/sms':
            return 'test_sms'
        if path == '/system-settings/llm/test':
            return 'update'
        if path == '/system-tools/ping':
            return 'ping'
        if path == '/system-tools/telnet':
            return 'telnet'
        if path == '/system-tools/curl':
            return 'curl'
        if path == '/system-tools/traceroute':
            return 'traceroute'
        if path == '/system-tools/mtr':
            return 'mtr'
        if path.startswith('/users/import/'):
            return 'import'
        if path.startswith('/system-settings/') and request.method == 'PUT':
            return self._setting_write_action(request, view)
        if path.startswith('/system-settings/') and request.method == 'DELETE':
            return 'delete'
        if action == 'clone':
            return 'create'
        if action in {'members', 'remove_member'} and request.method not in SAFE_METHODS:
            return 'update'
        if action in {'disable', 'enable'}:
            return 'disable'
        return self._standard_action(request, action)

    def _standard_action(self, request, action):
        """将标准 REST 方法和动作转换为查看、新增、编辑或删除。"""
        if request.method in SAFE_METHODS and action in {'', 'list', 'retrieve'}:
            return 'view'
        if action == 'create':
            return 'create'
        if action in {'update', 'partial_update'}:
            return 'update'
        if action == 'destroy':
            return 'delete'
        if action:
            return action
        return {
            'POST': 'create',
            'PUT': 'update',
            'PATCH': 'update',
            'DELETE': 'delete',
        }.get(request.method, 'view')

    def has_permission(self, request, view):
        """要求用户同时具备菜单组、页面和具体非查看操作权限。"""
        if not request.user or not request.user.is_authenticated:
            return False
        if is_permission_admin(request.user):
            return True

        page_code = self._page_code(request, view)
        if not page_code:
            return False
        for code in required_codes_for_page(page_code):
            if not has_permission(request.user, code):
                return False

        action_name = self._action_name(request, view)
        if action_name == 'view':
            return True
        return has_permission(request.user, action_code(page_code, action_name))


class AdminOnlyPermission(BasePermission):
    """超级管理员直接放行，普通用户仍按数据库功能策略校验。"""

    message = '没有该管理权限，请联系管理员授权。'

    def has_permission(self, request, view):
        """校验登录状态后复用统一的数据库权限策略。"""
        if not request.user or not request.user.is_authenticated:
            return False
        if is_permission_admin(request.user):
            return True
        return RoleBasedPermission().has_permission(request, view)
