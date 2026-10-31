import base64
import os
import re
import time
import uuid
import threading
import requests
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from django.db.models import Q
from .models import Notification, DispatchedEmailLog, ActivityLog, User, Task, TaskComment, UserDevice, UserSessionLog


def save_task_attachment_image(image_input, task_id=None):
    """
    Saves an uploaded image (Base64 data URI, raw base64, or UploadedFile)
    into the server media folder: media/task_attachments/
    and returns its clean URL path: /media/task_attachments/<filename>.
    
    If image_input is already a saved URL, it is returned unchanged.
    If image_input is empty, returns empty string.
    """
    if not image_input:
        return ""

    # If it's already a saved media URL or external URL, return as-is
    if isinstance(image_input, str):
        image_input_str = image_input.strip()
        if not image_input_str:
            return ""
        if image_input_str.startswith('/media/') or image_input_str.startswith('http://') or image_input_str.startswith('https://'):
            return image_input_str

    # Target directory inside MEDIA_ROOT
    media_root = getattr(settings, 'MEDIA_ROOT', os.path.join(settings.BASE_DIR, 'media'))
    target_dir = os.path.join(media_root, 'task_attachments')
    os.makedirs(target_dir, exist_ok=True)

    timestamp = int(time.time())
    unique_suffix = uuid.uuid4().hex[:8]
    id_prefix = f"task_{task_id}" if task_id else "task"

    # Case 1: UploadedFile (multipart/form-data upload)
    if hasattr(image_input, 'read') and hasattr(image_input, 'name'):
        ext = os.path.splitext(image_input.name)[1].lower() or '.jpg'
        if ext not in ['.jpg', '.jpeg', '.png', '.webp', '.gif']:
            ext = '.jpg'
        filename = f"{id_prefix}_{timestamp}_{unique_suffix}{ext}"
        file_path = os.path.join(target_dir, filename)
        try:
            with open(file_path, 'wb+') as dest:
                for chunk in image_input.chunks():
                    dest.write(chunk)
            return f"/media/task_attachments/{filename}"
        except Exception as e:
            print(f"⚠️ Error saving UploadedFile image: {e}")
            return ""

    # Case 2: Base64 String (data:image/...;base64,...)
    if isinstance(image_input, str):
        data_str = image_input.strip()
        ext = '.jpg'
        base64_content = data_str

        # Parse data URL scheme e.g. "data:image/png;base64,..."
        match = re.match(r'^data:image/([a-zA-Z0-9\+\-]+);base64,(.+)$', data_str, re.DOTALL)
        if match:
            raw_ext = match.group(1).lower()
            if raw_ext in ['jpeg', 'jpg']:
                ext = '.jpg'
            elif raw_ext == 'png':
                ext = '.png'
            elif raw_ext == 'webp':
                ext = '.webp'
            elif raw_ext == 'gif':
                ext = '.gif'
            else:
                ext = '.jpg'
            base64_content = match.group(2)
        elif data_str.startswith('data:') and ';base64,' in data_str:
            parts = data_str.split(';base64,', 1)
            base64_content = parts[1]

        try:
            image_bytes = base64.b64decode(base64_content)
            filename = f"{id_prefix}_{timestamp}_{unique_suffix}{ext}"
            file_path = os.path.join(target_dir, filename)
            with open(file_path, 'wb') as f:
                f.write(image_bytes)
            return f"/media/task_attachments/{filename}"
        except Exception as e:
            print(f"⚠️ Error decoding and saving base64 image: {e}")
            return data_str

    return ""



def _async_send_mail(subject, body, from_email, recipient_email):
    """Worker function executed in background thread to avoid blocking concurrent web requests."""
    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=from_email,
            recipient_list=[recipient_email],
            fail_silently=True,
        )
    except Exception as e:
        print(f"⚠️ Email dispatch notification for {recipient_email}: {e}")



