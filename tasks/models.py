from django.db import models
from django.contrib.auth.models import AbstractUser


class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=10, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.code})"


class User(AbstractUser):
    ROLE_SUPER_ADMIN = 'SUPER_ADMIN'
    ROLE_GENERAL_MANAGER = 'GENERAL_MANAGER'
    ROLE_DEPT_MANAGER = 'DEPT_MANAGER'
    ROLE_STAFF = 'STAFF'

    ROLE_CHOICES = [
        (ROLE_SUPER_ADMIN, 'Super Admin'),
        (ROLE_GENERAL_MANAGER, 'General Manager'),
        (ROLE_DEPT_MANAGER, 'Department Manager'),
        (ROLE_STAFF, 'Staff Member'),
    ]

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_STAFF)
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='members'
    )
    phone = models.CharField(max_length=25, blank=True)
    job_title = models.CharField(max_length=100, blank=True)
    allowed_pages = models.JSONField(default=list, blank=True)

    def is_gm_or_super(self):
        return self.role in [self.ROLE_GENERAL_MANAGER, self.ROLE_SUPER_ADMIN] or self.is_superuser

    def is_dept_manager(self):
        return self.role == self.ROLE_DEPT_MANAGER

    def is_staff_member(self):
        return self.role == self.ROLE_STAFF

    def get_allowed_pages(self):
        if self.role in [self.ROLE_SUPER_ADMIN, self.ROLE_GENERAL_MANAGER]:
            return self.allowed_pages or [
                'board', 'table', 'list', 'calendar', 'self_desk',
                'today', 'approvals', 'departments', 'staff', 'report', 'settings'
            ]
        if self.allowed_pages:
            return self.allowed_pages
        if self.role == self.ROLE_DEPT_MANAGER:
            return ['board', 'table', 'list', 'calendar', 'self_desk', 'departments', 'staff', 'report']
        return ['board', 'table', 'list', 'calendar', 'self_desk']

    def __str__(self):
        dept_str = f" [{self.department.code}]" if self.department else ""
        return f"{self.get_full_name() or self.username} ({self.get_role_display()}){dept_str}"


class Task(models.Model):
    PRIORITY_LOW = 'LOW'
    PRIORITY_MEDIUM = 'MEDIUM'
    PRIORITY_HIGH = 'HIGH'
    PRIORITY_URGENT = 'URGENT'

    PRIORITY_CHOICES = [
        (PRIORITY_LOW, 'Low'),
        (PRIORITY_MEDIUM, 'Medium'),
        (PRIORITY_HIGH, 'High'),
        (PRIORITY_URGENT, 'Urgent'),
    ]

    STATUS_TODO = 'TODO'
    STATUS_IN_PROGRESS = 'IN_PROGRESS'
    STATUS_PENDING_GM_APPROVAL = 'PENDING_GM_APPROVAL'
    STATUS_CHANGES_REQUESTED = 'CHANGES_REQUESTED'
    STATUS_CLOSED = 'CLOSED'

    STATUS_CHOICES = [
        (STATUS_TODO, 'To Do'),
        (STATUS_IN_PROGRESS, 'In Progress'),
        (STATUS_PENDING_GM_APPROVAL, 'Pending GM Approval'),
        (STATUS_CHANGES_REQUESTED, 'Changes Requested'),
        (STATUS_CLOSED, 'Closed & Verified'),
    ]

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='tasks')
    assigned_to = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_tasks'
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='created_tasks'
    )
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default=PRIORITY_MEDIUM)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_TODO)
    due_date = models.DateField(null=True, blank=True)
    
    # GM Verification fields
    gm_feedback_notes = models.TextField(blank=True)
    verified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_tasks'
    )
    closed_at = models.DateTimeField(null=True, blank=True)

    # Optional Progress / Work Proof / Incident Image
    attachment_image = models.TextField(blank=True, default='')

    # Flag for GM Own Personal Tasks (Never visible to Department Managers or Staff)
    is_gm_own_task = models.BooleanField(default=False, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.department.code}] {self.title} ({self.get_status_display()})"


class TaskComment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='comments')
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Comment by {self.author} on {self.task.title}"


class Notification(models.Model):
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=255)
    message = models.TextField()
    notification_type = models.CharField(max_length=50)
    task = models.ForeignKey(Task, on_delete=models.CASCADE, null=True, blank=True, related_name='notifications')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Notification for {self.recipient}: {self.title}"


class DispatchedEmailLog(models.Model):
    recipient_email = models.CharField(max_length=255)
    recipient_name = models.CharField(max_length=255, blank=True)
    subject = models.CharField(max_length=255)
    body = models.TextField()
    event_type = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Email to {self.recipient_email}: {self.subject}"


class ActivityLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='activity_logs')
    action = models.CharField(max_length=100)
    details = models.TextField()
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='activity_logs')
    task = models.ForeignKey(Task, on_delete=models.SET_NULL, null=True, blank=True, related_name='activity_logs')
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.timestamp:%Y-%m-%d %H:%M} - {self.action}: {self.details[:50]}"


class SelfTask(models.Model):
    PRIORITY_LOW = 'LOW'
    PRIORITY_MEDIUM = 'MEDIUM'
    PRIORITY_HIGH = 'HIGH'
    PRIORITY_URGENT = 'URGENT'

    PRIORITY_CHOICES = [
        (PRIORITY_LOW, 'Low'),
        (PRIORITY_MEDIUM, 'Medium'),
        (PRIORITY_HIGH, 'High'),
        (PRIORITY_URGENT, 'Urgent'),
    ]

    STATUS_TODO = 'TODO'
    STATUS_IN_PROGRESS = 'IN_PROGRESS'
    STATUS_COMPLETED = 'COMPLETED'

    STATUS_CHOICES = [
        (STATUS_TODO, 'To Do'),
        (STATUS_IN_PROGRESS, 'In Progress'),
        (STATUS_COMPLETED, 'Completed'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='self_tasks')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default=PRIORITY_MEDIUM)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_TODO)
    due_date = models.DateField(null=True, blank=True)
    is_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['is_completed', '-created_at']

    def __str__(self):
        return f"SelfTask: {self.title} ({self.user.username})"


class SelfNote(models.Model):
    CATEGORY_GENERAL = 'GENERAL'
    CATEGORY_WORK = 'WORK'
    CATEGORY_MEETING = 'MEETING'
    CATEGORY_IDEA = 'IDEA'
    CATEGORY_CHECKLIST = 'CHECKLIST'

    CATEGORY_CHOICES = [
        (CATEGORY_GENERAL, 'General Note'),
        (CATEGORY_WORK, 'Work Memo'),
        (CATEGORY_MEETING, 'Meeting Notes'),
        (CATEGORY_IDEA, 'Idea / Project Draft'),
        (CATEGORY_CHECKLIST, 'Quick Checklist'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='self_notes')
    title = models.CharField(max_length=255)
    content = models.TextField(blank=True, default='')
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, default=CATEGORY_GENERAL)
    color = models.CharField(max_length=30, default='default', blank=True)
    is_pinned = models.BooleanField(default=False)
    reminder_date = models.DateField(null=True, blank=True)
    reminder_time = models.TimeField(null=True, blank=True)
    reminder_enabled = models.BooleanField(default=False)
    is_reminder_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_pinned', '-updated_at']

    def __str__(self):
        return f"SelfNote: {self.title} ({self.user.username})"
