from rest_framework import serializers
from .models import (
    Department, User, Task, TaskComment, Notification, DispatchedEmailLog, ActivityLog,
    SelfTask, SelfNote, UserDevice, UserSessionLog, RoutineWorkItem, RoutineWorkLog
)
from .services import parse_attachments_list


class DepartmentSerializer(serializers.ModelSerializer):
    members_count = serializers.SerializerMethodField()
    active_tasks_count = serializers.SerializerMethodField()
    manager = serializers.SerializerMethodField()

    class Meta:
        model = Department
        fields = ['id', 'name', 'code', 'description', 'created_at', 'members_count', 'active_tasks_count', 'manager']

    def get_members_count(self, obj):
        return obj.members.filter(is_active=True).count()

    def get_active_tasks_count(self, obj):
        return obj.tasks.exclude(status=Task.STATUS_CLOSED).count()

    def get_manager(self, obj):
        mgr = obj.members.filter(role=User.ROLE_DEPT_MANAGER, is_active=True).first()
        if mgr:
            return {
                'id': mgr.id,
                'name': mgr.get_full_name() or mgr.username,
                'email': mgr.email,
                'username': mgr.username
            }
        return None


class UserSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source='department.name', read_only=True)
    department_code = serializers.CharField(source='department.code', read_only=True)
    full_name = serializers.SerializerMethodField()
    password = serializers.CharField(write_only=True, required=False)
    allowed_pages = serializers.ListField(child=serializers.CharField(), required=False, allow_empty=True)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 'full_name',
            'role', 'department', 'department_name', 'department_code',
            'phone', 'job_title', 'is_active', 'password', 'allowed_pages'
        ]

    def get_full_name(self, obj):
        return obj.get_full_name() or obj.username

    def validate(self, attrs):
        request = self.context.get('request')
        current_user = request.user if request else None

        if current_user and current_user.role == User.ROLE_DEPT_MANAGER:
            # Department Manager restrictions:
            # 1. Cannot assign user to any department other than their own
            attrs['department'] = current_user.department
            # 2. Cannot create GM or SuperAdmin or other Managers
            requested_role = attrs.get('role')
            if requested_role and requested_role != User.ROLE_STAFF:
                raise serializers.ValidationError({"role": "Department Managers can only manage Staff members in their own department."})
            attrs['role'] = User.ROLE_STAFF

        return attrs

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_password('staff123')
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            set_defaults = setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class TaskCommentSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()
    author_role = serializers.CharField(source='author.role', read_only=True)

    class Meta:
        model = TaskComment
        fields = ['id', 'task', 'author', 'author_name', 'author_role', 'content', 'created_at']
        read_only_fields = ['author', 'created_at']

    def get_author_name(self, obj):
        return obj.author.get_full_name() or obj.author.username


class TaskSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source='department.name', read_only=True)
    department_code = serializers.CharField(source='department.code', read_only=True)
    assigned_to_name = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    verified_by_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    assigned_to_email = serializers.SerializerMethodField()
    assigned_to_phone = serializers.SerializerMethodField()
    comments = TaskCommentSerializer(many=True, read_only=True)

    attachment_image = serializers.CharField(required=False, allow_blank=True, allow_null=True, default='')
    image = serializers.CharField(source='attachment_image', required=False, allow_blank=True, allow_null=True, default='')
    attachments = serializers.ListField(child=serializers.CharField(), read_only=True, default=list)

    class Meta:
        model = Task
        fields = [
            'id', 'title', 'description', 'department', 'department_name', 'department_code',
            'assigned_to', 'assigned_to_name', 'assigned_to_email', 'assigned_to_phone', 'created_by', 'created_by_name',
            'priority', 'priority_display', 'status', 'status_display', 'due_date',
            'gm_feedback_notes', 'verified_by', 'verified_by_name', 'closed_at',
            'attachment_image', 'image', 'attachments', 'is_gm_own_task',
            'created_at', 'updated_at', 'comments'
        ]
        read_only_fields = ['created_by', 'verified_by', 'closed_at', 'created_at', 'updated_at']

    def get_assigned_to_phone(self, obj):
        return obj.assigned_to.phone if obj.assigned_to else ""

    def get_assigned_to_email(self, obj):
        return obj.assigned_to.email if obj.assigned_to else ""

    def get_assigned_to_name(self, obj):
        return obj.assigned_to.get_full_name() or obj.assigned_to.username if obj.assigned_to else "Unassigned"

    def get_created_by_name(self, obj):
        return obj.created_by.get_full_name() or obj.created_by.username if obj.created_by else ""

    def get_verified_by_name(self, obj):
        return obj.verified_by.get_full_name() or obj.verified_by.username if obj.verified_by else ""

    def validate(self, attrs):
        request = self.context.get('request')
        current_user = request.user if request else None

        # Restrict Task creation and updates to General Manager and Super Admin only
        if request and request.method == 'POST':
            if not current_user or not current_user.is_gm_or_super():
                raise serializers.ValidationError({"detail": "Permission denied: Only General Manager and Super Admin are permitted to create tasks."})

        if request and request.method in ['PUT', 'PATCH']:
            if not current_user or not current_user.is_gm_or_super():
                raise serializers.ValidationError({"detail": "Permission denied: Only General Manager and Super Admin are permitted to edit task details."})

        # Exclusive GM Closure Check
        requested_status = attrs.get('status')
        if requested_status == Task.STATUS_CLOSED:
            if not current_user or not current_user.is_gm_or_super():
                raise serializers.ValidationError({
                    "status": "Exclusive GM Sign-off required: Only General Manager or Super Admin can approve and officially close tasks."
                })

        # Ensure optional attachment_image is never None in database
        if attrs.get('attachment_image') is None:
            attrs['attachment_image'] = ''

        return attrs

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        request = self.context.get('request')

        raw_val = instance.attachment_image or ''
        raw_list = parse_attachments_list(raw_val)

        formatted_list = []
        for raw_item in raw_list:
            if not raw_item:
                continue
            clean_path = raw_item.strip()
            if clean_path.startswith('data:'):
                formatted_list.append(clean_path)
                continue

            if '://' in clean_path:
                from urllib.parse import urlparse
                clean_path = urlparse(clean_path).path

            if not clean_path.startswith('/'):
                clean_path = '/' + clean_path

            if '/media/' in clean_path:
                sub_path = clean_path[clean_path.index('/media/') + len('/media/'):]
            else:
                sub_path = clean_path.lstrip('/')

            if request:
                host = request.get_host()
                if host in ['127.0.0.1', 'localhost', 'backend', '127.0.0.1:8000', '127.0.0.1:8007']:
                    host = 'www.rguedu.in'
                    scheme = 'https'
                else:
                    forwarded_proto = request.META.get('HTTP_X_FORWARDED_PROTO')
                    scheme = forwarded_proto if forwarded_proto else ('https' if request.is_secure() else 'http')
                    if 'rguedu.in' in host or 'rathinamtechzone.com' in host:
                        scheme = 'https'
                full_url = f"{scheme}://{host}/nextup/api/media/{sub_path}"
            else:
                full_url = f"https://www.rguedu.in/nextup/api/media/{sub_path}"
            formatted_list.append(full_url)

        ret['attachments'] = formatted_list
        primary_url = formatted_list[0] if formatted_list else ''
        ret['attachment_image'] = primary_url
        ret['image'] = primary_url
        return ret


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'recipient', 'title', 'message', 'notification_type', 'task', 'is_read', 'created_at']


class DispatchedEmailLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = DispatchedEmailLog
        fields = ['id', 'recipient_email', 'recipient_name', 'subject', 'body', 'event_type', 'created_at']


class ActivityLogSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    department_name = serializers.CharField(source='department.name', read_only=True)

    class Meta:
        model = ActivityLog
        fields = ['id', 'user', 'user_name', 'action', 'details', 'department', 'department_name', 'task', 'timestamp']

    def get_user_name(self, obj):
        return obj.user.get_full_name() or obj.user.username if obj.user else "System"


class SelfTaskSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = SelfTask
        fields = [
            'id', 'user', 'user_name', 'title', 'description',
            'priority', 'priority_display', 'status', 'status_display',
            'due_date', 'is_completed', 'created_at', 'updated_at'
        ]
        read_only_fields = ['user', 'created_at', 'updated_at']

    def get_user_name(self, obj):
        return obj.user.get_full_name() or obj.user.username


class SelfNoteSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    category_display = serializers.CharField(source='get_category_display', read_only=True)

    class Meta:
        model = SelfNote
        fields = [
            'id', 'user', 'user_name', 'title', 'content',
            'category', 'category_display', 'color', 'is_pinned',
            'reminder_date', 'reminder_time', 'reminder_enabled', 'is_reminder_sent',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['user', 'created_at', 'updated_at']

    def get_user_name(self, obj):
        return obj.user.get_full_name() or obj.user.username


class UserDeviceSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    department_name = serializers.SerializerMethodField()
    role_display = serializers.CharField(source='user.get_role_display', read_only=True)

    class Meta:
        model = UserDevice
        fields = [
            'id', 'user', 'user_name', 'department_name', 'role_display',
            'device_token', 'device_type', 'device_name', 'app_version',
            'is_active', 'last_seen', 'created_at'
        ]
        read_only_fields = ['user', 'last_seen', 'created_at']

    def get_user_name(self, obj):
        return obj.user.get_full_name() or obj.user.username

    def get_department_name(self, obj):
        return obj.user.department.name if obj.user.department else 'Global'


class UserSessionLogSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    department_name = serializers.SerializerMethodField()
    role_display = serializers.CharField(source='user.get_role_display', read_only=True)

    class Meta:
        model = UserSessionLog
        fields = [
            'id', 'user', 'user_name', 'department_name', 'role_display',
            'session_key', 'platform', 'device_info', 'ip_address',
            'user_agent', 'login_time', 'logout_time', 'last_activity', 'is_active'
        ]
        read_only_fields = ['login_time', 'last_activity']

    def get_user_name(self, obj):
        return obj.user.get_full_name() or obj.user.username

    def get_department_name(self, obj):
        return obj.user.department.name if obj.user.department else 'Global'


class RoutineWorkLogSerializer(serializers.ModelSerializer):
    completed_by_name = serializers.SerializerMethodField()
    item_title = serializers.CharField(source='item.title', read_only=True, default='')
    item_frequency = serializers.CharField(source='item.frequency', read_only=True, default='DAILY')
    department_id = serializers.IntegerField(source='item.department.id', read_only=True, default=None, allow_null=True)
    department_name = serializers.CharField(source='item.department.name', read_only=True, default='')
    department_code = serializers.CharField(source='item.department.code', read_only=True, default='')
    target_count = serializers.IntegerField(source='item.target_count', read_only=True, default=0)
    unit = serializers.CharField(source='item.unit', read_only=True, default='')

    class Meta:
        model = RoutineWorkLog
        fields = [
            'id', 'item', 'item_title', 'item_frequency', 'department_id', 'department_name', 'department_code',
            'target_count', 'unit', 'completed_by', 'completed_by_name', 'completed_at', 'period_identifier',
            'count', 'notes', 'status'
        ]
        read_only_fields = ['completed_at']

    def get_completed_by_name(self, obj):
        if obj.completed_by:
            return obj.completed_by.get_full_name() or obj.completed_by.username
        return ''


class RoutineWorkItemSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source='department.name', read_only=True)
    department_code = serializers.CharField(source='department.code', read_only=True)
    assigned_to_name = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    last_completed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = RoutineWorkItem
        fields = [
            'id', 'title', 'description', 'frequency', 'department', 'department_name', 'department_code',
            'assigned_to', 'assigned_to_name', 'created_by', 'created_by_name', 'priority', 'target_time',
            'target_count', 'unit', 'last_completed_count',
            'is_active', 'last_completed_at', 'last_completed_by', 'last_completed_by_name',
            'completion_notes', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'created_by']

    def get_assigned_to_name(self, obj):
        if obj.assigned_to:
            return obj.assigned_to.get_full_name() or obj.assigned_to.username
        return ''

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.username
        return ''

    def get_last_completed_by_name(self, obj):
        if obj.last_completed_by:
            return obj.last_completed_by.get_full_name() or obj.last_completed_by.username
        return ''
