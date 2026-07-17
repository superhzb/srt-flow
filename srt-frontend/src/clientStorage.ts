import type { Cue } from "./api.ts";
import type { FileEntry } from "./ConfigureScreen.tsx";

const DB_NAME = "srt-flow-client";
const DB_VERSION = 1;
const STORE = "records";
const PENDING_KEY = "pending-translation";
const DEMO_PREFIX = "demo:";
export const CLIENT_RECORD_TTL_MS = 30 * 60 * 1000;

export interface PendingTranslation {
  schemaVersion: 1;
  createdAt: number;
  entries: FileEntry[];
  worker: string;
  targets: string[];
}

export interface DemoHistoryEntry {
  schemaVersion: 1;
  id: string;
  createdAt: number;
  filename: string;
  sourceLang: string;
  targetLangs: string[];
  cuesByLanguage: Record<string, Cue[]>;
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(STORE))
        request.result.createObjectStore(STORE);
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function transaction<T>(
  mode: IDBTransactionMode,
  action: (store: IDBObjectStore) => IDBRequest<T>,
): Promise<T> {
  const db = await openDb();
  try {
    return await new Promise<T>((resolve, reject) => {
      const tx = db.transaction(STORE, mode);
      const request = action(tx.objectStore(STORE));
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
      tx.onerror = () => reject(tx.error);
    });
  } finally {
    db.close();
  }
}

const get = <T>(key: string) =>
  transaction("readonly", (store) => store.get(key)) as Promise<T | undefined>;
const put = (key: string, value: unknown) =>
  transaction("readwrite", (store) => store.put(value, key));
const remove = (key: string) =>
  transaction("readwrite", (store) => store.delete(key));

function fresh(createdAt: number): boolean {
  return Date.now() - createdAt <= CLIENT_RECORD_TTL_MS;
}

export async function savePendingTranslation(value: PendingTranslation) {
  await put(PENDING_KEY, value);
}

export async function takePendingTranslation(): Promise<PendingTranslation | null> {
  const value = await get<PendingTranslation>(PENDING_KEY);
  await remove(PENDING_KEY);
  return value?.schemaVersion === 1 && fresh(value.createdAt) ? value : null;
}

export async function clearPendingTranslation() {
  await remove(PENDING_KEY);
}

export async function saveDemoEntry(value: DemoHistoryEntry) {
  await put(`${DEMO_PREFIX}${value.id}`, value);
}

export async function listDemoEntries(): Promise<DemoHistoryEntry[]> {
  const db = await openDb();
  try {
    const entries = await new Promise<DemoHistoryEntry[]>((resolve, reject) => {
      const values: DemoHistoryEntry[] = [];
      const tx = db.transaction(STORE, "readwrite");
      const request = tx.objectStore(STORE).openCursor();
      request.onsuccess = () => {
        const cursor = request.result;
        if (!cursor) return;
        if (String(cursor.key).startsWith(DEMO_PREFIX)) {
          const value = cursor.value as DemoHistoryEntry;
          if (value.schemaVersion === 1 && fresh(value.createdAt))
            values.push(value);
          else cursor.delete();
        }
        cursor.continue();
      };
      tx.oncomplete = () =>
        resolve(values.sort((a, b) => b.createdAt - a.createdAt));
      tx.onerror = () => reject(tx.error);
    });
    return entries;
  } finally {
    db.close();
  }
}

export async function clearClientRecords() {
  await transaction("readwrite", (store) => store.clear());
}

// --- Analytics identity (localStorage, synchronous) -----------------------
//
// anon_id: stable per-browser id, sent before and after login so events can
// be joined anon→user at query time. session_id: rotates after 30 min of
// inactivity. Both are opaque UUIDs — no PII.

const ANON_KEY = "srt-flow-anon-id";
const SESSION_KEY = "srt-flow-session";
const SESSION_TTL_MS = 30 * 60 * 1000;

function uuid(): string {
  return crypto.randomUUID();
}

export function getAnonId(): string {
  let id = localStorage.getItem(ANON_KEY);
  if (!id) {
    id = uuid();
    localStorage.setItem(ANON_KEY, id);
  }
  return id;
}

export function getSessionId(): string {
  const now = Date.now();
  let id: string | null = null;
  let lastSeen = 0;
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as { id: string; lastSeen: number };
      id = parsed.id;
      lastSeen = parsed.lastSeen;
    }
  } catch {
    id = null;
  }
  if (!id || now - lastSeen > SESSION_TTL_MS) id = uuid();
  localStorage.setItem(SESSION_KEY, JSON.stringify({ id, lastSeen: now }));
  return id;
}
