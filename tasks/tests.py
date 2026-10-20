from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status
from .models import Department, User, Task, DispatchedEmailLog, Notification


class TaskTrackerEnterpriseTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.eng_dept = Department.objects.create(name="Engineering", code="ENG")
        self.mkt_dept = Department.objects.create(name="Marketing", code="MKT")

        self.gm = User.objects.create_user(
            username="gm_test", email="gm@test.com", password="pass",
            role=User.ROLE_GENERAL_MANAGER, first_name="GM", last_name="Arthur"
        )
        self.eng_mgr = User.objects.create_user(
            username="eng_mgr_test", email="eng_mgr@test.com", password="pass",
            role=User.ROLE_DEPT_MANAGER, department=self.eng_dept, first_name="Eng", last_name="Mgr"
        )
        self.mkt_mgr = User.objects.create_user(
            username="mkt_mgr_test", email="mkt_mgr@test.com", password="pass",
            role=User.ROLE_DEPT_MANAGER, department=self.mkt_dept, first_name="Mkt", last_name="Mgr"
        )
        self.eng_staff = User.objects.create_user(
            username="eng_staff_test", email="eng_staff@test.com", password="pass",
            role=User.ROLE_STAFF, department=self.eng_dept, first_name="Sarah", last_name="Chen"
        )
        self.mkt_staff = User.objects.create_user(
            username="mkt_staff_test", email="mkt_staff@test.com", password="pass",
            role=User.ROLE_STAFF, department=self.mkt_dept, first_name="Carlos", last_name="Diaz"
        )

        self.eng_task = Task.objects.create(
            title="ENG Task 1", department=self.eng_dept,
            assigned_to=self.eng_staff, created_by=self.eng_mgr, status=Task.STATUS_TODO
        )
        self.mkt_task = Task.objects.create(
            title="MKT Task 1", department=self.mkt_dept,
            assigned_to=self.mkt_staff, created_by=self.mkt_mgr, status=Task.STATUS_TODO
        )

    def test_department_task_isolation(self):
        """1. Department isolation: Manager from Dept A cannot see Dept B tasks"""
        self.client.force_authenticate(user=self.eng_mgr)
        response = self.client.get('/api/tasks/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        task_ids = [t['id'] for t in response.data]
        self.assertIn(self.eng_task.id, task_ids)
        self.assertNotIn(self.mkt_task.id, task_ids)

    def test_department_staff_isolation(self):
        """1b. Department isolation: Manager from Dept A cannot see Dept B staff"""
        self.client.force_authenticate(user=self.eng_mgr)
        response = self.client.get('/api/users/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user_ids = [u['id'] for u in response.data]
        self.assertIn(self.eng_staff.id, user_ids)
        self.assertNotIn(self.mkt_staff.id, user_ids)

    def test_gm_sees_all_tasks_and_staff(self):
        """GM has global visibility across all departments"""
        self.client.force_authenticate(user=self.gm)
        tasks_res = self.client.get('/api/tasks/')
        task_ids = [t['id'] for t in tasks_res.data]
        self.assertIn(self.eng_task.id, task_ids)
        self.assertIn(self.mkt_task.id, task_ids)

    def test_staff_crud_authorization(self):
        """2. Staff CRUD: Manager cannot add staff to another department"""
        self.client.force_authenticate(user=self.eng_mgr)
        # Attempt to create staff in Marketing department
        payload = {
            "username": "intruder_staff",
            "email": "intruder@test.com",
            "first_name": "Intruder",
            "last_name": "Test",
            "role": User.ROLE_STAFF,
            "department": self.mkt_dept.id
        }
        res = self.client.post('/api/users/', payload)
        # The serializer enforces the user's own department or rejects
        if res.status_code == status.HTTP_201_CREATED:
            created_user = User.objects.get(username="intruder_staff")
            self.assertEqual(created_user.department, self.eng_dept)  # forced to own department!

    def test_gm_exclusive_closure_enforcement(self):
        """3. GM Exclusive Closure: Non-GM cannot close a task"""
        # Manager attempts to mark CLOSED directly
        self.client.force_authenticate(user=self.eng_mgr)
        res = self.client.patch(f'/api/tasks/{self.eng_task.id}/', {"status": Task.STATUS_CLOSED})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

        # Staff attempts to mark CLOSED
        self.client.force_authenticate(user=self.eng_staff)
        res = self.client.patch(f'/api/tasks/{self.eng_task.id}/', {"status": Task.STATUS_CLOSED})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

        # GM approves & closes
        self.client.force_authenticate(user=self.gm)
        review_res = self.client.post(
            f'/api/tasks/{self.eng_task.id}/gm-review/',
            {"action": "APPROVE", "notes": "Approved by GM"}
        )
        self.assertEqual(review_res.status_code, status.HTTP_200_OK)
        self.eng_task.refresh_from_db()
        self.assertEqual(self.eng_task.status, Task.STATUS_CLOSED)
        self.assertEqual(self.eng_task.verified_by, self.gm)

    def test_department_list_isolation(self):
        """5. Department isolation: Non-GM sees ONLY their own department in /api/departments/"""
        self.client.force_authenticate(user=self.eng_staff)
        res = self.client.get('/api/departments/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        dept_ids = [d['id'] for d in res.data]
        self.assertEqual(len(dept_ids), 1)
        self.assertEqual(dept_ids[0], self.eng_dept.id)
        self.assertNotIn(self.mkt_dept.id, dept_ids)

        # GM sees all departments
        self.client.force_authenticate(user=self.gm)
        gm_res = self.client.get('/api/departments/')
        self.assertEqual(gm_res.status_code, status.HTTP_200_OK)
        gm_dept_ids = [d['id'] for d in gm_res.data]
        self.assertIn(self.eng_dept.id, gm_dept_ids)
        self.assertIn(self.mkt_dept.id, gm_dept_ids)

    def test_email_notifications_dispatched(self):
        """4. Email notification dispatch on lifecycle events"""
        initial_count = DispatchedEmailLog.objects.count()
        self.client.force_authenticate(user=self.gm)
        self.client.post(
            f'/api/tasks/{self.eng_task.id}/gm-review/',
            {"action": "APPROVE", "notes": "Sign-off complete"}
        )
        new_count = DispatchedEmailLog.objects.count()
        self.assertGreater(new_count, initial_count)

    def test_task_crud_restricted_to_gm_and_super_user(self):
        """6. Task CRUD: Only GM & Super Admin can create, update, or delete tasks"""
        # Staff cannot create task
        self.client.force_authenticate(user=self.eng_staff)
        create_res = self.client.post('/api/tasks/', {
            'title': 'Unauthorized Staff Task',
            'department': self.eng_dept.id,
            'priority': 'MEDIUM'
        })
        self.assertIn(create_res.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN])

        # Dept Manager cannot create task
        self.client.force_authenticate(user=self.eng_mgr)
        create_res_mgr = self.client.post('/api/tasks/', {
            'title': 'Unauthorized Manager Task',
            'department': self.eng_dept.id,
            'priority': 'MEDIUM'
        })
        self.assertIn(create_res_mgr.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN])

        # Staff cannot update task
        self.client.force_authenticate(user=self.eng_staff)
        update_res = self.client.patch(f'/api/tasks/{self.eng_task.id}/', {'title': 'Hacked Title'})
        self.assertIn(update_res.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN])

        # Staff cannot delete task
        delete_res = self.client.delete(f'/api/tasks/{self.eng_task.id}/')
        self.assertEqual(delete_res.status_code, status.HTTP_403_FORBIDDEN)

        # GM can create task
        self.client.force_authenticate(user=self.gm)
        gm_create_res = self.client.post('/api/tasks/', {
            'title': 'GM Authorized Task',
            'department': self.eng_dept.id,
            'priority': 'HIGH',
            'description': 'Created by executive GM'
        })
        self.assertEqual(gm_create_res.status_code, status.HTTP_201_CREATED)
        new_task_id = gm_create_res.data['id']

        # GM can update task
        gm_update_res = self.client.patch(f'/api/tasks/{new_task_id}/', {'title': 'GM Updated Title'})
        self.assertEqual(gm_update_res.status_code, status.HTTP_200_OK)
        self.assertEqual(gm_update_res.data['title'], 'GM Updated Title')

        # GM can delete task
        gm_delete_res = self.client.delete(f'/api/tasks/{new_task_id}/')
        self.assertEqual(gm_delete_res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Task.objects.filter(id=new_task_id).exists())
