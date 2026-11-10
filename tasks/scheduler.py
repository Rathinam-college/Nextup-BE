import threading
import time
import os
import sys

_scheduler_started = False
_scheduler_lock = threading.Lock()

def start_india_work_hours_scheduler():
    """
    Starts a background daemon thread that checks every 30 seconds.
    Operating Window: Monday to Saturday (Sunday is a strict weekly holiday).

    Scheduled Automated Emails (Strictly 2 per working day):
      1) 9:00 AM IST: Morning Work Start Briefing (tasks in TODO/IN_PROGRESS/CHANGES_REQUESTED).
      2) 6:00 PM IST: End-of-Day Wrap-Up Summary.

    Hourly 1-hour reminders are disabled per policy.
    Users with 0 active tasks are strictly excluded from emails.
    """
    global _scheduler_started
    with _scheduler_lock:
        if _scheduler_started:
            return
        _scheduler_started = True

    def _loop():
        # Delay initial startup slightly to allow Django apps and DB models to fully load
        time.sleep(12)
        print("[WorkSchedule] ✅ Active Schedule: Monday to Saturday. Scheduled Briefings: 9:00 AM (Start) & 6:00 PM (Wrap-Up) IST (Sunday Holiday).")

        last_dispatched_9am_date = None
        last_dispatched_6pm_date = None
        reminded_meeting_ids = set()

        while True:
            try:
                from .services import (
                    get_india_current_time,
                    is_sunday_holiday,
                    dispatch_morning_9am_work_email,
                    dispatch_evening_6pm_work_email,
                    parse_task_meeting_data,
                    notify_meeting_reminder,
                )
                from .models import Task
                from datetime import datetime, timedelta

                now_ist = get_india_current_time()
                today_date = now_ist.date()
                current_hour = now_ist.hour

                # Sunday is a weekly holiday: notifications & emails are completely silenced
                if is_sunday_holiday(now_ist):
                    time.sleep(60)
                    continue

                # 1) Automated Meeting Reminders: Check for meetings starting within 20 minutes
                try:
                    active_meetings = Task.objects.filter(
                        status__in=[Task.STATUS_TODO, Task.STATUS_IN_PROGRESS]
                    ).filter(
                        description__icontains='MEETING_DATA'
                    )
                    for m_task in active_meetings:
                        if m_task.id in reminded_meeting_ids:
                            continue
                        m_meta = parse_task_meeting_data(m_task)
                        m_time_str = m_meta.get('meeting_time')
                        if not m_time_str:
                            continue
                        # Parse meeting time
                        m_dt = None
                        for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M'):
                            try:
                                m_dt = datetime.strptime(m_time_str[:19], fmt)
                                break
                            except Exception:
                                continue
                        if m_dt:
                            # If timezone-naive, make comparable to now_ist
                            now_naive = now_ist.replace(tzinfo=None)
                            diff_sec = (m_dt - now_naive).total_seconds()
                            # If meeting starts in 0 to 20 minutes
                            if 0 <= diff_sec <= 20 * 60:
                                print(f"[WorkSchedule] ⏰ Triggering 15-minute advance reminder for meeting: '{m_task.title}'")
                                notify_meeting_reminder(m_task)
                                reminded_meeting_ids.add(m_task.id)
                except Exception as meet_err:
                    print(f"[WorkSchedule] Meeting reminder check notice: {meet_err}")

                # 2) Morning 9:00 AM Kick-Off (Fires once per day at 9:00 AM IST)
                if current_hour == 9 and last_dispatched_9am_date != today_date:
                    print(f"[WorkSchedule] ☀️ 9:00 AM IST ({now_ist.strftime('%A')}): Dispatching Morning Work Start emails...")
                    count = dispatch_morning_9am_work_email()
                    last_dispatched_9am_date = today_date
                    print(f"[WorkSchedule] ✅ 9:00 AM briefing dispatched to {count} recipient(s) with active tasks.")

                # 2) Evening 6:00 PM Wrap-Up (Fires once per day at 6:00 PM IST)
                elif current_hour == 18 and last_dispatched_6pm_date != today_date:
                    print(f"[WorkSchedule] 🏁 6:00 PM IST ({now_ist.strftime('%A')}): Dispatching End of Day Wrap-Up emails...")
                    count = dispatch_evening_6pm_work_email()
                    last_dispatched_6pm_date = today_date
                    print(f"[WorkSchedule] ✅ 6:00 PM wrap-up dispatched to {count} recipient(s) with active tasks.")

            except Exception as loop_err:
                print(f"[WorkSchedule] Notice: {loop_err}")

            time.sleep(30)

    t = threading.Thread(target=_loop, daemon=True, name="IndiaWorkHoursSchedulerThread")
    t.start()