def send_expo_push_notification(tokens, title, body, data=None):
    """
    Sends native mobile push notifications via Expo Push Notification API.
    Dispatches in a background daemon thread so it never blocks Django response.
    """
    if not tokens:
        return
    if isinstance(tokens, str):
        tokens = [tokens]
    
    valid_tokens = [
        t.strip() for t in tokens 
        if t and isinstance(t, str) and (t.startswith('ExponentPushToken[') or t.startswith('ExpoPushToken['))
    ]
    if not valid_tokens:
        return

    messages = []
    for token in valid_tokens:
        is_urgent_alert = 'urgent' in title.lower() or 'overdue' in title.lower() or 'due' in title.lower() or (data and data.get('is_urgent'))
        is_hourly = (data and data.get('type') == 'HOURLY_WORK_REMINDER')
        channel_id = 'urgent-due-alerts-channel' if is_urgent_alert else ('hourly-work-reminders' if is_hourly else 'task-alerts-channel')
        msg = {
            'to': token,
            'sound': 'default',
            'title': title,
            'body': body,
            'priority': 'high',
            'channelId': channel_id,
        }
        if data:
            msg['data'] = data
        messages.append(msg)

    def _do_push():
        try:
            resp = requests.post(
                'https://exp.host/--/api/v2/push/send',
                json=messages,
                headers={
                    'Accept': 'application/json',
                    'Accept-Encoding': 'gzip, deflate',
                    'Content-Type': 'application/json',
                },
                timeout=10
            )
            print(f"[ExpoPush] Sent to {len(messages)} device(s) - HTTP {resp.status_code}")
        except Exception as e:
            print(f"[ExpoPush] Push delivery exception: {e}")

    threading.Thread(target=_do_push, daemon=True).start()


def record_user_login(user, request, platform='web', device_info=''):
    ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', ''))
    if ip and ',' in ip:
        ip = ip.split(',')[0].strip()
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    session_key = getattr(request.session, 'session_key', '') or ''
    
    session_log = UserSessionLog.objects.create(
        user=user,
        session_key=session_key,
        platform=platform,
        device_info=device_info,
        ip_address=ip or '',
        user_agent=user_agent or '',
        is_active=True
    )
    return session_log


def record_user_logout(user, request=None):
    if user:
        UserSessionLog.objects.filter(user=user, is_active=True).update(
            is_active=False,
            logout_time=timezone.now()
        )

def dispatch_email_and_notification(recipient, subject, body, event_type, task=None, title=None):
    """
    Sends email via background thread, records it in DispatchedEmailLog,
    and creates an in-app Notification for the recipient without delaying API response.
    """
    if not recipient:
        return None

    # Ensure recipient has a valid email address
    if not getattr(recipient, 'email', None) or not recipient.email.strip():
        fallback_email = f"{recipient.username}@tasktracker.enterprise"
        recipient.email = fallback_email
        try:
            recipient.save(update_fields=['email'])
        except Exception:
            pass

    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'notifications@tasktracker.enterprise')

    # Non-blocking async dispatch: spawns background thread so HTTP worker immediately returns
    threading.Thread(
        target=_async_send_mail,
        args=(subject, body, from_email, recipient.email),
        daemon=True
    ).start()

    # Log dispatched email in database for real-time audit & UI demonstration
    log_body = body

    email_log = DispatchedEmailLog.objects.create(
        recipient_email=recipient.email,
        recipient_name=recipient.get_full_name() or recipient.username,
        subject=subject,
        body=log_body,
        event_type=event_type,
    )

    # Create in-app Notification
    notif_title = title or subject
    notification = Notification.objects.create(
        recipient=recipient,
        title=notif_title,
        message=body,
        notification_type=event_type,
        task=task,
    )

    # Dispatch native mobile push notification to recipient's active devices
    try:
        active_tokens = list(recipient.devices.filter(is_active=True).values_list('device_token', flat=True))
        if active_tokens:
            send_expo_push_notification(
                tokens=active_tokens,
                title=notif_title,
                body=body[:220],
                data={
                    'taskId': task.id if task else None,
                    'type': event_type,
                    'notificationId': notification.id,
                }
            )
    except Exception as push_err:
        print(f"[ExpoPush] Device lookup error: {push_err}")

    return email_log, notification



def log_activity(user, action, details, department=None, task=None):
    dept = department or (task.department if task else (user.department if user else None))
    return ActivityLog.objects.create(
        user=user,
        action=action,
        details=details,
        department=dept,
        task=task,
    )


