#!/usr/bin/env node

const bcrypt = require("bcryptjs");
const path = require("path");
const fs = require("fs");

const DB_PATH = path.join(__dirname, "..", "data", "dashboard.db");

async function main() {
  const initSqlJs = (await import("sql.js")).default;
  const SQL = await initSqlJs();

  let db;
  if (fs.existsSync(DB_PATH)) {
    db = new SQL.Database(fs.readFileSync(DB_PATH));
  } else {
    db = new SQL.Database();
  }

  db.run(`
    CREATE TABLE IF NOT EXISTS users (
      username TEXT PRIMARY KEY,
      role TEXT NOT NULL CHECK (role IN ('admin', 'user')),
      password_hash TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
  `);

  db.run(`
    CREATE TABLE IF NOT EXISTS config (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL,
      updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
  `);

  db.run(`
    CREATE TABLE IF NOT EXISTS sessions (
      token TEXT PRIMARY KEY,
      username TEXT NOT NULL,
      role TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT (datetime('now')),
      expires_at TEXT NOT NULL
    );
  `);

  const admins = [
    {
      username: "Mindavic",
      password: process.env.ADMIN_MINDAVIC_PASSWORD,
    },
    {
      username: "Noble prime",
      password: process.env.ADMIN_NOBLE_PRIME_PASSWORD,
    },
  ];

  for (const admin of admins) {
    if (!admin.password) {
      throw new Error(
        `Missing password environment variable for ${admin.username}`
      );
    }
  }

  for (const admin of admins) {
    const existing = db.exec(
      "SELECT username FROM users WHERE username = ?",
      [admin.username]
    );
    if (existing.length && existing[0].values.length > 0) {
      console.log(`  [skip] ${admin.username} already exists`);
      continue;
    }
    const hash = await bcrypt.hash(admin.password, 12);
    db.run(
      "INSERT INTO users (username, role, password_hash) VALUES (?, 'admin', ?)",
      [admin.username, hash]
    );
    console.log(`  [created] ${admin.username} / ${admin.password} (admin)`);
  }

  db.run(
    "INSERT OR REPLACE INTO config (key, value) VALUES ('strategy_version', 'Variant B S6C-2026-001')"
  );
  db.run(
    "INSERT OR REPLACE INTO config (key, value) VALUES ('risk_per_trade', '0.003')"
  );
  db.run(
    "INSERT OR REPLACE INTO config (key, value) VALUES ('max_hold_bars', '42')"
  );
  console.log("  [seeded] default config values");

  const dir = path.dirname(DB_PATH);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  const data = db.export();
  fs.writeFileSync(DB_PATH, Buffer.from(data));
  console.log(`\n  DB written to ${DB_PATH}`);
  console.log("  Seed complete.");
}

main().catch((e) => {
  console.error("Seed failed:", e);
  process.exit(1);
});
