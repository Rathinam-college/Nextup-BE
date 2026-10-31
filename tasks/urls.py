from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    DepartmentViewSet, UserViewSet, TaskViewSet,
    TaskCommentViewSet, NotificationViewSet,
    DispatchedEmailLogViewSet, ActivityLogViewSet,
    SelfTaskViewSet, SelfNoteViewSet,
    list_personas, current_user_me, dashboard_stats,
    login_user, logout_user,
    backup_database_sql, backup_database_json,
    restore_database_sql, restore_database_json,
    admin_system_stats, clear_database, get_email_status, send_test_email,
    update_email_settings, get_app_version,
    register_device, test_push_notification, admin_user_sessions, ping_user_activity
)

router = DefaultRouter()
router.register(r'departments', DepartmentViewSet, basename='department')
router.register(r'users', UserViewSet, basename='user')
router.register(r'tasks', TaskViewSet, basename='task')
router.register(r'self-tasks', SelfTaskViewSet, basename='self-task')
router.register(r'self-notes', SelfNoteViewSet, basename='self-note')
router.register(r'comments', TaskCommentViewSet, basename='comment')
router.register(r'notifications', NotificationViewSet, basename='notification')
router.register(r'email-logs', DispatchedEmailLogViewSet, basename='email-log')
router.register(r'activity-logs', ActivityLogViewSet, basename='activity-log')

urlpatterns = [
    path('auth/login/', login_user, name='login_user'),
    path('auth/logout/', logout_user, name='logout_user'),
    path('auth/personas/', list_personas, name='list_personas'),
    path('auth/me/', current_user_me, name='current_user_me'),
    path('dashboard/stats/', dashboard_stats, name='dashboard_stats'),
    path('admin/backup/sql/', backup_database_sql, name='backup_database_sql'),
    path('admin/backup/json/', backup_database_json, name='backup_database_json'),
    path('admin/restore/sql/', restore_database_sql, name='restore_database_sql'),
    path('admin/restore/json/', restore_database_json, name='restore_database_json'),
    path('admin/system-stats/', admin_system_stats, name='admin_system_stats'),
    path('admin/clear-database/', clear_database, name='clear_database'),
    path('admin/email-status/', get_email_status, name='get_email_status'),
    path('admin/email-settings/', update_email_settings, name='update_email_settings'),
    path('admin/send-test-email/', send_test_email, name='send_test_email'),
    path('devices/register/', register_device, name='register_device'),
    path('devices/test-push/', test_push_notification, name='test_push_notification'),
    path('admin/user-sessions/', admin_user_sessions, name='admin_user_sessions'),
    path('auth/ping/', ping_user_activity, name='ping_user_activity'),
    path('app-version/', get_app_version, name='app-version'),
    path('', include(router.urls)),
]
