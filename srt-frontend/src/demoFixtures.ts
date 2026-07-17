import type { Cue, LanguageInfo } from "./api.ts";
import { LANGUAGES } from "./languages.ts";

export const DEMO_FILENAME = "srt-flow-demo.srt";
export const DEMO_DOWNLOAD_FILENAME = "srt-flow-demo-stacked.srt";

export const DEMO_LANGUAGES: LanguageInfo[] = [
  "en",
  "es",
  "zh",
  "zh-TW",
  "fr",
  "de",
  "pt",
  "ja",
  "ko",
].map((code) => ({ code, name: LANGUAGES[code].en }));

export const DEMO_SAMPLE_SRT = `1
00:00:01,000 --> 00:00:04,000
It takes real strength to make it all the way to the end.

2
00:00:04,500 --> 00:00:07,500
You have to be brave enough to face what comes next.

3
00:00:08,000 --> 00:00:11,000
Every story deserves to reach a wider audience.
`;

const TIMES = [
  ["00:00:01,000", "00:00:04,000"],
  ["00:00:04,500", "00:00:07,500"],
  ["00:00:08,000", "00:00:11,000"],
] as const;

const TEXT: Record<string, string[]> = {
  en: [
    "It takes real strength to make it all the way to the end.",
    "You have to be brave enough to face what comes next.",
    "Every story deserves to reach a wider audience.",
  ],
  es: [
    "Hace falta mucha fuerza para llegar hasta el final.",
    "Hay que ser lo bastante valiente para afrontar lo que viene.",
    "Cada historia merece llegar a un público más amplio.",
  ],
  zh: [
    "坚持走到最后，需要真正的力量。",
    "你必须足够勇敢，去面对接下来的一切。",
    "每个故事都值得被更多观众看见。",
  ],
  "zh-TW": [
    "堅持走到最後，需要真正的力量。",
    "你必須足夠勇敢，去面對接下來的一切。",
    "每個故事都值得被更多觀眾看見。",
  ],
  fr: [
    "Il faut une vraie force pour aller jusqu'au bout.",
    "Il faut assez de courage pour affronter la suite.",
    "Chaque histoire mérite de toucher un public plus large.",
  ],
  de: [
    "Es braucht echte Stärke, um bis zum Ende durchzuhalten.",
    "Man muss mutig genug sein, sich dem Nächsten zu stellen.",
    "Jede Geschichte verdient ein größeres Publikum.",
  ],
  pt: [
    "É preciso muita força para chegar até o fim.",
    "É preciso coragem para enfrentar o que vem a seguir.",
    "Toda história merece alcançar um público maior.",
  ],
  ja: [
    "最後までやり抜くには、本当の強さが必要です。",
    "次に待つものと向き合う勇気が必要です。",
    "すべての物語には、より多くの人に届く価値があります。",
  ],
  ko: [
    "끝까지 해내려면 진정한 강인함이 필요합니다.",
    "앞으로 닥칠 일을 마주할 용기가 필요합니다.",
    "모든 이야기는 더 많은 관객에게 닿을 가치가 있습니다.",
  ],
};

export const DEMO_CUES: Record<string, Cue[]> = Object.fromEntries(
  Object.entries(TEXT).map(([lang, lines]) => [
    lang,
    lines.map((text, index) => ({
      index: index + 1,
      start: TIMES[index][0],
      end: TIMES[index][1],
      text,
    })),
  ]),
);

export function sampleFile(): File {
  return new File([DEMO_SAMPLE_SRT], DEMO_FILENAME, {
    type: "application/x-subrip",
  });
}
