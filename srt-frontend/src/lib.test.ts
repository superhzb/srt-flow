import { describe, expect, it, vi } from "vitest";

import { apiFetch, detectTargetLang, errMessage } from "./lib.ts";

describe("detectTargetLang", () => {
  it("returns the first supported non-English browser language", () => {
    expect(detectTargetLang(["fr-FR", "en-US"], "")).toBe("fr");
    expect(detectTargetLang(["ja"], "")).toBe("ja");
    expect(detectTargetLang(["de-DE"], "")).toBe("de");
  });

  it("distinguishes simplified vs traditional Chinese", () => {
    expect(detectTargetLang(["zh-CN"], "")).toBe("zh");
    expect(detectTargetLang(["zh"], "")).toBe("zh");
    expect(detectTargetLang(["zh-TW"], "")).toBe("zh-TW");
    expect(detectTargetLang(["zh-Hant-HK"], "")).toBe("zh-TW");
  });

  it("skips unsupported tags and keeps scanning", () => {
    expect(detectTargetLang(["hi-IN", "ko-KR"], "")).toBe("ko");
  });

  it("never targets English; uses region then timezone", () => {
    expect(detectTargetLang(["en-CA"], "")).toBe("fr");
    expect(detectTargetLang(["en-US"], "Asia/Tokyo")).toBe("ja");
    expect(detectTargetLang(["en-US"], "Europe/Berlin")).toBe("de");
  });

  it("falls back to fr when nothing resolves", () => {
    expect(detectTargetLang([], "")).toBe("fr");
    expect(detectTargetLang(["en-US"], "Pacific/Auckland")).toBe("fr");
    expect(detectTargetLang(["xx"], "")).toBe("fr");
  });
});

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
