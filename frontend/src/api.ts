import type { Project } from "./types";

const TOKEN_KEY = "durostcm.token";

function token(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export class ApiError extends Error {
  status: number;
  data: any;
  constructor(status: number, message: string, data: any) {
    super(message);
    this.status = status;
    this.data = data;
  }
}

async function request<T>(method: string, url: string, body?: unknown, isForm = false): Promise<T> {
  const headers: Record<string, string> = {};
  const t = token();
  if (t) headers["x-durostcm-token"] = t;
  let payload: BodyInit | undefined;
  if (body !== undefined) {
    if (isForm) payload = body as FormData;
    else {
      headers["content-type"] = "application/json";
      payload = JSON.stringify(body);
    }
  }
  const res = await fetch(url, { method, headers, body: payload });
  const ct = res.headers.get("content-type") || "";
  const data = ct.includes("json") ? await res.json() : await res.text();
  if (!res.ok) {
    const msg = typeof data === "object" && data && "detail" in data ? String((data as any).detail) : String(data).slice(0, 300);
    throw new ApiError(res.status, msg, data);
  }
  return data as T;
}

export const api = {
  get: <T = any>(url: string) => request<T>("GET", url),
  post: <T = any>(url: string, body?: unknown) => request<T>("POST", url, body ?? {}),
  put: <T = any>(url: string, body?: unknown) => request<T>("PUT", url, body ?? {}),
  patch: <T = any>(url: string, body?: unknown) => request<T>("PATCH", url, body ?? {}),
  del: <T = any>(url: string) => request<T>("DELETE", url),
  form: <T = any>(url: string, form: FormData) => request<T>("POST", url, form, true),
};

export function withToken(url: string): string {
  const t = token();
  if (!t) return url;
  return url + (url.includes("?") ? "&" : "?") + "token=" + encodeURIComponent(t);
}

let h264: boolean | null = null;
let aac: boolean | null = null;

/** Navegadores sin H.264/AAC (p. ej. Chromium sin códecs propietarios) reciben proxies WebM. */
function needsWebm(kind: "video" | "audio"): boolean {
  if (h264 === null) {
    const v = document.createElement("video");
    h264 = v.canPlayType('video/mp4; codecs="avc1.42E01E, mp4a.40.2"') !== "";
    aac = v.canPlayType('audio/mp4; codecs="mp4a.40.2"') !== "";
  }
  return kind === "video" ? !h264 : !aac;
}

export const urls = {
  file: (pid: string, rel: string | null | undefined) => (rel ? withToken(`/api/projects/${pid}/files/${rel.split("/").map(encodeURIComponent).join("/")}`) : ""),
  media: (pid: string, mid: string, proxy = true, kind: "video" | "audio" | "image" = "image") =>
    withToken(`/api/projects/${pid}/media/${mid}/file?proxy=${proxy}${kind !== "image" && needsWebm(kind) ? "&webm=true" : ""}`),
  frame: (pid: string, t: number, h = 540) => withToken(`/api/projects/${pid}/frame?t=${t.toFixed(3)}&h=${h}`),
  libImage: (kind: "characters" | "locations", id: string, name: string) => withToken(`/api/library/${kind}/${id}/images/${encodeURIComponent(name)}`),
  face: (id: string, thumb = true) => withToken(`/api/faces/${id}/image?thumb=${thumb}`),
  export: (pid: string, fmt: string) => withToken(`/api/projects/${pid}/export/${fmt}`),
};

export async function saveProject(p: Project): Promise<{ ok: boolean; rev: number; updated: number }> {
  return api.put(`/api/projects/${p.id}`, p);
}

export function wsUrl(): string {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return withToken(`${proto}://${location.host}/api/ws`);
}
