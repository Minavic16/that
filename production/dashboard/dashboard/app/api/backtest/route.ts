import { NextRequest, NextResponse } from "next/server";
import { withAuth } from "@/lib/rbac";
import { readFileSync, existsSync } from "fs";
import { join } from "path";

const RESULTS_DIR = "/root/nestquant/research_data";

export const GET = withAuth(async (req: NextRequest) => {
  try {
    const url = new URL(req.url);
    const experiment = url.searchParams.get("experiment") || "s6c";

    if (experiment === "s6c") {
      const resultsFile = join(RESULTS_DIR, "s6c", "S6C_causal_swing_results.json");
      if (!existsSync(resultsFile)) {
        return NextResponse.json({ error: "S6C results not found" }, { status: 404 });
      }
      const data = JSON.parse(readFileSync(resultsFile, "utf8"));
      return NextResponse.json({ experiment: "S6C-2026-001", data });
    }

    if (experiment === "all") {
      const experiments: Record<string, unknown> = {};
      const files = [
        { name: "S6C", path: join(RESULTS_DIR, "s6c", "S6C_causal_swing_results.json") },
        { name: "S6_adaptive", path: join(RESULTS_DIR, "simple_strategies", "S6_adaptive_risk_challenge.json") },
        { name: "S5_financial", path: join(RESULTS_DIR, "simple_strategies", "S5_financial_planning.json") },
        { name: "phase4_zscore", path: join(RESULTS_DIR, "phase4", "zscore_mr_backtest.json") },
        { name: "phase12_regime", path: join(RESULTS_DIR, "phase12", "phase12_results.json") },
      ];

      for (const f of files) {
        if (existsSync(f.path)) {
          try {
            experiments[f.name] = JSON.parse(readFileSync(/*turbopackIgnore: true*/ f.path, "utf8"));
          } catch {
            experiments[f.name] = { error: "parse failed" };
          }
        }
      }

      return NextResponse.json({ experiments });
    }

    return NextResponse.json({ error: "unknown experiment" }, { status: 400 });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "unknown error";
    return NextResponse.json({ error: msg }, { status: 500 });
  }
});
