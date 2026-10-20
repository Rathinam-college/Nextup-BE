import os
import sys
import django
from datetime import timedelta

# Setup django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'task_tracker.settings')
django.setup()

from django.utils import timezone
from tasks.models import Department, User, Task, TaskComment, Notification, DispatchedEmailLog, ActivityLog
from tasks.services import dispatch_email_and_notification, log_activity


def run_seed():
    print("Clearing existing data...")
    ActivityLog.objects.all().delete()
    DispatchedEmailLog.objects.all().delete()
    Notification.objects.all().delete()
    TaskComment.objects.all().delete()
    Task.objects.all().delete()
    User.objects.all().delete()
    Department.objects.all().delete()

    print("Creating Departments...")
    eng_dept = Department.objects.create(
        name="Engineering",
        code="ENG",
        description="Software engineering, cloud infrastructure, and core systems architecture."
    )

    mkt_dept = Department.objects.create(
        name="Marketing",
        code="MKT",
        description="Brand strategy, digital campaigns, customer outreach, and public relations."
    )

    cctv_dept = Department.objects.create(
        name="CCTV & Surveillance",
        code="CCTV",
        description="Campus video monitoring, security camera feeds, access control, and hardware maintenance."
    )

    print("Creating Super Admin and GM...")
    super_admin = User.objects.create_superuser(
        username="admin",
        email="admin@tasktracker.enterprise",
        password="admin",
        first_name="System",
        last_name="SuperAdmin",
        role=User.ROLE_SUPER_ADMIN,
        job_title="System Administrator"
    )

    gm_user = User.objects.create_user(
        username="gm",
        email="gm.arthur@tasktracker.enterprise",
        password="gm",
        first_name="Arthur",
        last_name="Vance",
        role=User.ROLE_GENERAL_MANAGER,
        job_title="General Manager (Executive VP)",
        is_staff=True
    )

    print("Creating Department Managers...")
    eng_manager = User.objects.create_user(
        username="alex.manager",
        email="alex.rivera@tasktracker.enterprise",
        password="alex",
        first_name="Alex",
        last_name="Rivera",
        role=User.ROLE_DEPT_MANAGER,
        department=eng_dept,
        job_title="Engineering Director"
    )

    mkt_manager = User.objects.create_user(
        username="maya.manager",
        email="maya.lin@tasktracker.enterprise",
        password="maya",
        first_name="Maya",
        last_name="Lin",
        role=User.ROLE_DEPT_MANAGER,
        department=mkt_dept,
        job_title="Marketing VP"
    )

    cctv_manager = User.objects.create_user(
        username="cctv.manager",
        email="cctv.manager@tasktracker.enterprise",
        password="cctv",
        first_name="Marcus",
        last_name="Ward",
        role=User.ROLE_DEPT_MANAGER,
        department=cctv_dept,
        job_title="CCTV Operations Supervisor"
    )

    print("Creating Staff Members...")
    sarah = User.objects.create_user(
        username="sarah.chen",
        email="sarah.chen@tasktracker.enterprise",
        password="sarah",
        first_name="Sarah",
        last_name="Chen",
        role=User.ROLE_STAFF,
        department=eng_dept,
        job_title="Senior Backend Engineer"
    )

    david = User.objects.create_user(
        username="david.kim",
        email="david.kim@tasktracker.enterprise",
        password="david",
        first_name="David",
        last_name="Kim",
        role=User.ROLE_STAFF,
        department=eng_dept,
        job_title="Cloud & DevOps Engineer"
    )

    carlos = User.objects.create_user(
        username="carlos.diaz",
        email="carlos.diaz@tasktracker.enterprise",
        password="carlos",
        first_name="Carlos",
        last_name="Diaz",
        role=User.ROLE_STAFF,
        department=mkt_dept,
        job_title="Content Strategist"
    )

    emma = User.objects.create_user(
        username="emma.watson",
        email="emma.watson@tasktracker.enterprise",
        password="emma",
        first_name="Emma",
        last_name="Watson",
        role=User.ROLE_STAFF,
        department=mkt_dept,
        job_title="Growth Campaign Lead"
    )

    cctv_staff = User.objects.create_user(
        username="cctv",
        email="cctv.operator@tasktracker.enterprise",
        password="cctv",
        first_name="CCTV",
        last_name="Operator",
        role=User.ROLE_STAFF,
        department=cctv_dept,
        job_title="Surveillance Monitoring Officer"
    )

    now = timezone.now()

    print("Creating Tasks...")
    # Engineering Tasks
    t1 = Task.objects.create(
        title="Migrate Authentication to Dual-Factor OAuth2",
        description="Upgrade backend auth tokens to support multi-factor auth and enterprise SSO integration.",
        department=eng_dept,
        assigned_to=sarah,
        created_by=eng_manager,
        priority=Task.PRIORITY_URGENT,
        status=Task.STATUS_PENDING_GM_APPROVAL,
        due_date=(now + timedelta(days=2)).date(),
    )
    TaskComment.objects.create(
        task=t1,
        author=sarah,
        content="Implementation and unit tests finished. Passing full test suite. Submitting for GM review."
    )

    t2 = Task.objects.create(
        title="PostgreSQL 18 Partitioning & Query Optimization",
        description="Implement declarative table partitioning on high-volume activity audit tables.",
        department=eng_dept,
        assigned_to=david,
        created_by=eng_manager,
        priority=Task.PRIORITY_HIGH,
        status=Task.STATUS_IN_PROGRESS,
        due_date=(now + timedelta(days=5)).date(),
    )
    TaskComment.objects.create(
        task=t2,
        author=david,
        content="Benchmarking shows 4x speedup on historical audit log queries. Finalizing migration script."
    )

    t3 = Task.objects.create(
        title="Automated Disaster Recovery Replication Script",
        description="Configure automated cross-region standby replication and failover verification.",
        department=eng_dept,
        assigned_to=david,
        created_by=eng_manager,
        priority=Task.PRIORITY_MEDIUM,
        status=Task.STATUS_TODO,
        due_date=(now + timedelta(days=9)).date(),
    )

    t4 = Task.objects.create(
        title="Microservice Latency Tracing with OpenTelemetry",
        description="Instrument key API endpoints with distributed tracing headers.",
        department=eng_dept,
        assigned_to=sarah,
        created_by=eng_manager,
        priority=Task.PRIORITY_MEDIUM,
        status=Task.STATUS_CLOSED,
        due_date=(now - timedelta(days=3)).date(),
        verified_by=gm_user,
        closed_at=now - timedelta(days=1),
        gm_feedback_notes="Traces verified in staging APM. Great performance latency reduction."
    )

    # Marketing Tasks
    t5 = Task.objects.create(
        title="Q4 Enterprise Product Launch Campaign",
        description="Draft press releases, coordinate product demo webinars, and schedule newsletter broadcast.",
        department=mkt_dept,
        assigned_to=emma,
        created_by=mkt_manager,
        priority=Task.PRIORITY_URGENT,
        status=Task.STATUS_PENDING_GM_APPROVAL,
        due_date=(now + timedelta(days=3)).date(),
    )
    TaskComment.objects.create(
        task=t5,
        author=emma,
        content="Webinar calendar and landing pages finalized. Ready for executive sign-off."
    )

    t6 = Task.objects.create(
        title="Global Brand Refresh & Asset Kit",
        description="Update visual typography, brand guidelines PDF, and social banner templates.",
        department=mkt_dept,
        assigned_to=carlos,
        created_by=mkt_manager,
        priority=Task.PRIORITY_HIGH,
        status=Task.STATUS_CHANGES_REQUESTED,
        due_date=(now + timedelta(days=4)).date(),
        gm_feedback_notes="Please update typography guidelines with high-contrast accessibility standards before sign-off."
    )
    TaskComment.objects.create(
        task=t6,
        author=gm_user,
        content="Review completed: Colors look solid, but typography needs WCAG AAA contrast verification."
    )

    t7 = Task.objects.create(
        title="Customer Success Story Video Series",
        description="Interview top 3 enterprise partners and produce 90-second testimonial highlight reels.",
        department=mkt_dept,
        assigned_to=carlos,
        created_by=mkt_manager,
        priority=Task.PRIORITY_MEDIUM,
        status=Task.STATUS_IN_PROGRESS,
        due_date=(now + timedelta(days=12)).date(),
    )

    t8 = Task.objects.create(
        title="SEO Audit & Technical Keyword Targeting",
        description="Optimize core landing page meta tags and schema markup.",
        department=mkt_dept,
        assigned_to=emma,
        created_by=mkt_manager,
        priority=Task.PRIORITY_LOW,
        status=Task.STATUS_TODO,
        due_date=(now + timedelta(days=14)).date(),
    )

    print("Creating CCTV Department Tasks...")
    t_cctv1 = Task.objects.create(
        title="Night Perimeter Camera 4K Calibration & Sync",
        description="Verify infrared night vision alignment and 4K optical clarity across gates 1 through 6.",
        department=cctv_dept,
        assigned_to=cctv_staff,
        created_by=cctv_manager,
        priority=Task.PRIORITY_URGENT,
        status=Task.STATUS_IN_PROGRESS,
        due_date=(now + timedelta(days=1)).date(),
    )
    TaskComment.objects.create(
        task=t_cctv1,
        author=cctv_staff,
        content="Gates 1 through 4 calibrated and passed latency test. Working on gate 5."
    )

    t_cctv2 = Task.objects.create(
        title="Server Room Biometric & Video Footage Audit",
        description="Cross-reference server room electronic keycard access logs with CCTV video footage timestamps.",
        department=cctv_dept,
        assigned_to=cctv_staff,
        created_by=cctv_manager,
        priority=Task.PRIORITY_HIGH,
        status=Task.STATUS_PENDING_GM_APPROVAL,
        due_date=(now + timedelta(days=3)).date(),
    )
    TaskComment.objects.create(
        task=t_cctv2,
        author=cctv_staff,
        content="Footage audit completed with zero anomalies found. Submitted for GM verification."
    )

    t_cctv3 = Task.objects.create(
        title="NAS Storage Video Archiving & Tape Backup",
        description="Archive 30-day surveillance footage cycle to secondary encrypted network storage.",
        department=cctv_dept,
        assigned_to=cctv_staff,
        created_by=cctv_manager,
        priority=Task.PRIORITY_MEDIUM,
        status=Task.STATUS_TODO,
        due_date=(now + timedelta(days=6)).date(),
    )

    print("Generating Initial Notifications and Dispatched Emails...")
    dispatch_email_and_notification(
        recipient=gm_user,
        subject=f"✉️ Task Awaiting Verification: {t1.title}",
        body=f"Task '{t1.title}' in Engineering has been marked complete by Sarah Chen and awaits your GM review.",
        event_type="GM_REVIEW_REQUEST",
        task=t1
    )

    dispatch_email_and_notification(
        recipient=gm_user,
        subject=f"✉️ Task Awaiting Verification: {t5.title}",
        body=f"Task '{t5.title}' in Marketing has been marked complete by Emma Watson and awaits your GM review.",
        event_type="GM_REVIEW_REQUEST",
        task=t5
    )

    dispatch_email_and_notification(
        recipient=carlos,
        subject=f"✉️ Changes Requested: {t6.title}",
        body=f"GM Arthur Vance requested revisions: 'Please update typography guidelines with high-contrast accessibility standards before sign-off.'",
        event_type="GM_CHANGES_REQUESTED",
        task=t6
    )

    dispatch_email_and_notification(
        recipient=sarah,
        subject=f"✉️ Task Verified & Closed: {t4.title}",
        body=f"GM Arthur Vance has officially verified and closed task '{t4.title}'. Remarks: 'Traces verified in staging APM. Great performance latency reduction.'",
        event_type="GM_APPROVED",
        task=t4
    )

    print("Logging activity events...")
    log_activity(eng_manager, "CREATED_TASK", f"Assigned task '{t1.title}' to Sarah Chen", department=eng_dept, task=t1)
    log_activity(sarah, "SUBMITTED_TASK_FOR_APPROVAL", f"Submitted '{t1.title}' for GM sign-off", department=eng_dept, task=t1)
    log_activity(gm_user, "GM_VERIFIED_TASK", f"Verified and closed '{t4.title}'", department=eng_dept, task=t4)
    log_activity(gm_user, "GM_REQUESTED_CHANGES", f"Requested revisions on '{t6.title}'", department=mkt_dept, task=t6)

    print("\nDatabase seed completed successfully!")
    print("Personas created:")
    print("  • Super Admin:       admin / admin")
    print("  • General Manager:   gm / gm (Arthur Vance)")
    print("  • Eng Manager:       alex.manager / alex (Alex Rivera)")
    print("  • Eng Staff:         sarah.chen / sarah (Sarah Chen)")
    print("  • Eng Staff:         david.kim / david (David Kim)")
    print("  • Marketing Manager: maya.manager / maya (Maya Lin)")
    print("  • Marketing Staff:   carlos.diaz / carlos (Carlos Diaz)")
    print("  • Marketing Staff:   emma.watson / emma (Emma Watson)")


if __name__ == '__main__':
    run_seed()
