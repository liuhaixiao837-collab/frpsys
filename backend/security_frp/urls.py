from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views


router = DefaultRouter()
router.register('security/frp/servers', views.FrpServerViewSet, basename='frp-server')
router.register('security/frp/agents', views.FrpAgentViewSet, basename='frp-agent')
router.register('security/frp/proxies', views.FrpProxyViewSet, basename='frp-proxy')
router.register('security/frp/heartbeats', views.FrpHeartbeatViewSet, basename='frp-heartbeat')
router.register('security/frp/audits', views.FrpAuditViewSet, basename='frp-audit')

urlpatterns = [
    path('security/frp/reports/', views.frp_report_center, name='frp-report-center'),
    path('security/frp/traffic-reports/', views.frp_traffic_report, name='frp-traffic-report'),
    path('security/frp/agent-register/', views.agent_register, name='frp-agent-register'),
    path('security/frp/agent-heartbeat/', views.agent_heartbeat, name='frp-agent-heartbeat'),
    path('security/frp/agent-config/', views.agent_config, name='frp-agent-config'),
    path('', include(router.urls)),
]
