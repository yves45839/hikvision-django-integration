import * as Application from 'expo-application';
import { useRouter } from 'expo-router';
import React, { useEffect, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { getMe, MeResponse } from '../../src/api/mobile';
import { useSession } from '../../src/auth/session';
import {
  Card,
  LangToggle,
  SecondaryButton,
} from '../../src/components/ui';
import { useI18n } from '../../src/i18n';
import { colors, spacing } from '../../src/lib/theme';

export default function SettingsScreen() {
  const { t, lang, setLang } = useI18n();
  const { session, signOut } = useSession();
  const router = useRouter();

  const [me, setMe] = useState<MeResponse | null>(null);
  const [loggingOut, setLoggingOut] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getMe()
      .then((data) => {
        if (!cancelled) setMe(data);
      })
      .catch(() => {
        // Identity falls back to the stored session user below.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const displayName =
    me?.employee.name ??
    session?.user.name ??
    [session?.user.first_name, session?.user.last_name]
      .filter(Boolean)
      .join(' ') ??
    '';
  const email = session?.user.email ?? '';
  const tenantName =
    me?.employee.tenant.name ?? session?.tenants[0]?.name ?? '';
  const appVersion = Application.nativeApplicationVersion ?? 'dev';

  const onLogout = async () => {
    setLoggingOut(true);
    try {
      // signOut deletes the push token from the backend, then clears the
      // access token (memory) and the refresh token (secure store).
      await signOut();
      router.replace('/login');
    } finally {
      setLoggingOut(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <ScrollView contentContainerStyle={styles.container}>
        <Text style={styles.title}>{t('settings.title')}</Text>

        {/* Language */}
        <Text style={styles.sectionTitle}>{t('settings.language')}</Text>
        <Card style={styles.card}>
          <View style={styles.langRow}>
            <Text style={styles.rowLabel}>
              {lang === 'fr' ? t('settings.french') : t('settings.english')}
            </Text>
            <LangToggle lang={lang} onChange={setLang} />
          </View>
        </Card>

        {/* Account */}
        <Text style={styles.sectionTitle}>{t('settings.account')}</Text>
        <Card style={styles.card}>
          {displayName ? (
            <Text style={styles.identityName}>{displayName}</Text>
          ) : null}
          {email ? <Text style={styles.identityLine}>{email}</Text> : null}
          {me ? (
            <Text style={styles.identityLine}>
              {t('settings.employeeNo')} : {me.employee.employee_no}
            </Text>
          ) : null}
          {tenantName ? (
            <Text style={styles.identityLine}>
              {t('settings.company')} : {tenantName}
            </Text>
          ) : null}
        </Card>

        {/* About */}
        <Text style={styles.sectionTitle}>{t('settings.about')}</Text>
        <Card style={styles.card}>
          <Text style={styles.identityLine}>
            {t('settings.version')} : {appVersion}
          </Text>
          <Text style={styles.gpsNotice}>{t('settings.gpsNotice')}</Text>
        </Card>

        <SecondaryButton
          title={loggingOut ? t('settings.loggingOut') : t('settings.logout')}
          onPress={() => void onLogout()}
          disabled={loggingOut}
          style={styles.logout}
        />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  container: { padding: spacing.md, paddingBottom: spacing.xl },
  title: {
    color: colors.text,
    fontSize: 24,
    fontWeight: '800',
    marginTop: spacing.sm,
    marginBottom: spacing.md,
  },
  sectionTitle: {
    color: colors.textFaint,
    fontSize: 12,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 1,
    marginBottom: spacing.sm,
    marginTop: spacing.sm,
  },
  card: { marginBottom: spacing.md },
  langRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  rowLabel: { color: colors.text, fontSize: 15 },
  identityName: {
    color: colors.text,
    fontSize: 17,
    fontWeight: '700',
    marginBottom: spacing.xs,
  },
  identityLine: {
    color: colors.textMuted,
    fontSize: 14,
    marginTop: 2,
  },
  gpsNotice: {
    color: colors.textFaint,
    fontSize: 12,
    fontStyle: 'italic',
    marginTop: spacing.sm,
    lineHeight: 17,
  },
  logout: {
    marginTop: spacing.md,
    borderColor: colors.danger,
  },
});
