/**
 * LR Time visual style — dark, clean, orange accent.
 * Consistent with the LR Time web dashboard.
 */
export const colors = {
  bg: '#0b0f14',
  card: '#151a21',
  cardElevated: '#1b212b',
  border: '#252c37',
  text: '#f4f4f5',
  textMuted: '#9ca3af',
  textFaint: '#6b7280',
  accent: '#f97316',
  accentPressed: '#ea580c',
  accentSoft: 'rgba(249, 115, 22, 0.12)',
  success: '#22c55e',
  successSoft: 'rgba(34, 197, 94, 0.12)',
  danger: '#ef4444',
  dangerSoft: 'rgba(239, 68, 68, 0.12)',
  warning: '#eab308',
  warningSoft: 'rgba(234, 179, 8, 0.12)',
  inputBg: '#10151c',
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
} as const;

export const radius = {
  sm: 8,
  md: 12,
  lg: 16,
  full: 999,
} as const;
