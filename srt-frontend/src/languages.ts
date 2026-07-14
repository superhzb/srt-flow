/**
 * Single source of truth for language display metadata.
 *
 * Merges the flag / English-name / native-name / tint maps that used to be
 * duplicated across ConfigureScreen, StackedOutput, LandingScreen and JobsScreen.
 */
export interface LangMeta {
  /** English name, e.g. "Spanish". */
  en: string;
  /** Endonym, e.g. "Español". */
  native: string;
  /** Flag emoji. */
  flag: string;
  /** Accent tint used by the stacked-output rows. */
  tint: string;
}

export const LANGUAGES: Record<string, LangMeta> = {
  en: { en: "English", native: "English", flag: "🇺🇸", tint: "#00a7c4" },
  fr: { en: "French", native: "Français", flag: "🇫🇷", tint: "#94a3b8" },
  es: { en: "Spanish", native: "Español", flag: "🇪🇸", tint: "#6366f1" },
  de: { en: "German", native: "Deutsch", flag: "🇩🇪", tint: "#f59e0b" },
  it: { en: "Italian", native: "Italiano", flag: "🇮🇹", tint: "#84cc16" },
  pt: { en: "Portuguese", native: "Português", flag: "🇵🇹", tint: "#14b8a6" },
  ja: { en: "Japanese", native: "日本語", flag: "🇯🇵", tint: "#3b82f6" },
  ko: { en: "Korean", native: "한국어", flag: "🇰🇷", tint: "#ec4899" },
  zh: {
    en: "Chinese (Simplified)",
    native: "简体中文",
    flag: "🇨🇳",
    tint: "#12b5a3",
  },
  "zh-TW": {
    en: "Chinese (Traditional)",
    native: "繁體中文",
    flag: "🇹🇼",
    tint: "#0ea5a3",
  },
  ar: { en: "Arabic", native: "العربية", flag: "🇸🇦", tint: "#f97316" },
  hi: { en: "Hindi", native: "हिन्दी", flag: "🇮🇳", tint: "#a855f7" },
  ru: { en: "Russian", native: "Русский", flag: "🇷🇺", tint: "#ef4444" },
  nl: { en: "Dutch", native: "Nederlands", flag: "🇳🇱", tint: "#eab308" },
  pl: { en: "Polish", native: "Polski", flag: "🇵🇱", tint: "#dc2626" },
  tr: { en: "Turkish", native: "Türkçe", flag: "🇹🇷", tint: "#06b6d4" },
  uk: { en: "Ukrainian", native: "Українська", flag: "🇺🇦", tint: "#3b82f6" },
};

/** Metadata for a code, with a safe fallback for unknown codes. */
export function langMeta(code: string): LangMeta {
  return (
    LANGUAGES[code] ?? {
      en: code.toUpperCase(),
      native: code.toUpperCase(),
      flag: "🏳️",
      tint: "#94a3b8",
    }
  );
}