# --- Lifecycle Notification Triggers ---

def format_timeline_text(due_date):
    if not due_date:
        return "Flexible timeline (No deadline)"
    today = timezone.now().date()
    diff = (due_date - today).days
    if diff < 0:
        return f"{due_date} (🚨 OVERDUE by {abs(diff)} day{'s' if abs(diff) != 1 else ''})"
    elif diff == 0:
        return f"{due_date} (⚠️ DUE TODAY)"
    elif diff == 1:
        return f"{due_date} (⏰ DUE TOMORROW)"
    else:
        return f"{due_date} (⏰ {diff} days remaining)"


def is_gm_own_task(task):
    if not task:
        return False
    if getattr(task, 'is_gm_own_task', False):
        return True
    if task.assigned_to and getattr(task.assigned_to, 'role', '') in [User.ROLE_GENERAL_MANAGER, User.ROLE_SUPER_ADMIN]:
        return True
    if getattr(task, 'department', None) and (getattr(task.department, 'code', '').upper() == 'GM' or 'general management' in getattr(task.department, 'name', '').lower()):
        return True
    return False


def notify_task_assigned(task, assigned_by):
    # GM Own Task: Never send notification or email to anyone
    if is_gm_own_task(task):
        return

    recipients = set()
    if task.assigned_to:
        recipients.add(task.assigned_to)

    # Also notify department managers of the new task assignment and timeline
    dept_managers = User.objects.filter(
        department=task.department,
        role=User.ROLE_DEPT_MANAGER,
        is_active=True
    ).exclude(id=assigned_by.id)
    for dm in dept_managers:
        recipients.add(dm)

    timeline_str = format_timeline_text(task.due_date)
    subject_prefix = f"[{task.department.code}]"
    if task.due_date:
        subject = f"✉️ {subject_prefix} New Task & Timeline: '{task.title}' (Due: {task.due_date})"
    else:
        subject = f"✉️ {subject_prefix} New Task Assigned: '{task.title}'"

    for rec in recipients:
        is_assignee = (task.assigned_to and rec.id == task.assigned_to.id)
        role_note = "You have been assigned to" if is_assignee else f"Staff member '{task.assigned_to.get_full_name() if task.assigned_to else 'Unassigned'}' was assigned to"

        body = (
            f"Hello {rec.get_full_name() or rec.username},\n\n"
            f"{role_note} task '{task.title}' by {assigned_by.get_full_name() or assigned_by.username}.\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📋 TASK TIMELINE & SPECIFICATIONS:\n"
            f"• Department: {task.department.name} ({task.department.code})\n"
            f"• Priority: {task.get_priority_display()}\n"
            f"• Target Timeline / Due Date: {timeline_str}\n"
            f"• Current Status: {task.get_status_display()}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Description:\n{task.description or 'No additional description provided.'}\n\n"
            f"Please ensure deliverables are planned and tracked according to this timeline on the Task Tracker portal.\n\n"
            f"Best regards,\nTaskTracker Enterprise Management System"
        )
        dispatch_email_and_notification(
            recipient=rec,
            subject=subject,
            body=body,
            event_type='TASK_ASSIGNED',
            task=task,
            title=f"Task Assigned: {task.title} (Due: {task.due_date or 'Flexible'})"
        )


def notify_task_timeline_updated(task, updated_by, old_due_date):
    if is_gm_own_task(task):
        return

    recipients = set()
    if task.assigned_to:
        recipients.add(task.assigned_to)

    dept_managers = User.objects.filter(
        department=task.department,
        role=User.ROLE_DEPT_MANAGER,
        is_active=True
    ).exclude(id=updated_by.id)
    for dm in dept_managers:
        recipients.add(dm)

    timeline_str = format_timeline_text(task.due_date)
    subject = f"⏰ [{task.department.code}] Timeline Updated: '{task.title}' (New Deadline: {task.due_date or 'None'})"

    for rec in recipients:
        body = (
            f"Hello {rec.get_full_name() or rec.username},\n\n"
            f"The timeline for task '{task.title}' has been updated by {updated_by.get_full_name() or updated_by.username}.\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📅 UPDATED TIMELINE:\n"
            f"• Previous Deadline: {old_due_date or 'None'}\n"
            f"• New Target Timeline: {timeline_str}\n"
            f"• Priority: {task.get_priority_display()}\n"
            f"• Department: {task.department.name}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Please adjust your schedule and task milestones accordingly."
        )
        dispatch_email_and_notification(
            recipient=rec,
            subject=subject,
            body=body,
            event_type='TIMELINE_UPDATED',
            task=task,
            title=f"Timeline Updated: {task.title} -> {task.due_date or 'Flexible'}"
        )


