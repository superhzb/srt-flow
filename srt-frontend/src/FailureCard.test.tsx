import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { FailureCard } from "./FailureCard.tsx";

describe("FailureCard", () => {
  it("renders friendly copy, not-charged line, and retry for a retryable kind", () => {
    render(
      <FailureCard
        name="episode-01.srt"
        errorKind="backend_unavailable"
        error="boom"
        showNotCharged
        onRetry={() => {}}
      />,
    );

    expect(
      screen.getByText("Translation service was temporarily unavailable"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("You weren't charged for this job."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Retry translation" }),
    ).toBeInTheDocument();
  });

  it("hides retry for a non-retryable kind", () => {
    render(
      <FailureCard
        name="episode-01.srt"
        errorKind="unsupported_language"
        showNotCharged
        onRetry={() => {}}
      />,
    );

    expect(
      screen.getByText("One of the languages isn't supported"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /retry/i })).toBeNull();
  });

  it("does not show a raw error_kind headline", () => {
    render(<FailureCard name="episode-01.srt" errorKind="worker_stream" />);
    expect(screen.queryByText("WORKER_STREAM")).toBeNull();
    // The kind still appears inside the collapsible technical details.
    expect(screen.getByText("Technical details")).toBeInTheDocument();
  });

  it("invokes onRetry on click", async () => {
    const onRetry = vi.fn().mockResolvedValue(undefined);
    render(
      <FailureCard name="e.srt" errorKind="worker_stream" onRetry={onRetry} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Retry translation" }));
    await waitFor(() => expect(onRetry).toHaveBeenCalledTimes(1));
  });
});
