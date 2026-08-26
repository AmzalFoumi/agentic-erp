import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /**
   * Build a self-contained server bundle in `.next/standalone`.
   *
   * Added for the Aisle demo box (gate 26). Next traces exactly which files the
   * built site needs and copies them, plus a small `server.js`, into that folder
   * — so the Docker image can run the site without `node_modules` and without an
   * `npm install` on the machine that runs it. See `frontend/Dockerfile`.
   *
   * This affects `next build` only. `next dev` is unchanged.
   *
   * Documented at
   * `node_modules/next/dist/docs/01-app/03-api-reference/05-config/01-next-config-js/output.md`.
   */
  output: "standalone",
};

export default nextConfig;