def notify_timeline_reminder(task, triggered_by=None):
    if is_gm_own_task(task):
        return []

    recipients = set()
    if task.assigned_to:
        recipients.add(task.assigned_to)

    dept_managers = User.objects.filter(
        department=task.department,
        role=User.ROLE_DEPT_MANAGER,
        is_active=True
    )
    for dm in dept_managers:
        recipients.add(dm)

    if not recipients:
        return []

    timeline_str = format_timeline_text(task.due_date)
    sender_note = f" sent by {triggered_by.get_full_name() or triggered_by.username}" if triggered_by else " (Automated System Reminder)"

    today = timezone.now().date()
    diff = (task.due_date - today).days if task.due_date else 999
    if diff < 0:
        prefix = "🚨 OVERDUE NOTICE"
    elif diff == 0:
        prefix = "⚠️ DUE TODAY"
    elif diff <= 2:
        prefix = "⏰ DEADLINE APPROACHING"
    else:
        prefix = "📅 TIMELINE REMINDER"

    subject = f"{prefix}: '{task.title}' [{task.department.code}]"

    logs = []
    for rec in recipients:
        body = (
            f"Hello {rec.get_full_name() or rec.username},\n\n"
            f"This is a milestone timeline reminder{sender_note} regarding task '{task.title}':\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⏰ TIMELINE REMINDER DETAILS:\n"
            f"• Target Deadline: {timeline_str}\n"
            f"• Assigned Staff: {task.assigned_to.get_full_name() if task.assigned_to else 'Unassigned'}\n"
            f"• Priority: {task.get_priority_display()}\n"
            f"• Current Status: {task.get_status_display()}\n"
            f"• Department: {task.department.name} ({task.department.code})\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Task Description:\n{task.description or 'No additional description provided.'}\n\n"
            f"Please verify progress and submit completed deliverables on the Task Tracker portal before the deadline."
        )
        res = dispatch_email_and_notification(
            recipient=rec,
            subject=subject,
            body=body,
            event_type='TIMELINE_REMINDER',
            task=task,
            title=f"{prefix}: {task.title}"
        )
        if res:
            logs.append(res)
    return logs


def check_and_dispatch_all_timeline_reminders():
    """
    Checks all active non-closed tasks with due dates and dispatches
    timeline reminder emails for tasks that are overdue, due today, or due in <= 2 days.
    """
    today = timezone.now().date()
    two_days_out = today + timezone.timedelta(days=2)

    active_tasks = Task.objects.exclude(status=Task.STATUS_CLOSED).filter(
        due_date__isnull=False,
        due_date__lte=two_days_out
    ).select_related('department', 'assigned_to')

    dispatched_count = 0
    items = []
    for task in active_tasks:
        res = notify_timeline_reminder(task)
        if res:
            dispatched_count += len(res)
        items.append({
            'task_id': task.id,
            'title': task.title,
            'timeline_text': format_timeline_text(task.due_date),
            'assignee_email': task.assigned_to.email if task.assigned_to else 'Unassigned',
        })

    return {
        'tasks_checked': active_tasks.count(),
        'emails_dispatched': dispatched_count,
        'items': items,
    }


