from rest_framework import serializers
from .models import (
    Department, User, Task, TaskComment, Notification, DispatchedEmailLog, ActivityLog,
    SelfTask, SelfNote
)


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

    class Meta:
        model = Task
        fields = [
            'id', 'title', 'description', 'department', 'department_name', 'department_code',
            'assigned_to', 'assigned_to_name', 'assigned_to_email', 'assigned_to_phone', 'created_by', 'created_by_name',
            'priority', 'priority_display', 'status', 'status_display', 'due_date',
            'gm_feedback_notes', 'verified_by', 'verified_by_name', 'closed_at',
            'attachment_image', 'image', 'is_gm_own_task',
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
        raw_img = ret.get('attachment_image')
        if raw_img and not (raw_img.startswith('http://') or raw_img.startswith('https://') or raw_img.startswith('data:')):
            request = self.context.get('request')
            if request:
                full_url = request.build_absolute_uri(raw_img)
                ret['attachment_image'] = full_url
                ret['image'] = full_url
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

