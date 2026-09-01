import { NextRequest, NextResponse } from "next/server";
import { withAdmin } from "@/lib/rbac";
import { getAllConfig, setConfigValue } from "@/lib/db";

export const GET = withAdmin(async (req: NextRequest) => {
  const config = await getAllConfig();
  return NextResponse.json({ config });
});

export const PUT = withAdmin(async (req: NextRequest) => {
  try {
    const body = await req.json();
    const { key, value } = body;
    if (!key || value === undefined) {
      return NextResponse.json({ error: "missing key or value" }, { status: 400 });
    }
    await setConfigValue(key, String(value));
    return NextResponse.json({ ok: true });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "unknown error";
    return NextResponse.json({ error: msg }, { status: 500 });
  }
});