def notify_submitted_for_gm_verification(task, submitted_by):
    # Alert all General Managers and Super Admins
    gms = User.objects.filter(role__in=[User.ROLE_GENERAL_MANAGER, User.ROLE_SUPER_ADMIN], is_active=True)
    for gm in gms:
        subject = f"✉️ Task Awaiting Verification: {task.title}"
        body = (
            f"Hello {gm.get_full_name() or gm.username},\n\n"
            f"Task '{task.title}' in {task.department.name} has been marked complete by "
            f"{submitted_by.get_full_name() or submitted_by.username} and is awaiting your final verification and closure sign-off.\n\n"
            f"Priority: {task.get_priority_display()}\n"
            f"Assigned Staff: {task.assigned_to.get_full_name() if task.assigned_to else 'Unassigned'}\n\n"
            f"Please log in to the GM Dashboard to review and approve or request changes."
        )
        dispatch_email_and_notification(
            recipient=gm,
            subject=subject,
            body=body,
            event_type='GM_REVIEW_REQUEST',
            task=task,
            title=f"Task Awaiting Verification: {task.title}"
        )


def notify_gm_approved(task, gm_user, notes=""):
    recipients = set()
    if task.assigned_to:
        recipients.add(task.assigned_to)
    # Also notify department manager(s)
    dept_managers = User.objects.filter(department=task.department, role=User.ROLE_DEPT_MANAGER, is_active=True)
    for m in dept_managers:
        recipients.add(m)

    notes_str = f"\nGM Approval Remarks: {notes}\n" if notes else ""

    for rec in recipients:
        subject = f"✉️ Task Verified & Closed: {task.title}"
        body = (
            f"Hello {rec.get_full_name() or rec.username},\n\n"
            f"Great news! Task '{task.title}' has been officially verified and closed by General Manager "
            f"{gm_user.get_full_name() or gm_user.username}.{notes_str}\n"
            f"Status: CLOSED & VERIFIED\n"
            f"Closed Date: {task.closed_at.strftime('%Y-%m-%d %H:%M') if task.closed_at else 'Just now'}\n\n"
            f"Thank you for your hard work!"
        )
        dispatch_email_and_notification(
            recipient=rec,
            subject=subject,
            body=body,
            event_type='GM_APPROVED',
            task=task,
            title=f"Task Verified & Closed: {task.title}"
        )


def notify_gm_changes_requested(task, gm_user, feedback_notes):
    recipients = set()
    if task.assigned_to:
        recipients.add(task.assigned_to)
    dept_managers = User.objects.filter(department=task.department, role=User.ROLE_DEPT_MANAGER, is_active=True)
    for m in dept_managers:
        recipients.add(m)

    for rec in recipients:
        subject = f"✉️ Changes Requested: {task.title}"
        body = (
            f"Hello {rec.get_full_name() or rec.username},\n\n"
            f"General Manager {gm_user.get_full_name() or gm_user.username} reviewed task '{task.title}' "
            f"and requested changes before final closure.\n\n"
            f"GM Feedback Notes:\n\"{feedback_notes}\"\n\n"
            f"Please address the feedback notes and re-submit the task for verification."
        )
        dispatch_email_and_notification(
            recipient=rec,
            subject=subject,
            body=body,
            event_type='GM_CHANGES_REQUESTED',
            task=task,
            title=f"Changes Requested: {task.title}"
        )


def notify_staff_created(staff_user, created_by_user):
    subject = f"✉️ Welcome to {staff_user.department.name if staff_user.department else 'the'} Team"
    body = (
        f"Hello {staff_user.get_full_name() or staff_user.username},\n\n"
        f"Your account has been created by {created_by_user.get_full_name() or created_by_user.username}.\n\n"
        f"Username: {staff_user.username}\n"
        f"Department: {staff_user.department.name if staff_user.department else 'Global'}\n"
        f"Role: {staff_user.get_role_display()}\n\n"
        f"You can now access the Task Tracker portal to manage your assigned tasks."
    )
    dispatch_email_and_notification(
        recipient=staff_user,
        subject=subject,
        body=body,
        event_type='STAFF_CREATED',
        task=None,
        title=f"Welcome to {staff_user.department.name if staff_user.department else 'the'} Team"
    )


