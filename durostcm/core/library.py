"""Biblioteca compartida entre proyectos: personajes, localizaciones, rostros de inspiración y consentimientos."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from ..config import get_config
from .project import Credit, new_id


class Voice(BaseModel):
    engine: str = ""  # kokoro, piper, system
    voice_id: str = ""
    description: str = ""
    speed: float = 1.0


class Consent(BaseModel):
    """Cesión de derechos de imagen de una persona real (actor/actriz, modelo, empleado)."""

    id: str = Field(default_factory=lambda: new_id("cs_"))
    person_name: str
    document: str = ""  # archivo del contrato/cesión dentro de library/consents
    scope: str = ""  # usos permitidos
    valid_until: str = ""  # fecha ISO o vacío = indefinido
    signed_on: str = ""
    notes: str = ""
    created: float = Field(default_factory=time.time)


class Character(BaseModel):
    id: str = Field(default_factory=lambda: new_id("ch_"))
    name: str = "Nuevo personaje"
    role: str = ""
    age: int | None = None
    gender: str = ""
    heritage: str = ""
    face: str = ""  # rasgos faciales (inglés, para prompts)
    skin: str = ""
    hair: str = ""
    eyes: str = ""
    build: str = ""
    wardrobe: str = ""
    signature: str = ""  # elemento distintivo (prop, accesorio)
    personality: str = ""
    mannerisms: str = ""
    backstory: str = ""
    voice: Voice = Field(default_factory=Voice)
    identity_prompt: str = ""
    negative: str = ""
    seed: int | None = None
    reference_images: list[str] = Field(default_factory=list)  # rutas relativas a la carpeta del personaje
    hero_image: str | None = None
    lora: str | None = None
    inspiration: list[Credit] = Field(default_factory=list)
    consent_id: str | None = None
    is_real_person: bool = False
    tags: list[str] = Field(default_factory=list)
    created: float = Field(default_factory=time.time)
    updated: float = Field(default_factory=time.time)


class Location(BaseModel):
    id: str = Field(default_factory=lambda: new_id("lo_"))
    name: str = "Nueva localización"
    description: str = ""
    era: str = ""
    time_of_day: str = ""
    weather: str = ""
    lighting: str = ""
    palette: str = ""
    props: str = ""
    ambience: str = ""
    identity_prompt: str = ""
    seed: int | None = None
    reference_images: list[str] = Field(default_factory=list)
    hero_image: str | None = None
    tags: list[str] = Field(default_factory=list)
    created: float = Field(default_factory=time.time)
    updated: float = Field(default_factory=time.time)


class FaceRef(BaseModel):
    """Rostro de inspiración con licencia libre (o propio / con consentimiento)."""

    id: str = Field(default_factory=lambda: new_id("fc_"))
    file: str  # nombre de archivo dentro de library/faces
    thumb: str | None = None
    credit: Credit = Field(default_factory=Credit)
    description: str = ""  # descripción de rasgos (generada por visión o manual)
    tags: list[str] = Field(default_factory=list)
    consent_id: str | None = None
    created: float = Field(default_factory=time.time)


Kind = Literal["characters", "locations"]


class Library:
    def __init__(self) -> None:
        self.root = get_config().library_dir

    # ------------------------------------------------------------ personajes / localizaciones
    def _dir(self, kind: Kind, item_id: str) -> Path:
        safe = "".join(ch for ch in item_id if ch.isalnum() or ch in "_-")
        if safe != item_id or not safe:
            raise KeyError(item_id)
        d = self.root / kind / safe
        return d

    def list(self, kind: Kind) -> list[dict]:
        out = []
        base = self.root / kind
        for d in sorted(base.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True) if base.exists() else []:
            f = d / "item.json"
            if f.exists():
                try:
                    out.append(json.loads(f.read_text("utf-8")))
                except Exception:
                    continue
        return out

    def get(self, kind: Kind, item_id: str) -> Character | Location:
        f = self._dir(kind, item_id) / "item.json"
        if not f.exists():
            raise KeyError(item_id)
        model = Character if kind == "characters" else Location
        return model.model_validate_json(f.read_text("utf-8"))

    def save(self, kind: Kind, item: Character | Location) -> Character | Location:
        d = self._dir(kind, item.id)
        d.mkdir(parents=True, exist_ok=True)
        item.updated = time.time()
        tmp = d / "item.json.tmp"
        tmp.write_text(item.model_dump_json(indent=1), "utf-8")
        tmp.replace(d / "item.json")
        return item

    def delete(self, kind: Kind, item_id: str) -> None:
        d = self._dir(kind, item_id)
        if d.exists():
            shutil.rmtree(d)

    def add_image(self, kind: Kind, item_id: str, src: Path, as_hero: bool = False) -> str:
        item = self.get(kind, item_id)
        d = self._dir(kind, item_id)
        name = f"ref_{int(time.time() * 1000)}{src.suffix.lower() or '.png'}"
        shutil.copy2(src, d / name)
        item.reference_images.append(name)
        if as_hero or not item.hero_image:
            item.hero_image = name
        self.save(kind, item)
        return name

    def file(self, kind: Kind, item_id: str, name: str) -> Path:
        d = self._dir(kind, item_id).resolve()
        p = (d / name).resolve()
        if d not in p.parents:
            raise PermissionError(name)
        return p

    # ------------------------------------------------------------ rostros
    @property
    def faces_dir(self) -> Path:
        return self.root / "faces"

    def faces(self) -> list[FaceRef]:
        f = self.faces_dir / "index.json"
        if not f.exists():
            return []
        try:
            return [FaceRef.model_validate(x) for x in json.loads(f.read_text("utf-8"))]
        except Exception:
            return []

    def save_faces(self, faces: list[FaceRef]) -> None:
        f = self.faces_dir / "index.json"
        f.write_text(json.dumps([x.model_dump() for x in faces], ensure_ascii=False, indent=1), "utf-8")

    def add_face(self, face: FaceRef) -> FaceRef:
        faces = [x for x in self.faces() if x.id != face.id]
        faces.insert(0, face)
        self.save_faces(faces)
        return face

    def delete_face(self, face_id: str) -> None:
        faces = self.faces()
        keep = []
        for x in faces:
            if x.id == face_id:
                for n in (x.file, x.thumb):
                    if n:
                        (self.faces_dir / n).unlink(missing_ok=True)
            else:
                keep.append(x)
        self.save_faces(keep)

    # ------------------------------------------------------------ consentimientos
    @property
    def consents_dir(self) -> Path:
        return self.root / "consents"

    def consents(self) -> list[Consent]:
        f = self.consents_dir / "index.json"
        if not f.exists():
            return []
        try:
            return [Consent.model_validate(x) for x in json.loads(f.read_text("utf-8"))]
        except Exception:
            return []

    def save_consent(self, c: Consent) -> Consent:
        items = [x for x in self.consents() if x.id != c.id]
        items.insert(0, c)
        (self.consents_dir / "index.json").write_text(json.dumps([x.model_dump() for x in items], ensure_ascii=False, indent=1), "utf-8")
        return c

    def delete_consent(self, cid: str) -> None:
        items = [x for x in self.consents() if x.id != cid]
        (self.consents_dir / "index.json").write_text(json.dumps([x.model_dump() for x in items], ensure_ascii=False, indent=1), "utf-8")


def get_library() -> Library:
    return Library()
