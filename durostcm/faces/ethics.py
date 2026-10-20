"""Guardián ético y legal de durosTCM.

Objetivo: que una productora pueda usar IA hiperrealista sin meterse en problemas.

* **Derecho a la propia imagen** (LO 1/1982 en España, RGPD art. 9 para datos
  biométricos, right of publicity en EE. UU.): recrear a una persona real identificable
  exige su consentimiento. durosTCM avisa cuando un prompt apunta a una persona real
  concreta y permite vincular una cesión de derechos firmada (registro de consentimientos).
* **Transparencia (Reglamento europeo de IA, art. 50)**: los contenidos "deepfake"
  deben etiquetarse. durosTCM añade metadatos "generado con IA", un manifiesto de
  procedencia y, opcionalmente, una marca visible.
* **Licencias**: sólo se aceptan rostros de inspiración con licencias que permitan
  uso comercial y obras derivadas; la atribución se guarda en los créditos.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

# Patrones que suelen indicar que se intenta replicar a una persona concreta.
_LIKENESS_PATTERNS = [
    r"\b(?:como|igual que|idéntic[oa] a|parecid[oa] a|clon de|doble de|que parezca)\s+(?:a\s+)?[A-ZÁÉÍÓÚÑ][\wáéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][\wáéíóúñ]+)+",
    r"\b(?:looks? like|lookalike of|as|resembling|exactly like|clone of|double of)\s+[A-Z][\w']+(?:\s+[A-Z][\w']+)+",
    r"\b(?:deepfake|face ?swap|cara de|rostro de)\s+(?:de\s+)?[A-ZÁÉÍÓÚÑ][\wáéíóúñ]+",
]
_SENSITIVE = [
    (r"\b(?:desnud[oa]s?|nude|naked|porn|sexual|erótic[oa])\b", "contenido sexual"),
    (r"\b(?:niñ[oa]s?|menor(?:es)? de edad|child|kid|minor)\b.*\b(?:desnud|sexual|nude|erótic)", "menores en contexto sexual"),
    (r"\b(?:presidente|presidenta|ministr[oa]|rey|reina|papa|candidat[oa])\s+[A-ZÁÉÍÓÚÑ][\wáéíóúñ]+", "figura pública/política real"),
]


class EthicsReport(BaseModel):
    ok: bool = True
    level: str = "ok"  # ok | warning | blocked
    issues: list[str] = Field(default_factory=list)
    advice: list[str] = Field(default_factory=list)
    requires_consent: bool = False


def check_prompt(text: str, consent_ids: list[str] | None = None) -> EthicsReport:
    rep = EthicsReport()
    if not text:
        return rep
    for pat in _LIKENESS_PATTERNS:
        m = re.search(pat, text)
        if m:
            rep.requires_consent = True
            rep.issues.append(f"Parece que se pide replicar a una persona real concreta: «{m.group(0)}».")
            break
    for pat, label in _SENSITIVE:
        if re.search(pat, text, re.I):
            if label == "menores en contexto sexual":
                rep.level = "blocked"
                rep.ok = False
                rep.issues.append("Contenido prohibido: menores en contexto sexual.")
                return rep
            rep.issues.append(f"Tema sensible detectado: {label}.")
    if rep.requires_consent and not consent_ids:
        rep.level = "warning"
        rep.advice.append(
            "Para recrear a una persona real necesitas su cesión de derechos de imagen. Regístrala en "
            "Biblioteca → Consentimientos y vincúlala al personaje, o crea una persona nueva inspirada en rasgos generales."
        )
    elif rep.issues:
        rep.level = "warning"
        rep.advice.append("Revisa el uso previsto y etiqueta el contenido como generado con IA al publicarlo.")
    return rep


def face_usage_notice() -> str:
    return (
        "Las licencias CC0/CC BY/Pexels/Unsplash cubren la fotografía, no el derecho a la propia imagen de la persona. "
        "durosTCM usa estos rostros como inspiración de rasgos generales (o mezclando varias referencias) para crear "
        "personas nuevas; no los uses para reproducir la identidad de alguien sin su consentimiento."
    )
