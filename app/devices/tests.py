import base64
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from devices.models import Device, DeviceOnboardingJob, DeviceOrganizationBinding
from employees.models import Employee, EmployeeFace, Organization, OrganizationMembership, OrganizationRole
from tenants.models import Tenant, TenantMembership, TenantRole


User = get_user_model()


class DeviceOwnershipTests(APITestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username='alice', password='pwd12345')
        self.user2 = User.objects.create_user(username='bob', password='pwd12345')
        self.tenant_a = Tenant.objects.create(name='Tenant A', code='TENANT-A')
        self.tenant_b = Tenant.objects.create(name='Tenant B', code='TENANT-B')
        TenantMembership.objects.create(user=self.user1, tenant=self.tenant_a, role=TenantRole.VIEWER)
        TenantMembership.objects.create(user=self.user2, tenant=self.tenant_b, role=TenantRole.VIEWER)
        TenantMembership.objects.create(user=self.user2, tenant=self.tenant_a, role=TenantRole.VIEWER)

    def test_list_devices_is_tenant_scoped_by_default(self):
        Device.objects.create(owner=self.user1, dev_index='dev-alice', serial_number='SN1234567AB', tenant=self.tenant_a)
        Device.objects.create(owner=self.user2, dev_index='dev-bob', serial_number='SN7654321CD', tenant=self.tenant_b)

        self.client.force_authenticate(self.user1)
        response = self.client.get('/api/devices/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['serial_number'], 'SN1234567AB')

    def test_owner_only_filters_devices(self):
        Device.objects.create(owner=self.user1, dev_index='dev-alice', serial_number='SN1234567AB', tenant=self.tenant_a)
        Device.objects.create(owner=self.user2, dev_index='dev-bob', serial_number='SN7654321CD', tenant=self.tenant_b)

        self.client.force_authenticate(self.user1)
        response = self.client.get('/api/devices/?owner_only=true')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['serial_number'], 'SN1234567AB')

    def test_create_device_with_constraints(self):
        self.client.force_authenticate(self.user1)
        payload = {
            'tenant': self.tenant_a.id,
            'dev_index': 'dev-new',
            'serial_number': 'ABC123456XYZ',
            'port': 7660,
            'ip_address': '1.2.3.4',
            'device_username': 'admin-device',
            'device_password': 'secret-device',
        }

        response = self.client.post('/api/devices/', payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        device = Device.objects.get(dev_index='dev-new')
        self.assertEqual(device.owner, self.user1)
        self.assertEqual(device.port, 7660)
        self.assertEqual(device.ip_address, '213.156.133.202')
        self.assertEqual(device.protocol, 'ISUP')
        self.assertEqual(device.device_username, 'admin-device')
        self.assertEqual(device.device_password, 'secret-device')
        self.assertNotIn('device_password', response.data)

    def test_port_must_be_7660_or_7661(self):
        self.client.force_authenticate(self.user1)
        payload = {
            'tenant': self.tenant_a.id,
            'dev_index': 'dev-invalid-port',
            'serial_number': 'ABC123456XYZ',
            'port': 7000,
        }

        response = self.client.post('/api/devices/', payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('port', response.data)

    @patch('devices.views.get_shared_gateway_client')
    def test_onboard_claim_conflict_other_tenant(self, mocked_client):
        Device.objects.create(
            owner=self.user2,
            tenant=self.tenant_b,
            dev_index='dev-existing',
            serial_number='K1T642',
        )
        self.client.force_authenticate(self.user1)

        response = self.client.post(
            '/api/devices/onboard/',
            {
                'tenant_code': self.tenant_a.code,
                'sn': 'K1T642',
                'ehome_key': 'test2024',
                'dev_name': 'Pointeuse Entree',
                'dev_type': 'AccessControl',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        mocked_client.assert_not_called()

    @patch('devices.views.get_shared_gateway_client')
    def test_onboard_is_idempotent_for_same_tenant(self, mocked_client):
        existing = Device.objects.create(
            owner=self.user1,
            tenant=self.tenant_a,
            dev_index='dev-existing',
            serial_number='K1T642',
        )
        self.client.force_authenticate(self.user1)

        response = self.client.post(
            '/api/devices/onboard/',
            {
                'tenant_code': self.tenant_a.code,
                'sn': 'K1T642',
                'ehome_key': 'test2024',
                'dev_name': 'Pointeuse Entree',
                'dev_type': 'AccessControl',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], existing.id)
        mocked_client.assert_not_called()

    @patch('devices.views.get_shared_gateway_client')
    def test_onboard_success_with_devindex_from_add_device_response(self, mocked_client):
        gateway = Mock()
        gateway.add_device.return_value = {
            'DeviceOutList': {
                'Device': {
                    'status': 'success',
                    'devIndex': 'uuid-001',
                }
            }
        }
        mocked_client.return_value = gateway

        self.client.force_authenticate(self.user1)
        response = self.client.post(
            '/api/devices/onboard/',
            {
                'tenant_code': self.tenant_a.code,
                'sn': 'K1T642',
                'ehome_key': 'test2024',
                'dev_name': 'Pointeuse Entree',
                'dev_type': 'AccessControl',
                'device_username': 'operator1',
                'device_password': 'super-secret',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['dev_index'], 'uuid-001')
        device = Device.objects.get(dev_index='uuid-001')
        self.assertEqual(device.tenant, self.tenant_a)
        self.assertEqual(device.device_username, 'operator1')
        self.assertEqual(device.device_password, 'super-secret')
        self.assertNotIn('device_password', response.data)

    @patch('devices.views.get_shared_gateway_client')
    def test_onboard_device_exist_fallbacks_to_device_list(self, mocked_client):
        gateway = Mock()
        gateway.add_device.return_value = {
            'DeviceOutList': {
                'Device': {
                    'status': 'failed',
                    'subStatusCode': 'deviceExist',
                }
            }
        }
        gateway.device_list_all.return_value = {
            'SearchResult': {
                'MatchList': [
                    {
                        'Device': {
                            'devIndex': 'uuid-from-list',
                            'EhomeParams': {'EhomeID': 'K1T642'},
                        }
                    }
                ]
            }
        }
        mocked_client.return_value = gateway

        self.client.force_authenticate(self.user1)
        response = self.client.post(
            '/api/devices/onboard/',
            {
                'tenant_code': self.tenant_a.code,
                'sn': 'K1T642',
                'ehome_key': 'test2024',
                'dev_name': 'Pointeuse Entree',
                'dev_type': 'AccessControl',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['dev_index'], 'uuid-from-list')

    @patch('devices.views.get_shared_gateway_client')
    def test_owner_can_delete_device_and_calls_gateway(self, mocked_client):
        device = Device.objects.create(
            owner=self.user1,
            tenant=self.tenant_a,
            dev_index='IDX-DEL-001',
            serial_number='SN-DEL-001',
        )
        gateway = Mock()
        mocked_client.return_value = gateway

        self.client.force_authenticate(self.user1)
        response = self.client.delete(f'/api/devices/{device.id}/')

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Device.objects.filter(id=device.id).exists())
        gateway.delete_device.assert_called_once_with(dev_index='IDX-DEL-001')

    @patch('devices.views.get_shared_gateway_client')
    def test_non_owner_cannot_delete_device(self, mocked_client):
        device = Device.objects.create(
            owner=self.user1,
            tenant=self.tenant_a,
            dev_index='IDX-DEL-002',
            serial_number='SN-DEL-002',
        )

        self.client.force_authenticate(self.user2)
        response = self.client.delete(f'/api/devices/{device.id}/')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Device.objects.filter(id=device.id).exists())
        mocked_client.assert_not_called()

    @patch('devices.views.get_shared_gateway_client')
    def test_delete_returns_502_and_keeps_device_when_gateway_fails(self, mocked_client):
        device = Device.objects.create(
            owner=self.user1,
            tenant=self.tenant_a,
            dev_index='IDX-DEL-003',
            serial_number='SN-DEL-003',
        )
        gateway = Mock()
        gateway.delete_device.side_effect = RuntimeError('gateway down')
        mocked_client.return_value = gateway

        self.client.force_authenticate(self.user1)
        response = self.client.delete(f'/api/devices/{device.id}/')

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertTrue(Device.objects.filter(id=device.id).exists())

    @patch('devices.views.get_shared_gateway_client')
    def test_post_delete_action_removes_device(self, mocked_client):
        device = Device.objects.create(
            owner=self.user1,
            tenant=self.tenant_a,
            dev_index='IDX-DEL-004',
            serial_number='SN-DEL-004',
        )
        gateway = Mock()
        mocked_client.return_value = gateway

        self.client.force_authenticate(self.user1)
        response = self.client.post(f'/api/devices/{device.id}/delete/')

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Device.objects.filter(id=device.id).exists())
        gateway.delete_device.assert_called_once_with(dev_index='IDX-DEL-004')

    @patch('devices.views.get_shared_gateway_client')
    def test_owner_can_reboot_device_and_calls_gateway(self, mocked_client):
        device = Device.objects.create(
            owner=self.user1,
            tenant=self.tenant_a,
            dev_index='IDX-REB-001',
            serial_number='SN-REB-001',
        )
        gateway = Mock()
        gateway.reboot_device.return_value = {'statusCode': 1, 'statusString': 'OK'}
        mocked_client.return_value = gateway

        self.client.force_authenticate(self.user1)
        response = self.client.post(f'/api/devices/{device.id}/reboot/', format='json')

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data['status'], 'accepted')
        gateway.reboot_device.assert_called_once_with(dev_index='IDX-REB-001')

    @patch('devices.views.get_shared_gateway_client')
    def test_non_owner_cannot_reboot_device(self, mocked_client):
        device = Device.objects.create(
            owner=self.user1,
            tenant=self.tenant_a,
            dev_index='IDX-REB-002',
            serial_number='SN-REB-002',
        )

        self.client.force_authenticate(self.user2)
        response = self.client.post(f'/api/devices/{device.id}/reboot/', format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        mocked_client.assert_not_called()

    @patch('devices.views.get_shared_gateway_client')
    def test_reboot_returns_502_when_gateway_fails(self, mocked_client):
        device = Device.objects.create(
            owner=self.user1,
            tenant=self.tenant_a,
            dev_index='IDX-REB-003',
            serial_number='SN-REB-003',
        )
        gateway = Mock()
        gateway.reboot_device.side_effect = RuntimeError('gateway down')
        mocked_client.return_value = gateway

        self.client.force_authenticate(self.user1)
        response = self.client.post(f'/api/devices/{device.id}/reboot/', format='json')

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        gateway.reboot_device.assert_called_once_with(dev_index='IDX-REB-003')

    @patch('devices.views.get_shared_gateway_client')
    def test_owner_can_set_manual_time_with_gmt_offset(self, mocked_client):
        device = Device.objects.create(
            owner=self.user1,
            tenant=self.tenant_a,
            dev_index='IDX-TIME-001',
            serial_number='SN-TIME-001',
        )
        gateway = Mock()
        gateway.set_device_time_sync.return_value = {'statusCode': 1, 'statusString': 'OK'}
        gateway.set_device_time_zone.return_value = {'statusCode': 1, 'statusString': 'OK'}
        mocked_client.return_value = gateway

        self.client.force_authenticate(self.user1)
        response = self.client.post(
            f'/api/devices/{device.id}/set-time/',
            {
                'mode': 'manual',
                'local_time': '2026-03-22T09:15:30',
                'gmt_offset': '+00:00',
                'time_zone': 'GMT+00:00:00',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        gateway.set_device_time_sync.assert_called_once_with(
            dev_index='IDX-TIME-001',
            payload={'Time': {'timeMode': 'manual', 'localTime': '2026-03-22T09:15:30+00:00'}},
        )
        gateway.set_device_time_zone.assert_called_once_with(
            dev_index='IDX-TIME-001',
            time_zone='GMT+00:00:00',
        )

    @patch('devices.views.get_shared_gateway_client')
    def test_owner_can_set_ntp_time_mode(self, mocked_client):
        device = Device.objects.create(
            owner=self.user1,
            tenant=self.tenant_a,
            dev_index='IDX-TIME-002',
            serial_number='SN-TIME-002',
        )
        gateway = Mock()
        gateway.set_device_time_sync.return_value = {'statusCode': 1, 'statusString': 'OK'}
        mocked_client.return_value = gateway

        self.client.force_authenticate(self.user1)
        response = self.client.post(
            f'/api/devices/{device.id}/set-time/',
            {'mode': 'NTP'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        gateway.set_device_time_sync.assert_called_once_with(
            dev_index='IDX-TIME-002',
            payload={'Time': {'timeMode': 'NTP'}},
        )
        gateway.set_device_time_zone.assert_not_called()

    @patch('devices.views.get_shared_gateway_client')
    def test_set_time_rejects_invalid_offset(self, mocked_client):
        device = Device.objects.create(
            owner=self.user1,
            tenant=self.tenant_a,
            dev_index='IDX-TIME-003',
            serial_number='SN-TIME-003',
        )
        self.client.force_authenticate(self.user1)
        response = self.client.post(
            f'/api/devices/{device.id}/set-time/',
            {'mode': 'manual', 'gmt_offset': 'UTC+0'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        mocked_client.assert_not_called()

    @patch('devices.views.get_shared_gateway_client')
    def test_non_owner_cannot_set_time(self, mocked_client):
        device = Device.objects.create(
            owner=self.user1,
            tenant=self.tenant_a,
            dev_index='IDX-TIME-004',
            serial_number='SN-TIME-004',
        )

        self.client.force_authenticate(self.user2)
        response = self.client.post(
            f'/api/devices/{device.id}/set-time/',
            {'mode': 'NTP'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        mocked_client.assert_not_called()

    @patch('devices.views.get_shared_gateway_client')
    def test_set_time_returns_502_when_gateway_fails(self, mocked_client):
        device = Device.objects.create(
            owner=self.user1,
            tenant=self.tenant_a,
            dev_index='IDX-TIME-005',
            serial_number='SN-TIME-005',
        )
        gateway = Mock()
        gateway.set_device_time_sync.side_effect = RuntimeError('gateway down')
        mocked_client.return_value = gateway

        self.client.force_authenticate(self.user1)
        response = self.client.post(
            f'/api/devices/{device.id}/set-time/',
            {'mode': 'NTP'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        gateway.set_device_time_sync.assert_called_once_with(
            dev_index='IDX-TIME-005',
            payload={'Time': {'timeMode': 'NTP'}},
        )

    def test_owner_can_patch_device_name(self):
        device = Device.objects.create(
            owner=self.user1,
            tenant=self.tenant_a,
            dev_index='IDX-UPD-001',
            serial_number='SN-UPD-001',
            name='Ancien nom',
        )

        self.client.force_authenticate(self.user1)
        response = self.client.patch(f'/api/devices/{device.id}/', {'name': 'Nouveau nom'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        device.refresh_from_db()
        self.assertEqual(device.name, 'Nouveau nom')

    def test_non_owner_cannot_patch_device_name(self):
        device = Device.objects.create(
            owner=self.user1,
            tenant=self.tenant_a,
            dev_index='IDX-UPD-002',
            serial_number='SN-UPD-002',
            name='Nom initial',
        )

        self.client.force_authenticate(self.user2)
        response = self.client.patch(f'/api/devices/{device.id}/', {'name': 'Nom pirate'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        device.refresh_from_db()
        self.assertEqual(device.name, 'Nom initial')

    @patch('devices.views.get_shared_gateway_client')
    def test_add_persons_pushes_cards_and_fingerprints(self, mocked_client):
        device = Device.objects.create(
            owner=self.user1,
            tenant=self.tenant_a,
            dev_index='IDX-ADD-PERSON',
            serial_number='SN-ADD-PERSON',
        )
        employee = Employee.objects.create(
            tenant=self.tenant_a,
            employee_no='E-ADD-1',
            name='Person To Push',
        )
        employee.cards.create(card_no='CARD-ADD-1', card_type='normalCard')
        employee.fingerprints.create(finger_index=1, template='fp-add-1')

        gateway = Mock()
        gateway.add_access_user.return_value = {'status': 'ok'}
        gateway.add_access_card.return_value = {'status': 'ok'}
        gateway.add_access_fingerprint.return_value = {'status': 'ok'}
        mocked_client.return_value = gateway

        self.client.force_authenticate(self.user1)
        response = self.client.post(
            f'/api/devices/{device.id}/add-persons/',
            {
                'employee_ids': [employee.id],
                'include_cards': True,
                'include_fingerprints': True,
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok')
        self.assertEqual(payload['success_count'], 1)
        self.assertEqual(gateway.add_access_user.call_count, 1)
        self.assertEqual(gateway.add_access_card.call_count, 1)
        self.assertEqual(gateway.add_access_fingerprint.call_count, 1)

    @patch('devices.views.get_shared_gateway_client')
    def test_enroll_fingerprint_collects_and_syncs(self, mocked_client):
        device = Device.objects.create(
            owner=self.user1,
            tenant=self.tenant_a,
            dev_index='IDX-ENROLL-FP',
            serial_number='SN-ENROLL-FP',
        )
        employee = Employee.objects.create(
            tenant=self.tenant_a,
            employee_no='E-ENROLL-1',
            name='Enroll Person',
        )

        gateway = Mock()
        gateway.capture_fingerprint.return_value = {
            'CaptureFingerPrint': {
                'fingerData': 'fp-captured-1',
                'fingerNo': 2,
                'fingerPrintQuality': 88,
            }
        }
        gateway.add_access_user.return_value = {'status': 'ok'}
        gateway.add_access_fingerprint.return_value = {'status': 'ok'}
        mocked_client.return_value = gateway

        self.client.force_authenticate(self.user1)
        response = self.client.post(
            f'/api/devices/{device.id}/enroll-fingerprint/',
            {
                'employee_id': employee.id,
                'finger_index': 2,
                'push_to_all_readers': False,
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok')
        self.assertEqual(payload['finger_index'], 2)
        self.assertEqual(payload['finger_quality'], 88)
        self.assertTrue(employee.fingerprints.filter(finger_index=2, template='fp-captured-1').exists())
        gateway.capture_fingerprint.assert_called_once_with(dev_index='IDX-ENROLL-FP', finger_no=2)
        self.assertEqual(gateway.add_access_user.call_count, 1)
        self.assertEqual(gateway.add_access_fingerprint.call_count, 1)

    @patch('devices.views.get_shared_gateway_client')
    def test_enroll_face_uses_stored_photo_and_syncs(self, mocked_client):
        device = Device.objects.create(
            owner=self.user1,
            tenant=self.tenant_a,
            dev_index='IDX-ENROLL-FACE',
            serial_number='SN-ENROLL-FACE',
        )
        employee = Employee.objects.create(
            tenant=self.tenant_a,
            employee_no='EENROLLFACE1',
            name='Face Person',
        )
        face_binary = b'face-image-binary'
        EmployeeFace.objects.create(
            employee=employee,
            face_data=base64.b64encode(face_binary).decode('ascii'),
        )

        gateway = Mock()
        gateway.add_access_user.return_value = {'status': 'ok'}
        gateway.add_access_face.return_value = {'status': 'ok'}
        mocked_client.return_value = gateway

        self.client.force_authenticate(self.user1)
        response = self.client.post(
            f'/api/devices/{device.id}/enroll-face/',
            {
                'employee_id': employee.id,
                'push_to_all_readers': False,
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok')
        self.assertEqual(payload['success_count'], 1)
        self.assertEqual(gateway.add_access_user.call_count, 1)
        self.assertEqual(gateway.add_access_face.call_count, 1)
        add_face_kwargs = gateway.add_access_face.call_args.kwargs
        self.assertEqual(add_face_kwargs['dev_index'], 'IDX-ENROLL-FACE')
        self.assertEqual(add_face_kwargs['employee_no'], 'EENROLLFACE1')
        self.assertEqual(add_face_kwargs['face_image'], face_binary)
        self.assertEqual(add_face_kwargs['content_type'], 'image/jpeg')
        self.assertEqual(add_face_kwargs['face_lib_type'], 'blackFD')

    @patch('devices.views.get_shared_gateway_client')
    def test_enroll_face_accepts_request_face_data_and_persists(self, mocked_client):
        device = Device.objects.create(
            owner=self.user1,
            tenant=self.tenant_a,
            dev_index='IDX-ENROLL-FACE-REQ',
            serial_number='SN-ENROLL-FACE-REQ',
        )
        employee = Employee.objects.create(
            tenant=self.tenant_a,
            employee_no='EENROLLFACE2',
            name='Face Person 2',
        )
        face_binary = b'face-image-png'
        face_b64 = base64.b64encode(face_binary).decode('ascii')
        face_data_uri = f'data:image/png;base64,{face_b64}'

        gateway = Mock()
        gateway.add_access_user.return_value = {'status': 'ok'}
        gateway.add_access_face.return_value = {'status': 'ok'}
        mocked_client.return_value = gateway

        self.client.force_authenticate(self.user1)
        response = self.client.post(
            f'/api/devices/{device.id}/enroll-face/',
            {
                'employee_id': employee.id,
                'face_data': face_data_uri,
                'push_to_all_readers': False,
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        employee.refresh_from_db()
        self.assertEqual(employee.face.face_data, face_data_uri)
        add_face_kwargs = gateway.add_access_face.call_args.kwargs
        self.assertEqual(add_face_kwargs['face_image'], face_binary)
        self.assertEqual(add_face_kwargs['content_type'], 'image/png')


class DeviceOnboardingJobTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="job-owner", password="pwd12345", email="owner@job.test", is_active=True)
        self.tenant = Tenant.objects.create(
            name="Tenant Jobs",
            code="TENANT-JOBS",
            domain="job.test",
            is_active=True,
            is_domain_verified=True,
            device_quota=10,
        )
        self.organization = Organization.objects.create(
            tenant=self.tenant,
            name="Ops",
            code="OPS",
        )
        TenantMembership.objects.create(
            user=self.user,
            tenant=self.tenant,
            role=TenantRole.TENANT_ADMIN,
            is_primary=True,
        )
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.organization,
            role=OrganizationRole.ORG_ADMIN,
        )
        self.client.force_authenticate(self.user)

    @patch("devices.services.onboarding.get_shared_gateway_client")
    def test_create_onboarding_job_processes_and_links_device(self, mocked_client):
        gateway = Mock()
        gateway.add_device.return_value = {
            "DeviceOutList": {
                "Device": {
                    "status": "success",
                    "devIndex": "IDX-JOB-001",
                }
            }
        }
        mocked_client.return_value = gateway

        response = self.client.post(
            "/api/device-onboarding-jobs/?process_now=true",
            {
                "tenant_code": self.tenant.code,
                "organization_id": self.organization.id,
                "sn": "SN-JOB-001",
                "ehome_key": "A" * 32,
                "dev_name": "Reader Job 1",
                "dev_type": "AccessControl",
                "device_username": "admin",
                "device_password": "pass",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        payload = response.json()
        self.assertEqual(payload["status"], DeviceOnboardingJob.STATUS_COMPLETED)
        device = Device.objects.get(dev_index="IDX-JOB-001")
        self.assertEqual(device.tenant_id, self.tenant.id)
        self.assertTrue(
            DeviceOrganizationBinding.objects.filter(
                device=device,
                organization=self.organization,
            ).exists()
        )

    def test_create_onboarding_job_goes_manual_review_when_quota_exceeded(self):
        self.tenant.device_quota = 1
        self.tenant.save(update_fields=["device_quota"])
        Device.objects.create(
            owner=self.user,
            tenant=self.tenant,
            serial_number="SN-EXISTING",
            dev_index="IDX-EXISTING",
        )

        response = self.client.post(
            "/api/device-onboarding-jobs/?process_now=true",
            {
                "tenant_code": self.tenant.code,
                "organization_id": self.organization.id,
                "sn": "SN-JOB-OVER",
                "ehome_key": "B" * 32,
                "dev_name": "Reader Job Over",
                "dev_type": "AccessControl",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        payload = response.json()
        self.assertEqual(payload["status"], DeviceOnboardingJob.STATUS_MANUAL_REVIEW)
        self.assertEqual(payload["review_reason"], DeviceOnboardingJob.REVIEW_QUOTA_EXCEEDED)
        self.assertFalse(Device.objects.filter(serial_number="SN-JOB-OVER", tenant=self.tenant).exists())

    @patch("devices.services.onboarding.get_shared_gateway_client")
    def test_approve_manual_review_job_processes_it(self, mocked_client):
        gateway = Mock()
        gateway.add_device.return_value = {
            "DeviceOutList": {
                "Device": {
                    "status": "success",
                    "devIndex": "IDX-JOB-APPROVE",
                }
            }
        }
        mocked_client.return_value = gateway

        self.tenant.is_active = False
        self.tenant.save(update_fields=["is_active"])
        create_response = self.client.post(
            "/api/device-onboarding-jobs/?process_now=true",
            {
                "tenant_code": self.tenant.code,
                "organization_id": self.organization.id,
                "sn": "SN-JOB-APPROVE",
                "ehome_key": "C" * 32,
                "dev_name": "Reader Job Approve",
                "dev_type": "AccessControl",
            },
            format="json",
        )
        job_id = create_response.json()["id"]
        self.assertEqual(create_response.json()["status"], DeviceOnboardingJob.STATUS_MANUAL_REVIEW)

        self.tenant.is_active = True
        self.tenant.save(update_fields=["is_active"])

        approve = self.client.post(
            f"/api/device-onboarding-jobs/{job_id}/approve/?process_now=true",
            {"ehome_key": "C" * 32},
            format="json",
        )
        self.assertEqual(approve.status_code, status.HTTP_200_OK)
        self.assertEqual(approve.json()["status"], DeviceOnboardingJob.STATUS_COMPLETED)
        self.assertTrue(Device.objects.filter(dev_index="IDX-JOB-APPROVE").exists())
