import initSqlJs, { Database } from "sql.js";
import { readFileSync, writeFileSync, existsSync, mkdirSync } from "fs";
import { dirname, join } from "path";

const PROJECT_ROOT = "/root/nestquant";
const DB_PATH = join(PROJECT_ROOT, "data", "dashboard.db");
const WASM_PATH = join(PROJECT_ROOT, "dashboard", "node_modules", "sql.js", "dist", "sql-wasm.wasm");

let db: Database | null = null;

async function getDb(): Promise<Database> {
  if (db) return db;

  const wasmBuffer = readFileSync(WASM_PATH).buffer;
  const SQL = await initSqlJs({ wasmBinary: wasmBuffer });

  if (existsSync(DB_PATH)) {
    const buf = readFileSync(DB_PATH);
    db = new SQL.Database(buf);
  } else {
    db = new SQL.Database();
  }

  db!.run(`
    CREATE TABLE IF NOT EXISTS users (
      username TEXT PRIMARY KEY,
      role TEXT NOT NULL,
      password_hash TEXT NOT NULL,
      created_at TEXT NOT NULL
    );
  `);

  db!.run(`
    CREATE TABLE IF NOT EXISTS config (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
  `);

  db!.run(`
    CREATE TABLE IF NOT EXISTS sessions (
      token TEXT PRIMARY KEY,
      username TEXT NOT NULL,
      role TEXT NOT NULL,
      created_at TEXT NOT NULL,
      expires_at TEXT NOT NULL
    );
  `);

  saveDb();
  return db!;
}

function saveDb() {
  if (!db) return;
  const dir = dirname(DB_PATH);
  if (!existsSync(dir)) {
    mkdirSync(dir, { recursive: true });
  }
  const data = db.export();
  writeFileSync(DB_PATH, Buffer.from(data));
}

export interface UserRow {
  username: string;
  role: "admin" | "user";
  password_hash: string;
  created_at: string;
}

export async function getUser(username: string): Promise<UserRow | null> {
  const database = await getDb();
  const stmt = database.prepare(
    "SELECT username, role, password_hash, created_at FROM users WHERE username = ?"
  );
  stmt.bind([username]);
  if (stmt.step()) {
    const row = stmt.getAsObject() as unknown as UserRow;
    stmt.free();
    return row;
  }
  stmt.free();
  return null;
}

export async function listUsers(): Promise<UserRow[]> {
  const database = await getDb();
  const results = database.exec(
    "SELECT username, role, password_hash, created_at FROM users ORDER BY created_at"
  );
  if (!results.length) return [];
  return results[0].values.map((row: unknown[]) => ({
    username: row[0] as string,
    role: row[1] as "admin" | "user",
    password_hash: row[2] as string,
    created_at: row[3] as string,
  }));
}

export async function createUser(
  username: string,
  role: "admin" | "user",
  passwordHash: string
): Promise<void> {
  const database = await getDb();
  const now = new Date().toISOString();
  database.run(
    "INSERT INTO users (username, role, password_hash, created_at) VALUES (?, ?, ?, ?)",
    [username, role, passwordHash, now]
  );
  saveDb();
}

export async function deleteUser(username: string): Promise<boolean> {
  const database = await getDb();
  database.run("DELETE FROM users WHERE username = ?", [username]);
  saveDb();
  return true;
}

export async function getConfigValue(key: string): Promise<string | null> {
  const database = await getDb();
  const stmt = database.prepare("SELECT value FROM config WHERE key = ?");
  stmt.bind([key]);
  if (stmt.step()) {
    const row = stmt.getAsObject();
    stmt.free();
    return row.value as string;
  }
  stmt.free();
  return null;
}

export async function setConfigValue(key: string, value: string): Promise<void> {
  const database = await getDb();
  const now = new Date().toISOString();
  database.run(
    "INSERT OR REPLACE INTO config (key, value, updated_at) VALUES (?, ?, ?)",
    [key, value, now]
  );
  saveDb();
}

export async function getAllConfig(): Promise<Record<string, string>> {
  const database = await getDb();
  const results = database.exec("SELECT key, value FROM config");
  if (!results.length) return {};
  const out: Record<string, string> = {};
  for (const row of results[0].values) {
    out[row[0] as string] = row[1] as string;
  }
  return out;
}
