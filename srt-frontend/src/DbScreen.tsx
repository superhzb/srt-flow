import { useEffect, useState } from "react";

import {
  clearAllData,
  getTableRows,
  listTables,
  type TableInfo,
  type TablePage,
} from "./api.ts";

const PAGE_SIZE = 20;

export function DbScreen() {
  const [tables, setTables] = useState<TableInfo[] | null>(null);
  const [pages, setPages] = useState<Record<string, TablePage>>({});
  const [pageByTable, setPageByTable] = useState<Record<string, number>>({});
  const [error, setError] = useState<string | null>(null);
  const [clearing, setClearing] = useState(false);

  function loadTables() {
    setError(null);
    listTables()
      .then((nextTables) => {
        setTables(nextTables);
        nextTables.forEach((table) => {
          const page = pageByTable[table.name] ?? 0;
          void loadPage(table.name, page);
        });
      })
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : "failed to load tables");
      });
  }

  function loadPage(name: string, page: number) {
    setError(null);
    getTableRows(name, page, PAGE_SIZE)
      .then((body) => {
        setPages((prev) => ({ ...prev, [name]: body }));
        setPageByTable((prev) => ({ ...prev, [name]: page }));
      })
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : "failed to load table rows");
      });
  }

  async function handleClear() {
    if (!window.confirm("Clear all database rows and re-seed the dev user?")) return;
    setClearing(true);
    setError(null);
    try {
      await clearAllData();
      setPageByTable({});
      setPages({});
      loadTables();
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to clear data");
    } finally {
      setClearing(false);
    }
  }

  useEffect(() => {
    loadTables();
  }, []);

  return (
    <section className="mt-6 space-y-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Database</h2>
          <p className="text-sm text-slate-600">Raw rows for development.</p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={loadTables}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-slate-50"
          >
            Refresh
          </button>
          <button
            type="button"
            onClick={handleClear}
            disabled={clearing}
            className="rounded-md border border-red-300 bg-white px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {clearing ? "Clearing..." : "Clear all data"}
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          {error}
        </div>
      )}

      {tables === null && !error && (
        <p className="text-sm text-slate-600">Loading...</p>
      )}

      {tables?.map((table) => (
        <TableSection
          key={table.name}
          table={table}
          page={pages[table.name]}
          onPage={(page) => loadPage(table.name, page)}
        />
      ))}
    </section>
  );
}

function TableSection({
  table,
  page,
  onPage,
}: {
  table: TableInfo;
  page: TablePage | undefined;
  onPage: (page: number) => void;
}) {
  const currentPage = page?.page ?? 0;
  const total = page?.total ?? table.count;
  const canPrev = currentPage > 0;
  const canNext = page ? (currentPage + 1) * page.size < page.total : false;

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="font-semibold">
            <span className="font-mono">{table.name}</span>
          </h3>
          <p className="text-sm text-slate-600">{total} rows</p>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <button
            type="button"
            onClick={() => onPage(currentPage - 1)}
            disabled={!canPrev}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 font-medium hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Prev
          </button>
          <span className="min-w-28 text-center text-slate-600">
            page {currentPage + 1} / {Math.max(1, Math.ceil(total / PAGE_SIZE))}
          </span>
          <button
            type="button"
            onClick={() => onPage(currentPage + 1)}
            disabled={!canNext}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 font-medium hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Next
          </button>
        </div>
      </div>

      {!page && <p className="text-sm text-slate-600">Loading...</p>}

      {page && page.rows.length === 0 && (
        <p className="text-sm text-slate-600">No rows.</p>
      )}

      {page && page.rows.length > 0 && (
        <div className="overflow-auto rounded-lg border border-slate-200">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-100 text-slate-600">
              <tr>
                {page.columns.map((column) => (
                  <th key={column} className="px-3 py-2 text-left">
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {page.rows.map((row, index) => (
                <tr key={String(row.id ?? index)} className="border-t border-slate-100">
                  {page.columns.map((column) => (
                    <td
                      key={column}
                      className="max-w-[32rem] truncate px-3 py-2 font-mono text-xs"
                      title={formatCell(row[column])}
                    >
                      {formatCell(row[column])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
