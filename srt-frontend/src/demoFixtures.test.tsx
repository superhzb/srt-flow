import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DecisionModal } from "./DecisionModal.tsx";
import { DemoProcessing } from "./DemoProcessing.tsx";
import { UploadFlow } from "./UploadFlow.tsx";
import {
  billedCreditMinutes,
  formatDuration,
  sourceCreditMinutes,
  sourceDurationMs,
} from "./sourceMetrics.ts";
import { DEMO_CUES, DEMO_LANGUAGES, DEMO_SAMPLE_SRT } from "./demoFixtures.ts";
import { LandingScreen } from "./LandingScreen.tsx";

afterEach(() => vi.useRealTimers());

describe("guest demo fixtures", () => {
  it("covers every bundled target with complete translated cues", () => {
    expect(DEMO_SAMPLE_SRT).toContain("00:00:01,000 --> 00:00:04,000");
    for (const language of DEMO_LANGUAGES) {
      expect(DEMO_CUES[language.code]).toHaveLength(3);
      expect(DEMO_CUES[language.code].every((cue) => cue.text.length > 0)).toBe(
        true,
      );
    }
  });
});

describe("DecisionModal", () => {
  it("has named actions, closes on Escape, and restores focus", () => {
    const close = vi.fn();
    const trigger = document.createElement("button");
    document.body.append(trigger);
    trigger.focus();
    const view = render(
      <DecisionModal onSignIn={vi.fn()} onDemo={vi.fn()} onClose={close} />,
    );

    expect(
      screen.getByRole("dialog", { name: "Ready to translate?" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: "Sign in for up to 30 free minutes/month",
      }),
    ).toHaveFocus();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(close).toHaveBeenCalledOnce();

    view.unmount();
    expect(trigger).toHaveFocus();
    trigger.remove();
  });
});

describe("requested navigation and demo flow", () => {
  it("cycles the landing comparison through every target language", () => {
    vi.useFakeTimers();
    render(<LandingScreen />);

    expect(
      screen.getByRole("heading", {
        name: "One subtitle in. Every language out.",
      }),
    ).toBeInTheDocument();
    for (const badge of [
      "EN + 简中",
      "EN + FR",
      "EN + ES",
      "EN + 繁中",
      "EN + DE",
      "EN + PT",
      "EN + JA",
      "EN + KO",
    ]) {
      expect(screen.getByText(badge)).toBeInTheDocument();
      act(() => vi.advanceTimersByTime(4000));
    }
    expect(screen.getByText("EN + 简中")).toBeInTheDocument();
  });

  it("does not offer the sample loader in the signed-in upload flow", () => {
    render(
      <UploadFlow
        onSubmit={vi.fn()}
        onLoadSample={vi.fn()}
        showSample={false}
      />,
    );

    expect(
      screen.queryByRole("button", { name: "Load sample SRT" }),
    ).toBeNull();
  });

  it("hides the live demo on signed-in home", () => {
    render(<LandingScreen signedIn onOpenApp={vi.fn()} />);

    expect(screen.queryByRole("navigation")).toBeNull();
    expect(screen.queryByRole("button", { name: "Live demo" })).toBeNull();
    expect(
      screen.getByRole("heading", { name: "Three steps. Zero friction." }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Current plan" })).toBeDisabled();
    expect(screen.queryByText("Arabic")).toBeNull();
    expect(screen.getByText("Chinese (Traditional)")).toBeInTheDocument();
  });

  it("waits for an explicit result click after fake processing", () => {
    vi.useFakeTimers();
    const complete = vi.fn();
    render(<DemoProcessing onComplete={complete} />);

    for (let step = 0; step < 3; step += 1)
      act(() => vi.advanceTimersByTime(550));
    expect(complete).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("button", { name: "View result in History →" }),
    );
    expect(complete).toHaveBeenCalledOnce();
  });
});

describe("source credit preview", () => {
  const cues = [
    {
      index: 1,
      start: "00:00:01,000",
      end: "00:01:00,001",
      text: "Hello",
    },
  ];

  it("matches backend whole-minute billing and formats the duration", () => {
    expect(sourceDurationMs(cues)).toBe(60_001);
    expect(sourceCreditMinutes(cues)).toBe(2);
    expect(formatDuration(sourceDurationMs(cues))).toBe("1:01");
  });

  it("bills source minutes once per target language (option A)", () => {
    expect(billedCreditMinutes(cues, 1)).toBe(2);
    expect(billedCreditMinutes(cues, 3)).toBe(6);
    // A job always has >= 1 target after dedup.
    expect(billedCreditMinutes(cues, 0)).toBe(2);
  });
});
