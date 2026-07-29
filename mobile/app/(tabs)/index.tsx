import * as Application from 'expo-application';
import * as Location from 'expo-location';
import { useFocusEffect } from 'expo-router';
import React, {
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react';
import {
  ActivityIndicator,
  Animated,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { ApiError, NetworkError } from '../../src/api/client';
import {
  getMe,
  MeResponse,
  punch,
  PunchAction,
  PunchResponse,
  ScheduleSlot,
} from '../../src/api/mobile';
import { Card, PrimaryButton, SecondaryButton } from '../../src/components/ui';
import { useI18n } from '../../src/i18n';
import { newUuid } from '../../src/lib/installation';
import { colors, radius, spacing } from '../../src/lib/theme';

// ---------------------------------------------------------------------------
// Punch UI state machine
// ---------------------------------------------------------------------------

type PunchUiState =
  | { kind: 'idle' }
  | { kind: 'locating' }
  | { kind: 'sending' }
  | { kind: 'success'; result: PunchResponse }
  | {
      kind: 'error';
      code: string;
      message: string;
      canRetryHighAccuracy?: boolean;
      /** Epoch ms until which TOO_SOON blocks a new attempt. */
      retryUntil?: number;
    };

const CLIENT_ACCURACY_RETRY_THRESHOLD_M = 150;

function asNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value)
    ? value
    : undefined;
}

// ---------------------------------------------------------------------------
// Screen
// ---------------------------------------------------------------------------

