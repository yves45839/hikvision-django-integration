from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from devices.models import Device
from employees.models import (
    AccessGroup,
    Department,
    Employee,
    Organization,
    Planning,
    PlanningAssignment,
    PlanningEntry,
    PlanningPeriod,
    WorkShift,
)
from employees.services import build_card_info_payloads
from tenants.models import Tenant


User = get_user_model()


class EmployeeApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="emp-admin", password="pass", is_staff=True)
        self.client.force_authenticate(user=self.user)

        self.tenant = Tenant.objects.create(name="Tenant Employees", code="tenant-employees")
        self.device = Device.objects.create(
            owner=self.user,
            tenant=self.tenant,
            serial_number="SN-EMP-1",
            dev_index="IDX-EMP-1",
        )
        self.device_secondary = Device.objects.create(
            owner=self.user,
            tenant=self.tenant,
            serial_number="SN-EMP-2",
            dev_index="IDX-EMP-2",
        )
        self.organization = Organization.objects.create(
            tenant=self.tenant,
            name="HQ",
            code="ORG-HQ",
        )
        self.root_planning = Planning.objects.create(
            tenant=self.tenant,
            name="Planning Root",
            code="PLN-ROOT",
        )
        self.root_department = Department.objects.create(
            tenant=self.tenant,
            organization=self.organization,
            name="Direction",
            code="DEP-DIR",
            planning=self.root_planning,
        )
        self.child_department = Department.objects.create(
            tenant=self.tenant,
            organization=self.organization,
            parent=self.root_department,
            name="RH",
            code="DEP-RH",
        )
        self.shift_morning = WorkShift.objects.create(
            tenant=self.tenant,
            name="Matin",
            code="SHIFT-AM",
            start_time="08:00:00",
            end_time="12:00:00",
        )
        self.shift_evening = WorkShift.objects.create(
            tenant=self.tenant,
            name="Soir",
            code="SHIFT-PM",
            start_time="14:00:00",
            end_time="18:00:00",
        )
        self.access_group_main = AccessGroup.objects.create(
            tenant=self.tenant,
            planning=self.root_planning,
            name="Main Access",
            code="AG-MAIN",
        )
        self.access_group_main.readers.add(self.device)
        self.access_group_secondary = AccessGroup.objects.create(
            tenant=self.tenant,
            planning=self.root_planning,
            name="Secondary Access",
            code="AG-SECONDARY",
        )
        self.access_group_secondary.readers.add(self.device_secondary)

    @patch("employees.views.get_shared_gateway_client")
    def test_create_employee_with_attributes(self, mock_get_client):
        mock_client = mock_get_client.return_value
        mock_client.add_access_user.return_value = {"status": "ok"}
        mock_client.add_access_card.return_value = {"status": "ok"}
        mock_client.add_access_fingerprint.return_value = {"status": "ok"}

        response = self.client.post(
            "/api/employees/",
            {
                "tenant": self.tenant.id,
                "devices": [self.device.id],
                "department": self.child_department.id,
                "employee_no": "E1001",
                "name": "Jean Kouassi",
                "first_name": "Jean",
                "last_name": "Kouassi",
                "cards": [
                    {"card_no": "CARD-001", "card_type": "normalCard"},
                    {"card_no": "CARD-002", "card_type": "normalCard"},
                ],
                "fingerprints": [
                    {"finger_index": 1, "template": "fp-template-1"},
                    {"finger_index": 2, "template": "fp-template-2"},
                ],
                "face": {"face_data": "face-template"},
                "attributes": [
                    {"name": "user_type", "value": "normal"},
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()["gateway_push"]["status"], "ok")
        employee = Employee.objects.get(employee_no="E1001")
        self.assertEqual(employee.tenant, self.tenant)
        self.assertFalse(employee.needs_gateway_push)
        self.assertEqual(employee.attributes.count(), 1)
        self.assertEqual(employee.department, self.child_department)
        self.assertEqual(employee.effective_planning, self.root_planning)
        self.assertEqual(employee.cards.count(), 2)
        self.assertEqual(employee.fingerprints.count(), 2)
        self.assertTrue(hasattr(employee, "face"))
        mock_client.add_access_user.assert_called_once()
        self.assertEqual(mock_client.add_access_card.call_count, 2)
        self.assertEqual(mock_client.add_access_fingerprint.call_count, 2)

    @patch("employees.views.get_shared_gateway_client")
    def test_push_to_gateway_uses_user_card_and_fingerprint_endpoints(self, mock_get_client):
        employee = Employee.objects.create(
            tenant=self.tenant,
            department=self.child_department,
            employee_no="E2002",
            name="Awa Traore",
            first_name="Awa",
            last_name="Traore",
            is_active=True,
        )
        employee.devices.add(self.device)
        employee.cards.create(card_no="CARD-001", card_type="normalCard")
        employee.cards.create(card_no="CARD-002", card_type="normalCard")
        employee.fingerprints.create(finger_index=1, template="fp-template-a")
        employee.fingerprints.create(finger_index=2, template="fp-template-b")

        mock_client = mock_get_client.return_value
        mock_client.add_access_user.return_value = {"status": "ok"}
        mock_client.add_access_card.return_value = {"status": "ok"}
        mock_client.add_access_fingerprint.return_value = {"status": "ok"}

        response = self.client.post(f"/api/employees/{employee.id}/push-to-gateway/", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["status"], "ok")
        mock_client.add_access_user.assert_called_once()
        self.assertEqual(mock_client.add_access_card.call_count, 2)
        self.assertEqual(mock_client.add_access_fingerprint.call_count, 2)

    @patch("employees.views.get_shared_gateway_client")
    def test_push_to_gateway_still_pushes_cards_when_user_already_exists(self, mock_get_client):
        employee = Employee.objects.create(
            tenant=self.tenant,
            department=self.child_department,
            employee_no="E2003",
            name="Existing User",
            is_active=True,
        )
        employee.devices.add(self.device)
        employee.cards.create(card_no="CARD-EX-001", card_type="normalCard")

        mock_client = mock_get_client.return_value
        mock_client.add_access_user.side_effect = Exception("employeeNoAlreadyExist")
        mock_client.add_access_card.return_value = {"status": "ok"}

        response = self.client.post(f"/api/employees/{employee.id}/push-to-gateway/", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(mock_client.add_access_user.call_count, 1)
        self.assertEqual(mock_client.add_access_card.call_count, 1)
        pushed_rows = response.json()["pushed"]
        self.assertEqual(pushed_rows[0]["user_response"]["subStatusCode"], "employeeNoAlreadyExist")

    def test_build_card_payload_preserves_non_numeric_card_number(self):
        employee = Employee.objects.create(
            tenant=self.tenant,
            department=self.child_department,
            employee_no="E2004",
            name="Card Format",
        )
        employee.cards.create(card_no="CARD-AB12-001", card_type="normalCard")

        payloads = build_card_info_payloads(employee)

        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0]["CardInfo"]["cardNo"], "CARD-AB12-001")

    @patch("employees.views.get_shared_gateway_client")
    def test_push_to_gateway_uses_department_devices_when_mode_department_only(self, mock_get_client):
        self.child_department.devices.add(self.device_secondary)
        employee = Employee.objects.create(
            tenant=self.tenant,
            department=self.child_department,
            employee_no="E2100",
            name="Dept Device",
            device_assignment_mode=Employee.DEVICE_ASSIGNMENT_DEPARTMENT_ONLY,
        )

        mock_client = mock_get_client.return_value
        mock_client.add_access_user.return_value = {"status": "ok"}
        mock_client.add_access_card.return_value = {"status": "ok"}

        response = self.client.post(f"/api/employees/{employee.id}/push-to-gateway/", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(mock_client.add_access_user.call_count, 1)
        called_dev_index = mock_client.add_access_user.call_args.kwargs["dev_index"]
        self.assertEqual(called_dev_index, self.device_secondary.dev_index)

    @patch("employees.views.get_shared_gateway_client")
    def test_push_to_gateway_combined_mode_deduplicates_employee_and_department_devices(self, mock_get_client):
        self.child_department.devices.add(self.device, self.device_secondary)
        employee = Employee.objects.create(
            tenant=self.tenant,
            department=self.child_department,
            employee_no="E2200",
            name="Combined Device",
            device_assignment_mode=Employee.DEVICE_ASSIGNMENT_COMBINED,
        )
        employee.devices.add(self.device)

        mock_client = mock_get_client.return_value
        mock_client.add_access_user.return_value = {"status": "ok"}
        mock_client.add_access_card.return_value = {"status": "ok"}

        response = self.client.post(f"/api/employees/{employee.id}/push-to-gateway/", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(mock_client.add_access_user.call_count, 2)
        pushed_indexes = {
            call.kwargs["dev_index"]
            for call in mock_client.add_access_user.call_args_list
        }
        self.assertEqual(
            pushed_indexes,
            {self.device.dev_index, self.device_secondary.dev_index},
        )

    def test_create_employee_rejects_department_from_another_tenant(self):
        foreign_tenant = Tenant.objects.create(name="Tenant Foreign", code="tenant-foreign")
        foreign_org = Organization.objects.create(tenant=foreign_tenant, name="Foreign Org", code="ORG-FRG")
        foreign_department = Department.objects.create(
            tenant=foreign_tenant,
            organization=foreign_org,
            name="IT",
            code="DEP-IT",
        )

        response = self.client.post(
            "/api/employees/",
            {
                "tenant": self.tenant.id,
                "department": foreign_department.id,
                "employee_no": "E3003",
                "name": "Test Foreign Department",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("department", response.json())

    @patch("employees.views.get_shared_gateway_client")
    def test_post_employees_upsert_updates_existing_employee(self, mock_get_client):
        existing = Employee.objects.create(
            tenant=self.tenant,
            department=self.child_department,
            employee_no="E7007",
            name="Old Name",
        )
        existing.devices.add(self.device)

        mock_client = mock_get_client.return_value
        mock_client.add_access_user.return_value = {"status": "ok"}
        mock_client.add_access_card.return_value = {"status": "ok"}

        response = self.client.post(
            "/api/employees/",
            {
                "tenant": self.tenant.id,
                "department": self.child_department.id,
                "devices": [self.device.id],
                "employee_no": "E7007",
                "name": "New Name",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["id"], existing.id)
        self.assertEqual(response.json()["name"], "New Name")
        self.assertEqual(response.json()["gateway_push"]["status"], "ok")
        self.assertEqual(Employee.objects.filter(tenant=self.tenant, employee_no="E7007").count(), 1)

    @patch("employees.views.get_shared_gateway_client")
    def test_import_from_gateway_upserts_employees(self, mock_get_client):
        mock_client = mock_get_client.return_value
        mock_client.search_access_users_all.return_value = {
            "UserInfoSearch": {
                "searchID": "1",
                "responseStatusStrg": "OK",
                "numOfMatches": 2,
                "totalMatches": 2,
                "UserInfo": [
                    {
                        "employeeNo": "IMP1001",
                        "name": "Imported One",
                        "firstName": "Imported",
                        "lastName": "One",
                        "userType": "normal",
                        "doorRight": "1",
                        "RightPlan": [{"doorNo": 1, "planTemplateNo": "1"}],
                        "localUIRight": True,
                        "isSuperUser": True,
                        "isBlocklisted": False,
                        "isDeviceOperator": True,
                        "customProfile": "staff",
                        "remark": "badge actif",
                        "dateOfBirth": "1990-01-10",
                        "certificateType": "passport",
                        "certificateNo": "AB123456",
                        "position": "Supervisor",
                        "hireDate": "2020-05-20",
                        "address": "Abidjan",
                        "Valid": {
                            "enable": True,
                            "beginTime": "2026-01-01T08:00:00",
                            "endTime": "2027-01-01T08:00:00",
                        },
                    },
                    {
                        "employeeNo": "IMP1002",
                        "name": "Imported Two",
                        "userType": "visitor",
                        "Valid": {
                            "enable": False,
                            "beginTime": "2026-01-01T08:00:00",
                            "endTime": "2027-01-01T08:00:00",
                        },
                    },
                ],
            }
        }
        mock_client.search_access_cards_all.return_value = {
            "CardInfoSearch": {
                "searchID": "1",
                "responseStatusStrg": "OK",
                "numOfMatches": 1,
                "totalMatches": 1,
                "CardInfo": [
                    {
                        "employeeNo": "IMP1001",
                        "cardNo": "CARD-IMP-001",
                        "cardType": "normalCard",
                    }
                ],
            }
        }
        mock_client.search_access_fingerprints_all.side_effect = lambda **kwargs: (
            {
                "FingerPrintInfo": {
                    "searchID": "1",
                    "status": "OK",
                    "FingerPrintList": [
                        {
                            "cardReaderNo": 1,
                            "fingerPrintID": 1,
                            "fingerType": "normalFP",
                            "fingerData": "fp-imported-1",
                        }
                    ],
                }
            }
            if kwargs.get("employee_no") == "IMP1001"
            else {
                "FingerPrintInfo": {
                    "searchID": "1",
                    "status": "NoFP",
                    "FingerPrintList": [],
                }
            }
        )

        response = self.client.post(
            "/api/employees/import-from-gateway/",
            {
                "tenant": self.tenant.id,
                "dev_indexes": [self.device.dev_index],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["imported_count"], 2)
        self.assertIn("gateway_user_info", response.json()["imported"][0])
        self.assertIn("RightPlan", response.json()["imported"][0]["gateway_user_info"])
        imported_rows = {row["employee_no"]: row for row in response.json()["imported"]}
        self.assertIn("CARD-IMP-001", imported_rows["IMP1001"]["card_numbers"])
        self.assertEqual(imported_rows["IMP1001"]["fingerprint_slots"], [1])
        self.assertEqual(Employee.objects.filter(tenant=self.tenant, employee_no="IMP1001").count(), 1)
        self.assertEqual(Employee.objects.filter(tenant=self.tenant, employee_no="IMP1002").count(), 1)
        imported = Employee.objects.get(tenant=self.tenant, employee_no="IMP1001")
        self.assertTrue(imported.devices.filter(id=self.device.id).exists())
        self.assertFalse(imported.needs_gateway_push)
        self.assertEqual(imported.attributes.get(name="user_type").value, "normal")
        self.assertEqual(imported.attributes.get(name="gateway_door_right").value, "1")
        self.assertIn("planTemplateNo", imported.attributes.get(name="gateway_right_plan").value)
        self.assertEqual(imported.attributes.get(name="gateway_valid_begin_time").value, "2026-01-01T08:00:00")
        self.assertEqual(imported.attributes.get(name="door_no").value, "1")
        self.assertEqual(imported.attributes.get(name="plan_template_no").value, "1")
        self.assertTrue(imported.is_super_user)
        self.assertFalse(imported.is_visitor)
        self.assertTrue(imported.is_device_operator)
        self.assertEqual(imported.custom_profile, "staff")
        self.assertEqual(imported.identity_type, "passport")
        self.assertEqual(imported.identity_no, "AB123456")
        self.assertTrue(imported.cards.filter(card_no="CARD-IMP-001").exists())
        self.assertTrue(imported.fingerprints.filter(finger_index=1, template="fp-imported-1").exists())

    def test_department_effective_planning_uses_parent(self):
        response = self.client.get(f"/api/departments/{self.child_department.id}/", format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["effective_planning"]["id"], self.root_planning.id)

    def test_department_can_assign_devices(self):
        response = self.client.patch(
            f"/api/departments/{self.child_department.id}/",
            {
                "devices": [self.device.id, self.device_secondary.id],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.child_department.refresh_from_db()
        self.assertEqual(
            set(self.child_department.devices.values_list("id", flat=True)),
            {self.device.id, self.device_secondary.id},
        )

    def test_assign_planning_prompts_reader_selection_when_not_provided(self):
        employee = Employee.objects.create(
            tenant=self.tenant,
            department=self.child_department,
            employee_no="E9001",
            name="Prompt Reader",
        )

        response = self.client.post(
            f"/api/employees/{employee.id}/assign-planning/",
            {"planning": self.root_planning.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertIn("reader_selection_prompt", payload)
        self.assertTrue(payload["reader_selection_prompt"].get("reader_selection_required"))
        self.assertIn("available_readers", payload["reader_selection_prompt"])
        self.assertGreaterEqual(len(payload["reader_selection_prompt"]["available_readers"]), 1)

    @patch("employees.views.get_shared_gateway_client")
    def test_assign_planning_accepts_readers_and_mode(self, mock_get_client):
        mock_client = mock_get_client.return_value
        mock_client.add_access_user.return_value = {"status": "ok"}
        mock_client.add_access_card.return_value = {"status": "ok"}
        mock_client.add_access_fingerprint.return_value = {"status": "ok"}

        employee = Employee.objects.create(
            tenant=self.tenant,
            department=self.child_department,
            employee_no="E9002",
            name="Assign Reader",
        )

        response = self.client.post(
            f"/api/employees/{employee.id}/assign-planning/",
            {
                "planning": self.root_planning.id,
                "reader_ids": [self.device.id, self.device_secondary.id],
                "device_assignment_mode": Employee.DEVICE_ASSIGNMENT_EMPLOYEE_ONLY,
                "push_now": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        employee.refresh_from_db()
        self.assertEqual(employee.planning_id, self.root_planning.id)
        self.assertEqual(employee.device_assignment_mode, Employee.DEVICE_ASSIGNMENT_EMPLOYEE_ONLY)
        self.assertEqual(
            set(employee.devices.values_list("id", flat=True)),
            {self.device.id, self.device_secondary.id},
        )
        self.assertIn("reader_selection", response.json())

    @patch("employees.views.get_shared_gateway_client")
    def test_assign_devices_replaces_employee_readers(self, mock_get_client):
        mock_client = mock_get_client.return_value
        mock_client.add_access_user.return_value = {"status": "ok"}
        mock_client.add_access_card.return_value = {"status": "ok"}
        mock_client.add_access_fingerprint.return_value = {"status": "ok"}

        employee = Employee.objects.create(
            tenant=self.tenant,
            department=self.child_department,
            employee_no="E9003",
            name="Assign Devices",
        )
        employee.devices.add(self.device)
        employee.needs_gateway_push = False
        employee.last_gateway_push_at = timezone.now()
        employee.save(update_fields=["needs_gateway_push", "last_gateway_push_at", "updated_at"])

        response = self.client.post(
            f"/api/employees/{employee.id}/assign-devices/",
            {
                "devices": [self.device_secondary.id],
                "device_assignment_mode": Employee.DEVICE_ASSIGNMENT_EMPLOYEE_ONLY,
                "push_now": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        employee.refresh_from_db()
        self.assertEqual(employee.device_assignment_mode, Employee.DEVICE_ASSIGNMENT_EMPLOYEE_ONLY)
        self.assertEqual(set(employee.devices.values_list("id", flat=True)), {self.device_secondary.id})
        self.assertTrue(employee.needs_gateway_push)
        self.assertIsNone(employee.last_gateway_push_at)
        self.assertIn("reader_selection", response.json())

    @patch("employees.views.get_shared_gateway_client")
    def test_assign_access_groups_replaces_employee_groups(self, mock_get_client):
        mock_client = mock_get_client.return_value
        mock_client.add_access_user.return_value = {"status": "ok"}
        mock_client.add_access_card.return_value = {"status": "ok"}
        mock_client.add_access_fingerprint.return_value = {"status": "ok"}

        employee = Employee.objects.create(
            tenant=self.tenant,
            department=self.child_department,
            employee_no="E9004",
            name="Assign Access Groups",
        )
        employee.access_groups.add(self.access_group_main)
        employee.needs_gateway_push = False
        employee.last_gateway_push_at = timezone.now()
        employee.save(update_fields=["needs_gateway_push", "last_gateway_push_at", "updated_at"])

        response = self.client.post(
            f"/api/employees/{employee.id}/assign-access-groups/",
            {
                "access_groups": [self.access_group_secondary.id],
                "push_now": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        employee.refresh_from_db()
        self.assertEqual(set(employee.access_groups.values_list("id", flat=True)), {self.access_group_secondary.id})
        self.assertTrue(employee.needs_gateway_push)
        self.assertIsNone(employee.last_gateway_push_at)
        self.assertIn("access_group_selection", response.json())

    @patch("employees.views.get_shared_gateway_client")
    def test_access_group_reader_update_auto_syncs_linked_employees(self, mock_get_client):
        employee = Employee.objects.create(
            tenant=self.tenant,
            department=self.child_department,
            employee_no="E9005",
            name="Auto Sync Group",
        )
        employee.access_groups.add(self.access_group_main)
        employee.needs_gateway_push = False
        employee.last_gateway_push_at = timezone.now()
        employee.save(update_fields=["needs_gateway_push", "last_gateway_push_at", "updated_at"])

        mock_client = mock_get_client.return_value
        mock_client.add_access_user.return_value = {"status": "ok"}
        mock_client.add_access_card.return_value = {"status": "ok"}

        response = self.client.patch(
            f"/api/access-groups/{self.access_group_main.id}/",
            {"readers": [self.device_secondary.id]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        employee.refresh_from_db()
        self.assertFalse(employee.needs_gateway_push)
        self.assertIsNotNone(employee.last_gateway_push_at)
        mock_client.add_access_user.assert_called_once()
        self.assertEqual(
            mock_client.add_access_user.call_args.kwargs["dev_index"],
            self.device_secondary.dev_index,
        )

    @patch("employees.views.get_shared_gateway_client")
    def test_access_group_reader_update_can_defer_auto_sync(self, mock_get_client):
        employee = Employee.objects.create(
            tenant=self.tenant,
            department=self.child_department,
            employee_no="E9006",
            name="Deferred Group Sync",
        )
        employee.access_groups.add(self.access_group_main)
        employee.needs_gateway_push = False
        employee.last_gateway_push_at = timezone.now()
        employee.save(update_fields=["needs_gateway_push", "last_gateway_push_at", "updated_at"])

        response = self.client.patch(
            f"/api/access-groups/{self.access_group_main.id}/?push_now=false",
            {"readers": [self.device_secondary.id]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        employee.refresh_from_db()
        self.assertTrue(employee.needs_gateway_push)
        self.assertIsNone(employee.last_gateway_push_at)
        mock_get_client.assert_not_called()

    @patch("employees.views.get_shared_gateway_client")
    def test_department_reader_update_auto_syncs_descendant_employees(self, mock_get_client):
        employee = Employee.objects.create(
            tenant=self.tenant,
            department=self.child_department,
            employee_no="E9007",
            name="Auto Sync Department",
            device_assignment_mode=Employee.DEVICE_ASSIGNMENT_DEPARTMENT_ONLY,
            needs_gateway_push=False,
        )
        employee.last_gateway_push_at = timezone.now()
        employee.save(update_fields=["last_gateway_push_at", "updated_at"])

        mock_client = mock_get_client.return_value
        mock_client.add_access_user.return_value = {"status": "ok"}
        mock_client.add_access_card.return_value = {"status": "ok"}

        response = self.client.patch(
            f"/api/departments/{self.root_department.id}/",
            {"devices": [self.device_secondary.id]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        employee.refresh_from_db()
        self.assertFalse(employee.needs_gateway_push)
        self.assertIsNotNone(employee.last_gateway_push_at)
        mock_client.add_access_user.assert_called_once()
        self.assertEqual(
            mock_client.add_access_user.call_args.kwargs["dev_index"],
            self.device_secondary.dev_index,
        )

    def test_create_employee_requires_name(self):
        response = self.client.post(
            "/api/employees/",
            {
                "tenant": self.tenant.id,
                "department": self.child_department.id,
                "employee_no": "E4004",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("name", response.json())

    def test_reject_more_than_ten_fingerprints(self):
        fingerprints = [{"finger_index": idx, "template": f"fp-{idx}"} for idx in range(1, 12)]
        response = self.client.post(
            "/api/employees/",
            {
                "tenant": self.tenant.id,
                "department": self.child_department.id,
                "employee_no": "E5005",
                "name": "Too Many Fingers",
                "fingerprints": fingerprints,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fingerprints", response.json())

    @patch("employees.views.get_shared_gateway_client")
    def test_patch_employee_updates_name_but_ignores_id(self, mock_get_client):
        mock_client = mock_get_client.return_value
        mock_client.add_access_user.return_value = {"status": "ok"}
        mock_client.add_access_card.return_value = {"status": "ok"}

        employee = Employee.objects.create(
            tenant=self.tenant,
            department=self.child_department,
            employee_no="E8008",
            name="Nom Initial",
            phone="+2250100000000",
        )

        response = self.client.patch(
            f"/api/employees/{employee.id}/",
            {
                "id": employee.id + 999,
                "name": "Nom Modifie",
                "phone": "+2250700000000",
                "remark": "Mise a jour OK",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["gateway_push"]["status"], "skipped")
        employee.refresh_from_db()
        self.assertEqual(employee.name, "Nom Modifie")
        self.assertEqual(employee.phone, "+2250700000000")
        self.assertEqual(employee.remark, "Mise a jour OK")
        self.assertTrue(employee.needs_gateway_push)
        mock_client.add_access_user.assert_not_called()

    @patch("employees.views.get_shared_gateway_client")
    def test_create_employee_with_push_now_true_pushes_immediately(self, mock_get_client):
        mock_client = mock_get_client.return_value
        mock_client.add_access_user.return_value = {"status": "ok"}
        mock_client.add_access_card.return_value = {"status": "ok"}

        response = self.client.post(
            "/api/employees/",
            {
                "tenant": self.tenant.id,
                "devices": [self.device.id],
                "department": self.child_department.id,
                "employee_no": "E9009",
                "name": "Push Direct",
                "cards": [{"card_no": "CARD-9009", "card_type": "normalCard"}],
                "push_now": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()["gateway_push"]["status"], "ok")
        employee = Employee.objects.get(employee_no="E9009")
        self.assertFalse(employee.needs_gateway_push)
        self.assertIsNotNone(employee.last_gateway_push_at)
        mock_client.add_access_user.assert_called_once()
        self.assertEqual(mock_client.add_access_card.call_count, 1)

    @patch("employees.views.get_shared_gateway_client")
    def test_push_pending_pushes_new_and_modified_employees(self, mock_get_client):
        mock_client = mock_get_client.return_value
        mock_client.add_access_user.return_value = {"status": "ok"}
        mock_client.add_access_card.return_value = {"status": "ok"}

        emp_new = Employee.objects.create(
            tenant=self.tenant,
            department=self.child_department,
            employee_no="E9010",
            name="Nouveau",
            needs_gateway_push=True,
        )
        emp_new.devices.add(self.device)
        emp_new.cards.create(card_no="CARD-9010", card_type="normalCard")

        emp_modified = Employee.objects.create(
            tenant=self.tenant,
            department=self.child_department,
            employee_no="E9011",
            name="Modifie",
            needs_gateway_push=True,
        )
        emp_modified.devices.add(self.device)
        emp_modified.cards.create(card_no="CARD-9011", card_type="normalCard")

        response = self.client.post(
            "/api/employees/push-pending/",
            {"tenant": self.tenant.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.json()["pushed_count"], 2)
        emp_new.refresh_from_db()
        emp_modified.refresh_from_db()
        self.assertFalse(emp_new.needs_gateway_push)
        self.assertFalse(emp_modified.needs_gateway_push)
        self.assertEqual(mock_client.add_access_user.call_count, 2)
        self.assertEqual(mock_client.add_access_card.call_count, 2)

    def test_department_crud_with_sub_department(self):
        response_create = self.client.post(
            "/api/departments/",
            {
                "tenant": self.tenant.id,
                "organization": self.organization.id,
                "parent": self.root_department.id,
                "name": "Finance",
                "code": "DEP-FIN",
            },
            format="json",
        )
        self.assertEqual(response_create.status_code, status.HTTP_201_CREATED)
        dep_id = response_create.json()["id"]

        response_patch = self.client.patch(
            f"/api/departments/{dep_id}/",
            {"name": "Finance & Control"},
            format="json",
        )
        self.assertEqual(response_patch.status_code, status.HTTP_200_OK)
        self.assertEqual(response_patch.json()["name"], "Finance & Control")

        response_delete = self.client.delete(f"/api/departments/{dep_id}/")
        self.assertEqual(response_delete.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Department.objects.filter(id=dep_id).exists())

    def test_move_employee_to_another_department(self):
        target_department = Department.objects.create(
            tenant=self.tenant,
            organization=self.organization,
            parent=self.root_department,
            name="IT",
            code="DEP-IT",
        )
        employee = Employee.objects.create(
            tenant=self.tenant,
            department=self.child_department,
            employee_no="E9020",
            name="To Move",
            needs_gateway_push=False,
        )

        response = self.client.post(
            f"/api/employees/{employee.id}/move-department/",
            {"department": target_department.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        employee.refresh_from_db()
        self.assertEqual(employee.department_id, target_department.id)
        self.assertTrue(employee.needs_gateway_push)

    def test_move_employee_rejects_department_of_another_tenant(self):
        other_tenant = Tenant.objects.create(name="Tenant B", code="tenant-b")
        other_org = Organization.objects.create(tenant=other_tenant, name="ORG B", code="ORG-B")
        foreign_department = Department.objects.create(
            tenant=other_tenant,
            organization=other_org,
            name="Foreign DEP",
            code="DEP-FRG",
        )
        employee = Employee.objects.create(
            tenant=self.tenant,
            department=self.child_department,
            employee_no="E9021",
            name="Should Fail",
        )

        response = self.client.post(
            f"/api/employees/{employee.id}/move-department/",
            {"department": foreign_department.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.json())

    def test_assign_planning_to_department_and_employee(self):
        planning_department = Planning.objects.create(
            tenant=self.tenant,
            name="Planning Departement",
            code="PLN-DEP",
        )
        planning_employee = Planning.objects.create(
            tenant=self.tenant,
            name="Planning Employee",
            code="PLN-EMP",
        )
        employee = Employee.objects.create(
            tenant=self.tenant,
            department=self.child_department,
            employee_no="E9022",
            name="Assign Planning",
        )

        response_dep = self.client.post(
            f"/api/departments/{self.child_department.id}/assign-planning/",
            {"planning": planning_department.id},
            format="json",
        )
        self.assertEqual(response_dep.status_code, status.HTTP_200_OK)
        self.child_department.refresh_from_db()
        self.assertEqual(self.child_department.planning_id, planning_department.id)

        response_emp = self.client.post(
            f"/api/employees/{employee.id}/assign-planning/",
            {"planning": planning_employee.id},
            format="json",
        )
        self.assertEqual(response_emp.status_code, status.HTTP_200_OK)
        employee.refresh_from_db()
        self.assertEqual(employee.planning_id, planning_employee.id)
        self.assertEqual(employee.effective_planning.id, planning_employee.id)
        self.assertTrue(employee.needs_gateway_push)
        self.assertTrue(
            PlanningAssignment.objects.filter(employee=employee, planning=planning_employee, valid_to__isnull=True).exists()
        )

    def test_employee_effective_planning_prefers_assignment_over_legacy_department(self):
        department_planning = Planning.objects.create(
            tenant=self.tenant,
            name="Planning Assignment Department",
            code="PLN-ASG-DEP",
        )
        employee_planning = Planning.objects.create(
            tenant=self.tenant,
            name="Planning Assignment Employee",
            code="PLN-ASG-EMP",
        )
        employee = Employee.objects.create(
            tenant=self.tenant,
            department=self.child_department,
            employee_no="E9029",
            name="Assignment Priority User",
        )
        PlanningAssignment.objects.create(
            tenant=self.tenant,
            department=self.root_department,
            planning=department_planning,
            valid_from=date(2026, 1, 1),
            include_sub_departments=True,
        )
        PlanningAssignment.objects.create(
            tenant=self.tenant,
            employee=employee,
            planning=employee_planning,
            valid_from=date(2026, 1, 1),
        )

        self.assertEqual(employee.effective_planning, employee_planning)

    def test_employee_schedule_prefers_temporary_employee_assignment(self):
        standard_planning = Planning.objects.create(
            tenant=self.tenant,
            name="Planning Standard",
            code="PLN-STANDARD",
        )
        temporary_planning = Planning.objects.create(
            tenant=self.tenant,
            name="Planning Temporaire",
            code="PLN-TEMP",
        )
        PlanningEntry.objects.create(
            planning=standard_planning,
            day_of_week=0,
            work_shift=self.shift_morning,
            label="Lundi standard",
        )
        PlanningEntry.objects.create(
            planning=temporary_planning,
            start_date=date(2026, 3, 2),
            end_date=date(2026, 3, 2),
            work_shift=self.shift_evening,
            label="Surcharge temporaire",
        )
        employee = Employee.objects.create(
            tenant=self.tenant,
            department=self.child_department,
            employee_no="E9036",
            name="Temporary Override User",
        )
        PlanningAssignment.objects.create(
            tenant=self.tenant,
            department=self.root_department,
            planning=standard_planning,
            valid_from=date(2026, 1, 1),
            include_sub_departments=True,
        )
        PlanningAssignment.objects.create(
            tenant=self.tenant,
            employee=employee,
            planning=temporary_planning,
            valid_from=date(2026, 3, 2),
            valid_to=date(2026, 3, 2),
        )

        response = self.client.get(f"/api/employees/{employee.id}/schedule/?month=2026-03", format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        monday = next((day for day in payload["days"] if day["date"] == "2026-03-02"), None)
        self.assertIsNotNone(monday)
        self.assertEqual(monday["planning_id"], temporary_planning.id)
        self.assertEqual(monday["slots"][0]["label"], "Surcharge temporaire")
        self.assertEqual(monday["shifts"][0]["id"], self.shift_evening.id)

    @patch("employees.views.get_shared_gateway_client")
    def test_create_employee_with_multiple_work_shifts(self, mock_get_client):
        mock_client = mock_get_client.return_value
        mock_client.add_access_user.return_value = {"status": "ok"}
        mock_client.add_access_card.return_value = {"status": "ok"}

        response = self.client.post(
            "/api/employees/",
            {
                "tenant": self.tenant.id,
                "department": self.child_department.id,
                "employee_no": "E9031",
                "name": "Multi Shift User",
                "work_shift": self.shift_morning.id,
                "work_shifts": [self.shift_morning.id, self.shift_evening.id],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(response.json()["effective_work_shifts"]), 2)
        employee = Employee.objects.get(employee_no="E9031")
        self.assertEqual(employee.work_shift_id, self.shift_morning.id)
        self.assertEqual(employee.work_shifts.count(), 2)

    def test_assign_multiple_plannings_to_employee(self):
        planning_a = Planning.objects.create(
            tenant=self.tenant,
            name="Planning A",
            code="PLN-A",
        )
        planning_b = Planning.objects.create(
            tenant=self.tenant,
            name="Planning B",
            code="PLN-B",
        )
        employee = Employee.objects.create(
            tenant=self.tenant,
            department=self.child_department,
            employee_no="E9032",
            name="Assign Multi Planning",
        )

        response = self.client.post(
            f"/api/employees/{employee.id}/assign-plannings/",
            {"plannings": [planning_a.id, planning_b.id]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        employee.refresh_from_db()
        self.assertEqual(employee.planning_id, planning_a.id)
        self.assertEqual(
            PlanningAssignment.objects.filter(
                employee=employee,
                planning_id__in=[planning_a.id, planning_b.id],
                valid_to__isnull=True,
            ).count(),
            2,
        )
        self.assertEqual(response.json()["effective_planning"]["id"], planning_a.id)
        self.assertTrue(employee.needs_gateway_push)

    def test_employee_effective_planning_prefers_direct_planning(self):
        direct_planning = Planning.objects.create(
            tenant=self.tenant,
            name="Planning Direct",
            code="PLN-DIRECT",
        )
        employee = Employee.objects.create(
            tenant=self.tenant,
            department=self.child_department,
            planning=direct_planning,
            employee_no="E9030",
            name="Direct Planning User",
        )

        response = self.client.get(f"/api/employees/{employee.id}/", format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["effective_planning"]["id"], direct_planning.id)
        self.assertEqual(employee.effective_planning, direct_planning)

    def test_create_planning_with_daily_slots(self):
        response = self.client.post(
            "/api/plannings/",
            {
                "tenant": self.tenant.id,
                "name": "Semaine + Weekend",
                "code": "PLN-WEEK",
                "timezone": "Africa/Abidjan",
                "daily_slots": [
                    {
                        "day_of_week": 0,
                        "slot_type": "work",
                        "start_time": "09:00:00",
                        "end_time": "18:00:00",
                        "label": "Jours ouvres",
                    },
                    {
                        "day_of_week": 6,
                        "slot_type": "rest",
                        "start_time": "00:00:00",
                        "end_time": "23:59:00",
                        "label": "Weekend",
                    },
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(response.json()["daily_slots"]), 2)

        planning_id = response.json()["id"]
        detail = self.client.get(f"/api/plannings/{planning_id}/", format="json")
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(len(detail.json()["daily_slots"]), 2)

    def test_create_planning_with_periods_and_work_shifts(self):
        response = self.client.post(
            "/api/plannings/",
            {
                "tenant": self.tenant.id,
                "name": "Rotation Mars",
                "code": "PLN-MARCH",
                "periods": [
                    {
                        "label": "Semaine A",
                        "start_date": "2026-03-02",
                        "end_date": "2026-03-06",
                        "work_shifts": [self.shift_morning.id, self.shift_evening.id],
                    },
                    {
                        "label": "Weekend",
                        "start_date": "2026-03-07",
                        "end_date": "2026-03-08",
                        "work_shifts": [],
                    },
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(response.json()["periods"]), 2)
        self.assertEqual(response.json()["periods"][0]["shift_count"], 2)

        planning_id = response.json()["id"]
        detail = self.client.get(f"/api/plannings/{planning_id}/", format="json")
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(len(detail.json()["periods"]), 2)
        self.assertEqual(PlanningPeriod.objects.filter(planning_id=planning_id).count(), 2)

    def test_create_planning_with_multiple_shift_entries_per_day(self):
        response = self.client.post(
            "/api/plannings/",
            {
                "tenant": self.tenant.id,
                "name": "Planning Equipe Combine",
                "code": "PLN-COMBINE",
                "entries": [
                    {
                        "day_of_week": 0,
                        "work_shift": self.shift_morning.id,
                        "label": "Lundi matin",
                        "is_rest_day": False,
                    },
                    {
                        "day_of_week": 0,
                        "work_shift": self.shift_evening.id,
                        "label": "Lundi soir",
                        "is_rest_day": False,
                    },
                    {
                        "day_of_week": 6,
                        "label": "Repos",
                        "is_rest_day": True,
                    },
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(response.json()["entries"]), 3)

        planning_id = response.json()["id"]
        employee = Employee.objects.create(
            tenant=self.tenant,
            department=self.child_department,
            planning_id=planning_id,
            employee_no="E9040",
            name="Planning Combine User",
        )

        schedule = self.client.get(f"/api/employees/{employee.id}/schedule/?month=2026-03", format="json")
        self.assertEqual(schedule.status_code, status.HTTP_200_OK)
        monday = next((day for day in schedule.json()["days"] if day["date"] == "2026-03-02"), None)
        self.assertIsNotNone(monday)
        self.assertEqual(len(monday["shifts"]), 2)
        self.assertEqual({shift["id"] for shift in monday["shifts"]}, {self.shift_morning.id, self.shift_evening.id})

    def test_create_planning_rejects_rest_and_shift_on_same_day_entry_group(self):
        response = self.client.post(
            "/api/plannings/",
            {
                "tenant": self.tenant.id,
                "name": "Planning Invalide",
                "code": "PLN-INVALID",
                "entries": [
                    {
                        "day_of_week": 2,
                        "work_shift": self.shift_morning.id,
                        "label": "Mercredi matin",
                        "is_rest_day": False,
                    },
                    {
                        "day_of_week": 2,
                        "label": "Repos mercredi",
                        "is_rest_day": True,
                    },
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("entries", response.json())

    def test_create_planning_rejects_overlapping_periods(self):
        response = self.client.post(
            "/api/plannings/",
            {
                "tenant": self.tenant.id,
                "name": "Rotation Ambigue",
                "code": "PLN-OVERLAP",
                "periods": [
                    {
                        "label": "Bloc 1",
                        "start_date": "2026-03-01",
                        "end_date": "2026-03-10",
                        "work_shifts": [self.shift_morning.id],
                    },
                    {
                        "label": "Bloc 2",
                        "start_date": "2026-03-05",
                        "end_date": "2026-03-12",
                        "work_shifts": [self.shift_evening.id],
                    },
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("periods", response.json())

    def test_employee_monthly_schedule_uses_effective_planning_and_shifts(self):
        employee = Employee.objects.create(
            tenant=self.tenant,
            department=self.child_department,
            employee_no="E9033",
            name="Monthly Planning User",
            work_shift=self.shift_morning,
        )
        employee.work_shifts.set([self.shift_morning, self.shift_evening])
        self.root_planning.daily_slots.create(
            day_of_week=0,
            slot_type="work",
            start_time="08:00:00",
            end_time="12:00:00",
            label="Matin",
        )
        self.root_planning.daily_slots.create(
            day_of_week=6,
            slot_type="rest",
            start_time="00:00:00",
            end_time="23:59:00",
            label="Repos",
        )

        response = self.client.get(f"/api/employees/{employee.id}/schedule/?month=2026-03", format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload["month"], "2026-03")
        self.assertEqual(payload["employee"]["id"], employee.id)
        self.assertEqual(payload["planning"]["id"], self.root_planning.id)
        self.assertEqual(len(payload["work_shifts"]), 2)
        self.assertEqual(payload["summary"]["days_in_month"], 31)

        monday = next((day for day in payload["days"] if day["date"] == "2026-03-02"), None)
        sunday = next((day for day in payload["days"] if day["date"] == "2026-03-01"), None)

        self.assertIsNotNone(monday)
        self.assertTrue(monday["has_work_period"])
        self.assertEqual(len(monday["slots"]), 1)
        self.assertEqual(len(monday["shifts"]), 2)

        self.assertIsNotNone(sunday)
        self.assertTrue(sunday["is_rest_day"])
        self.assertEqual(sunday["slots"][0]["slot_type"], "rest")
        self.assertEqual(sunday["shifts"], [])

    def test_employee_monthly_schedule_prefers_planning_periods(self):
        planning = Planning.objects.create(
            tenant=self.tenant,
            name="Planning Periodise",
            code="PLN-PERIOD",
        )
        planning.daily_slots.create(
            day_of_week=0,
            slot_type="work",
            start_time="06:00:00",
            end_time="07:00:00",
            label="Legacy slot",
        )
        first_period = PlanningPeriod.objects.create(
            planning=planning,
            label="Cycle A",
            start_date=date(2026, 3, 2),
            end_date=date(2026, 3, 4),
        )
        first_period.work_shifts.set([self.shift_morning, self.shift_evening])
        PlanningPeriod.objects.create(
            planning=planning,
            label="Repos",
            start_date=date(2026, 3, 5),
            end_date=date(2026, 3, 5),
        )

        employee = Employee.objects.create(
            tenant=self.tenant,
            department=self.child_department,
            planning=planning,
            employee_no="E9035",
            name="Period Planning User",
        )

        response = self.client.get(f"/api/employees/{employee.id}/schedule/?month=2026-03", format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(len(payload["work_shifts"]), 2)

        monday = next((day for day in payload["days"] if day["date"] == "2026-03-02"), None)
        thursday = next((day for day in payload["days"] if day["date"] == "2026-03-05"), None)

        self.assertIsNotNone(monday)
        self.assertTrue(monday["has_work_period"])
        self.assertEqual(len(monday["slots"]), 2)
        self.assertEqual({slot["slot_type"] for slot in monday["slots"]}, {"shift"})
        self.assertEqual(monday["planned_minutes"], 480)

        self.assertIsNotNone(thursday)
        self.assertTrue(thursday["is_rest_day"])
        self.assertEqual(thursday["slots"][0]["slot_type"], "rest")
        self.assertEqual(thursday["shifts"], [])

    def test_employee_monthly_schedule_rejects_invalid_month(self):
        employee = Employee.objects.create(
            tenant=self.tenant,
            department=self.child_department,
            employee_no="E9034",
            name="Invalid Month User",
        )

        response = self.client.get(f"/api/employees/{employee.id}/schedule/?month=2026-13", format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.json())

    def test_work_shift_delete_check_reports_assigned_users(self):
        employee = Employee.objects.create(
            tenant=self.tenant,
            department=self.child_department,
            employee_no="E9050",
            name="Shift Assigned User",
            work_shift=self.shift_morning,
        )
        employee.work_shifts.add(self.shift_morning)

        response = self.client.get(f"/api/work-shifts/{self.shift_morning.id}/delete-check/", format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertTrue(payload["has_assigned_users"])
        self.assertFalse(payload["can_delete_without_force"])
        self.assertEqual(payload["assigned_users_count"], 1)
        self.assertEqual(payload["assigned_users"][0]["id"], employee.id)

    def test_create_work_shift_with_late_and_early_allowable_minutes(self):
        response = self.client.post(
            "/api/work-shifts/",
            {
                "tenant": self.tenant.id,
                "name": "Shift Avec Tolerance",
                "start_time": "09:00:00",
                "end_time": "18:00:00",
                "late_allowable_minutes": 10,
                "early_leave_allowable_minutes": 15,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        payload = response.json()
        self.assertEqual(payload["late_allowable_minutes"], 10)
        self.assertEqual(payload["early_leave_allowable_minutes"], 15)

        created_shift = WorkShift.objects.get(id=payload["id"])
        self.assertEqual(created_shift.late_allowable_minutes, 10)
        self.assertEqual(created_shift.early_leave_allowable_minutes, 15)

    def test_delete_work_shift_requires_force_when_links_exist(self):
        employee = Employee.objects.create(
            tenant=self.tenant,
            department=self.child_department,
            employee_no="E9051",
            name="No Force User",
            work_shift=self.shift_morning,
        )
        employee.work_shifts.add(self.shift_morning)

        response = self.client.delete(f"/api/work-shifts/{self.shift_morning.id}/")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("force=true", response.json()["detail"])
        self.assertEqual(response.json()["usage"]["assigned_users_count"], 1)
        self.assertTrue(WorkShift.objects.filter(id=self.shift_morning.id).exists())

    def test_delete_work_shift_with_force_true(self):
        employee = Employee.objects.create(
            tenant=self.tenant,
            department=self.child_department,
            employee_no="E9052",
            name="Force Delete User",
            work_shift=self.shift_morning,
        )
        employee.work_shifts.add(self.shift_morning)

        response = self.client.delete(f"/api/work-shifts/{self.shift_morning.id}/?force=true")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(WorkShift.objects.filter(id=self.shift_morning.id).exists())
        employee.refresh_from_db()
        self.assertIsNone(employee.work_shift_id)
        self.assertFalse(employee.work_shifts.filter(id=self.shift_morning.id).exists())

    def test_delete_planning_requires_force_when_links_exist(self):
        planning = Planning.objects.create(
            tenant=self.tenant,
            name="Planning To Delete",
            code="PLN-DEL",
        )
        employee = Employee.objects.create(
            tenant=self.tenant,
            department=self.child_department,
            employee_no="E9053",
            name="Planning User",
            planning=planning,
        )

        check_response = self.client.get(f"/api/plannings/{planning.id}/delete-check/", format="json")
        self.assertEqual(check_response.status_code, status.HTTP_200_OK)
        self.assertEqual(check_response.json()["assigned_employees_count"], 1)
        self.assertFalse(check_response.json()["can_delete_without_force"])

        delete_response = self.client.delete(f"/api/plannings/{planning.id}/")
        self.assertEqual(delete_response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("force=true", delete_response.json()["detail"])
        self.assertTrue(Planning.objects.filter(id=planning.id).exists())

        force_delete_response = self.client.delete(f"/api/plannings/{planning.id}/?force=true")
        self.assertEqual(force_delete_response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Planning.objects.filter(id=planning.id).exists())
        employee.refresh_from_db()
        self.assertIsNone(employee.planning_id)