def notify_comment_added(comment):
    task = comment.task
    recipients = set()
    if task.assigned_to and task.assigned_to != comment.author:
        recipients.add(task.assigned_to)
    if task.created_by and task.created_by != comment.author:
        recipients.add(task.created_by)

    for rec in recipients:
        subject = f"✉️ New Note on {task.title}"
        body = (
            f"Hello {rec.get_full_name() or rec.username},\n\n"
            f"{comment.author.get_full_name() or comment.author.username} added a comment on '{task.title}':\n\n"
            f"\"{comment.content}\"\n\n"
            f"View task details to reply."
        )
        dispatch_email_and_notification(
            recipient=rec,
            subject=subject,
            body=body,
            event_type='COMMENT_ADDED',
            task=task,
            title=f"New Note on {task.title}"
        )


def send_test_email_verification(to_email, sender_user):
    """
    Directly tests email transmission (SMTP or Console) to a specified recipient address.
    """
    subject = "✉️ [Rathinam TaskTracker] Live Email System Verification"
    body = (
        f"Hello,\n\n"
        f"This is an automated test email from Rathinam TaskTracker Enterprise Management System.\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"System Status: ONLINE\n"
        f"Triggered by: {sender_user.get_full_name() or sender_user.username} ({sender_user.email})\n"
        f"Server Timestamp: {timezone.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
        f"Email Backend: {getattr(settings, 'EMAIL_BACKEND', 'console')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"If you received this message, your email dispatch system is fully connected and active!\n\n"
        f"Best regards,\nRathinam TaskTracker Enterprise System"
    )

    email_error = None
    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'notifications@tasktracker.enterprise'),
            recipient_list=[to_email],
            fail_silently=False,
        )
    except Exception as e:
        email_error = str(e)

    log_body = body
    if email_error:
        log_body += f"\n\n[Delivery Status: Queued in Console / SMTP Notice: {email_error}]"

    email_log = DispatchedEmailLog.objects.create(
        recipient_email=to_email,
        recipient_name=to_email.split('@')[0],
        subject=subject,
        body=log_body,
        event_type='SYSTEM_TEST',
    )

    return {
        'success': email_error is None,
        'error': email_error,
        'email_log_id': email_log.id,
        'recipient': to_email,
        'backend': getattr(settings, 'EMAIL_BACKEND', 'console')
    }


