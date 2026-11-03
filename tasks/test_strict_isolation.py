import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'task_tracker.settings')
django.setup()

from django.test import RequestFactory
from django.db import transaction
from rest_framework.request import Request
from tasks.models import User, Department, Task, RoutineWorkItem
from tasks.views import TaskViewSet, RoutineWorkItemViewSet, dashboard_stats
from tasks.services import get_task_target_recipients


def run_verification():
    rf = RequestFactory()

    gm = User.objects.filter(role=User.ROLE_GENERAL_MANAGER).first()
    admin = User.objects.filter(role=User.ROLE_SUPER_ADMIN).first()
    td = Department.objects.filter(code='TD').first()
    nandha = User.objects.filter(username__iexact='Transport').first()

    with transaction.atomic():
        pavit, _ = User.objects.get_or_create(
            username='pavithran_verify_user',
            defaults={
                'first_name': 'Pavithran',
                'last_name': 'K',
                'role': User.ROLE_STAFF,
                'department': td
            }
        )
        pavit.department = td
        pavit.save()

        # Task 1: Assigned to Nandha Kumar
        t1 = Task.objects.create(
            title='Bus Maintenance Checklist',
            department=td,
            assigned_to=nandha,
            created_by=gm,
            priority=Task.PRIORITY_HIGH,
            status=Task.STATUS_TODO
        )

        # Task 2: Assigned to Pavithran
        t2 = Task.objects.create(
            title='Driver Attendance Log',
            department=td,
            assigned_to=pavit,
            created_by=gm,
            priority=Task.PRIORITY_MEDIUM,
            status=Task.STATUS_TODO
        )

        # Task 3: Co-assigned to both Nandha and Pavithran
        co_team_str = f'<!-- CO_ASSIGN_TEAM:[{{"assignedToId": {pavit.id}, "staffName": "Pavithran"}}] -->'
        t3 = Task.objects.create(
            title='Route 5 Inspection Joint Deliverable',
            department=td,
            assigned_to=nandha,
            description=f'Joint check details {co_team_str}',
            created_by=gm,
            priority=Task.PRIORITY_URGENT,
            status=Task.STATUS_TODO
        )

        # Verification 1: Pavithran TaskViewSet Queryset
        view = TaskViewSet()
        req_pavit = Request(rf.get('/api/tasks/'))
        req_pavit._user = pavit
        view.request = req_pavit
        pavit_tasks = list(view.get_queryset())
        pavit_task_ids = [t.id for t in pavit_tasks]

        print(f"[*] Pavithran visible tasks: {pavit_task_ids}")
        assert t1.id not in pavit_task_ids, "SECURITY VIOLATION: Pavithran saw Nandha Kumar task t1!"
        assert t2.id in pavit_task_ids, "FAILURE: Pavithran did not see his own task t2!"
        assert t3.id in pavit_task_ids, "FAILURE: Pavithran did not see co-assigned task t3!"
        print("[VERIFIED 1] Pavithran CANNOT see Nandha Kumar's task, but sees his own task and co-assigned task.")

        # Verification 2: Nandha Kumar TaskViewSet Queryset
        view_n = TaskViewSet()
        req_nandha = Request(rf.get('/api/tasks/'))
        req_nandha._user = nandha
        view_n.request = req_nandha
        nandha_tasks = list(view_n.get_queryset())
        nandha_task_ids = [t.id for t in nandha_tasks]

        print(f"[*] Nandha Kumar visible tasks: {nandha_task_ids}")
        assert t1.id in nandha_task_ids, "FAILURE: Nandha did not see task t1!"
        assert t2.id not in nandha_task_ids, "SECURITY VIOLATION: Nandha saw Pavithran task t2!"
        assert t3.id in nandha_task_ids, "FAILURE: Nandha did not see co-assigned task t3!"
        print("[VERIFIED 2] Nandha Kumar CANNOT see Pavithran's task, but sees his own task and co-assigned task.")

        # Verification 3: GM Overview Queryset
        view_gm = TaskViewSet()
        req_gm = Request(rf.get('/api/tasks/'))
        req_gm._user = gm
        view_gm.request = req_gm
        gm_tasks = list(view_gm.get_queryset())
        gm_task_ids = [t.id for t in gm_tasks]
        assert t1.id in gm_task_ids and t2.id in gm_task_ids and t3.id in gm_task_ids, "FAILURE: GM cannot see all tasks!"
        print("[VERIFIED 3] GM can oversee all tasks across all users.")

        # Verification 4: Notification Recipient Isolation
        recipients_t1 = get_task_target_recipients(t1)
        recipients_t2 = get_task_target_recipients(t2)
        recipients_t3 = get_task_target_recipients(t3)

        assert pavit not in recipients_t1, "SECURITY VIOLATION: Pavithran in t1 recipients!"
        assert nandha in recipients_t1, "FAILURE: Nandha not in t1 recipients!"
        assert nandha not in recipients_t2, "SECURITY VIOLATION: Nandha in t2 recipients!"
        assert pavit in recipients_t2, "FAILURE: Pavithran not in t2 recipients!"
        assert nandha in recipients_t3 and pavit in recipients_t3, "FAILURE: Co-assignees missing in t3!"
        print("[VERIFIED 4] Notifications strictly sent only to assignee and co-assignees. Never leaked to other staff/managers.")

        # Verification 5: Routine Work Checklist Isolation
        r1 = RoutineWorkItem.objects.create(title='Nandha Daily Inspection', department=td, assigned_to=nandha, created_by=gm, frequency='DAILY')
        r2 = RoutineWorkItem.objects.create(title='Pavithran Daily Bus Cleaning', department=td, assigned_to=pavit, created_by=gm, frequency='DAILY')

        rview = RoutineWorkItemViewSet()
        req_pavit_r = Request(rf.get('/api/routine-items/'))
        req_pavit_r._user = pavit
        rview.request = req_pavit_r
        pavit_routine_ids = [r.id for r in rview.get_queryset()]

        assert r1.id not in pavit_routine_ids, "SECURITY VIOLATION: Pavithran saw Nandha routine item r1!"
        assert r2.id in pavit_routine_ids, "FAILURE: Pavithran did not see his routine item r2!"
        print("[VERIFIED 5] Routine checklist strictly isolated to assigned individual.")

        # Verification 6: Unauthorized Direct Task Detail Access (404)
        # Pavithran attempts to fetch Nandha's task t1 by ID
        req_pavit_detail = Request(rf.get(f'/api/tasks/{t1.id}/'))
        req_pavit_detail._user = pavit
        view_detail = TaskViewSet()
        view_detail.request = req_pavit_detail
        view_detail.kwargs = {'pk': str(t1.id)}
        qs_detail = view_detail.get_queryset().filter(pk=t1.id)
        assert not qs_detail.exists(), "SECURITY VIOLATION: Pavithran was able to query Nandha's task t1 by ID!"
        print("[VERIFIED 6] Unauthorized task detail query strictly returns empty/404.")

        # Verification 7: Dashboard Stats Isolation
        req_pavit_stats = rf.get('/api/dashboard-stats/')
        req_pavit_stats.user = pavit
        resp_pavit_stats = dashboard_stats(req_pavit_stats)
        # Pavithran should only have 2 tasks (t2 and t3)
        assert resp_pavit_stats.data['total_tasks'] == 2, f"SECURITY VIOLATION: Stats counted non-assigned tasks! Got: {resp_pavit_stats.data['total_tasks']}"
        print("[VERIFIED 7] Dashboard stats strictly count only the user's assigned tasks (2 tasks).")

        # Rollback all test data so database remains unchanged
        transaction.set_rollback(True)
        print("\n=======================================================")
        print("  ALL 7 STRICT TASK ISOLATION TESTS PASSED PERFECTLY!  ")
        print("=======================================================\n")


if __name__ == '__main__':
    run_verification()
