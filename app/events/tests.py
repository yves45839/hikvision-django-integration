from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from devices.models import Device
from events.models import AttendanceEvent
from tenants.models import Tenant, TenantMembership, TenantRole


User = get_user_model()


class AttendanceEventTenantScopingTests(APITestCase):
    """La liste des events est scopée par appartenance tenant (BACKLOG 4.5)."""

    def setUp(self):
        self.user1 = User.objects.create_user(username='alice', password='pwd12345')
        self.user2 = User.objects.create_user(username='bob', password='pwd12345')
        self.tenant_a = Tenant.objects.create(name='Tenant A', code='tenant-a')
        self.tenant_b = Tenant.objects.create(name='Tenant B', code='tenant-b')
        TenantMembership.objects.create(
            user=self.user1, tenant=self.tenant_a, role=TenantRole.VIEWER
        )
        TenantMembership.objects.create(
            user=self.user2, tenant=self.tenant_b, role=TenantRole.VIEWER
        )

    def test_user_only_sees_events_for_own_tenants(self):
        device_a = Device.objects.create(
            owner=self.user1,
            tenant=self.tenant_a,
            dev_index='dev-alice',
            serial_number='SN1234567',
        )
        device_b = Device.objects.create(
            owner=self.user2,
            tenant=self.tenant_b,
            dev_index='dev-bob',
            serial_number='SN7654321',
        )

        AttendanceEvent.objects.create(
            tenant=self.tenant_a,
            device=device_a,
            user_id='E1001',
            timestamp='2026-02-01T08:00:00Z',
            event_type='checkin',
        )
        AttendanceEvent.objects.create(
            tenant=self.tenant_b,
            device=device_b,
            user_id='E2001',
            timestamp='2026-02-01T08:05:00Z',
            event_type='checkin',
        )

        self.client.force_authenticate(self.user1)
        response = self.client.get('/api/events/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['user_id'], 'E1001')

    def test_user_without_membership_sees_nothing(self):
        outsider = User.objects.create_user(username='eve', password='pwd12345')
        device_a = Device.objects.create(
            owner=self.user1,
            tenant=self.tenant_a,
            dev_index='dev-a2',
            serial_number='SN0000001',
        )
        AttendanceEvent.objects.create(
            tenant=self.tenant_a,
            device=device_a,
            user_id='E1001',
            timestamp='2026-02-01T08:00:00Z',
            event_type='checkin',
        )

        self.client.force_authenticate(outsider)
        response = self.client.get('/api/events/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)
