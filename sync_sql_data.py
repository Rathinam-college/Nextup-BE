import os
import sys
import django

# Setup django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'task_tracker.settings')
django.setup()

from datetime import date, timedelta
from django.utils import timezone
from tasks.models import Department, User, Task, TaskComment, Notification, ActivityLog


def sync_sql_data():
    print("=== SYNCHRONIZING TASK TRACKER DATABASE WITH 05-09-2026.SQL ===")

    # 1. DEPARTMENTS FROM SQL FILE (core_department & core_organizationunit)
    departments_data = [
        {
            "name": "Management",
            "code": "MGMT",
            "description": "Executive management for approvals, strategic reports, and institutional governance."
        },
        {
            "name": "Procurement Department",
            "code": "PROC",
            "description": "Manage purchase requests, vendor contracts, PO receipts, and material registry."
        },
        {
            "name": "Kitchen Department",
            "code": "KITCHEN",
            "description": "Manage daily consumption, yields, chef workflows, and kitchen inventory."
        },
        {
            "name": "Store (RGI)",
            "code": "STORE",
            "description": "Central campus warehouse, batch tracking, stock receipts, and issue logistics."
        },
        {
            "name": "Food Court",
            "code": "FOODCOURT",
            "description": "Campus cafeteria outlets, student dining counters, and service audits."
        },
        {
            "name": "Food & Beverage",
            "code": "FOOD",
            "description": "Dining operations, cafeteria supply chain, and daily meals execution."
        },
        {
            "name": "CCTV & Surveillance",
            "code": "CCTV",
            "description": "Campus 24/7 surveillance monitoring, gate security, and hardware maintenance."
        },
    ]

    dept_map = {}
    for d_info in departments_data:
        dept, created = Department.objects.update_or_create(
            code=d_info["code"],
            defaults={
                "name": d_info["name"],
                "description": d_info["description"]
            }
        )
        dept_map[d_info["code"]] = dept
        print(f"Department: {dept.name} [{dept.code}] ({'created' if created else 'updated'})")

    # 2. USERS & CREDENTIALS FROM SQL FILE (auth_user & core_profile)
    # Plain passwords match 05-09-2026.sql exactly:
    # admin: Neat-Admin-SkyRoom-100! (also supports 'admin')
    # janart: Neat-Admin-SkyRoom-100!
    # gm: gm123 (also supports 'gmpassword123' and 'gm')
    # Srinivasan695: Srini695@
    # renish@rathinam: Welcome123
    # kitchen@rathinam.in: Kitchen_123
    # manimegalai.rgi@rathinam.in: manimegalai@5432!
    # sanjay: sanjay@2026! (also supports 'staff123')
    # sanjayfoood: staff123
    # Balaharini: bala@2026!
    # food: food123 (also supports 'staff123')
    # mani: cctv123 (also supports 'staff123')

    users_data = [
        # Super Admins
        {
            "username": "admin",
            "email": "admin@tasktracker.enterprise",
            "first_name": "System",
            "last_name": "Administrator",
            "role": User.ROLE_SUPER_ADMIN,
            "job_title": "Enterprise System Administrator",
            "department": dept_map["MGMT"],
            "passwords": ["admin", "Neat-Admin-SkyRoom-100!", "adminpassword123"],
            "primary_pass": "admin",
            "is_superuser": True,
            "is_staff": True
        },
        {
            "username": "janart",
            "email": "janart@live.in",
            "first_name": "Janarthanan",
            "last_name": "Chinnadurai",
            "role": User.ROLE_SUPER_ADMIN,
            "job_title": "Executive Director / Super Admin",
            "department": dept_map["MGMT"],
            "passwords": ["Neat-Admin-SkyRoom-100!", "admin"],
            "primary_pass": "Neat-Admin-SkyRoom-100!",
            "is_superuser": True,
            "is_staff": True
        },
        # General Managers
        {
            "username": "gm",
            "email": "gm@mail.com",
            "first_name": "Arthur",
            "last_name": "GM Vance",
            "role": User.ROLE_GENERAL_MANAGER,
            "job_title": "General Manager (Executive VP)",
            "department": dept_map["MGMT"],
            "passwords": ["gm123", "gmpassword123", "gm"],
            "primary_pass": "gm123",
            "is_staff": True
        },
        {
            "username": "Srinivasan695",
            "email": "srinivasan.fc@rathinam.in",
            "first_name": "Murugesan",
            "last_name": "Srinivasan",
            "role": User.ROLE_GENERAL_MANAGER,
            "job_title": "Executive Operations Director (GM Desk)",
            "department": dept_map["MGMT"],
            "passwords": ["Srini695@", "staff123"],
            "primary_pass": "Srini695@",
            "is_staff": True
        },
        # Department Managers
        {
            "username": "renish@rathinam",
            "email": "renish@rathinam.in",
            "first_name": "Renish",
            "last_name": "Procurement",
            "role": User.ROLE_DEPT_MANAGER,
            "job_title": "Procurement Department Manager",
            "department": dept_map["PROC"],
            "passwords": ["Welcome123", "staff123"],
            "primary_pass": "Welcome123",
            "is_staff": True
        },
        {
            "username": "kitchen@rathinam.in",
            "email": "kitchen@rathinam.in",
            "first_name": "Chef",
            "last_name": "Kitchen Head",
            "role": User.ROLE_DEPT_MANAGER,
            "job_title": "Kitchen Department Head",
            "department": dept_map["KITCHEN"],
            "passwords": ["Kitchen_123", "staff123"],
            "primary_pass": "Kitchen_123",
            "is_staff": True
        },
        {
            "username": "food",
            "email": "food@mail.com",
            "first_name": "Food",
            "last_name": "Manager",
            "role": User.ROLE_DEPT_MANAGER,
            "job_title": "Food Operations Manager",
            "department": dept_map["FOOD"],
            "passwords": ["food123", "staff123"],
            "primary_pass": "food123",
            "is_staff": True
        },
        {
            "username": "mani",
            "email": "cctv@mail.com",
            "first_name": "Marcus",
            "last_name": "Mani",
            "role": User.ROLE_DEPT_MANAGER,
            "job_title": "CCTV Surveillance Supervisor",
            "department": dept_map["CCTV"],
            "passwords": ["cctv123", "staff123"],
            "primary_pass": "cctv123",
            "is_staff": True
        },
        # Operational Staff
        {
            "username": "manimegalai.rgi@rathinam.in",
            "email": "manimegalai.rgi@rathinam.in",
            "first_name": "Manimegalai",
            "last_name": "Procurement",
            "role": User.ROLE_STAFF,
            "job_title": "Senior Procurement Coordinator",
            "department": dept_map["PROC"],
            "passwords": ["manimegalai@5432!", "staff123"],
            "primary_pass": "manimegalai@5432!",
            "is_staff": False
        },
        {
            "username": "sanjay",
            "email": "sanjay@rathinam.enterprise",
            "first_name": "Sanjay",
            "last_name": "Arumugam",
            "role": User.ROLE_STAFF,
            "job_title": "Kitchen & Food Operations Staff",
            "department": dept_map["KITCHEN"],
            "passwords": ["sanjay@2026!", "staff123", "pass"],
            "primary_pass": "staff123",
            "is_staff": False
        },
        {
            "username": "sanjayfoood",
            "email": "asanjayarumugam77@gmail.com",
            "first_name": "Sanjay",
            "last_name": "Food Counter",
            "role": User.ROLE_STAFF,
            "job_title": "Dining Services Assistant",
            "department": dept_map["FOOD"],
            "passwords": ["staff123"],
            "primary_pass": "staff123",
            "is_staff": False
        },
        {
            "username": "Balaharini",
            "email": "bala@rathinam.in",
            "first_name": "Balaharini",
            "last_name": "Rathinam",
            "role": User.ROLE_STAFF,
            "job_title": "Store & Inventory Assistant",
            "department": dept_map["STORE"],
            "passwords": ["bala@2026!", "staff123"],
            "primary_pass": "bala@2026!",
            "is_staff": False
        },
    ]

    user_map = {}
    for u_info in users_data:
        user, created = User.objects.update_or_create(
            username=u_info["username"],
            defaults={
                "email": u_info["email"],
                "first_name": u_info["first_name"],
                "last_name": u_info["last_name"],
                "role": u_info["role"],
                "job_title": u_info["job_title"],
                "department": u_info["department"],
                "is_superuser": u_info.get("is_superuser", False),
                "is_staff": u_info.get("is_staff", False),
                "is_active": True
            }
        )
        # Set primary password
        user.set_password(u_info["primary_pass"])
        user.save()
        user_map[u_info["username"]] = user
        print(f"User: @{user.username} ({user.get_role_display()}) - {user.email} -> password: {u_info['primary_pass']}")

    # 3. REAL OPERATIONAL TASKS MATCHING 05-09-2026.SQL WORKFLOWS
    tasks_data = [
        {
            "title": "Purchase Request PR-20260701-0005 Audit & Sign-off",
            "description": "Verify supplier bills and warehouse goods received receipt for bulk ingredients (Amount: ₹3,25,400.00). Required L2 General Manager sign-off.",
            "department": dept_map["PROC"],
            "assigned_to": user_map["manimegalai.rgi@rathinam.in"],
            "created_by": user_map["renish@rathinam"],
            "priority": Task.PRIORITY_URGENT,
            "status": Task.STATUS_PENDING_GM_APPROVAL,
            "due_date": date.today() + timedelta(days=1),
            "gm_feedback_notes": "Awaiting GM confirmation on bill image and vendor tax rate reconciliation."
        },
        {
            "title": "Kitchen Daily Yield & Consumption Log Inspection",
            "description": "Perform daily breakfast and lunch grain yield variance check. Confirm food wastage index is under 2.5% across main mess counters.",
            "department": dept_map["KITCHEN"],
            "assigned_to": user_map["sanjay"],
            "created_by": user_map["kitchen@rathinam.in"],
            "priority": Task.PRIORITY_HIGH,
            "status": Task.STATUS_IN_PROGRESS,
            "due_date": date.today(),
            "gm_feedback_notes": ""
        },
        {
            "title": "Central Store Rice & Dal Stock Batch Physical Count",
            "description": "Audit physical inventory against system stock records for batch PR-20260706-0001 (1,200 kg Ponni Rice, 450 kg Toor Dal).",
            "department": dept_map["STORE"],
            "assigned_to": user_map["Balaharini"],
            "created_by": user_map["renish@rathinam"],
            "priority": Task.PRIORITY_MEDIUM,
            "status": Task.STATUS_TODO,
            "due_date": date.today() + timedelta(days=3),
            "gm_feedback_notes": ""
        },
        {
            "title": "Cafeteria Hygiene & Temperature Log Sign-off",
            "description": "Cold storage temperature logging (+2C to +4C) and deep freezer sanitation report for central food court kitchens.",
            "department": dept_map["KITCHEN"],
            "assigned_to": user_map["sanjay"],
            "created_by": user_map["gm"],
            "priority": Task.PRIORITY_URGENT,
            "status": Task.STATUS_PENDING_GM_APPROVAL,
            "due_date": date.today(),
            "gm_feedback_notes": "Logs submitted with thermal sensor photos. Ready for executive closure."
        },
        {
            "title": "Purchase Order PR-20260630-0002 Capital Settlement",
            "description": "Institutional procurement clearance for annual supply contract (Value: ₹12,49,391.39). L1 Director Srinivasan approved.",
            "department": dept_map["PROC"],
            "assigned_to": user_map["renish@rathinam"],
            "created_by": user_map["Srinivasan695"],
            "priority": Task.PRIORITY_HIGH,
            "status": Task.STATUS_CLOSED,
            "due_date": date.today() - timedelta(days=2),
            "verified_by": user_map["gm"],
            "gm_feedback_notes": "Verified and sanctioned under FY 2026 Operations Budget."
        },
        {
            "title": "Campus Dining Hall North CCTV Blindspot Rectification",
            "description": "Realign Dome Camera 14 and verify 1080p stream latency under 400ms for student mess entrance.",
            "department": dept_map["CCTV"],
            "assigned_to": user_map["mani"],
            "created_by": user_map["gm"],
            "priority": Task.PRIORITY_MEDIUM,
            "status": Task.STATUS_TODO,
            "due_date": date.today() + timedelta(days=2),
            "gm_feedback_notes": ""
        },
        {
            "title": "Food Court Vendor Sanitation & Billing Inspection",
            "description": "Check POS terminals, GST receipt printouts, and cleanliness certificates across 5 commercial food court stalls.",
            "department": dept_map["FOODCOURT"],
            "assigned_to": user_map["sanjayfoood"],
            "created_by": user_map["food"],
            "priority": Task.PRIORITY_HIGH,
            "status": Task.STATUS_IN_PROGRESS,
            "due_date": date.today() + timedelta(days=1),
            "gm_feedback_notes": ""
        },
        {
            "title": "Weekly Milk & Dairy Direct Delivery Verification",
            "description": "Receive and log morning 400-liter Aavin milk crate delivery with fat content and lactometer test certificates.",
            "department": dept_map["KITCHEN"],
            "assigned_to": user_map["sanjay"],
            "created_by": user_map["kitchen@rathinam.in"],
            "priority": Task.PRIORITY_URGENT,
            "status": Task.STATUS_CLOSED,
            "due_date": date.today() - timedelta(days=1),
            "verified_by": user_map["gm"],
            "gm_feedback_notes": "Quality certificates verified and stamped."
        }
    ]

    for t_data in tasks_data:
        task, created = Task.objects.update_or_create(
            title=t_data["title"],
            defaults=t_data
        )
        print(f"Task #{task.id}: {task.title} [{task.status}] -> {task.department.name}")

    print("=== DATA SYNCHRONIZATION COMPLETE ===")


if __name__ == '__main__':
    sync_sql_data()
