import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect } from 'expo-router';
import React, { useCallback, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { ApiError, NetworkError } from '../../src/api/client';
import { getHistory, PunchRecord } from '../../src/api/mobile';
import { Card, SecondaryButton } from '../../src/components/ui';
import { useI18n } from '../../src/i18n';
import { colors, spacing } from '../../src/lib/theme';

interface DayGroup {
  /** Local date key, e.g. "2026-07-29". */
  key: string;
  date: Date;
  punches: PunchRecord[];
}

function localDateKey(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function groupByDay(records: PunchRecord[]): DayGroup[] {
  const groups = new Map<string, DayGroup>();
  for (const record of records) {
    const date = new Date(record.timestamp);
    const key = localDateKey(date);
    let group = groups.get(key);
    if (!group) {
      group = { key, date, punches: [] };
      groups.set(key, group);
    }
    group.punches.push(record);
  }
  // Newest day first; within a day keep the API order (newest first).
  return [...groups.values()].sort((a, b) => (a.key < b.key ? 1 : -1));
}

export default function HistoryScreen() {
  const { t, locale } = useI18n();

  const [records, setRecords] = useState<PunchRecord[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const tRef = useRef(t);
  tRef.current = t;

  const load = useCallback(async () => {
    setError(null);
    try {
      const data = await getHistory(50);
      setRecords(data.results);
    } catch (err) {
      setError(
        err instanceof NetworkError
          ? tRef.current('common.networkError')
          : err instanceof ApiError
            ? err.detail
            : tRef.current('common.genericError')
      );
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load])
  );

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  }, [load]);

  const groups = useMemo(
    () => (records ? groupByDay(records) : []),
    [records]
  );

  const formatDay = useCallback(
    (date: Date) =>
      date.toLocaleDateString(locale, {
        weekday: 'long',
        day: 'numeric',
        month: 'long',
        year: 'numeric',
      }),
    [locale]
  );

  const formatTime = useCallback(
    (iso: string) =>
      new Date(iso).toLocaleTimeString(locale, {
        hour: '2-digit',
        minute: '2-digit',
      }),
    [locale]
  );

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <ScrollView
        contentContainerStyle={styles.container}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => void onRefresh()}
            tintColor={colors.accent}
            colors={[colors.accent]}
          />
        }
      >
        <Text style={styles.title}>{t('history.title')}</Text>

        {records === null && !error ? (
          <View style={styles.center}>
            <ActivityIndicator size="large" color={colors.accent} />
          </View>
        ) : null}

        {error ? (
          <Card style={styles.errorCard}>
            <Text style={styles.errorText}>{error}</Text>
            <SecondaryButton
              title={t('common.retry')}
              onPress={() => void load()}
              style={styles.retry}
            />
          </Card>
        ) : null}

        {records !== null && records.length === 0 && !error ? (
          <Text style={styles.empty}>{t('history.empty')}</Text>
        ) : null}

        {groups.map((group) => (
          <View key={group.key} style={styles.group}>
            <Text style={styles.groupTitle}>{formatDay(group.date)}</Text>
            <Card>
              {group.punches.map((punch, index) => (
                <View
                  key={punch.id}
                  style={[
                    styles.row,
                    index < group.punches.length - 1 && styles.rowBorder,
                  ]}
                >
                  <Ionicons
                    name={
                      punch.action === 'CHECK_IN'
                        ? 'arrow-down-circle'
                        : 'arrow-up-circle'
                    }
                    size={22}
                    color={
                      punch.action === 'CHECK_IN'
                        ? colors.success
                        : colors.accent
                    }
                    style={styles.rowIcon}
                  />
                  <View style={styles.rowBody}>
                    <Text style={styles.rowAction}>
                      {punch.action === 'CHECK_IN'
                        ? t('history.checkIn')
                        : t('history.checkOut')}
                    </Text>
                    {punch.site_name ? (
                      <Text style={styles.rowSite} numberOfLines={1}>
                        {punch.site_name}
                      </Text>
                    ) : null}
                  </View>
                  <Text style={styles.rowTime}>
                    {formatTime(punch.timestamp)}
                  </Text>
                </View>
              ))}
            </Card>
          </View>
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  container: { padding: spacing.md, paddingBottom: spacing.xl },
  center: { paddingVertical: spacing.xl, alignItems: 'center' },
  title: {
    color: colors.text,
    fontSize: 24,
    fontWeight: '800',
    marginTop: spacing.sm,
    marginBottom: spacing.md,
  },
  empty: {
    color: colors.textMuted,
    fontSize: 14,
    marginTop: spacing.md,
  },
  errorCard: {
    backgroundColor: colors.dangerSoft,
    borderColor: colors.danger,
    marginBottom: spacing.md,
  },
  errorText: { color: colors.text, fontSize: 14 },
  retry: { marginTop: spacing.sm },
  group: { marginBottom: spacing.md },
  groupTitle: {
    color: colors.textFaint,
    fontSize: 13,
    fontWeight: '700',
    textTransform: 'capitalize',
    marginBottom: spacing.sm,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 10,
  },
  rowBorder: {
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  rowIcon: { marginRight: spacing.sm },
  rowBody: { flex: 1 },
  rowAction: {
    color: colors.text,
    fontSize: 15,
    fontWeight: '600',
  },
  rowSite: {
    color: colors.textFaint,
    fontSize: 13,
    marginTop: 1,
  },
  rowTime: {
    color: colors.textMuted,
    fontSize: 15,
    fontVariant: ['tabular-nums'],
  },
});
