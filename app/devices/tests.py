from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from devices.models import Device


User = get_user_model()


class DeviceOwnershipTests(APITestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username='alice', password='pwd12345')
        self.user2 = User.objects.create_user(username='bob', password='pwd12345')

    def test_user_only_sees_own_devices(self):
        Device.objects.create(owner=self.user1, dev_index='dev-alice', serial_number='SN1234567')
        Device.objects.create(owner=self.user2, dev_index='dev-bob', serial_number='SN7654321')

        self.client.force_authenticate(self.user1)
        response = self.client.get('/api/devices/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['serial_number'], 'SN1234567')

    def test_create_device_with_constraints(self):
        self.client.force_authenticate(self.user1)
        payload = {
            'dev_index': 'dev-new',
            'serial_number': 'ABC123456',
            'port': 7660,
            'ip_address': '1.2.3.4',
        }

        response = self.client.post('/api/devices/', payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        device = Device.objects.get(dev_index='dev-new')
        self.assertEqual(device.owner, self.user1)
        self.assertEqual(device.port, 7660)
        self.assertEqual(device.ip_address, '213.156.133.202')
        self.assertEqual(device.protocol, 'ISUP')

    def test_serial_number_must_be_exactly_9_characters(self):
        self.client.force_authenticate(self.user1)
        payload = {
            'dev_index': 'dev-invalid-sn',
            'serial_number': 'SHORT',
            'port': 7661,
        }

        response = self.client.post('/api/devices/', payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('serial_number', response.data)

    def test_port_must_be_7660_or_7661(self):
        self.client.force_authenticate(self.user1)
        payload = {
            'dev_index': 'dev-invalid-port',
            'serial_number': 'ABC123456',
            'port': 7000,
        }

        response = self.client.post('/api/devices/', payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('port', response.data)
