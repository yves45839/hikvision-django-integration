import { useLocalSearchParams, useRouter } from 'expo-router';
import React, { useCallback, useEffect, useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import {
  acceptInvitation,
  InvitationPreview,
  previewInvitation,
} from '../src/api/auth';
import { ApiError, NetworkError } from '../src/api/client';
import { useSession } from '../src/auth/session';
import {
  Card,
  Input,
  Label,
  LangToggle,
  PrimaryButton,
} from '../src/components/ui';
import { useI18n } from '../src/i18n';
import { TranslationKey } from '../src/i18n/translations';
import { colors, spacing } from '../src/lib/theme';

const INVITATION_ERROR_KEYS: Record<string, TranslationKey> = {
  INVALID_TOKEN: 'invitation.error.INVALID_TOKEN',
  EXPIRED: 'invitation.error.EXPIRED',
  ALREADY_LINKED: 'invitation.error.ALREADY_LINKED',
  WEAK_PASSWORD: 'invitation.error.WEAK_PASSWORD',
  EMAIL_IN_USE: 'invitation.error.EMAIL_IN_USE',
};

export default function AcceptInvitationScreen() {
  const { t, lang, setLang, locale } = useI18n();
  const { signIn } = useSession();
  const router = useRouter();

  // Token can arrive via the lrtime://accept-invitation?token=... deep link
  // (expo-router exposes it as a search param) or be pasted manually.
  const params = useLocalSearchParams<{ token?: string }>();
  const deepLinkToken = typeof params.token === 'string' ? params.token : '';

  const [token, setToken] = useState(deepLinkToken);
  const [preview, setPreview] = useState<InvitationPreview | null>(null);
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [checking, setChecking] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const translateError = useCallback(
    (err: unknown): string => {
      if (err instanceof ApiError) {
        const key = err.code ? INVITATION_ERROR_KEYS[err.code] : undefined;
        if (key) return t(key);
        return err.detail || t('common.genericError');
      }
      if (err instanceof NetworkError) return t('common.networkError');
      return t('common.genericError');
    },
    [t]
  );

  const checkToken = useCallback(
    async (value: string) => {
      const trimmed = value.trim();
      if (!trimmed) return;
      setChecking(true);
      setError(null);
      setPreview(null);
      try {
        setPreview(await previewInvitation(trimmed));
      } catch (err) {
        setError(translateError(err));
      } finally {
        setChecking(false);
      }
    },
    [translateError]
  );

  // Auto-preview when opened from a deep link.
  useEffect(() => {
    if (deepLinkToken) {
      setToken(deepLinkToken);
      void checkToken(deepLinkToken);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deepLinkToken]);

  const onAccept = async () => {
    if (password !== confirmPassword) {
      setError(t('invitation.passwordMismatch'));
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      // 201 response has the same shape as login: the account is signed in.
      const session = await acceptInvitation(token.trim(), password);
      signIn(session);
      router.replace('/(tabs)');
    } catch (err) {
      setError(translateError(err));
    } finally {
      setSubmitting(false);
    }
  };

  const expiresAt = preview
    ? new Date(preview.expires_at).toLocaleDateString(locale, {
        day: 'numeric',
        month: 'long',
        year: 'numeric',
      })
    : '';

  return (
    <SafeAreaView style={styles.safe}>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <ScrollView
          contentContainerStyle={styles.container}
          keyboardShouldPersistTaps="handled"
        >
          <LangToggle lang={lang} onChange={setLang} />

          <Text style={styles.title}>{t('invitation.title')}</Text>
          <Text style={styles.subtitle}>{t('invitation.subtitle')}</Text>

          <Label>{t('invitation.tokenLabel')}</Label>
          <Input
            value={token}
            onChangeText={(value) => {
              setToken(value);
              setPreview(null);
            }}
            placeholder={t('invitation.tokenPlaceholder')}
            autoCapitalize="none"
            autoCorrect={false}
            editable={!checking && !submitting}
          />

          {!preview ? (
            <PrimaryButton
              title={checking ? t('invitation.checking') : t('invitation.check')}
              onPress={() => void checkToken(token)}
              loading={checking}
              disabled={!token.trim()}
              style={styles.action}
            />
          ) : (
            <>
              <Card style={styles.previewCard}>
                <Text style={styles.previewName}>
                  {t('invitation.previewEmployee', {
                    name: preview.employee_name,
                  })}
                </Text>
                <Text style={styles.previewLine}>
                  {t('invitation.previewTenant', {
                    tenant: preview.tenant_name,
                  })}
                </Text>
                <Text style={styles.previewLine}>
                  {t('invitation.previewEmail', { email: preview.email })}
                </Text>
                <Text style={styles.previewExpires}>
                  {t('invitation.previewExpires', { date: expiresAt })}
                </Text>
              </Card>

              <Label>{t('invitation.password')}</Label>
              <Input
                value={password}
                onChangeText={setPassword}
                secureTextEntry
                textContentType="newPassword"
                editable={!submitting}
              />

              <Label>{t('invitation.confirmPassword')}</Label>
              <Input
                value={confirmPassword}
                onChangeText={setConfirmPassword}
                secureTextEntry
                textContentType="newPassword"
                editable={!submitting}
              />

              <PrimaryButton
                title={
                  submitting
                    ? t('invitation.submitting')
                    : t('invitation.submit')
                }
                onPress={onAccept}
                loading={submitting}
                disabled={!password || !confirmPassword}
                style={styles.action}
              />
            </>
          )}

          {error ? <Text style={styles.error}>{error}</Text> : null}

          <Pressable
            onPress={() => router.replace('/login')}
            style={styles.backLink}
          >
            <Text style={styles.backLinkText}>
              {t('invitation.backToLogin')}
            </Text>
          </Pressable>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  flex: { flex: 1 },
  container: {
    flexGrow: 1,
    padding: spacing.lg,
  },
  title: {
    color: colors.text,
    fontSize: 26,
    fontWeight: '800',
    marginTop: spacing.lg,
  },
  subtitle: {
    color: colors.textMuted,
    fontSize: 14,
    marginTop: spacing.xs,
    marginBottom: spacing.md,
  },
  previewCard: {
    marginTop: spacing.md,
    borderColor: colors.accent,
  },
  previewName: {
    color: colors.text,
    fontSize: 17,
    fontWeight: '700',
  },
  previewLine: {
    color: colors.textMuted,
    fontSize: 14,
    marginTop: spacing.xs,
  },
  previewExpires: {
    color: colors.textFaint,
    fontSize: 12,
    marginTop: spacing.sm,
  },
  action: {
    marginTop: spacing.lg,
  },
  error: {
    color: colors.danger,
    marginTop: spacing.md,
    fontSize: 14,
  },
  backLink: {
    marginTop: spacing.lg,
    alignItems: 'center',
    paddingVertical: spacing.sm,
  },
  backLinkText: {
    color: colors.accent,
    fontSize: 15,
    fontWeight: '600',
  },
});
