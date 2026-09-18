from django.conf import settings
from django.conf.urls.static import static
from django.http import Http404
from django.urls import include, path, re_path
from django.views.static import serve
from rest_framework.routers import DefaultRouter

from ops import views
from platform_logs import views as log_views


router = DefaultRouter()
router.register('users', views.UserViewSet)
router.register('orgs', views.OrganizationViewSet)
router.register('departments', views.OrganizationViewSet, basename='department')
router.register('roles', views.RoleViewSet)
router.register('permission-policies', views.PermissionPolicyViewSet)
router.register('user-logs', log_views.UserLogViewSet, basename='user-log')
router.register('system-logs', log_views.SystemLogViewSet, basename='system-log')
router.register('settings', views.SystemSettingViewSet)


def frontend_app(request, path=''):
    """返回前端单页应用入口文件，使浏览器路由可由前端接管。

    参数：`request` 表示当前请求对象；`path` 表示该步骤所需的path 参数。
    返回：返回该业务步骤生成、查询或校验后的结果。
    副作用：不直接修改持久化数据。
    """
    if path.startswith(('api/', 'uploads/', 'assets/', 'ws/')):
        raise Http404()
    return serve(request, 'index.html', document_root=settings.FRONT_DIST_DIR)


urlpatterns = [
    path('api/v1/auth/captcha', views.CaptchaView.as_view()),
    path('api/v1/auth/slider-captcha', views.SliderCaptchaView.as_view()),
    path('api/v1/auth/login', views.LoginView.as_view()),
    path('api/v1/auth/sms-login/send', views.SmsLoginSendView.as_view()),
    path('api/v1/auth/sms-login/verify', views.SmsLoginVerifyView.as_view()),
    path('api/v1/auth/otp/setup', views.OtpSetupView.as_view()),
    path('api/v1/auth/otp/confirm', views.OtpConfirmView.as_view()),
    path('api/v1/auth/otp/verify', views.OtpVerifyView.as_view()),
    path('api/v1/auth/password-reset/start', views.PasswordResetStartView.as_view()),
    path('api/v1/auth/password-reset/verify-otp', views.PasswordResetOtpView.as_view()),
    path('api/v1/auth/password-reset/complete', views.PasswordResetCompleteView.as_view()),
    path('api/v1/auth/refresh', views.RefreshView.as_view()),
    path('api/v1/auth/logout', views.LogoutView.as_view()),
    path('api/v1/auth/switch-org', views.SwitchOrganizationView.as_view()),
    path('api/v1/public/platform', views.PublicPlatformSettingsView.as_view()),
    path('api/v1/public/navigation', views.PublicNavigationView.as_view()),
    path('api/v1/me', views.MeView.as_view()),
    path('api/v1/permission-catalog', views.PermissionCatalogView.as_view()),
    path('api/v1/users/password-policy/', views.UserPasswordPolicyView.as_view()),
    path('api/v1/user-report/', views.UserReportView.as_view()),
    path('api/v1/users/import/template/', views.UserImportTemplateView.as_view()),
    path('api/v1/users/import/precheck/', views.UserImportPrecheckView.as_view()),
    path('api/v1/users/import/confirm/', views.UserImportConfirmView.as_view()),
    path('api/v1/menu-order/', views.MenuOrderView.as_view()),
    path('api/v1/system-status/', views.SystemStatusView.as_view()),
    path('api/v1/system-tools/ping/', views.SystemToolPingView.as_view()),
    path('api/v1/system-tools/telnet/', views.SystemToolTelnetView.as_view()),
    path('api/v1/system-tools/curl/', views.SystemToolCurlView.as_view()),
    path('api/v1/system-tools/traceroute/', views.SystemToolTracerouteView.as_view()),
    path('api/v1/system-tools/mtr/', views.SystemToolMtrView.as_view()),
    path('api/v1/system-settings/platform/logo-upload/', views.PlatformLogoUploadView.as_view()),
    path('api/v1/system-settings/notification/test/email/', views.NotificationEmailTestView.as_view()),
    path('api/v1/system-settings/notification/test/sms/', views.NotificationSmsTestView.as_view()),
    path('api/v1/system-settings/llm/test/', views.LlmProviderTestView.as_view()),
    path(
        'api/v1/system-settings/<str:category>/<str:key>/',
        views.SystemSettingDetailView.as_view(),
    ),
    path(
        'api/v1/system-settings/<str:category>/<str:key>/reveal',
        views.SystemSettingRevealView.as_view(),
    ),
    path('api/v1/', include(router.urls)),
    path('api/v1/', include('security_frp.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += [
        path('', frontend_app),
        path('assets/<path:path>', serve, {'document_root': settings.FRONT_DIST_DIR + '/assets'}),
        re_path(r'^(?P<path>(?!api/|uploads/|assets/|ws/).*)$', frontend_app),
    ]
