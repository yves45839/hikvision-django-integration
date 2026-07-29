import { Ionicons } from '@expo/vector-icons';
import { Tabs, useRouter } from 'expo-router';
import React, { useEffect } from 'react';
import {
  addNotificationTapListener,
  registerForPushNotifications,
} from '../../src/notifications';
import { useI18n } from '../../src/i18n';
import { colors } from '../../src/lib/theme';

export default function TabsLayout() {
  const { t, locale } = useI18n();
  const router = useRouter();

  // Only runs once signed in (this layout is behind the auth gate).
  useEffect(() => {
    void registerForPushNotifications(locale);
    const removeTapListener = addNotificationTapListener(() => {
      router.navigate('/(tabs)');
    });
    return removeTapListener;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarStyle: {
          backgroundColor: colors.card,
          borderTopColor: colors.border,
        },
        tabBarActiveTintColor: colors.accent,
        tabBarInactiveTintColor: colors.textFaint,
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: t('tabs.home'),
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="finger-print" size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="history"
        options={{
          title: t('tabs.history'),
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="time-outline" size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="settings"
        options={{
          title: t('tabs.settings'),
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="settings-outline" size={size} color={color} />
          ),
        }}
      />
    </Tabs>
  );
}
