from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from devices.models import Device
from employees.models import Department, Employee, Organization, Planning
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

    @patch("employees.views.get_shared_gateway_client")
    def test_create_employee_with_attributes(self, mock_get_client):
        mock_client = mock_get_client.return_value
        mock_client.add_access_user.return_value = {"status": "ok"}
        mock_client.add_access_card.return_value = {"status": "ok"}

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
        self.assertEqual(employee.attributes.count(), 1)
        self.assertEqual(employee.department, self.child_department)
        self.assertEqual(employee.effective_planning, self.root_planning)
        self.assertEqual(employee.cards.count(), 2)
        self.assertEqual(employee.fingerprints.count(), 2)
        self.assertTrue(hasattr(employee, "face"))
        mock_client.add_access_user.assert_called_once()
        self.assertEqual(mock_client.add_access_card.call_count, 2)

    @patch("employees.views.get_shared_gateway_client")
    def test_push_to_gateway_uses_user_and_card_endpoints(self, mock_get_client):
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

        mock_client = mock_get_client.return_value
        mock_client.add_access_user.return_value = {"status": "ok"}
        mock_client.add_access_card.return_value = {"status": "ok"}

        response = self.client.post(f"/api/employees/{employee.id}/push-to-gateway/", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["status"], "ok")
        mock_client.add_access_user.assert_called_once()
        self.assertEqual(mock_client.add_access_card.call_count, 2)

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
        self.assertEqual(Employee.objects.filter(tenant=self.tenant, employee_no="IMP1001").count(), 1)
        self.assertEqual(Employee.objects.filter(tenant=self.tenant, employee_no="IMP1002").count(), 1)
        imported = Employee.objects.get(tenant=self.tenant, employee_no="IMP1001")
        self.assertTrue(imported.devices.filter(id=self.device.id).exists())
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

    def test_department_effective_planning_uses_parent(self):
        response = self.client.get(f"/api/departments/{self.child_department.id}/", format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["effective_planning"]["id"], self.root_planning.id)

    def test_create_employee_requires_name(self):
        response = self.client.post(
            "/api/employees/",
            {
                "tenant": self.tenant.id,
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
