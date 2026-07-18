import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StackedOutput } from "./StackedOutput.tsx";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("history language visibility", () => {
  it("removes a hidden language from the review and downloaded SRT", async () => {
    const createObjectURL = vi
      .fn()
      .mockReturnValueOnce("blob:all-languages")
      .mockReturnValueOnce("blob:translated-only");
    class MockURL extends URL {
      static createObjectURL = createObjectURL;
      static revokeObjectURL = vi.fn();
    }
    vi.stubGlobal("URL", MockURL);
    const sidebar = document.createElement("aside");
    document.body.append(sidebar);

    render(
      <StackedOutput
        demoCues={{
          en: [
            {
              index: 1,
              start: "00:00:01,000",
              end: "00:00:02,000",
              text: "Original line",
            },
          ],
          fr: [
            {
              index: 1,
              start: "00:00:01,000",
              end: "00:00:02,000",
              text: "Translated line",
            },
          ],
        }}
        sourceLang="en"
        targetLangs={["fr"]}
        historyHeader={{ filename: "sample.srt", meta: "Complete" }}
        historySidebar={sidebar}
      />,
    );

    expect(await screen.findByText("Original line")).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", {
        name: "Hide English in review and download",
      }),
    );

    await waitFor(() => {
      expect(screen.queryByText("Original line")).toBeNull();
      expect(screen.getByText("Translated line")).toBeInTheDocument();
      expect(createObjectURL).toHaveBeenCalledTimes(2);
    });
    expect(
      screen.getByRole("button", {
        name: "Show English in review and download",
      }),
    ).toHaveAttribute("aria-pressed", "false");
    expect(
      screen.getByRole("link", { name: /Download \.srt/ }),
    ).toHaveAttribute("href", "blob:translated-only");

    sidebar.remove();
  });
});
