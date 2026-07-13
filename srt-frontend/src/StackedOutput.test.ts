import { describe, expect, it } from "vitest";

import { parseStackedPreview } from "./stackedPreview.ts";

describe("parseStackedPreview", () => {
  it("turns SRT blocks into review cues", () => {
    expect(
      parseStackedPreview(
        "1\r\n00:00:01,000 --> 00:00:03,000\r\nHello\r\nBonjour\r\n\r\n2\r\n00:00:04,000 --> 00:00:05,000\r\nBye\r\nAu revoir\r\n",
      ),
    ).toEqual([
      {
        index: "1",
        timecode: "00:00:01,000 --> 00:00:03,000",
        lines: ["Hello", "Bonjour"],
      },
      {
        index: "2",
        timecode: "00:00:04,000 --> 00:00:05,000",
        lines: ["Bye", "Au revoir"],
      },
    ]);
  });
});
