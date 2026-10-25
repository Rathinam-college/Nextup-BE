import threading
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from .models import Notification, DispatchedEmailLog, ActivityLog, User, Task, TaskComment


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


def dispatch_hourly_work_reminders(user=None):
    """
    Dispatches continuous 1-hour recurring work update reminder:
    '⏰ Hourly Work Update Reminder: Please update your work report and active task deliverables.'
    Creates in-app notification and email audit log.
    """
    if user:
        recipients = [user]
    else:
        recipients = list(User.objects.filter(is_active=True))

    subject = "⏰ Hourly Work Update Reminder"
    body = (
        "Hello!\n\n"
        "This is your continuous 1-hour work check-in reminder. Please update your current task progress, "
        "review pending deliverables, and update your work reports in the Rathinam Task Tracker workspace."
    )

    count = 0
    for r in recipients:
        try:
            dispatch_email_and_notification(
                recipient=r,
                subject=subject,
                body=body,
                event_type='HOURLY_WORK_REMINDER',
                title=subject,
            )
            count += 1
        except Exception as e:
            print(f"Error dispatching hourly reminder to {r}: {e}")

    return count


def dispatch_daily_9am_work_reminders(user=None):
    """
    Dispatches work update reminder. Forwarded to dispatch_hourly_work_reminders.
    """
    return dispatch_hourly_work_reminders(user=user)



