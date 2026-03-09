from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from devices.models import Device
from tenants.models import Tenant


User = get_user_model()


class DeviceOwnershipTests(APITestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username='alice', password='pwd12345')
        self.user2 = User.objects.create_user(username='bob', password='pwd12345')
        self.tenant_a = Tenant.objects.create(name='Tenant A', code='TENANT-A')
        self.tenant_b = Tenant.objects.create(name='Tenant B', code='TENANT-B')

    def test_list_devices_returns_all_by_default(self):
        Device.objects.create(owner=self.user1, dev_index='dev-alice', serial_number='SN1234567AB', tenant=self.tenant_a)
        Device.objects.create(owner=self.user2, dev_index='dev-bob', serial_number='SN7654321CD', tenant=self.tenant_b)

        self.client.force_authenticate(self.user1)
        response = self.client.get('/api/devices/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

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