export default function HomeScreen() {
  const { t, locale } = useI18n();

  const [me, setMe] = useState<MeResponse | null>(null);
  const [meError, setMeError] = useState<string | null>(null);
  const [initialLoading, setInitialLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [punchState, setPunchState] = useState<PunchUiState>({ kind: 'idle' });
  // Set from a SUGGESTED_ACTION_CHANGED error until /me/ reloads.
  const [actionOverride, setActionOverride] = useState<PunchAction | null>(
    null
  );
  // Ticks every second while a TOO_SOON countdown is showing.
  const [now, setNow] = useState(() => Date.now());

  // Idempotency key of the in-flight attempt. Created per attempt and KEPT
  // across retries until a server response (success or API error) arrives,
  // so a network retry can never create a duplicate punch.
  const pendingKeyRef = useRef<string | null>(null);

  const loadMe = useCallback(async (silent = false) => {
    if (!silent) setMeError(null);
    try {
      const data = await getMe();
      setMe(data);
      setActionOverride(null);
      setMeError(null);
    } catch (err) {
      if (!silent) {
        setMeError(
          err instanceof NetworkError
            ? tRef.current('common.networkError')
            : err instanceof ApiError
              ? err.detail
              : tRef.current('common.genericError')
        );
      }
    } finally {
      setInitialLoading(false);
    }
  }, []);

  // Keep a stable ref to t for use inside stable callbacks.
  const tRef = useRef(t);
  tRef.current = t;

  useFocusEffect(
    useCallback(() => {
      void loadMe(me !== null);
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [loadMe])
  );

  const onPullRefresh = useCallback(async () => {
    setRefreshing(true);
    await loadMe();
    setRefreshing(false);
  }, [loadMe]);

  // TOO_SOON countdown ticker.
  useEffect(() => {
    if (punchState.kind !== 'error' || !punchState.retryUntil) return;
    const interval = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(interval);
  }, [punchState]);

  const retrySecondsLeft =
    punchState.kind === 'error' && punchState.retryUntil
      ? Math.max(0, Math.ceil((punchState.retryUntil - now) / 1000))
      : 0;

  useEffect(() => {
    if (
      punchState.kind === 'error' &&
      punchState.retryUntil &&
      retrySecondsLeft <= 0
    ) {
      setPunchState({ kind: 'idle' });
    }
  }, [punchState, retrySecondsLeft]);

  const displayedAction: PunchAction =
    actionOverride ?? me?.suggested_action ?? 'CHECK_IN';

  // -------------------------------------------------------------------------
  // Punch flow
  // -------------------------------------------------------------------------

  const handleApiError = useCallback((err: ApiError) => {
    const t = tRef.current;
    const p = err.payload;
    switch (err.code) {
      case 'OUT_OF_ZONE': {
        const nearest = p.nearest_site as
          | { id?: number; name?: string }
          | undefined;
        setPunchState({
          kind: 'error',
          code: err.code,
          message: t('home.error.OUT_OF_ZONE', {
            distance: Math.round(asNumber(p.distance_m) ?? 0),
            site: nearest?.name ?? '—',
            tolerance: Math.round(asNumber(p.tolerance_m) ?? 0),
          }),
        });
        break;
      }
      case 'TOO_SOON': {
        const retryAfter = asNumber(p.retry_after_s) ?? 60;
        setNow(Date.now());
        setPunchState({
          kind: 'error',
          code: err.code,
          message: '', // rendered live from the countdown
          retryUntil: Date.now() + retryAfter * 1000,
        });
        break;
      }
      case 'ACCURACY_TOO_LOW': {
        setPunchState({
          kind: 'error',
          code: err.code,
          message: t('home.error.ACCURACY_TOO_LOW', {
            max: Math.round(asNumber(p.max_accuracy_m) ?? 0),
          }),
          canRetryHighAccuracy: true,
        });
        break;
      }
      case 'SUGGESTED_ACTION_CHANGED': {
        const suggested = p.suggested_action;
        if (suggested === 'CHECK_IN' || suggested === 'CHECK_OUT') {
          setActionOverride(suggested);
        }
        setPunchState({
          kind: 'error',
          code: err.code,
          message: t('home.error.SUGGESTED_ACTION_CHANGED'),
        });
        void loadMeRef.current(true);
        break;
      }
      case 'NO_SITE_CONFIGURED':
        setPunchState({
          kind: 'error',
          code: err.code,
          message: t('home.error.NO_SITE_CONFIGURED'),
        });
        break;
      case 'PROFILE_NOT_LINKED':
        setPunchState({
          kind: 'error',
          code: err.code,
          message: t('home.error.PROFILE_NOT_LINKED'),
        });
        break;
      case 'INVALID_COORDINATES':
        setPunchState({
          kind: 'error',
          code: err.code,
          message: t('home.error.INVALID_COORDINATES'),
        });
        break;
      default:
        setPunchState({
          kind: 'error',
          code: err.code ?? 'UNKNOWN',
          message: err.detail || t('common.genericError'),
        });
    }
  }, []);

  const loadMeRef = useRef(loadMe);
  loadMeRef.current = loadMe;

  const doPunch = useCallback(
    async (forceHighAccuracy = false) => {
      const t = tRef.current;
      const action = displayedAction;

      setPunchState({ kind: 'locating' });

      // 1. Permission
      const permission = await Location.requestForegroundPermissionsAsync();
      if (!permission.granted) {
        setPunchState({
          kind: 'error',
          code: 'LOCATION_DENIED',
          message: t('home.error.locationDenied'),
        });
        return;
      }

      // 2. Position (Balanced first; one High-accuracy retry when > 150 m)
      let position: Location.LocationObject;
      try {
        position = await Location.getCurrentPositionAsync({
          accuracy: forceHighAccuracy
            ? Location.Accuracy.High
            : Location.Accuracy.Balanced,
        });
        const accuracy = position.coords.accuracy;
        if (
          !forceHighAccuracy &&
          (accuracy == null || accuracy > CLIENT_ACCURACY_RETRY_THRESHOLD_M)
        ) {
          position = await Location.getCurrentPositionAsync({
            accuracy: Location.Accuracy.High,
          });
        }
      } catch {
        setPunchState({
          kind: 'error',
          code: 'LOCATION_UNAVAILABLE',
          message: t('home.error.locationUnavailable'),
        });
        return;
      }

      // 3. Payload — reuse the pending idempotency key when retrying after
      //    a network failure; only a server response clears it.
      if (!pendingKeyRef.current) {
        pendingKeyRef.current = newUuid();
      }
      const idempotencyKey = pendingKeyRef.current;

      setPunchState({ kind: 'sending' });
      try {
        const result = await punch({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          accuracy_m: Math.round(position.coords.accuracy ?? 9999),
          action,
          idempotency_key: idempotencyKey,
          client_reported_at: new Date().toISOString(),
          app_version: Application.nativeApplicationVersion ?? undefined,
          mocked: position.mocked ?? false,
        });
        pendingKeyRef.current = null;
        setPunchState({ kind: 'success', result });
        void loadMeRef.current(true);
      } catch (err) {
        if (err instanceof ApiError) {
          pendingKeyRef.current = null; // the server saw this key
          handleApiError(err);
        } else if (err instanceof NetworkError) {
          // Keep the key: retrying with it is safe (idempotent server-side).
          setPunchState({
            kind: 'error',
            code: 'NETWORK',
            message: t('common.networkError'),
          });
        } else {
          pendingKeyRef.current = null;
          setPunchState({
            kind: 'error',
            code: 'UNKNOWN',
            message: t('common.genericError'),
          });
        }
      }
    },
    [displayedAction, handleApiError]
  );

  // -------------------------------------------------------------------------
  // Render helpers
  // -------------------------------------------------------------------------

  const formatTime = useCallback(
    (iso: string) =>
      new Date(iso).toLocaleTimeString(locale, {
        hour: '2-digit',
        minute: '2-digit',
      }),
    [locale]
  );

  const busy = punchState.kind === 'locating' || punchState.kind === 'sending';
  const blocked =
    punchState.kind === 'error' &&
    punchState.code === 'TOO_SOON' &&
    retrySecondsLeft > 0;

  const punchButtonTitle =
    punchState.kind === 'locating'
      ? t('home.locating')
      : punchState.kind === 'sending'
        ? t('home.sending')
        : displayedAction === 'CHECK_IN'
          ? t('home.actionCheckIn')
          : t('home.actionCheckOut');

  const dateLabel = me
    ? new Date(`${me.date}T00:00:00`).toLocaleDateString(locale, {
        weekday: 'long',
        day: 'numeric',
        month: 'long',
      })
    : '';

  if (initialLoading) {
    return (
      <SafeAreaView style={styles.safe}>
        <View style={styles.center}>
          <ActivityIndicator size="large" color={colors.accent} />
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <ScrollView
        contentContainerStyle={styles.container}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => void onPullRefresh()}
            tintColor={colors.accent}
            colors={[colors.accent]}
          />
        }
      >
        {/* Greeting */}
        <Text style={styles.greeting}>
          {t('home.greeting', { name: me?.employee.name ?? '' })}
        </Text>
        <Text style={styles.dateLabel}>{dateLabel}</Text>

        {meError ? (
          <Card style={styles.errorCard}>
            <Text style={styles.errorText}>{meError}</Text>
            <SecondaryButton
              title={t('common.retry')}
              onPress={() => void loadMe()}
              style={styles.errorRetry}
            />
          </Card>
        ) : null}

        {/* Schedule */}
        {me ? (
          <Card style={styles.sectionCard}>
            <Text style={styles.sectionTitle}>{t('home.scheduleTitle')}</Text>
            {me.day_schedule.is_rest_day ? (
              <Text style={styles.mutedText}>{t('home.restDay')}</Text>
            ) : me.day_schedule.slots.length === 0 ? (
              <Text style={styles.mutedText}>{t('home.noSchedule')}</Text>
            ) : (
              me.day_schedule.slots.map((slot, index) => (
                <ScheduleSlotRow key={index} slot={slot} />
              ))
            )}
          </Card>
        ) : null}

        {/* Punch button + result */}
        <View style={styles.punchSection}>
          <PrimaryButton
            title={punchButtonTitle}
            onPress={() => void doPunch()}
            disabled={busy || blocked || !me}
            loading={busy}
            style={styles.punchButton}
          />

          {punchState.kind === 'success' ? (
            <SuccessCard
              result={punchState.result}
              formatTime={formatTime}
            />
          ) : null}

          {punchState.kind === 'error' ? (
            <Card style={styles.punchErrorCard}>
              <Text style={styles.errorText}>
                {punchState.code === 'TOO_SOON'
                  ? t('home.error.TOO_SOON', { seconds: retrySecondsLeft })
                  : punchState.message}
              </Text>
              {punchState.canRetryHighAccuracy ? (
                <SecondaryButton
                  title={t('home.retryHighAccuracy')}
                  onPress={() => void doPunch(true)}
                  style={styles.errorRetry}
                />
              ) : null}
              {punchState.code === 'NETWORK' ? (
                <SecondaryButton
                  title={t('common.retry')}
                  onPress={() => void doPunch()}
                  style={styles.errorRetry}
                />
              ) : null}
              {punchState.code !== 'TOO_SOON' ? (
                <Pressable
                  onPress={() => setPunchState({ kind: 'idle' })}
                  style={styles.dismiss}
                >
                  <Text style={styles.dismissText}>{t('home.dismiss')}</Text>
                </Pressable>
              ) : null}
            </Card>
          ) : null}
        </View>

        {/* Punches today */}
        {me ? (
          <Card style={styles.sectionCard}>
            <Text style={styles.sectionTitle}>{t('home.punchesTitle')}</Text>
            {me.punches_today.length === 0 ? (
              <Text style={styles.mutedText}>{t('home.noPunches')}</Text>
            ) : (
              me.punches_today.map((p) => (
                <View key={p.id} style={styles.punchRow}>
                  <View
                    style={[
                      styles.punchDot,
                      p.action === 'CHECK_IN'
                        ? styles.punchDotIn
                        : styles.punchDotOut,
                    ]}
                  />
                  <Text style={styles.punchRowAction}>
                    {p.action === 'CHECK_IN'
                      ? t('history.checkIn')
                      : t('history.checkOut')}
                  </Text>
                  <Text style={styles.punchRowSite} numberOfLines={1}>
                    {p.site_name ?? ''}
                  </Text>
                  <Text style={styles.punchRowTime}>
                    {formatTime(p.timestamp)}
                  </Text>
                </View>
              ))
            )}
          </Card>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

// ---------------------------------------------------------------------------
// Schedule slot row
// ---------------------------------------------------------------------------

function ScheduleSlotRow({ slot }: { slot: ScheduleSlot }) {
  const isRest = slot.slot_type === 'rest';
  const times =
    slot.start_time && slot.end_time
      ? `${slot.start_time} – ${slot.end_time}`
      : '—';
  return (
    <View style={styles.slotRow}>
      <Text style={[styles.slotLabel, isRest && styles.slotRest]}>
        {slot.label}
      </Text>
      <Text style={[styles.slotTimes, isRest && styles.slotRest]}>
        {times}
      </Text>
    </View>
  );
}

// ---------------------------------------------------------------------------
// Success card (subtle entrance animation)
// ---------------------------------------------------------------------------

function SuccessCard({
  result,
  formatTime,
}: {
  result: PunchResponse;
  formatTime: (iso: string) => string;
}) {
  const { t } = useI18n();
  const opacity = useRef(new Animated.Value(0)).current;
  const translateY = useRef(new Animated.Value(12)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.timing(opacity, {
        toValue: 1,
        duration: 250,
        useNativeDriver: true,
      }),
      Animated.spring(translateY, {
        toValue: 0,
        friction: 7,
        useNativeDriver: true,
      }),
    ]).start();
  }, [opacity, translateY]);

  const schedule = result.schedule;
  let scheduleLine: string;
  if (schedule.in_schedule) {
    scheduleLine = t('home.scheduleOnTime');
  } else if (schedule.delta_minutes === null) {
    scheduleLine = t('home.scheduleOutside');
  } else {
    // Negative delta = before the scheduled boundary (early),
    // positive delta = after it (late).
    scheduleLine =
      schedule.delta_minutes < 0
        ? t('home.scheduleEarly', { minutes: Math.abs(schedule.delta_minutes) })
        : t('home.scheduleLate', { minutes: Math.abs(schedule.delta_minutes) });
  }

  return (
    <Animated.View
      style={[styles.successCard, { opacity, transform: [{ translateY }] }]}
    >
      <Text style={styles.successTitle}>
        {result.action === 'CHECK_IN'
          ? t('home.successCheckIn')
          : t('home.successCheckOut')}{' '}
        {t('home.successAtSite', { site: result.site.name })}
      </Text>
      <Text style={styles.successLine}>
        {formatTime(result.timestamp)} ·{' '}
        {t('home.successDistance', {
          distance: Math.round(result.distance_m),
        })}
      </Text>
      {result.zone === 'borderline' ? (
        <Text style={styles.successWarn}>{t('home.zoneBorderline')}</Text>
      ) : null}
      <Text style={styles.successLine}>{scheduleLine}</Text>
    </Animated.View>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  container: { padding: spacing.md, paddingBottom: spacing.xl },
  greeting: {
    color: colors.text,
    fontSize: 24,
    fontWeight: '800',
    marginTop: spacing.sm,
  },
  dateLabel: {
    color: colors.textMuted,
    fontSize: 14,
    marginTop: 2,
    marginBottom: spacing.md,
    textTransform: 'capitalize',
  },
  sectionCard: {
    marginBottom: spacing.md,
  },
  sectionTitle: {
    color: colors.textFaint,
    fontSize: 12,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 1,
    marginBottom: spacing.sm,
  },
  mutedText: {
    color: colors.textMuted,
    fontSize: 14,
  },
  slotRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 6,
  },
  slotLabel: {
    color: colors.text,
    fontSize: 15,
  },
  slotTimes: {
    color: colors.text,
    fontSize: 15,
    fontVariant: ['tabular-nums'],
  },
  slotRest: {
    color: colors.textFaint,
  },
  punchSection: {
    marginBottom: spacing.md,
  },
  punchButton: {
    minHeight: 64,
    borderRadius: radius.lg,
  },
  successCard: {
    marginTop: spacing.md,
    backgroundColor: colors.successSoft,
    borderColor: colors.success,
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: spacing.md,
  },
  successTitle: {
    color: colors.success,
    fontSize: 17,
    fontWeight: '700',
  },
  successLine: {
    color: colors.text,
    fontSize: 14,
    marginTop: spacing.xs,
  },
  successWarn: {
    color: colors.warning,
    fontSize: 13,
    marginTop: spacing.xs,
  },
  punchErrorCard: {
    marginTop: spacing.md,
    backgroundColor: colors.dangerSoft,
    borderColor: colors.danger,
  },
  errorCard: {
    marginBottom: spacing.md,
    backgroundColor: colors.dangerSoft,
    borderColor: colors.danger,
  },
  errorText: {
    color: colors.text,
    fontSize: 14,
    lineHeight: 20,
  },
  errorRetry: {
    marginTop: spacing.sm,
  },
  dismiss: {
    marginTop: spacing.sm,
    alignSelf: 'flex-start',
  },
  dismissText: {
    color: colors.textMuted,
    fontSize: 13,
    fontWeight: '600',
  },
  punchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 6,
  },
  punchDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginRight: spacing.sm,
  },
  punchDotIn: { backgroundColor: colors.success },
  punchDotOut: { backgroundColor: colors.accent },
  punchRowAction: {
    color: colors.text,
    fontSize: 15,
    fontWeight: '600',
    marginRight: spacing.sm,
  },
  punchRowSite: {
    color: colors.textFaint,
    fontSize: 13,
    flex: 1,
  },
  punchRowTime: {
    color: colors.textMuted,
    fontSize: 15,
    fontVariant: ['tabular-nums'],
  },
});
