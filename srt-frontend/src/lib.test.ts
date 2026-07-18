import { describe, expect, it, vi } from "vitest";

import { apiFetch, errMessage } from "./lib.ts";

describe("errMessage", () => {
  it("returns the message of an Error", () => {
    expect(errMessage(new Error("boom"), "fallback")).toBe("boom");
  });

  it("falls back for non-Error throwables", () => {
    expect(errMessage("string thrown", "fallback")).toBe("fallback");
    expect(errMessage(undefined, "fallback")).toBe("fallback");
    expect(errMessage({ code: 42 }, "fallback")).toBe("fallback");
  });
});

describe("apiFetch", () => {
  it("returns parsed JSON on a 2xx response", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(JSON.stringify({ ok: true }), { status: 200 }),
      );

    const body = await apiFetch<{ ok: boolean }>("/x");
    expect(body).toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledWith("/x", undefined);
    fetchMock.mockRestore();
  });

  it("throws an Error whose message includes the detail on non-2xx", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "nope" }), { status: 400 }),
    );

    await expect(apiFetch("/x")).rejects.toThrow("nope");
  });

  it("falls back when the body has no detail field", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("plain", { status: 500 }),
    );

    await expect(apiFetch("/x", {}, "boom")).rejects.toThrow(/boom \(500\)/);
  });
});
