from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import Department, User, Task, TaskComment, Notification, DispatchedEmailLog, ActivityLog


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'created_at', 'get_members_count', 'get_tasks_count')
    search_fields = ('name', 'code', 'description')

    def get_members_count(self, obj):
        return obj.members.count()
    get_members_count.short_description = 'Staff Members'

    def get_tasks_count(self, obj):
        return obj.tasks.count()
    get_tasks_count.short_description = 'Total Tasks'


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'role', 'department', 'is_active', 'is_staff')
    list_filter = ('role', 'department', 'is_active', 'is_staff')
    search_fields = ('username', 'first_name', 'last_name', 'email')
    ordering = ('username',)

    fieldsets = BaseUserAdmin.fieldsets + (
        ('Task Tracker Enterprise Details', {
            'fields': ('role', 'department', 'job_title', 'phone')
        }),
    )

    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Task Tracker Enterprise Details', {
            'fields': ('role', 'department', 'job_title', 'phone')
        }),
    )


class TaskCommentInline(admin.TabularInline):
    model = TaskComment
    extra = 1
    readonly_fields = ('created_at',)


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'department', 'assigned_to', 'priority', 'status', 'due_date', 'verified_by', 'closed_at')
    list_filter = ('status', 'priority', 'department', 'created_at', 'due_date')
    search_fields = ('title', 'description', 'gm_feedback_notes')
    readonly_fields = ('created_at', 'updated_at', 'closed_at', 'verified_by')
    inlines = [TaskCommentInline]

    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'description', 'department', 'priority', 'due_date')
        }),
        ('Assignment & Lifecycle', {
            'fields': ('assigned_to', 'created_by', 'status')
        }),
        ('GM Verification Sign-Off', {
            'fields': ('gm_feedback_notes', 'verified_by', 'closed_at')
        }),
        ('System Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )


@admin.register(TaskComment)
class TaskCommentAdmin(admin.ModelAdmin):
    list_display = ('task', 'author', 'created_at', 'get_content_preview')
    list_filter = ('created_at', 'author')
    search_fields = ('content', 'task__title')

    def get_content_preview(self, obj):
        return obj.content[:50]
    get_content_preview.short_description = 'Snippet'


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'title', 'notification_type', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read', 'created_at')
    search_fields = ('title', 'message', 'recipient__username')


@admin.register(DispatchedEmailLog)
class DispatchedEmailLogAdmin(admin.ModelAdmin):
    list_display = ('recipient_email', 'recipient_name', 'subject', 'event_type', 'created_at')
    list_filter = ('event_type', 'created_at')
    search_fields = ('recipient_email', 'subject', 'body')
    readonly_fields = ('created_at',)


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'user', 'action', 'department', 'task')
    list_filter = ('action', 'department', 'timestamp')
    search_fields = ('details', 'user__username', 'action')
    readonly_fields = ('timestamp',)
