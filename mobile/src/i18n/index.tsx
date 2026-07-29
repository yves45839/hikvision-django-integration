import AsyncStorage from '@react-native-async-storage/async-storage';
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { dictionaries, Lang, TranslationKey } from './translations';

const LANG_STORAGE_KEY = 'lrtime.lang';

interface I18nContextValue {
  lang: Lang;
  /** BCP-47 locale used for date/time formatting. */
  locale: string;
  setLang: (lang: Lang) => void;
  t: (key: TranslationKey, vars?: Record<string, string | number>) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

function interpolate(
  template: string,
  vars?: Record<string, string | number>
): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) => {
    const value = vars[name];
    return value === undefined ? match : String(value);
  });
}

export function I18nProvider({ children }: { children: React.ReactNode }) {
  // EN is the default language.
  const [lang, setLangState] = useState<Lang>('en');
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    AsyncStorage.getItem(LANG_STORAGE_KEY)
      .then((stored) => {
        if (!cancelled && (stored === 'en' || stored === 'fr')) {
          setLangState(stored);
        }
      })
      .catch(() => {
        // Ignore storage errors — fall back to default language.
      })
      .finally(() => {
        if (!cancelled) setReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const setLang = useCallback((next: Lang) => {
    setLangState(next);
    AsyncStorage.setItem(LANG_STORAGE_KEY, next).catch(() => {
      // Non-fatal: the choice simply won't persist.
    });
  }, []);

  const t = useCallback(
    (key: TranslationKey, vars?: Record<string, string | number>) =>
      interpolate(dictionaries[lang][key], vars),
    [lang]
  );

  const value = useMemo<I18nContextValue>(
    () => ({
      lang,
      locale: lang === 'fr' ? 'fr-FR' : 'en-US',
      setLang,
      t,
    }),
    [lang, setLang, t]
  );

  // Render nothing until the persisted choice is loaded to avoid a language flash.
  if (!ready) return null;

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) {
    throw new Error('useI18n must be used within an I18nProvider');
  }
  return ctx;
}
