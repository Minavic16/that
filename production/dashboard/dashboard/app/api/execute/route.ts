import { NextRequest, NextResponse } from "next/server";
import { withAdmin } from "@/lib/rbac";
import { exec } from "child_process";
import { promisify } from "util";
import { readFileSync, existsSync } from "fs";
import { join } from "path";

const execAsync = promisify(exec);

export const POST = withAdmin(async (req: NextRequest) => {
  try {
    const body = await req.json();
    const { action } = body;

    if (action === "start") {
      const pairs = (body.pairs as string[]) || [
        "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF", "USD/CAD",
        "AUD/USD", "NZD/USD", "EUR/GBP", "EUR/JPY", "EUR/CHF",
        "EUR/CAD", "EUR/AUD", "EUR/NZD", "GBP/JPY", "GBP/CHF",
        "GBP/CAD", "GBP/AUD", "GBP/NZD", "CHF/JPY", "CAD/JPY",
      ];

      const enableExec = body.enable_execution ? "1" : "0";
      const cmd = `cd /root/that && NESTQUANT_LIVE_MODE=${enableExec} MT5_API_URL=http://127.0.0.1:5001 /root/venv/bin/python scripts/run_live_executor.py --pairs ${pairs.length} --poll 5 --log-dir logs/shadow_live &`;
      await execAsync(cmd);

      return NextResponse.json({ ok: true, mode: enableExec === "1" ? "LIVE" : "SHADOW", pairs: pairs.length });
    }

    if (action === "stop") {
      await execAsync("touch /root/that/logs/shadow_live/kill_switch");
      return NextResponse.json({ ok: true, message: "Kill switch activated" });
    }

    if (action === "status") {
      const logDir = "/root/that/logs/shadow_live";
      const stateFile = join(logDir, "state.json");
      const killFile = join(logDir, "kill_switch");

      let state: Record<string, unknown> = {};
      if (existsSync(stateFile)) {
        state = JSON.parse(readFileSync(stateFile, "utf8"));
      }

      return NextResponse.json({
        kill_switch: existsSync(killFile),
        state,
      });
    }

    return NextResponse.json({ error: "unknown action" }, { status: 400 });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "unknown error";
    return NextResponse.json({ error: msg }, { status: 500 });
  }
});
