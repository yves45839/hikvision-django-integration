from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from devices.models import Device
from events.models import AttendanceEvent
from tenants.models import Tenant


User = get_user_model()


class AttendanceEventOwnershipTests(APITestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username='alice', password='pwd12345')
        self.user2 = User.objects.create_user(username='bob', password='pwd12345')
        self.tenant = Tenant.objects.create(name='Tenant A', code='tenant-a')

    def test_user_only_sees_events_for_owned_devices(self):
        device_alice = Device.objects.create(
            owner=self.user1,
            tenant=self.tenant,
            dev_index='dev-alice',
            serial_number='SN1234567',
        )
        device_bob = Device.objects.create(
            owner=self.user2,
            tenant=self.tenant,
            dev_index='dev-bob',
            serial_number='SN7654321',
        )

        AttendanceEvent.objects.create(
            tenant=self.tenant,
            device=device_alice,
            user_id='E1001',
            timestamp='2026-02-01T08:00:00Z',
            event_type='checkin',
        )
        AttendanceEvent.objects.create(
            tenant=self.tenant,
            device=device_bob,
            user_id='E2001',
            timestamp='2026-02-01T08:05:00Z',
            event_type='checkin',
        )

        self.client.force_authenticate(self.user1)
        response = self.client.get('/api/events/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['user_id'], 'E1001')