def push_message_to_assigned_staff(task, sender_user, message_text, send_email=True, send_in_app=True, priority_urgent=False):
    """
    Pushes an instant direct message from manager/GM/admin to the assigned staff member of a task.
    - Sends a dedicated notification email to staff.
    - Creates an in-app notification in their tray.
    - Logs in ActivityLog and records on the TaskComment timeline.
    """
    staff = task.assigned_to
    if not staff:
        raise ValueError("This task does not have an assigned staff member.")

    sender_name = sender_user.get_full_name() or sender_user.username
    sender_role = sender_user.get_role_display()
    staff_name = staff.get_full_name() or staff.username

    urgency_prefix = "🚨 [URGENT] " if priority_urgent else "💬 "
    subject = f"{urgency_prefix}Direct Message from {sender_name}: '{task.title}'"

    formatted_time = timezone.now().strftime('%Y-%m-%d %H:%M UTC')
    deadline_str = format_timeline_text(task.due_date)

    email_body = (
        f"Hello {staff_name},\n\n"
        f"You have received a direct message regarding your assigned task on Rathinam TaskTracker:\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 DELIVERABLE DETAILS:\n"
        f"• Task ID: #{task.id}\n"
        f"• Title: {task.title}\n"
        f"• Department: {task.department.name} ({task.department.code})\n"
        f"• Status: {task.get_status_display()}\n"
        f"• Priority: {task.get_priority_display()}\n"
        f"• Target Timeline: {deadline_str}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💬 DIRECT MESSAGE FROM {sender_name.upper()} ({sender_role}):\n"
        f"\"{message_text}\"\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Sent at: {formatted_time}\n\n"
        f"Please view the task in the portal to reply and update your deliverables:\n"
        f"Portal: http://localhost:5173/board\n\n"
        f"Best regards,\n"
        f"Rathinam TaskTracker Enterprise System"
    )

    email_log = None
    notification = None

    if send_email:
        email_error = None
        try:
            send_mail(
                subject=subject,
                message=email_body,
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'notifications@tasktracker.enterprise'),
                recipient_list=[staff.email],
                fail_silently=False,
            )
        except Exception as e:
            email_error = str(e)
            print(f"⚠️ Email dispatch error: {e}")

        log_body = email_body
        if email_error:
            log_body += f"\n\n[Delivery Status: Logged in System / SMTP Notice: {email_error}]"

        email_log = DispatchedEmailLog.objects.create(
            recipient_email=staff.email,
            recipient_name=staff_name,
            subject=subject,
            body=log_body,
            event_type='DIRECT_STAFF_MESSAGE',
        )

    if send_in_app:
        notification = Notification.objects.create(
            recipient=staff,
            title=f"{urgency_prefix}Direct Message from {sender_name}",
            message=f"Task #{task.id} '{task.title}': {message_text}",
            notification_type='DIRECT_STAFF_MESSAGE',
            task=task,
        )

    # Record in Task Comments so it's transparent on the deliverable thread
    urgent_tag = " [URGENT ALERT]" if priority_urgent else ""
    TaskComment.objects.create(
        task=task,
        author=sender_user,
        content=f"💬 [DIRECT MESSAGE PUSHED TO {staff_name}]{urgent_tag}:\n\"{message_text}\""
    )

    # Dispatch mobile push notification to staff devices
    try:
        staff_tokens = list(staff.devices.filter(is_active=True).values_list('device_token', flat=True))
        if staff_tokens:
            send_expo_push_notification(
                tokens=staff_tokens,
                title=f"{urgency_prefix}Direct Message from {sender_name}",
                body=f"Task #{task.id} '{task.title}': {message_text}",
                data={
                    'taskId': task.id,
                    'type': 'DIRECT_STAFF_MESSAGE',
                    'is_urgent': priority_urgent,
                }
            )
    except Exception as staff_push_err:
        print(f"[ExpoPush] Staff message push error: {staff_push_err}")

    # Activity log
    log_activity(
        user=sender_user,
        action="PUSHED_MESSAGE_TO_STAFF",
        details=f"Pushed direct message to {staff_name} on task '{task.title}': '{message_text[:80]}...'",
        department=task.department,
        task=task
    )

    return {
        'staff_id': staff.id,
        'staff_name': staff_name,
        'staff_email': staff.email,
        'email_sent': send_email,
        'in_app_sent': send_in_app,
        'is_urgent': priority_urgent,
        'notification_id': notification.id if notification else None,
        'email_log_id': email_log.id if email_log else None,
        'timestamp': formatted_time,
    }


def dispatch_hourly_work_reminders(user=None, enforce_work_hours=False):
    """
    Dispatches 1-hour recurring work check-in reminder during working hours (9:00 AM to 6:00 PM).
    If user has urgent or due date tasks, the push notification explicitly highlights them!
    """
    now_local = timezone.localtime(timezone.now())
    if enforce_work_hours and not (9 <= now_local.hour <= 18):
        print(f"[HourlyReminder] Outside working hours (Current hour: {now_local.hour}:00). Reminders run between 9:00 AM and 6:00 PM.")
        return 0

    if user:
        recipients = [user]
    else:
        recipients = list(User.objects.filter(is_active=True))

    today = timezone.now().date()
    count = 0

    for r in recipients:
        try:
            active_tasks = Task.objects.filter(assigned_to=r).exclude(status=Task.STATUS_CLOSED)
            urgent_or_due = active_tasks.filter(
                Q(priority=Task.PRIORITY_URGENT) | Q(due_date__lte=today)
            ).order_by('due_date')

            urgent_count = urgent_or_due.count()
            if urgent_count > 0:
                top_task = urgent_or_due.first()
                if top_task.due_date and top_task.due_date < today:
                    tag = f"OVERDUE by {(today - top_task.due_date).days}d"
                elif top_task.due_date and top_task.due_date == today:
                    tag = "DUE TODAY"
                else:
                    tag = "URGENT PRIORITY"

                subject = f"🚨 [9AM-6PM Check-In] {urgent_count} Urgent / Due Deliverable(s)"
                body = (
                    f"Hello {r.get_full_name() or r.username},\n\n"
                    f"This is your hourly work check-in (9:00 AM – 6:00 PM Work Hours).\n\n"
                    f"⚠️ ATTENTION - PENDING URGENT DELIVERABLE:\n"
                    f"• Task: #{top_task.id} '{top_task.title}'\n"
                    f"• Department: {top_task.department.name} ({top_task.department.code})\n"
                    f"• Priority: {top_task.get_priority_display()}\n"
                    f"• Due Date: {top_task.due_date or 'Immediate'}\n"
                    f"• Status Notice: {tag}\n\n"
                    f"Total urgent / due tasks waiting: {urgent_count}.\n"
                    f"Please review and submit your progress updates on NextUp."
                )
                event_type = 'HOURLY_WORK_REMINDER'
                notif_title = f"🚨 [Urgent Task Due] #{top_task.id} {top_task.title}"
                top_task_obj = top_task
            else:
                subject = "⏰ Hourly Work Check-In (9:00 AM – 6:00 PM)"
                body = (
                    f"Hello {r.get_full_name() or r.username},\n\n"
                    f"This is your continuous 1-hour work check-in reminder (9:00 AM - 6:00 PM).\n"
                    f"Please keep your active tasks, progress reports, and deliverables current."
                )
                event_type = 'HOURLY_WORK_REMINDER'
                notif_title = "⏰ 1-Hour Work Check-In (9 AM - 6 PM)"
                top_task_obj = None

            dispatch_email_and_notification(
                recipient=r,
                subject=subject,
                body=body,
                event_type=event_type,
                task=top_task_obj,
                title=notif_title,
            )
            count += 1
        except Exception as e:
            print(f"Error dispatching hourly reminder to {r}: {e}")

    return count


