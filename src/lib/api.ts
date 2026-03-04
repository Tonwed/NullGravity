/**
 * apiFetch — CORS-safe fetch wrapper for NullGravity.
 *
 * 不 import @tauri-apps/plugin-http npm 包——Tauri 会通过 IIFE 自动把
 * plugin-http 注入到 window.__TAURI__.http.fetch，直接使用即可。
 * 这样完全避免了 npm 包被 Turbopack 静态打包进 chunk 的问题。
 *
 * - Tauri packaged:  window.__TAURI__.http.fetch（Rust 层，绕过 CORS）
 *                    端口由 window.__BACKEND_PORT__ 提供
 * - Dev server:      原生 browser fetch（CORS 已允许 localhost）
 *                    端口默认 8046
 */

declare global {
  interface Window {
    __TAURI__?: {
      http?: {
        fetch: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
      };
    };
    __TAURI_INTERNALS__?: unknown;
    __BACKEND_PORT__?: number;
  }
}

/** 获取后端端口（Tauri 注入 or 开发默认 8046） */
function getBackendPort(): number {
  if (typeof window !== "undefined" && window.__BACKEND_PORT__) {
    return window.__BACKEND_PORT__;
  }
  return 8046;
}

/** HTTP API 基础地址，例如 "http://127.0.0.1:51234/api" */
export function getApiBase(): string {
  return `http://127.0.0.1:${getBackendPort()}/api`;
}

/** WebSocket 基础地址，例如 "ws://127.0.0.1:51234/api" */
export function getWsBase(): string {
  return `ws://127.0.0.1:${getBackendPort()}/api`;
}

export async function apiFetch(
  input: RequestInfo | URL,
  init?: RequestInit
): Promise<Response> {
  // 使用 Tauri 注入的全局 http.fetch（不经过 webview CORS 限制）
  if (
    typeof window !== "undefined" &&
    window.__TAURI__?.http?.fetch
  ) {
    return window.__TAURI__.http.fetch(input, init);
  }
  // 开发模式 fallback：原生 fetch
  return fetch(input, init);
}
