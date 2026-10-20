"""Búsqueda de rostros de inspiración con licencias de uso libre.

Proveedores:
* **Openverse** (WordPress/Creative Commons): sin clave; filtra por licencia (CC0, PDM, BY, BY-SA…).
* **Wikimedia Commons**: sin clave; licencias leídas de los metadatos de cada archivo.
* **Pexels** y **Unsplash**: con clave gratuita; licencias propias que permiten uso comercial.

Importante: estas licencias cubren los derechos de autor de la FOTO, no el derecho a la
propia imagen de la persona retratada. durosTCM usa estos rostros sólo como
*inspiración* (rasgos generales, mezcla de varias referencias) para crear personas
NUEVAS, y guarda la atribución en los créditos del proyecto.
"""

from __future__ import annotations

import asyncio
import html
import re
from typing import Any

import httpx
from pydantic import BaseModel

from .. import APP_NAME, __version__
from ..config import get_config

UA = f"{APP_NAME}/{__version__} (local video studio; contact: local-user)"


class FaceResult(BaseModel):
    id: str
    provider: str
    title: str = ""
    thumb_url: str
    url: str
    landing_url: str = ""
    creator: str = ""
    license: str = ""  # cc0, pdm, by, by-sa, by-nc, pexels, unsplash...
    license_version: str = ""
    license_url: str = ""
    attribution: str = ""
    width: int | None = None
    height: int | None = None
    commercial_ok: bool = False
    modification_ok: bool = False
    requires_attribution: bool = True


LICENSES = {
    "cc0": {"label": "CC0 (dominio público)", "commercial": True, "modify": True, "attribution": False},
    "pdm": {"label": "Marca de dominio público", "commercial": True, "modify": True, "attribution": False},
    "by": {"label": "CC BY (atribución)", "commercial": True, "modify": True, "attribution": True},
    "by-sa": {"label": "CC BY-SA (atribución, compartir igual)", "commercial": True, "modify": True, "attribution": True},
    "by-nd": {"label": "CC BY-ND (sin derivadas)", "commercial": True, "modify": False, "attribution": True},
    "by-nc": {"label": "CC BY-NC (no comercial)", "commercial": False, "modify": True, "attribution": True},
    "by-nc-sa": {"label": "CC BY-NC-SA", "commercial": False, "modify": True, "attribution": True},
    "by-nc-nd": {"label": "CC BY-NC-ND", "commercial": False, "modify": False, "attribution": True},
    "pexels": {"label": "Licencia Pexels", "commercial": True, "modify": True, "attribution": False},
    "unsplash": {"label": "Licencia Unsplash", "commercial": True, "modify": True, "attribution": False},
}


def _apply_license(r: FaceResult) -> FaceResult:
    info = LICENSES.get(r.license, {"commercial": False, "modify": False, "attribution": True})
    r.commercial_ok = info["commercial"]
    r.modification_ok = info["modify"]
    r.requires_attribution = info["attribution"]
    if not r.attribution:
        lic = LICENSES.get(r.license, {}).get("label", r.license.upper())
        r.attribution = f"«{r.title or 'Imagen'}» por {r.creator or 'autor desconocido'} — {lic}" + (f" ({r.license_url})" if r.license_url else "")
    return r


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=20, headers={"User-Agent": UA}, follow_redirects=True)


async def search_openverse(q: str, licenses: list[str], page: int = 1, per_page: int = 24) -> list[FaceResult]:
    ov_lic = [x for x in licenses if x in ("cc0", "pdm", "by", "by-sa", "by-nd", "by-nc", "by-nc-sa", "by-nc-nd")]
    params: dict[str, Any] = {"q": q, "page": page, "page_size": per_page, "category": "photograph", "mature": "false"}
    if ov_lic:
        params["license"] = ",".join(ov_lic)
    async with _client() as c:
        r = await c.get("https://api.openverse.org/v1/images/", params=params)
        r.raise_for_status()
        data = r.json()
    out = []
    for it in data.get("results", []):
        out.append(_apply_license(FaceResult(
            id=f"openverse:{it.get('id')}", provider="openverse", title=it.get("title") or "", thumb_url=it.get("thumbnail") or it.get("url"),
            url=it.get("url"), landing_url=it.get("foreign_landing_url") or "", creator=it.get("creator") or "",
            license=(it.get("license") or "").lower(), license_version=it.get("license_version") or "", license_url=it.get("license_url") or "",
            attribution=it.get("attribution") or "", width=it.get("width"), height=it.get("height"),
        )))
    return out


_WM_LIC = [
    (re.compile(r"^cc0|public domain dedication", re.I), "cc0"),
    (re.compile(r"^pd|public domain", re.I), "pdm"),
    (re.compile(r"cc[- ]by[- ]sa", re.I), "by-sa"),
    (re.compile(r"cc[- ]by[- ]nc[- ]sa", re.I), "by-nc-sa"),
    (re.compile(r"cc[- ]by[- ]nc", re.I), "by-nc"),
    (re.compile(r"cc[- ]by[- ]nd", re.I), "by-nd"),
    (re.compile(r"cc[- ]by", re.I), "by"),
]