def dispatch_daily_9am_work_reminders(user=None):
    """Backward-compatible alias for dispatch_hourly_work_reminders"""
    return dispatch_hourly_work_reminders(user=user)


def dispatch_urgent_and_due_date_reminders(user=None):
    """
    Specifically scans and dispatches push notifications and emails for tasks
    that are marked as URGENT priority, or have a due date of TODAY or are OVERDUE.
    """
    today = timezone.now().date()
    tomorrow = today + timezone.timedelta(days=1)

    tasks_qs = Task.objects.exclude(status=Task.STATUS_CLOSED).filter(
        Q(priority=Task.PRIORITY_URGENT) |
        Q(due_date__isnull=False, due_date__lte=tomorrow)
    ).select_related('assigned_to', 'department', 'created_by')

    if user:
        tasks_qs = tasks_qs.filter(assigned_to=user)

    dispatched = 0
    items = []

    for task in tasks_qs:
        assignee = task.assigned_to
        if not assignee:
            continue

        if task.due_date and task.due_date < today:
            diff = (today - task.due_date).days
            headline = f"🚨 [OVERDUE BY {diff}D] '{task.title}'"
            urgency = "OVERDUE"
        elif task.due_date and task.due_date == today:
            headline = f"⚠️ [DUE TODAY] '{task.title}'"
            urgency = "DUE_TODAY"
        else:
            headline = f"🚨 [URGENT DELIVERABLE] '{task.title}'"
            urgency = "URGENT"

        body = (
            f"Hello {assignee.get_full_name() or assignee.username},\n\n"
            f"⚠️ URGENT TASK REMINDER:\n"
            f"• Deliverable: #{task.id} {task.title}\n"
            f"• Department: {task.department.name} ({task.department.code})\n"
            f"• Priority: {task.get_priority_display()}\n"
            f"• Target Deadline: {task.due_date or 'Immediate'}\n"
            f"• Status: {task.get_status_display()}\n\n"
            f"Please prioritize this task and submit your deliverables before 6:00 PM."
        )

        try:
            dispatch_email_and_notification(
                recipient=assignee,
                subject=f"{headline} [{task.department.code}]",
                body=body,
                event_type='URGENT_TASK_REMINDER',
                task=task,
                title=headline,
            )
            dispatched += 1
            items.append({
                'task_id': task.id,
                'title': task.title,
                'urgency': urgency,
                'due_date': str(task.due_date) if task.due_date else None,
                'assigned_to': assignee.username,
            })
        except Exception as e:
            print(f"[UrgentReminder] Error dispatching to {assignee}: {e}")

    return {
        'count': dispatched,
        'tasks': items,
    }
