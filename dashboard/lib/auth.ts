import bcrypt from "bcryptjs";
import jwt from "jsonwebtoken";
import { cookies } from "next/headers";
import { getUser } from "./db";

const SECRET = process.env.DASHBOARD_SECRET || "";
const COOKIE_NAME = "__Host-session";
const SESSION_TTL_HOURS = 24;

export interface SessionPayload {
  username: string;
  role: "admin" | "user";
}

export function hashPassword(plain: string): Promise<string> {
  return bcrypt.hash(plain, 12);
}

export function verifyPassword(plain: string, hash: string): Promise<boolean> {
  return bcrypt.compare(plain, hash);
}

export function signToken(payload: SessionPayload): string {
  return jwt.sign(payload as unknown as Record<string, unknown>, SECRET, {
    expiresIn: `${SESSION_TTL_HOURS}h`,
    algorithm: "HS256",
  });
}

export function verifyToken(token: string): SessionPayload | null {
  try {
    const decoded = jwt.verify(token, SECRET, {
      algorithms: ["HS256"],
    }) as Record<string, unknown>;
    if (typeof decoded.username !== "string" || typeof decoded.role !== "string") return null;
    return { username: decoded.username, role: decoded.role as "admin" | "user" };
  } catch {
    return null;
  }
}

export async function setSessionCookie(payload: SessionPayload): Promise<string> {
  const token = signToken(payload);
  const store = await cookies();
  store.set(COOKIE_NAME, token, {
    httpOnly: true,
    secure: true,
    sameSite: "strict",
    path: "/",
    maxAge: SESSION_TTL_HOURS * 60 * 60,
  });
  return token;
}

export async function clearSessionCookie(): Promise<void> {
  const store = await cookies();
  store.set(COOKIE_NAME, "", {
    httpOnly: true,
    secure: true,
    sameSite: "strict",
    path: "/",
    maxAge: 0,
  });
}

export async function getSession(): Promise<SessionPayload | null> {
  const store = await cookies();
  const cookieVal = store.get(COOKIE_NAME)?.value;
  if (!cookieVal) return null;
  return verifyToken(cookieVal);
}

export async function requireAuth(): Promise<SessionPayload> {
  const session = await getSession();
  if (!session) throw new Error("UNAUTHORIZED");
  return session;
}

export async function requireAdmin(): Promise<SessionPayload> {
  const session = await requireAuth();
  if (session.role !== "admin") throw new Error("FORBIDDEN");
  return session;
}
