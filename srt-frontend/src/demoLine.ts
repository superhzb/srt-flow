/**
 * The tagline shown over the landing-page compare demo, translated into every
 * language srt·flow supports (see pkg-translator/languages.yaml). The right-hand
 * demo card pairs the English line with whichever of these the visitor's browser
 * points at — see detectTargetLang() in lib.ts.
 */

/** Supported target languages, in the same order as the backend catalogue. */
export const SUPPORTED_LANGS = [
  "en",
  "es",
  "zh",
  "zh-TW",
  "fr",
  "de",
  "pt",
  "ja",
  "ko",
] as const;

export type LangCode = (typeof SUPPORTED_LANGS)[number];

/** Short badge label per language, e.g. "EN + FR". */
export const LANG_LABEL: Record<LangCode, string> = {
  en: "EN",
  es: "ES",
  zh: "简中",
  "zh-TW": "繁中",
  fr: "FR",
  de: "DE",
  pt: "PT",
  ja: "JA",
  ko: "KO",
};

/** The demo line, per language. `en` is always the anchor / bottom line. */
export const DEMO_LINE: Record<LangCode, string> = {
  en: "Brace yourself, we're going straight through!",
  es: "¡Agárrate, vamos a atravesarlo de frente!",
  zh: "抓稳了，我们直接冲过去！",
  "zh-TW": "抓穩了，我們直接衝過去！",
  fr: "Accroche-toi, on fonce tout droit !",
  de: "Halt dich fest, wir fliegen mitten durch!",
  pt: "Segura firme, vamos passar direto!",
  ja: "しっかりつかまって、このまま突き抜けるぞ！",
  ko: "꽉 잡아, 그대로 뚫고 간다!",
};
