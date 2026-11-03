import threading
import time
import os
import sys

_scheduler_started = False
_scheduler_lock = threading.Lock()

def start_india_work_hours_scheduler():
    """
    Starts a background daemon thread that checks every 30 seconds.
    Between 9:00 AM and 6:00 PM Indian Standard Time (IST), it dispatches
    the 1-hour work check-in reminder to all active staff at the top of each hour.
    Outside working hours (before 9 AM or after 6 PM IST), notifications are silenced.
    """
    global _scheduler_started
    with _scheduler_lock:
        if _scheduler_started:
            return
        _scheduler_started = True

    def _loop():
        # Delay initial startup slightly to allow Django apps and DB models to fully load
        time.sleep(12)
        print("[IndiaWorkHoursScheduler] ✅ 9:00 AM – 6:00 PM IST 1-hour reminder scheduler active.")

        last_dispatched_hour = -1

        while True:
            try:
                from .services import is_within_india_work_hours, get_india_current_time, dispatch_hourly_work_reminders
                now_ist = get_india_current_time()
                current_hour = now_ist.hour

                if is_within_india_work_hours():
                    if current_hour != last_dispatched_hour:
                        print(f"[IndiaWorkHoursScheduler] ⏰ Top of hour ({current_hour}:00 IST): Dispatching 1-hour work check-in to staff...")
                        count = dispatch_hourly_work_reminders(enforce_work_hours=True)
                        last_dispatched_hour = current_hour
                        print(f"[IndiaWorkHoursScheduler] ✅ {current_hour}:00 IST check-in dispatched to {count} recipient(s).")
            except Exception as loop_err:
                print(f"[IndiaWorkHoursScheduler] Notice: {loop_err}")

            time.sleep(30)

    t = threading.Thread(target=_loop, daemon=True, name="IndiaWorkHoursSchedulerThread")
    t.start()