def _strip_html(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


async def search_wikimedia(q: str, licenses: list[str], page: int = 1, per_page: int = 24) -> list[FaceResult]:
    params = {
        "action": "query", "format": "json", "generator": "search", "gsrsearch": f"{q} filetype:bitmap", "gsrnamespace": 6,
        "gsrlimit": per_page, "gsroffset": (page - 1) * per_page, "prop": "imageinfo", "iiprop": "url|extmetadata|size",
        "iiurlwidth": 400,
    }
    async with _client() as c:
        r = await c.get("https://commons.wikimedia.org/w/api.php", params=params)
        r.raise_for_status()
        data = r.json()
    out = []
    for page_ in (data.get("query", {}).get("pages", {}) or {}).values():
        ii = (page_.get("imageinfo") or [{}])[0]
        md = ii.get("extmetadata", {})
        short = (md.get("LicenseShortName", {}) or {}).get("value", "")
        lic = next((code for rx, code in _WM_LIC if rx.search(short)), "")
        if not lic or (licenses and lic not in licenses):
            continue
        out.append(_apply_license(FaceResult(
            id=f"wikimedia:{page_.get('pageid')}", provider="wikimedia", title=page_.get("title", "").replace("File:", ""),
            thumb_url=ii.get("thumburl") or ii.get("url"), url=ii.get("url"), landing_url=ii.get("descriptionurl", ""),
            creator=_strip_html((md.get("Artist", {}) or {}).get("value", "")), license=lic,
            license_url=(md.get("LicenseUrl", {}) or {}).get("value", ""), width=ii.get("width"), height=ii.get("height"),
        )))
    return out


async def search_pexels(q: str, page: int = 1, per_page: int = 24) -> list[FaceResult]:
    key = get_config().settings.api_keys.pexels
    if not key:
        return []
    async with _client() as c:
        r = await c.get("https://api.pexels.com/v1/search", params={"query": q, "page": page, "per_page": per_page}, headers={"Authorization": key})
        r.raise_for_status()
        data = r.json()
    return [_apply_license(FaceResult(
        id=f"pexels:{p['id']}", provider="pexels", title=p.get("alt") or "", thumb_url=p["src"]["medium"], url=p["src"]["original"],
        landing_url=p.get("url", ""), creator=p.get("photographer", ""), license="pexels", license_url="https://www.pexels.com/license/",
        width=p.get("width"), height=p.get("height"),
    )) for p in data.get("photos", [])]


async def search_unsplash(q: str, page: int = 1, per_page: int = 24) -> list[FaceResult]:
    key = get_config().settings.api_keys.unsplash
    if not key:
        return []
    async with _client() as c:
        r = await c.get("https://api.unsplash.com/search/photos", params={"query": q, "page": page, "per_page": per_page}, headers={"Authorization": f"Client-ID {key}"})
        r.raise_for_status()
        data = r.json()
    return [_apply_license(FaceResult(
        id=f"unsplash:{p['id']}", provider="unsplash", title=p.get("alt_description") or "", thumb_url=p["urls"]["small"], url=p["urls"]["full"],
        landing_url=p.get("links", {}).get("html", ""), creator=(p.get("user") or {}).get("name", ""), license="unsplash",
        license_url="https://unsplash.com/license", width=p.get("width"), height=p.get("height"),
    )) for p in data.get("results", [])]


async def search_faces(q: str, providers: list[str] | None = None, licenses: list[str] | None = None, page: int = 1) -> dict:
    """Busca en paralelo en todos los proveedores y devuelve resultados + errores por proveedor."""
    allowed = licenses or get_config().settings.ethics.allowed_face_licenses
    providers = providers or ["openverse", "wikimedia", "pexels", "unsplash"]
    query = q if any(w in q.lower() for w in ("portrait", "retrato", "face", "rostro")) else f"{q} portrait"
    tasks = {}
    if "openverse" in providers:
        tasks["openverse"] = search_openverse(query, allowed, page)
    if "wikimedia" in providers:
        tasks["wikimedia"] = search_wikimedia(query, allowed, page)
    if "pexels" in providers and get_config().settings.api_keys.pexels:
        tasks["pexels"] = search_pexels(query, page)
    if "unsplash" in providers and get_config().settings.api_keys.unsplash:
        tasks["unsplash"] = search_unsplash(query, page)
    results: list[FaceResult] = []
    errors: dict[str, str] = {}
    done = await asyncio.gather(*tasks.values(), return_exceptions=True)
    for name, res in zip(tasks, done):
        if isinstance(res, Exception):
            errors[name] = f"{type(res).__name__}: {str(res)[:200]}"
        else:
            results.extend(res)
    # intercalar proveedores para variedad
    by: dict[str, list[FaceResult]] = {}
    for r in results:
        by.setdefault(r.provider, []).append(r)
    mixed: list[FaceResult] = []
    while any(by.values()):
        for k in list(by):
            if by[k]:
                mixed.append(by[k].pop(0))
    return {"results": [m.model_dump() for m in mixed], "errors": errors, "licenses": allowed}


async def download(url: str) -> bytes:
    async with _client() as c:
        r = await c.get(url)
        r.raise_for_status()
        if len(r.content) > 40 * 1024 * 1024:
            raise ValueError("Imagen demasiado grande")
        return r.content
