from django.urls import path
from rest_framework.routers import DefaultRouter

from ops import views

router = DefaultRouter()
router.register('users', views.UserViewSet)
router.register('orgs', views.OrganizationViewSet)
router.register('departments', views.OrganizationViewSet, basename='department')
router.register('roles', views.RoleViewSet)

urlpatterns = [
    path('auth/captcha', views.CaptchaView.as_view()),
    path('auth/login', views.LoginView.as_view()),
    path('auth/register', views.RegisterView.as_view()),
    path('auth/refresh', views.RefreshView.as_view()),
    path('auth/logout', views.LogoutView.as_view()),
    path('auth/switch-org', views.SwitchOrganizationView.as_view()),
    path('me', views.MeView.as_view()),
    *router.urls,
]
