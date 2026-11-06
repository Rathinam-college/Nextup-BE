import base64
import html
import json
import os
import re
import time
import uuid
import threading
from urllib.parse import unquote
import requests
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from django.db.models import Q
from .models import Notification, DispatchedEmailLog, ActivityLog, User, Task, TaskComment, UserDevice, UserSessionLog

try:
    import zoneinfo
except ImportError:
    from backports import zoneinfo


def get_india_current_time():
    """Returns the current datetime in India Standard Time (Asia/Kolkata)."""
    try:
        india_tz = zoneinfo.ZoneInfo('Asia/Kolkata')
    except Exception:
        import pytz
        india_tz = pytz.timezone('Asia/Kolkata')
    return timezone.now().astimezone(india_tz)


def is_within_india_work_hours():
    """
    Checks if current India Standard Time (IST) is strictly within
    the 9:00 AM to 6:00 PM working window (09:00 through 18:00 IST).
    """
    now_ist = get_india_current_time()
    total_minutes = now_ist.hour * 60 + now_ist.minute
    return 540 <= total_minutes <= 1080  # 9:00 AM (540m) to 6:00 PM (1080m)


def parse_attachments_list(raw_value):
    """
    Parses a stored attachment_image field into a clean list of URLs/paths.
    Supports JSON arrays, newline/comma-separated strings, and single URLs.
    """
    if not raw_value:
        return []
    val = raw_value.strip() if isinstance(raw_value, str) else ''
    if not val:
        return []
    if val.startswith('[') and val.endswith(']'):
        try:
            parsed = json.loads(val)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
        except Exception:
            pass
    if '\n' in val:
        return [x.strip() for x in val.split('\n') if x.strip()]
    if ',' in val:
        return [x.strip() for x in val.split(',') if x.strip()]
    return [val]


def serialize_attachments_list(attachments_list):
    """
    Serializes a list of attachment URLs into a single string for storage.
    Filters out duplicates and empty strings.
    """
    if not attachments_list:
        return ''
    clean_list = []
    for item in attachments_list:
        if isinstance(item, str) and item.strip() and item.strip() not in clean_list:
            clean_list.append(item.strip())
    if not clean_list:
        return ''
    return json.dumps(clean_list)


