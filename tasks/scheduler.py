import threading
import time
import os
import sys

_scheduler_started = False
_scheduler_lock = threading.Lock()

def start_india_work_hours_scheduler():
    """
    Starts a background daemon thread that checks every 30 seconds.
    Operating Window: Monday to Saturday, 9:00 AM to 6:00 PM Indian Standard Time (IST).
    At the top of each hour during working hours, it dispatches the 1-hour work check-in
    reminder to active staff members with assigned tasks.
    Weekly Holiday: Sunday (notifications, emails, and reminders are strictly silenced).
    """
    global _scheduler_started
    with _scheduler_lock:
        if _scheduler_started:
            return
        _scheduler_started = True

    def _loop():
        # Delay initial startup slightly to allow Django apps and DB models to fully load
        time.sleep(12)
        print("[IndiaWorkHoursScheduler] ✅ Active Schedule: Monday to Saturday, 9:00 AM – 6:00 PM IST (Sunday Holiday).")

        last_dispatched_hour = -1

        while True:
            try:
                from .services import is_within_india_work_hours, get_india_current_time, dispatch_hourly_work_reminders, is_sunday_holiday
                now_ist = get_india_current_time()
                current_hour = now_ist.hour

                # Sunday is a weekly holiday: notifications & emails are completely silenced
                if is_sunday_holiday(now_ist):
                    time.sleep(60)
                    continue

                if is_within_india_work_hours(now_ist):
                    if current_hour != last_dispatched_hour:
                        print(f"[IndiaWorkHoursScheduler] ⏰ Top of hour ({current_hour}:00 IST • {now_ist.strftime('%A')}): Dispatching 1-hour work check-in to staff...")
                        count = dispatch_hourly_work_reminders(enforce_work_hours=True)
                        last_dispatched_hour = current_hour
                        print(f"[IndiaWorkHoursScheduler] ✅ {current_hour}:00 IST check-in dispatched to {count} recipient(s).")
            except Exception as loop_err:
                print(f"[IndiaWorkHoursScheduler] Notice: {loop_err}")

            time.sleep(30)

    t = threading.Thread(target=_loop, daemon=True, name="IndiaWorkHoursSchedulerThread")
    t.start()

