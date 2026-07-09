import { useState } from "react";

import type { ParseResponse } from "./api.ts";

interface Props {
  result: ParseResponse;
}

// Cues rendered two ways, toggled by a single control:
//   - table (index / start→end / text) — default, scannable
//   - raw JSON — exact wire view, for debugging / trust
export function CuesView({ result }: Props) {
  const [showJson, setShowJson] = useState(false);

  return (
    <section className="mt-6">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold">
          {result.count} cue{result.count === 1 ? "" : "s"}
        </h2>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={showJson}
            onChange={(e) => setShowJson(e.target.checked)}
          />
          raw JSON
        </label>
      </div>

      {showJson ? (
        <pre className="bg-slate-900 text-slate-100 rounded-lg p-4 overflow-auto text-xs">
          {JSON.stringify(result, null, 2)}
        </pre>
      ) : (
        <div className="overflow-auto rounded-lg border border-slate-200">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-100 text-slate-600">
              <tr>
                <th className="px-3 py-2 text-left w-16">#</th>
                <th className="px-3 py-2 text-left w-80">start → end</th>
                <th className="px-3 py-2 text-left">text</th>
              </tr>
            </thead>
            <tbody>
              {result.cues.map((cue) => (
                <tr
                  key={cue.index}
                  className="border-t border-slate-100 align-top"
                >
                  <td className="px-3 py-2 text-slate-500 tabular-nums">
                    {cue.index}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs">
                    <span className="text-slate-700">{cue.start}</span>
                    <span className="text-slate-400"> → </span>
                    <span className="text-slate-700">{cue.end}</span>
                  </td>
                  <td className="px-3 py-2 whitespace-pre-wrap">{cue.text}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
