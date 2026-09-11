declare module "jsonwebtoken" {
  export function sign(
    payload: string | Buffer | Record<string, unknown>,
    secretOrPrivateKey: string | Buffer,
    options?: { expiresIn?: string | number; algorithm?: string; [key: string]: unknown }
  ): string;
  export function verify(
    token: string,
    secretOrPublicKey: string | Buffer,
    options?: { algorithms?: string[]; [key: string]: unknown }
  ): Record<string, unknown>;
}
