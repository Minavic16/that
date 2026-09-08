import { NextRequest, NextResponse } from "next/server";
import { withAdmin } from "@/lib/rbac";
import { listUsers, createUser, deleteUser, getUser } from "@/lib/db";
import { hashPassword } from "@/lib/auth";

export const GET = withAdmin(async (req: NextRequest) => {
  const users = await listUsers();
  const safe = users.map((u) => ({
    username: u.username,
    role: u.role,
    created_at: u.created_at,
  }));
  return NextResponse.json({ users: safe });
});

export const POST = withAdmin(async (req: NextRequest) => {
  try {
    const body = await req.json();
    const { username, password, role } = body;

    if (!username || !password) {
      return NextResponse.json({ error: "missing username or password" }, { status: 400 });
    }

    if (!["admin", "user"].includes(role)) {
      return NextResponse.json({ error: "role must be admin or user" }, { status: 400 });
    }

    const existing = await getUser(username);
    if (existing) {
      return NextResponse.json({ error: "user already exists" }, { status: 409 });
    }

    const hash = await hashPassword(password);
    await createUser(username, role, hash);

    return NextResponse.json({ ok: true, username, role });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "unknown error";
    return NextResponse.json({ error: msg }, { status: 500 });
  }
});

export const DELETE = withAdmin(async (req: NextRequest) => {
  try {
    const url = new URL(req.url);
    const username = url.searchParams.get("username");
    if (!username) {
      return NextResponse.json({ error: "missing username" }, { status: 400 });
    }

    if (username === "Mindavic" || username === "Noble prime") {
      return NextResponse.json({ error: "cannot delete protected admin" }, { status: 403 });
    }

    await deleteUser(username);
    return NextResponse.json({ ok: true });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "unknown error";
    return NextResponse.json({ error: msg }, { status: 500 });
  }
});
