import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { QuotaBar } from "./components.tsx";

describe("QuotaBar", () => {
  it("shows the percentage of free credits remaining", () => {
    render(<QuotaBar used={10} limit={40} />);

    expect(screen.getByText("Free · 30/40 min")).toBeInTheDocument();
    expect(screen.getByText("75%")).toBeInTheDocument();
    expect(
      screen.getByRole("progressbar", {
        name: "Monthly free credits remaining",
      }),
    ).toHaveAttribute("aria-valuenow", "30");
    expect(screen.getByRole("progressbar").firstElementChild).toHaveStyle({
      width: "75%",
    });
  });
});
