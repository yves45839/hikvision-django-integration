import { useRouter } from 'expo-router';
import React, { useState } from 'react';
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
import { login } from '../src/api/auth';
import { ApiError, NetworkError } from '../src/api/client';
import { useSession } from '../src/auth/session';
import {
  Input,
  Label,
  LangToggle,
  PrimaryButton,
} from '../src/components/ui';
import { useI18n } from '../src/i18n';
import { colors, spacing } from '../src/lib/theme';

export default function LoginScreen() {
  const { t, lang, setLang } = useI18n();
  const { signIn } = useSession();
  const router = useRouter();

  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async () => {
    const id = identifier.trim();
    if (!id || !password) {
      setError(t('login.missingFields'));
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const session = await login(id, password);
      signIn(session);
      router.replace('/(tabs)');
    } catch (err) {
      if (err instanceof ApiError) {
        setError(
          err.status === 400 || err.status === 401
            ? t('login.invalidCredentials')
            : err.detail || t('common.genericError')
        );
      } else if (err instanceof NetworkError) {
        setError(t('common.networkError'));
      } else {
        setError(t('common.genericError'));
      }
    } finally {
      setSubmitting(false);
    }
  };

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

          <View style={styles.header}>
            <Text style={styles.brand}>
              LR <Text style={styles.brandAccent}>Time</Text>
            </Text>
            <Text style={styles.subtitle}>{t('login.subtitle')}</Text>
          </View>

          <Label>{t('login.identifier')}</Label>
          <Input
            value={identifier}
            onChangeText={setIdentifier}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="email-address"
            textContentType="username"
            editable={!submitting}
          />

          <Label>{t('login.password')}</Label>
          <Input
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            textContentType="password"
            editable={!submitting}
            onSubmitEditing={onSubmit}
            returnKeyType="go"
          />

          {error ? <Text style={styles.error}>{error}</Text> : null}

          <PrimaryButton
            title={submitting ? t('login.submitting') : t('login.submit')}
            onPress={onSubmit}
            loading={submitting}
            style={styles.submit}
          />

          <Pressable
            onPress={() => router.push('/accept-invitation')}
            style={styles.invitationLink}
          >
            <Text style={styles.invitationLinkText}>
              {t('login.invitationLink')}
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
    justifyContent: 'center',
  },
  header: {
    alignItems: 'center',
    marginBottom: spacing.xl,
  },
  brand: {
    color: colors.text,
    fontSize: 40,
    fontWeight: '800',
    letterSpacing: 1,
  },
  brandAccent: {
    color: colors.accent,
  },
  subtitle: {
    color: colors.textMuted,
    fontSize: 15,
    marginTop: spacing.xs,
  },
  error: {
    color: colors.danger,
    marginTop: spacing.md,
    fontSize: 14,
  },
  submit: {
    marginTop: spacing.lg,
  },
  invitationLink: {
    marginTop: spacing.lg,
    alignItems: 'center',
    paddingVertical: spacing.sm,
  },
  invitationLinkText: {
    color: colors.accent,
    fontSize: 15,
    fontWeight: '600',
  },
});