def save_task_attachment_image(image_input, task_id=None):
    """
    Saves an uploaded file or image (Base64 data URI, raw base64, or UploadedFile)
    into the server media folder: media/task_attachments/
    and returns its clean URL path: /media/task_attachments/<filename>.
    
    Supports:
    - Photos & Images: .jpg, .jpeg, .png, .webp, .gif
    - Documents: .pdf
    - Spreadsheets: .xlsx, .xls, .csv
    - Documents: .docx, .doc, .txt
    
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

    allowed_exts = ['.jpg', '.jpeg', '.png', '.webp', '.gif', '.pdf', '.xlsx', '.xls', '.csv', '.ppt', '.pptx', '.doc', '.docx', '.txt']

    # Case 1: UploadedFile (multipart/form-data upload)
    if hasattr(image_input, 'read') and hasattr(image_input, 'name'):
        ext = os.path.splitext(image_input.name)[1].lower() or '.jpg'
        if ext not in allowed_exts:
            if 'pdf' in ext:
                ext = '.pdf'
            elif 'pptx' in ext or 'presentation' in ext or 'powerpoint' in ext:
                ext = '.pptx'
            elif 'ppt' in ext:
                ext = '.ppt'
            elif 'xls' in ext or 'sheet' in ext:
                ext = '.xlsx'
            elif 'csv' in ext:
                ext = '.csv'
            else:
                ext = '.jpg'
        filename = f"{id_prefix}_{timestamp}_{unique_suffix}{ext}"
        file_path = os.path.join(target_dir, filename)
        try:
            with open(file_path, 'wb+') as dest:
                for chunk in image_input.chunks():
                    dest.write(chunk)
            return f"/media/task_attachments/{filename}"
        except Exception as e:
            print(f"⚠️ Error saving UploadedFile: {e}")
            return ""

    # Case 2: Base64 String (data:...;base64,...)
    if isinstance(image_input, str):
        data_str = image_input.strip()
        ext = '.jpg'
        base64_content = data_str

        # Parse data URL scheme e.g. "data:application/pdf;base64,...", "data:application/pdf;name=myfile.pdf;base64,..."
        # or "data:image/png;base64,..."
        header_match = re.match(r'^data:([^;]+)(?:;name=([^;]+))?;base64,(.+)$', data_str, re.DOTALL)
        if not header_match:
            header_match = re.match(r'^data:([^,]+),(.+)$', data_str, re.DOTALL)

        if header_match:
            mime = header_match.group(1).lower()
            orig_name = header_match.group(2) if len(header_match.groups()) >= 3 and header_match.group(2) else ''
            base64_content = header_match.group(header_match.lastindex)

            # Try to resolve ext from filename if provided
            if orig_name:
                orig_ext = os.path.splitext(unquote(orig_name))[1].lower()
                if orig_ext in allowed_exts:
                    ext = orig_ext

            if ext == '.jpg':
                if 'pdf' in mime:
                    ext = '.pdf'
                elif 'presentation' in mime or 'powerpoint' in mime or 'pptx' in mime:
                    ext = '.pptx'
                elif 'ppt' in mime:
                    ext = '.ppt'
                elif 'spreadsheet' in mime or 'xlsx' in mime or 'openxmlformats' in mime:
                    ext = '.xlsx'
                elif 'ms-excel' in mime or 'xls' in mime:
                    ext = '.xls'
                elif 'csv' in mime:
                    ext = '.csv'
                elif 'png' in mime:
                    ext = '.png'
                elif 'webp' in mime:
                    ext = '.webp'
                elif 'gif' in mime:
                    ext = '.gif'
                elif 'word' in mime or 'docx' in mime:
                    ext = '.docx'
                elif 'jpeg' in mime or 'jpg' in mime:
                    ext = '.jpg'
                elif 'text/plain' in mime:
                    ext = '.txt'
                elif 'application' in mime:
                    ext = '.pdf'
        elif data_str.startswith('data:') and ';base64,' in data_str:
            parts = data_str.split(';base64,', 1)
            base64_content = parts[1]

        try:
            file_bytes = base64.b64decode(base64_content)
            filename = f"{id_prefix}_{timestamp}_{unique_suffix}{ext}"
            file_path = os.path.join(target_dir, filename)
            with open(file_path, 'wb') as f:
                f.write(file_bytes)
            return f"/media/task_attachments/{filename}"
        except Exception as e:
            print(f"⚠️ Error decoding and saving base64 attachment: {e}")
            return data_str

    return ""



def build_branded_html_email(
    title,
    recipient_name,
    badge_text=None,
    badge_variant='primary',
    headline=None,
    intro_lines=None,
    details_dict=None,
    description_text=None,
    notes_callout=None,
    action_url="https://www.rguedu.in/nextup/",
    action_text="Open NextUp Portal",
    closing_text=None,
):
    """
    Constructs a responsive, cross-client HTML email template with NextUp and Rathinam logos,
    modern card layout, semantic badges, structured specifications, and clean footers.
    Compatible with Gmail (web/app), Outlook, Apple Mail, and mobile email clients.
    """
    safe_recipient = html.escape(str(recipient_name or "Team Member"))
    safe_title = html.escape(str(title or "NextUp Notification"))
    safe_headline = html.escape(str(headline or title or "NextUp Notification"))

    # Semantic badge styling
    badge_styles = {
        'urgent': 'background-color: #FEE2E2; color: #991B1B; border: 1px solid #FECACA;',
        'warning': 'background-color: #FEF3C7; color: #92400E; border: 1px solid #FDE68A;',
        'success': 'background-color: #DCFCE7; color: #166534; border: 1px solid #BBF7D0;',
        'purple': 'background-color: #EDE9FE; color: #6D28D9; border: 1px solid #DDD6FE;',
        'primary': 'background-color: #E0F2FE; color: #0369A1; border: 1px solid #BAE6FD;',
        'slate': 'background-color: #F1F5F9; color: #334155; border: 1px solid #CBD5E1;',
    }
    badge_style = badge_styles.get(badge_variant, badge_styles['primary'])

    badge_html = ""
    if badge_text:
        safe_badge = html.escape(str(badge_text))
        badge_html = f"""
        <div style="margin-bottom: 16px;">
          <span style="display: inline-block; padding: 5px 14px; border-radius: 9999px; font-size: 11px; font-weight: 700; letter-spacing: 0.6px; text-transform: uppercase; {badge_style}">
            {safe_badge}
          </span>
        </div>
        """

    # Intro paragraphs
    intro_html = ""
    if intro_lines:
        for line in intro_lines:
            line_str = str(line).strip()
            if line_str:
                intro_html += f"""<p style="margin: 0 0 14px 0; font-size: 15px; color: #334155; line-height: 1.6;">{line_str}</p>"""

    # Structured details table
    details_html = ""
    if details_dict and len(details_dict) > 0:
        rows_html = ""
        valid_items = [it for it in details_dict if (isinstance(it, (list, tuple)) and len(it) >= 2) or isinstance(it, dict)]
        for i, item in enumerate(valid_items):
            if isinstance(item, (list, tuple)):
                k, v = item[0], item[1]
            else:
                k = item.get('label') or item.get('key') or ''
                v = item.get('value') or ''

            k_safe = html.escape(str(k))
            v_raw = str(v)
            v_safe = html.escape(v_raw)

            # Auto-highlight pills for priority, overdue, or due today
            v_styled = v_safe
            upper_raw = v_raw.upper()
            if 'URGENT' in upper_raw or 'OVERDUE' in upper_raw:
                v_styled = f"""<span style="display: inline-block; background-color: #FEE2E2; color: #991B1B; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 700; border: 1px solid #FECACA;">{v_safe}</span>"""
            elif 'DUE TODAY' in upper_raw or 'HIGH' in upper_raw or 'WARNING' in upper_raw:
                v_styled = f"""<span style="display: inline-block; background-color: #FEF3C7; color: #92400E; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 700; border: 1px solid #FDE68A;">{v_safe}</span>"""
            elif 'CLOSED' in upper_raw or 'VERIFIED' in upper_raw or 'COMPLETE' in upper_raw or 'ONLINE' in upper_raw:
                v_styled = f"""<span style="display: inline-block; background-color: #DCFCE7; color: #166534; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 700; border: 1px solid #BBF7D0;">{v_safe}</span>"""

            border_bottom = "border-bottom: 1px solid #E2E8F0;" if i < len(valid_items) - 1 else ""
            rows_html += f"""
            <tr>
              <td style="padding: 10px 14px; font-size: 13px; font-weight: 600; color: #64748B; width: 34%; vertical-align: top; {border_bottom}">
                {k_safe}
              </td>
              <td style="padding: 10px 14px; font-size: 13px; font-weight: 600; color: #0F172A; width: 66%; vertical-align: top; {border_bottom}">
                {v_styled}
              </td>
            </tr>
            """

        details_html = f"""
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin: 18px 0; background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; border-collapse: separate; overflow: hidden;">
          {rows_html}
        </table>
        """

    # Description callout
    desc_html = ""
    if description_text and str(description_text).strip():
        safe_desc = html.escape(str(description_text).strip())
        desc_html = f"""
        <div style="margin: 18px 0; background-color: #F8FAFC; border-left: 4px solid #0284C7; border-radius: 4px; padding: 14px 16px;">
          <div style="font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.6px; color: #0284C7; margin-bottom: 6px;">
            Task Description & Instructions
          </div>
          <div style="font-size: 14px; color: #334155; line-height: 1.6; white-space: pre-wrap;">{safe_desc}</div>
        </div>
        """

    # Notes / remarks callout (e.g. GM feedback or direct message)
    notes_html = ""
    if notes_callout and str(notes_callout).strip():
        safe_notes = html.escape(str(notes_callout).strip())
        notes_html = f"""
        <div style="margin: 18px 0; background-color: #FEFCE8; border: 1px solid #FEF08A; border-left: 4px solid #CA8A04; border-radius: 4px; padding: 14px 16px;">
          <div style="font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.6px; color: #A16207; margin-bottom: 6px;">
            Remarks / Direct Message
          </div>
          <div style="font-size: 14px; color: #713F12; line-height: 1.6; font-style: italic;">"{safe_notes}"</div>
        </div>
        """

    # CTA Button
    cta_html = ""
    if action_url:
        safe_action_url = html.escape(str(action_url))
        safe_action_text = html.escape(str(action_text or "Open NextUp Portal"))
        cta_html = f"""
        <div style="margin: 28px 0 16px 0; text-align: center;">
          <a href="{safe_action_url}" target="_blank" style="display: inline-block; background-color: #0284C7; background: linear-gradient(135deg, #0284C7 0%, #0369A1 100%); color: #FFFFFF !important; text-decoration: none; font-size: 14px; font-weight: 700; padding: 13px 32px; border-radius: 8px; letter-spacing: 0.3px; box-shadow: 0 3px 10px rgba(2, 132, 199, 0.35);">
            {safe_action_text} &rarr;
          </a>
        </div>
        """

    # Closing text
    safe_closing = html.escape(str(closing_text or "Please ensure deliverables are planned and tracked according to this timeline on the NextUp portal."))
    now_ist_str = get_india_current_time().strftime('%d-%b-%Y %I:%M %p')

    # Full Email HTML Template with NextUp Logo & Rathinam Logo
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="X-UA-Compatible" content="IE=edge">
  <title>{safe_title}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #F1F5F9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; -webkit-font-smoothing: antialiased; -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color: #F1F5F9; padding: 24px 12px;">
    <tr>
      <td align="center">
        <!-- Main Container Card -->
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width: 600px; background-color: #FFFFFF; border-radius: 12px; overflow: hidden; border: 1px solid #E2E8F0; box-shadow: 0 4px 18px rgba(15, 23, 42, 0.06); border-collapse: separate;">
          
          <!-- Header Bar with Logos -->
          <tr>
            <td style="background-color: #0F172A; background: linear-gradient(135deg, #0F172A 0%, #1E293B 100%); padding: 22px 28px; border-radius: 12px 12px 0 0;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <!-- Left: NextUp Logo -->
                  <td align="left" valign="middle" style="padding-right: 12px;">
                    <a href="https://www.rguedu.in/nextup/" target="_blank" style="text-decoration: none; display: inline-block;">
                      <table role="presentation" cellpadding="0" cellspacing="0" border="0">
                        <tr>
                          <td valign="middle">
                            <img src="https://www.rguedu.in/nextup/nextup-logo.png" alt="NextUp" height="38" style="height: 38px; max-height: 38px; width: auto; max-width: 170px; display: block; border: 0;" />
                          </td>
                        </tr>
                      </table>
                    </a>
                  </td>
                  <!-- Right: Rathinam Logo -->
                  <td align="right" valign="middle">
                    <a href="https://rathinamcollege.edu.in/" target="_blank" style="text-decoration: none; display: inline-block;">
                      <img src="https://www.rguedu.in/nextup/rathinam-logo.png" alt="Rathinam Group" height="32" style="height: 32px; max-height: 32px; width: auto; max-width: 140px; display: block; border: 0; opacity: 0.9;" />
                    </a>
                  </td>
                </tr>
                <tr>
                  <td colspan="2" style="padding-top: 10px;">
                    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 11px; font-weight: 600; letter-spacing: 0.8px; text-transform: uppercase; color: #94A3B8;">
                      Enterprise Workflow & Productivity Platform
                    </div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Email Content Body -->
          <tr>
            <td style="padding: 28px 28px 24px 28px;">
              {badge_html}

              <h1 style="margin: 0 0 16px 0; font-size: 20px; font-weight: 700; color: #0F172A; line-height: 1.35;">
                {safe_headline}
              </h1>

              <p style="margin: 0 0 14px 0; font-size: 15px; color: #334155; line-height: 1.6;">
                Hello <strong>{safe_recipient}</strong>,
              </p>

              {intro_html}

              {details_html}

              {desc_html}

              {notes_html}

              {cta_html}

              <p style="margin: 22px 0 0 0; font-size: 13px; color: #64748B; line-height: 1.5;">
                {safe_closing}
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background-color: #F8FAFC; border-top: 1px solid #E2E8F0; border-radius: 0 0 12px 12px; padding: 18px 28px; text-align: center;">
              <p style="margin: 0 0 6px 0; font-size: 12px; font-weight: 700; color: #475569;">
                NextUp • Rathinam Group of Institutions
              </p>
              <p style="margin: 0 0 6px 0; font-size: 11px; color: #94A3B8;">
                Eachanari, Coimbatore, Tamil Nadu 641021
              </p>
              <p style="margin: 0; font-size: 11px; color: #CBD5E1;">
                Dispatched: {now_ist_str} IST • Automated operational notification • Please do not reply directly
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def render_plain_body_to_html(subject, body, recipient_name="Team Member", event_type=None, task=None):
    """
    Fallback parser that converts arbitrary plain-text email content into the
    NextUp branded HTML template, ensuring 100% of outgoing emails have the logo and design.
    """
    lower_subject = (subject or "").lower()
    lower_event = (event_type or "").lower()

    if 'urgent' in lower_subject or 'urgent' in lower_event or 'overdue' in lower_subject:
        badge_variant = 'urgent'
        badge_text = "🚨 URGENT DELIVERABLE"
    elif 'timeline' in lower_subject or 'timeline' in lower_event or 'reminder' in lower_subject:
        badge_variant = 'warning'
        badge_text = "⏰ TIMELINE REMINDER"
    elif 'verified' in lower_subject or 'approved' in lower_event or 'closed' in lower_subject:
        badge_variant = 'success'
        badge_text = "✅ TASK VERIFIED & CLOSED"
    elif 'check-in' in lower_subject or 'hourly' in lower_event:
        badge_variant = 'purple'
        badge_text = "⏰ HOURLY WORK CHECK-IN"
    elif 'comment' in lower_event or 'note' in lower_subject:
        badge_variant = 'primary'
        badge_text = "💬 WORKSPACE NOTE"
    else:
        badge_variant = 'primary'
        badge_text = "📋 NEXTUP NOTIFICATION"

    lines = (body or "").split('\n')
    intro_lines = []
    details_dict = []
    desc_lines = []
    in_desc = False

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        # Skip horizontal dividers
        if set(line).issubset({'━', '-', '=', '_', '*'}) and len(line) >= 4:
            continue
        # Skip redundant greetings as template provides it
        if line.lower().startswith('hello ') and (',' in line or len(line) < 40):
            continue
        # Skip sign-offs covered by branded footer
        if line.lower().startswith('best regards') or line.lower().startswith('thank you'):
            continue
        if 'tasktracker enterprise' in line.lower() or 'nextup enterprise' in line.lower():
            continue

        if line.lower().startswith('description:') or line.lower().startswith('task description:'):
            in_desc = True
            continue

        if in_desc:
            desc_lines.append(line)
            continue

        # Check for bullet points: "• Key: Value" or "- Key: Value"
        bullet_match = re.match(r'^[•\-\*]\s*([^:]+):\s*(.*)$', line)
        if bullet_match:
            details_dict.append((bullet_match.group(1).strip(), bullet_match.group(2).strip()))
            continue

        intro_lines.append(html.escape(line))

    description_text = "\n".join(desc_lines).strip() if desc_lines else None

    # Enrich from task object if available and no bullet points found
    if task and not details_dict:
        details_dict.append(("Task Title", task.title))
        if task.department:
            details_dict.append(("Department", f"{task.department.name} ({task.department.code})"))
        details_dict.append(("Priority", task.get_priority_display()))
        details_dict.append(("Target Timeline", format_timeline_text(task.due_date)))
        details_dict.append(("Status", task.get_status_display()))

    return build_branded_html_email(
        title=subject,
        recipient_name=recipient_name,
        badge_text=badge_text,
        badge_variant=badge_variant,
        headline=subject,
        intro_lines=intro_lines if intro_lines else None,
        details_dict=details_dict if details_dict else None,
        description_text=description_text,
        action_url="https://www.rguedu.in/nextup/",
        action_text="Open NextUp Portal"
    )


def _async_send_mail(subject, body, from_email, recipient_email, html_body=None):
    """Worker function executed in background thread to avoid blocking concurrent web requests."""
    try:
        # Cross-worker credential sync: load from email_config.json if worker memory lacks password
        if not getattr(settings, 'EMAIL_HOST_PASSWORD', ''):
            json_path = settings.BASE_DIR / 'email_config.json'
            if json_path.exists():
                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        cfg = json.load(f)
                        if cfg.get('email_host_user'):
                            settings.EMAIL_HOST_USER = cfg['email_host_user'].strip()
                        if cfg.get('email_host_password'):
                            settings.EMAIL_HOST_PASSWORD = cfg['email_host_password'].strip()
                            settings.EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
                        if cfg.get('email_host'):
                            settings.EMAIL_HOST = cfg['email_host'].strip()
                        if cfg.get('email_port'):
                            settings.EMAIL_PORT = int(cfg['email_port'])
                        if 'email_use_tls' in cfg:
                            settings.EMAIL_USE_TLS = bool(cfg['email_use_tls'])
                except Exception:
                    pass

        sender = getattr(settings, 'EMAIL_HOST_USER', '') or getattr(settings, 'DEFAULT_FROM_EMAIL', '') or from_email
        if not recipient_email or '@tasktracker.enterprise' in recipient_email:
            print(f"[Email] Skipping non-routable simulation recipient: {recipient_email}")
            return
        send_mail(
            subject=subject,
            message=body,
            from_email=sender,
            recipient_list=[recipient_email],
            fail_silently=False,
            html_message=html_body,
        )
        print(f"[Email] Successfully dispatched branded email to {recipient_email}")
    except Exception as e:
        print(f"⚠️ Email dispatch notification error for {recipient_email}: {e}")



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

def dispatch_email_and_notification(recipient, subject, body, event_type, task=None, title=None, push_title=None, push_body=None, push_data=None, html_body=None):
    """
    Sends email via background thread, records it in DispatchedEmailLog,
    creates an in-app Notification, and dispatches a rich push notification
    containing ALL task details directly to mobile devices.
    Guarantees responsive HTML email template with NextUp and Rathinam logos.
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

    # Automatically construct branded HTML email if not explicitly provided
    final_html_body = html_body
    if not final_html_body:
        rec_name = (recipient.get_full_name() or recipient.username) if recipient else "Team Member"
        final_html_body = render_plain_body_to_html(
            subject=subject,
            body=body,
            recipient_name=rec_name,
            event_type=event_type,
            task=task
        )

    # Non-blocking async dispatch: spawns background thread so HTTP worker immediately returns
    threading.Thread(
        target=_async_send_mail,
        args=(subject, body, from_email, recipient.email, final_html_body),
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

    # Determine rich push notification title and body with ALL task details
    final_push_title = push_title or notif_title

    if push_body:
        final_push_body = push_body
    elif task:
        due_str = str(task.due_date) if task.due_date else "Flexible timeline"
        dept_str = f"{task.department.name} ({task.department.code})" if task.department else "General"
        priority_str = task.get_priority_display()
        status_str = task.get_status_display()
        raw_desc = (task.description or "").strip()
        clean_desc = re.sub(r'<!--.*?-->', '', raw_desc).strip()
        if len(clean_desc) > 180:
            clean_desc = clean_desc[:180] + "..."
        if not clean_desc:
            clean_desc = "No additional instructions provided."

        assigned_by_str = ""
        if hasattr(task, 'created_by') and task.created_by:
            assigned_by_str = f" • By: {task.created_by.get_full_name() or task.created_by.username}"

        final_push_body = (
            f"🎯 Priority: {priority_str} • 📅 Due: {due_str}\n"
            f"🏢 Dept: {dept_str}{assigned_by_str} • 📊 {status_str}\n"
            f"📝 {clean_desc}"
        )
    else:
        final_push_body = body[:240]

    merged_push_data = {
        'taskId': task.id if task else None,
        'type': event_type,
        'notificationId': notification.id,
    }
    if task:
        merged_push_data.update({
            'title': task.title,
            'priority': task.priority,
            'department': task.department.code if task.department else 'General',
            'dueDate': str(task.due_date) if task.due_date else '',
            'status': task.status,
            'description': task.description or '',
            'is_urgent': (task.priority == Task.PRIORITY_URGENT),
        })
    if push_data and isinstance(push_data, dict):
        merged_push_data.update(push_data)

    # Dispatch native mobile push notification to recipient's active devices
    try:
        active_tokens = list(recipient.devices.filter(is_active=True).values_list('device_token', flat=True))
        if active_tokens:
            send_expo_push_notification(
                tokens=active_tokens,
                title=final_push_title,
                body=final_push_body,
                data=merged_push_data
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
    # If explicitly flagged as GM own task
    if getattr(task, 'is_gm_own_task', False):
        # But if assigned to a regular staff member, it is a delegated task to staff, not a private GM task
        if task.assigned_to and getattr(task.assigned_to, 'role', '') not in [User.ROLE_GENERAL_MANAGER, User.ROLE_SUPER_ADMIN]:
            return False
        return True
    if task.assigned_to and getattr(task.assigned_to, 'role', '') in [User.ROLE_GENERAL_MANAGER, User.ROLE_SUPER_ADMIN]:
        # Only GM own task if there are NO co-assigned team members
        if '<!-- CO_ASSIGN_TEAM:' not in (getattr(task, 'description', '') or ''):
            return True
    return False


def get_task_target_recipients(task):
    """
    Strict Task Isolation:
    Returns ONLY the directly assigned individual and explicitly co-assigned team members.
    Never broadcasts or shares task alerts with other department members or managers.
    """
    recipients = set()
    if task.assigned_to and task.assigned_to.is_active:
        recipients.add(task.assigned_to)

    import json
    match = re.search(r'<!-- CO_ASSIGN_TEAM:(.*?) -->', task.description or '')
    if match:
        try:
            team_info = json.loads(match.group(1))
            for item in team_info:
                assigned_to_id = item.get('assignedToId') or item.get('staffId')
                if assigned_to_id:
                    co_user = User.objects.filter(id=assigned_to_id, is_active=True).first()
                    if co_user:
                        recipients.add(co_user)
        except Exception:
            pass
    return recipients


def notify_task_assigned(task, assigned_by):
    # GM Own Task: Never send notification or email to anyone
    if is_gm_own_task(task):
        return

    # Strictly notify only the assigned person and explicitly co-assigned team members
    recipients = get_task_target_recipients(task)
    if not recipients and task.assigned_to and task.assigned_to.is_active:
        recipients = {task.assigned_to}

    timeline_str = format_timeline_text(task.due_date)
    subject_prefix = f"[{task.department.code}]" if (task.department and getattr(task.department, 'code', None)) else "[NextUp]"
    if task.due_date:
        subject = f"✉️ {subject_prefix} New Task & Timeline: '{task.title}' (Due: {task.due_date})"
    else:
        subject = f"✉️ {subject_prefix} New Task Assigned: '{task.title}'"

    assigned_by_name = (assigned_by.get_full_name() or assigned_by.username) if assigned_by else "Management"
    due_str = str(task.due_date) if task.due_date else "Flexible timeline"
    dept_str = f"{task.department.name} ({task.department.code})" if task.department else "General"
    priority_str = task.get_priority_display()
    status_str = task.get_status_display()

    # Clean description for mobile push notification
    raw_desc = (task.description or "").strip()
    clean_desc = re.sub(r'<!--.*?-->', '', raw_desc).strip()
    if len(clean_desc) > 200:
        clean_desc = clean_desc[:200] + "..."
    if not clean_desc:
        clean_desc = "No additional instructions provided."

    push_title = f"📋 New Task Assigned: {task.title}"
    if task.priority == Task.PRIORITY_URGENT:
        push_title = f"🚨 [URGENT TASK] {task.title}"

    push_body = (
        f"🎯 Priority: {priority_str} • 📅 Due: {due_str}\n"
        f"🏢 Dept: {dept_str} • 👤 By: {assigned_by_name}\n"
        f"📝 {clean_desc}"
    )

    is_urgent = (task.priority == Task.PRIORITY_URGENT)
    badge_variant = 'urgent' if is_urgent else 'primary'
    badge_text = "🚨 URGENT TASK ASSIGNED" if is_urgent else "📋 NEW TASK ASSIGNMENT"

    for rec in recipients:
        is_assignee = (task.assigned_to and rec.id == task.assigned_to.id)
        role_note = "You have been assigned to" if is_assignee else f"Staff member '{task.assigned_to.get_full_name() if task.assigned_to else 'Unassigned'}' was assigned to"

        body = (
            f"Hello {rec.get_full_name() or rec.username},\n\n"
            f"{role_note} task '{task.title}' by {assigned_by_name}.\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📋 TASK TIMELINE & SPECIFICATIONS:\n"
            f"• Department: {dept_str}\n"
            f"• Priority: {priority_str}\n"
            f"• Target Timeline / Due Date: {timeline_str}\n"
            f"• Current Status: {status_str}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Description:\n{clean_desc}\n\n"
            f"Please ensure deliverables are planned and tracked according to this timeline on the NextUp portal.\n\n"
            f"Best regards,\nNextUp • Rathinam Group of Institutions"
        )

        details_dict = [
            ("Department", dept_str),
            ("Priority", priority_str),
            ("Target Timeline", timeline_str),
            ("Current Status", status_str),
            ("Assigned By", assigned_by_name),
        ]
        if not is_assignee and task.assigned_to:
            details_dict.insert(3, ("Assigned Staff", task.assigned_to.get_full_name() or task.assigned_to.username))

        html_body = build_branded_html_email(
            title=subject,
            recipient_name=rec.get_full_name() or rec.username,
            badge_text=badge_text,
            badge_variant=badge_variant,
            headline=f"Task Assignment: {task.title}",
            intro_lines=[
                f"{role_note} task <strong>'{html.escape(task.title)}'</strong> by <strong>{html.escape(assigned_by_name)}</strong>."
            ],
            details_dict=details_dict,
            description_text=clean_desc,
            action_url="https://www.rguedu.in/nextup/",
            action_text="View Task in NextUp Portal",
            closing_text="Please ensure deliverables are planned and tracked according to this timeline on the NextUp portal."
        )

        dispatch_email_and_notification(
            recipient=rec,
            subject=subject,
            body=body,
            event_type='TASK_ASSIGNED',
            task=task,
            title=f"Task Assigned: {task.title} (Due: {task.due_date or 'Flexible'})",
            push_title=push_title,
            push_body=push_body,
            html_body=html_body,
        )


def notify_task_timeline_updated(task, updated_by, old_due_date):
    if is_gm_own_task(task):
        return

    # Strictly notify only assigned person and explicitly co-assigned team members
    recipients = get_task_target_recipients(task)

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
            f"Please adjust your schedule and task milestones accordingly on NextUp."
        )
        html_body = build_branded_html_email(
            title=subject,
            recipient_name=rec.get_full_name() or rec.username,
            badge_text="⏰ TIMELINE RESCHEDULED",
            badge_variant="warning",
            headline=f"Timeline Updated: {task.title}",
            intro_lines=[
                f"The target timeline for task <strong>'{html.escape(task.title)}'</strong> has been updated by <strong>{html.escape(updated_by.get_full_name() or updated_by.username)}</strong>."
            ],
            details_dict=[
                ("Task", task.title),
                ("Previous Deadline", str(old_due_date or 'Flexible / None')),
                ("New Target Timeline", timeline_str),
                ("Priority", task.get_priority_display()),
                ("Department", task.department.name if task.department else "General"),
            ],
            action_url="https://www.rguedu.in/nextup/",
            action_text="Review Updated Timeline",
            closing_text="Please adjust your schedule and milestone deliverables accordingly on NextUp."
        )
        dispatch_email_and_notification(
            recipient=rec,
            subject=subject,
            body=body,
            event_type='TIMELINE_UPDATED',
            task=task,
            title=f"Timeline Updated: {task.title} -> {task.due_date or 'Flexible'}",
            html_body=html_body,
        )


def notify_timeline_reminder(task, triggered_by=None):
    if is_gm_own_task(task):
        return []

    # Strictly notify only assigned person and explicitly co-assigned team members
    recipients = get_task_target_recipients(task)

    if not recipients:
        return []

    timeline_str = format_timeline_text(task.due_date)
    sender_note = f" sent by {triggered_by.get_full_name() or triggered_by.username}" if triggered_by else " (Automated System Reminder)"

    today = timezone.now().date()
    diff = (task.due_date - today).days if task.due_date else 999
    if diff < 0:
        prefix = "🚨 OVERDUE NOTICE"
        badge_variant = "urgent"
    elif diff == 0:
        prefix = "⚠️ DUE TODAY"
        badge_variant = "warning"
    elif diff <= 2:
        prefix = "⏰ DEADLINE APPROACHING"
        badge_variant = "warning"
    else:
        prefix = "📅 TIMELINE REMINDER"
        badge_variant = "primary"

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
            f"Please verify progress and submit completed deliverables on the NextUp portal before the deadline."
        )
        html_body = build_branded_html_email(
            title=subject,
            recipient_name=rec.get_full_name() or rec.username,
            badge_text=prefix,
            badge_variant=badge_variant,
            headline=f"{prefix}: {task.title}",
            intro_lines=[
                f"This is an operational milestone timeline reminder{html.escape(sender_note)} regarding task <strong>'{html.escape(task.title)}'</strong>."
            ],
            details_dict=[
                ("Target Deadline", timeline_str),
                ("Assigned Staff", task.assigned_to.get_full_name() if task.assigned_to else "Unassigned"),
                ("Priority", task.get_priority_display()),
                ("Current Status", task.get_status_display()),
                ("Department", f"{task.department.name} ({task.department.code})" if task.department else "General"),
            ],
            description_text=(task.description or "").strip(),
            action_url="https://www.rguedu.in/nextup/",
            action_text="Open Task in NextUp",
            closing_text="Please verify progress and submit completed deliverables on the NextUp portal before the deadline."
        )
        res = dispatch_email_and_notification(
            recipient=rec,
            subject=subject,
            body=body,
            event_type='TIMELINE_REMINDER',
            task=task,
            title=f"{prefix}: {task.title}",
            html_body=html_body,
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
        html_body = build_branded_html_email(
            title=subject,
            recipient_name=gm.get_full_name() or gm.username,
            badge_text="🔍 VERIFICATION & CLOSURE REQUEST",
            badge_variant="purple",
            headline=f"Task Awaiting Verification: {task.title}",
            intro_lines=[
                f"Task <strong>'{html.escape(task.title)}'</strong> in <strong>{html.escape(task.department.name if task.department else 'General')}</strong> has been marked complete by <strong>{html.escape(submitted_by.get_full_name() or submitted_by.username)}</strong> and is awaiting your final verification and closure sign-off."
            ],
            details_dict=[
                ("Task", task.title),
                ("Department", task.department.name if task.department else "General"),
                ("Priority", task.get_priority_display()),
                ("Assigned Staff", task.assigned_to.get_full_name() if task.assigned_to else "Unassigned"),
                ("Submitted By", submitted_by.get_full_name() or submitted_by.username),
            ],
            action_url="https://www.rguedu.in/nextup/approvals",
            action_text="Open GM Verification Hub",
            closing_text="Please log in to the GM Dashboard to review and approve or request changes."
        )
        dispatch_email_and_notification(
            recipient=gm,
            subject=subject,
            body=body,
            event_type='GM_REVIEW_REQUEST',
            task=task,
            title=f"Task Awaiting Verification: {task.title}",
            html_body=html_body,
        )


def notify_gm_approved(task, gm_user, notes=""):
    # Strictly notify only assigned person and explicitly co-assigned team members
    recipients = get_task_target_recipients(task)

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
        html_body = build_branded_html_email(
            title=subject,
            recipient_name=rec.get_full_name() or rec.username,
            badge_text="✅ TASK VERIFIED & CLOSED",
            badge_variant="success",
            headline=f"Task Verified & Closed: {task.title}",
            intro_lines=[
                f"Great news! Task <strong>'{html.escape(task.title)}'</strong> has been officially verified and closed by General Manager <strong>{html.escape(gm_user.get_full_name() or gm_user.username)}</strong>."
            ],
            details_dict=[
                ("Task", task.title),
                ("Status", "CLOSED & VERIFIED"),
                ("Closed Date", task.closed_at.strftime('%Y-%m-%d %H:%M') if task.closed_at else "Just now"),
                ("Verified By", gm_user.get_full_name() or gm_user.username),
            ],
            notes_callout=notes if notes else None,
            action_url="https://www.rguedu.in/nextup/",
            action_text="View Closed Task",
            closing_text="Thank you for your dedicated hard work and milestone completion!"
        )
        dispatch_email_and_notification(
            recipient=rec,
            subject=subject,
            body=body,
            event_type='GM_APPROVED',
            task=task,
            title=f"Task Verified & Closed: {task.title}",
            html_body=html_body,
        )


def notify_gm_changes_requested(task, gm_user, feedback_notes):
    # Strictly notify only assigned person and explicitly co-assigned team members
    recipients = get_task_target_recipients(task)

    for rec in recipients:
        subject = f"✉️ Changes Requested: {task.title}"
        body = (
            f"Hello {rec.get_full_name() or rec.username},\n\n"
            f"General Manager {gm_user.get_full_name() or gm_user.username} reviewed task '{task.title}' "
            f"and requested changes before final closure.\n\n"
            f"GM Feedback Notes:\n\"{feedback_notes}\"\n\n"
            f"Please address the feedback notes and re-submit the task for verification."
        )
        html_body = build_branded_html_email(
            title=subject,
            recipient_name=rec.get_full_name() or rec.username,
            badge_text="⚠️ REVISIONS REQUESTED",
            badge_variant="warning",
            headline=f"Changes Requested: {task.title}",
            intro_lines=[
                f"General Manager <strong>{html.escape(gm_user.get_full_name() or gm_user.username)}</strong> reviewed task <strong>'{html.escape(task.title)}'</strong> and requested changes before final closure."
            ],
            details_dict=[
                ("Task", task.title),
                ("Department", task.department.name if task.department else "General"),
                ("Reviewed By", gm_user.get_full_name() or gm_user.username),
            ],
            notes_callout=feedback_notes,
            action_url="https://www.rguedu.in/nextup/",
            action_text="Open Task & Update Deliverables",
            closing_text="Please address the feedback notes and re-submit the task for verification."
        )
        dispatch_email_and_notification(
            recipient=rec,
            subject=subject,
            body=body,
            event_type='GM_CHANGES_REQUESTED',
            task=task,
            title=f"Changes Requested: {task.title}",
            html_body=html_body,
        )


def notify_staff_created(staff_user, created_by_user):
    subject = f"✉️ Welcome to {staff_user.department.name if staff_user.department else 'the'} Team"
    body = (
        f"Hello {staff_user.get_full_name() or staff_user.username},\n\n"
        f"Your account has been created by {created_by_user.get_full_name() or created_by_user.username}.\n\n"
        f"Username: {staff_user.username}\n"
        f"Department: {staff_user.department.name if staff_user.department else 'Global'}\n"
        f"Role: {staff_user.get_role_display()}\n\n"
        f"You can now access the NextUp portal to manage your assigned tasks."
    )
    html_body = build_branded_html_email(
        title=subject,
        recipient_name=staff_user.get_full_name() or staff_user.username,
        badge_text="👋 WELCOME TO NEXTUP",
        badge_variant="primary",
        headline=f"Welcome to NextUp, {staff_user.get_full_name() or staff_user.username}!",
        intro_lines=[
            f"Your NextUp account has been created by <strong>{html.escape(created_by_user.get_full_name() or created_by_user.username)}</strong>."
        ],
        details_dict=[
            ("Username", staff_user.username),
            ("Department", staff_user.department.name if staff_user.department else "Global"),
            ("Role", staff_user.get_role_display()),
        ],
        action_url="https://www.rguedu.in/nextup/",
        action_text="Log In to NextUp Portal",
        closing_text="You can now access the NextUp portal to manage your assigned tasks and deliverables."
    )
    dispatch_email_and_notification(
        recipient=staff_user,
        subject=subject,
        body=body,
        event_type='STAFF_CREATED',
        task=None,
        title=f"Welcome to {staff_user.department.name if staff_user.department else 'the'} Team",
        html_body=html_body,
    )


def notify_comment_added(comment):
    task = comment.task
    recipients = set()
    if task.assigned_to and task.assigned_to != comment.author:
        recipients.add(task.assigned_to)
    if task.created_by and task.created_by != comment.author:
        recipients.add(task.created_by)

    author_name = comment.author.get_full_name() or comment.author.username
    subject = f"✉️ New Note on {task.title}"

    for rec in recipients:
        body = (
            f"Hello {rec.get_full_name() or rec.username},\n\n"
            f"{author_name} added a comment on '{task.title}':\n\n"
            f"\"{comment.content}\"\n\n"
            f"View task details to reply."
        )
        html_body = build_branded_html_email(
            title=subject,
            recipient_name=rec.get_full_name() or rec.username,
            badge_text="💬 NEW NOTE ADDED",
            badge_variant="primary",
            headline=f"New Note on '{task.title}'",
            intro_lines=[
                f"<strong>{html.escape(author_name)}</strong> added a new note on task <strong>'{html.escape(task.title)}'</strong>:"
            ],
            notes_callout=comment.content,
            details_dict=[
                ("Task", task.title),
                ("Author", author_name),
                ("Department", task.department.name if task.department else "General"),
            ],
            action_url="https://www.rguedu.in/nextup/",
            action_text="Reply to Note on NextUp",
            closing_text="View task details on the NextUp portal to reply."
        )
        dispatch_email_and_notification(
            recipient=rec,
            subject=subject,
            body=body,
            event_type='COMMENT_ADDED',
            task=task,
            title=f"New Note on {task.title}",
            html_body=html_body,
        )


def send_test_email_verification(to_email, sender_user):
    """
    Directly tests email transmission (SMTP or Console) to a specified recipient address.
    """
    subject = "✉️ [NextUp • Rathinam] Live Email System Verification"
    sender_name = (sender_user.get_full_name() or sender_user.username) if sender_user else "System Admin"
    backend_name = str(getattr(settings, 'EMAIL_BACKEND', 'console'))
    now_utc_str = timezone.now().strftime('%Y-%m-%d %H:%M:%S UTC')

    body = (
        f"Hello,\n\n"
        f"This is an automated operational test email from NextUp Enterprise Management Platform (Rathinam Group of Institutions).\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"System Status: ONLINE & ACTIVE\n"
        f"Triggered by: {sender_name} ({getattr(sender_user, 'email', 'admin')})\n"
        f"Server Timestamp: {now_utc_str}\n"
        f"Email Backend: {backend_name}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"If you received this message, your NextUp email dispatch system is fully connected and active!\n\n"
        f"Best regards,\nNextUp • Rathinam Group of Institutions"
    )

    test_html = build_branded_html_email(
        title=subject,
        recipient_name=sender_name,
        badge_text="🟢 SYSTEM ONLINE",
        badge_variant="success",
        headline="Live Email Dispatch System Verification",
        intro_lines=[
            "This is an automated operational test email dispatched from the NextUp Enterprise Management Platform."
        ],
        details_dict=[
            ("System Status", "ONLINE & CONNECTED"),
            ("Triggered By", f"{sender_name} ({getattr(sender_user, 'email', 'admin')})"),
            ("Server Timestamp", f"{now_utc_str}"),
            ("Email Backend", backend_name),
        ],
        action_url="https://www.rguedu.in/nextup/",
        action_text="Open NextUp Portal",
        closing_text="If you received this message, your NextUp email dispatch system is fully configured and active!"
    )

    email_error = None
    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'notifications@tasktracker.enterprise'),
            recipient_list=[to_email],
            fail_silently=False,
            html_message=test_html,
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
        f"You have received a direct message regarding your assigned task on NextUp:\n\n"
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
        f"Portal: https://www.rguedu.in/nextup/\n\n"
        f"Best regards,\n"
        f"NextUp • Rathinam Group of Institutions"
    )

    direct_msg_html = build_branded_html_email(
        title=subject,
        recipient_name=staff_name,
        badge_text="🚨 URGENT DIRECT MESSAGE" if priority_urgent else f"💬 MESSAGE FROM {sender_role.upper()}",
        badge_variant="urgent" if priority_urgent else "primary",
        headline=f"Direct Message: '{task.title}'",
        intro_lines=[
            f"You received an instant message from <strong>{html.escape(sender_name)}</strong> ({html.escape(sender_role)}) regarding your deliverable on NextUp."
        ],
        notes_callout=message_text,
        details_dict=[
            ("Task ID", f"#{task.id}"),
            ("Task Title", task.title),
            ("Department", f"{task.department.name} ({task.department.code})" if task.department else "General"),
            ("Status", task.get_status_display()),
            ("Priority", task.get_priority_display()),
            ("Target Timeline", deadline_str),
            ("Sent At", formatted_time),
        ],
        action_url="https://www.rguedu.in/nextup/",
        action_text="Open Task & Respond",
        closing_text="Please open NextUp to reply and record your progress."
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
                html_message=direct_msg_html,
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
    Dispatches 1-hour recurring work check-in reminder during India working hours (9:00 AM to 6:00 PM IST).
    If user has urgent or due date tasks, the push notification explicitly highlights them with all details!
    """
    now_ist = get_india_current_time()
    if enforce_work_hours and not is_within_india_work_hours():
        print(f"[HourlyReminder] Outside India working hours (Current IST: {now_ist.strftime('%I:%M %p')}). Reminders run between 9:00 AM and 6:00 PM IST.")
        return 0

    if user:
        recipients = [user]
    else:
        recipients = list(User.objects.filter(is_active=True))

    today = now_ist.date()
    count = 0
    now_str = now_ist.strftime('%I:%M %p')

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

                subject = f"🚨 [9AM-6PM IST Check-In] {urgent_count} Urgent / Due Deliverable(s)"
                body = (
                    f"Hello {r.get_full_name() or r.username},\n\n"
                    f"This is your hourly work check-in ({now_str} IST • 9:00 AM – 6:00 PM Work Hours).\n\n"
                    f"⚠️ ATTENTION - PENDING URGENT DELIVERABLE:\n"
                    f"• Task: #{top_task.id} '{top_task.title}'\n"
                    f"• Department: {top_task.department.name} ({top_task.department.code})\n"
                    f"• Priority: {top_task.get_priority_display()}\n"
                    f"• Due Date: {top_task.due_date or 'Immediate'}\n"
                    f"• Status Notice: {tag}\n\n"
                    f"Total urgent / due tasks waiting: {urgent_count}.\n"
                    f"Please review and submit your progress updates on NextUp."
                )
                html_body = build_branded_html_email(
                    title=subject,
                    recipient_name=r.get_full_name() or r.username,
                    badge_text=f"🚨 {now_str} IST CHECK-IN • URGENT DELIVERABLE",
                    badge_variant="urgent",
                    headline=f"Urgent Deliverable Alert ({now_str} IST)",
                    intro_lines=[
                        f"This is your continuous 1-hour work check-in reminder during India working hours (9:00 AM – 6:00 PM IST).",
                        f"<strong>⚠️ Attention:</strong> You have <strong>{urgent_count} urgent / pending deliverable(s)</strong> awaiting completion."
                    ],
                    details_dict=[
                        ("Pending Task", f"#{top_task.id} {top_task.title}"),
                        ("Department", f"{top_task.department.name} ({top_task.department.code})" if top_task.department else "General"),
                        ("Priority", top_task.get_priority_display()),
                        ("Target Due Date", f"{top_task.due_date or 'Immediate'} ({tag})"),
                        ("Status Notice", tag),
                        ("Total Urgent Tasks", str(urgent_count)),
                    ],
                    description_text=(top_task.description or "").strip(),
                    action_url="https://www.rguedu.in/nextup/",
                    action_text="Prioritize & Update Deliverable",
                    closing_text="Please review and submit your progress updates on the NextUp portal."
                )
                event_type = 'HOURLY_WORK_REMINDER'
                notif_title = f"🚨 [Urgent Task Due] #{top_task.id} {top_task.title}"
                push_title = f"🚨 [{now_str} IST] {urgent_count} Urgent / Due Task(s)"
                push_body = (
                    f"⚠️ #{top_task.id} {top_task.title}\n"
                    f"Priority: {top_task.get_priority_display()} • Due: {top_task.due_date or 'Immediate'} ({tag})\n"
                    f"Dept: {top_task.department.code if top_task.department else 'General'} • Please update progress!"
                )
                top_task_obj = top_task
            else:
                active_count = active_tasks.count()
                subject = f"⏰ Hourly Work Check-In ({now_str} IST)"
                body = (
                    f"Hello {r.get_full_name() or r.username},\n\n"
                    f"This is your continuous 1-hour work check-in reminder (9:00 AM - 6:00 PM IST).\n"
                    f"Active deliverables: {active_count} tasks in progress.\n"
                    f"Please keep your active tasks, progress reports, and deliverables current."
                )
                intro = [
                    f"This is your continuous 1-hour work check-in reminder during India working hours (9:00 AM – 6:00 PM IST)."
                ]
                if active_count == 0:
                    intro.append("You currently have <strong>0 active tasks in progress</strong>. You're all caught up! Keep up the momentum or review upcoming department deliverables on the portal.")
                else:
                    intro.append(f"You currently have <strong>{active_count} active deliverable(s)</strong> in progress. Please keep your active tasks, progress reports, and milestone updates current.")

                details_list = [
                    ("Check-In Time", f"{now_str} IST"),
                    ("Working Window", "9:00 AM – 6:00 PM IST"),
                    ("Active Deliverables", f"{active_count} task{'s' if active_count != 1 else ''} in progress"),
                ]

                html_body = build_branded_html_email(
                    title=subject,
                    recipient_name=r.get_full_name() or r.username,
                    badge_text=f"⏰ HOURLY WORK CHECK-IN • {now_str} IST",
                    badge_variant="purple",
                    headline=f"Hourly Work Check-In ({now_str} IST)",
                    intro_lines=intro,
                    details_dict=details_list,
                    action_url="https://www.rguedu.in/nextup/",
                    action_text="Open NextUp Portal",
                    closing_text="Please keep your active tasks, progress reports, and deliverables current on NextUp."
                )
                event_type = 'HOURLY_WORK_REMINDER'
                notif_title = f"⏰ 1-Hour Work Check-In ({now_str} IST)"
                push_title = notif_title
                push_body = (
                    f"1-Hour check-in (9:00 AM – 6:00 PM IST).\n"
                    f"You have {active_count} active task(s) in progress. Please review and update deliverables on NextUp."
                )
                top_task_obj = None

            dispatch_email_and_notification(
                recipient=r,
                subject=subject,
                body=body,
                event_type=event_type,
                task=top_task_obj,
                title=notif_title,
                push_title=push_title,
                push_body=push_body,
                html_body=html_body,
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

        html_body = build_branded_html_email(
            title=f"{headline} [{task.department.code if task.department else 'NextUp'}]",
            recipient_name=assignee.get_full_name() or assignee.username,
            badge_text=f"🚨 {urgency.replace('_', ' ')}",
            badge_variant="urgent",
            headline=f"Urgent Deliverable: {task.title}",
            intro_lines=[
                f"⚠️ Urgent deliverable reminder for task <strong>'{html.escape(task.title)}'</strong>."
            ],
            details_dict=[
                ("Deliverable", f"#{task.id} {task.title}"),
                ("Department", f"{task.department.name} ({task.department.code})" if task.department else "General"),
                ("Priority", task.get_priority_display()),
                ("Target Deadline", str(task.due_date) if task.due_date else "Immediate"),
                ("Status", task.get_status_display()),
            ],
            description_text=(task.description or "").strip(),
            action_url="https://www.rguedu.in/nextup/",
            action_text="Open Deliverable in NextUp",
            closing_text="Please prioritize this task and submit your deliverables before 6:00 PM."
        )

        try:
            dispatch_email_and_notification(
                recipient=assignee,
                subject=f"{headline} [{task.department.code}]",
                body=body,
                event_type='URGENT_TASK_REMINDER',
                task=task,
                title=headline,
                html_body=html_body,
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
