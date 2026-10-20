"""Motor de imaginación de durosTCM.

Convierte ideas sueltas (en español o inglés) en prompts cinematográficos
fotorrealistas, diseña personajes y localizaciones con "biblia" de continuidad y
escribe storyboards completos (anuncios, cortometrajes, presentación de personaje).

Funciona en dos modos:
* **LLM local** (Ollama / LM Studio): un equipo de "personas" creativas (guionista,
  director, director de fotografía, diseñador de personajes) produce JSON estructurado.
* **Sin LLM**: un sistema combinatorio con vocabulario de cine, coherencia temática y
  un dial de imaginación que introduce giros visuales inesperados.
"""

from __future__ import annotations

import random
import re
from typing import Any

from ...core.library import Character, Location, Voice
from ...core.project import Camera, DialogueLine, Shot, Storyboard
from . import vocab as V

# ------------------------------------------------------------------ utilidades


def to_english_hints(text: str) -> str:
    """Añade equivalentes en inglés de los términos españoles detectados."""
    low = text.lower()
    hints = []
    for es in sorted(V.ES_EN, key=len, reverse=True):
        if re.search(rf"(?<!\w){re.escape(es)}(?!\w)", low):
            en = V.ES_EN[es]
            if en not in hints and en not in low:
                hints.append(en)
    return ", ".join(hints)


def _rng(seed: int | None) -> random.Random:
    return random.Random(seed if seed is not None else random.randint(0, 2**31))


def _pick(r: random.Random, items: list, k: int = 1):
    return r.sample(items, min(k, len(items))) if k > 1 else r.choice(items)


def _detect(text: str, table: dict[str, list[str]]) -> str | None:
    low = text.lower()
    for key, words in table.items():
        if any(w in low for w in words):
            return key
    return None


# ------------------------------------------------------------------ prompts


def enhance_prompt(
    idea: str,
    *,
    kind: str = "image",
    style: str = "cinematic",
    realism: float = 1.0,
    imagination: float = 0.5,
    seed: int | None = None,
    camera: Camera | None = None,
    lighting: str | None = None,
    look: str | None = None,
    extra: list[str] | None = None,
) -> dict[str, Any]:
    """Enriquece una idea en un prompt profesional. Devuelve prompt, negativo y desglose."""
    r = _rng(seed)
    idea = idea.strip().rstrip(".")
    hints = to_english_hints(idea)
    parts: list[str] = []
    breakdown: dict[str, str] = {}

    if camera is not None:
        shot = V.SHOT_SIZES.get(camera.shot_size, camera.shot_size.replace("_", " "))
        angle = V.ANGLES.get(camera.angle, camera.angle.replace("_", " "))
        parts.append(f"{shot}, {angle}")
        breakdown["plano"] = shot
    elif kind == "image":
        shot = r.choice(["cinematic still", "film still", "editorial photograph", "cinematic frame"])
        parts.append(shot)

    parts.append(idea + (f" ({hints})" if hints else ""))
    breakdown["sujeto"] = idea

    if imagination > 0.35:
        n = 1 if imagination < 0.7 else 2
        wonders = _pick(r, V.WONDER, n) if n > 1 else [_pick(r, V.WONDER)]
        parts.extend(wonders)
        breakdown["imaginación"] = "; ".join(wonders)
    if imagination > 0.15:
        env = _pick(r, V.ENVIRONMENT_DETAILS)
        parts.append(env)

    light_key = lighting or _detect(idea, {
        "neon": ["neon", "neón", "cyberpunk"], "golden_hour": ["atardecer", "sunset", "golden"], "moonlight": ["noche", "night", "luna"],
        "candle": ["vela", "candle"], "fire": ["fuego", "fire", "hoguera"], "studio_beauty": ["producto", "product", "estudio", "studio", "packshot"],
        "overcast": ["nublado", "lluvia", "rain", "overcast"], "volumetric": ["bosque", "forest", "iglesia", "church", "niebla", "fog"],
    }) or r.choice(["rembrandt", "rim", "soft_window", "golden_hour", "chiaroscuro", "volumetric", "practical"])
    light = V.LIGHTING.get(light_key, light_key)
    parts.append(light)
    breakdown["luz"] = light

    if style in ("cinematic", "film", "cine", "noir", "fantasy", "scifi", "drama"):
        lens = r.choice(V.LENSES)
        cam = r.choice(V.CAMERAS)
        stock = r.choice(V.FILM_STOCKS)
        parts += [f"shot on {cam}, {lens} lens, {r.choice(V.APERTURES)}", f"{stock} color science"]
        breakdown["cámara"] = f"{cam} · {lens} · {stock}"
    elif style in ("commercial", "anuncio", "product", "producto"):
        parts += ["high-end commercial photography", "crisp product lighting", "premium advertising look", "100mm macro lens" if "product" in idea.lower() or "producto" in idea.lower() else "50mm lens"]
        breakdown["cámara"] = "publicidad premium"
    elif style in ("documentary", "documental"):
        parts += ["documentary realism", "available light", "35mm handheld"]
    elif style in ("editorial", "fashion", "moda"):
        parts += ["fashion editorial", "Vogue-style composition", "85mm lens", "medium format look"]

    palette = r.choice(V.PALETTES) if not look else look.replace("_", " ") + " color grade"
    parts.append(palette)
    breakdown["paleta"] = palette
    mood = r.choice(V.MOODS)
    parts.append(f"{mood} atmosphere")
    breakdown["ánimo"] = mood

    if kind == "video":
        mv = V.MOVEMENTS.get(camera.movement, camera.movement) if camera else r.choice(list(V.MOVEMENTS.values()))
        parts.insert(1, mv)
        breakdown["movimiento"] = mv
        if realism > 0.3:
            parts += V.REALISM_VIDEO[: 3 + int(realism * 5)]
        negative = V.NEGATIVE_VIDEO
    else:
        if realism > 0.3:
            k = 4 + int(realism * 8)
            parts += V.REALISM[:k]
        negative = V.NEGATIVE_IMAGE
    if extra:
        parts += extra
    prompt = ", ".join(p for p in parts if p)
    return {"prompt": prompt, "negative": negative, "breakdown": breakdown, "seed": seed}


# ------------------------------------------------------------------ personajes

_PLACE_HERITAGE = {
    ("madrid", "españa", "spain", "español", "española", "sevilla", "valencia", "toledo"): ["Andalusian Spanish", "Basque", "Catalan", "Galician"],
    ("barcelona", "catalu"): ["Catalan"], ("bilbao", "euskadi", "vasco", "vasca"): ["Basque"],
    ("méxico", "mexico", "mexican"): ["Mexican"], ("tokio", "tokyo", "japón", "japon"): ["Japanese"], ("lagos", "nigeria"): ["Nigerian"],
    ("buenos aires", "argentin"): ["Argentinian"], ("bogotá", "colombia"): ["Colombian"], ("cuba", "habana"): ["Cuban"],
}
_HAIR_ES = {"pelirroj": "copper red", "rubi": "golden blonde", "moren": "dark brown", "castañ": "chestnut", "canos": "silver grey", "pelo negro": "jet black", "pelo blanco": "white"}

_FEM_WORDS = {"cocinera", "doctora", "médica", "abogada", "profesora", "ingeniera", "enfermera", "empresaria", "científica", "guerrera",
              "exploradora", "bailarina", "pintora", "relojera", "camarera", "agricultora", "pescadora", "señora", "anciana", "niña", "chica",
              "mujer", "actriz", "reina", "bruja", "abuela", "madre", "hija", "hermana", "jefa", "inspectora", "detective femenina"}
_MASC_WORDS = {"cocinero", "doctor", "médico", "abogado", "profesor", "ingeniero", "enfermero", "empresario", "científico", "guerrero",
               "explorador", "bailarín", "pintor", "relojero", "camarero", "agricultor", "pescador", "señor", "anciano", "niño", "chico",
               "hombre", "actor", "rey", "mago", "abuelo", "padre", "hijo", "hermano", "jefe", "inspector"}


def _gender_of(low: str) -> str | None:
    words = set(re.findall(r"[\wáéíóúñ]+", low))
    if words & _FEM_WORDS or re.search(r"\b(woman|girl|she|female|lady)\b", low):
        return "f"
    if words & _MASC_WORDS or re.search(r"\b(man|boy|he|male|guy)\b", low):
        return "m"
    if re.match(r"\s*(una|la)\s", low):
        return "f"
    if re.match(r"\s*(un|el)\s", low):
        return "m"
    return None


_GENDER = {"f": ["mujer", "woman", "chica", "girl", "señora", "actriz", "she", "ella", "reina", "doctora", "detective femenina", "guerrera", "anciana", "niña"],
           "m": ["hombre", "man", "chico", "boy", "señor", "actor", "he ", "él ", "rey", "guerrero", "anciano", "niño"]}


def design_character(brief: str = "", seed: int | None = None, imagination: float = 0.5) -> Character:
    """Diseña un personaje coherente a partir de una descripción (rellena lo que falte)."""
    r = _rng(seed)
    low = brief.lower()
    gender = _gender_of(low) or r.choice(["f", "m"])
    gender_en = {"f": "woman", "m": "man"}.get(gender, "person")
    age_match = re.search(r"(\d{1,2})\s*(?:años|years|yo|y/o)", low)
    if age_match:
        age = int(age_match.group(1))
    elif any(w in low for w in ("anciano", "anciana", "elderly", "old ")):
        age = r.randint(68, 85)
    elif any(w in low for w in ("joven", "young", "chica", "chico")):
        age = r.randint(19, 27)
    elif any(w in low for w in ("niña", "niño", "child", "kid")):
        age = r.randint(8, 12)
    else:
        age = r.randint(24, 58)
    if age < 16:
        gender_en = "girl" if gender == "f" else "boy"
    role = next((en for es, en in V.ES_EN.items() if es in low and en in V.ROLE_WARDROBE), None)
    if role is None:
        role = next((k for k in V.ROLE_WARDROBE if k in low), "")
    heritage = next((h for h in V.HERITAGE if h.lower().split()[0] in low), None)
    if heritage is None:
        for keys, options in _PLACE_HERITAGE.items():
            if any(k in low for k in keys):
                heritage = r.choice(options)
                break
    heritage = heritage or r.choice(V.HERITAGE)
    eyes_es = re.search(r"ojos (azules|verdes|marrones|negros|grises|miel)", low)
    eye_color = {"azules": "blue", "verdes": "green", "marrones": "brown", "negros": "dark", "grises": "grey", "miel": "honey"}[eyes_es.group(1)] if eyes_es else r.choice(V.EYE_COLORS)
    hair_color = next((c for w, c in _HAIR_ES.items() if w in low), None) or r.choice(V.HAIR_COLORS)
    hair_style = "bald head" if "calvo" in low or "bald" in low else r.choice(V.HAIR_STYLES)
    if age > 65 and "bald" not in hair_style:
        hair_color = r.choice(["silver grey", "white", "salt-and-pepper"])
    marks = _pick(r, V.SKIN_MARKS, 2 if imagination > 0.5 else 1)
    marks = marks if isinstance(marks, list) else [marks]
    face = f"{r.choice(V.FACE_SHAPES)}, {r.choice(V.BROWS)}, {r.choice(V.NOSES)}, {r.choice(V.LIPS)}"
    eyes = f"{r.choice(V.EYE_SHAPES)} {eye_color} eyes"
    skin = f"{r.choice(V.SKIN_TONES)} skin with {', '.join(marks)}"
    hair = f"{hair_style}" if "bald" in hair_style else f"{hair_color} {hair_style}"
    build = r.choice(V.BUILDS)
    wardrobe = V.ROLE_WARDROBE.get(role or "", r.choice(V.DEFAULT_WARDROBE))
    if "barba" in low or "beard" in low:
        face += ", well-groomed beard"
    signature = r.choice(["a worn silver ring", "round tortoiseshell glasses", "a red scarf", "a vintage wristwatch", "a small gold hoop earring",
                          "a leather notebook", "a faded friendship bracelet", "a pendant shaped like a compass"])
    first = r.choice(V.NAMES.get(gender, V.NAMES["n"]))
    name = f"{first} {r.choice(V.SURNAMES)}"
    identity = (
        f"a {age}-year-old {gender_en} of {heritage} heritage, {face}, {eyes}, {skin}, {hair}, {build}, "
        f"wearing {wardrobe}, {signature}"
    )
    if brief:
        extra = [h for h in to_english_hints(brief).split(", ") if h and h not in identity and h not in ("woman", "man", "person", "character")]
        extra = [h for h in extra if not any(k in h for k in ("haired", "eyes", "blonde"))]
        if extra:
            identity += ", " + ", ".join(extra)
    voice_id = ("ef_dora" if gender == "f" else "em_alex")
    personality = r.choice(V.PERSONALITY)
    return Character(
        name=name, role=role or "", age=age, gender={"f": "mujer", "m": "hombre"}.get(gender, ""), heritage=heritage,
        face=face, skin=skin, hair=hair, eyes=eyes, build=build, wardrobe=wardrobe, signature=signature,
        personality=personality, mannerisms=r.choice(V.MANNERISMS),
        backstory=_backstory(r, first, role or "", personality, brief),
        voice=Voice(engine="kokoro", voice_id=voice_id, description=r.choice(["voz cálida y pausada", "voz grave y segura", "voz clara y enérgica", "voz ronca con humor"])),
        identity_prompt=identity, negative=V.NEGATIVE_IMAGE, seed=r.randint(0, 2**31 - 1), tags=[t for t in (role, heritage) if t],
    )


def _backstory(r: random.Random, name: str, role: str, personality: str, brief: str) -> str:
    hooks = [
        "creció entre redes de pesca en un puerto que ya no existe",
        "fue campeona de ajedrez juvenil antes de abandonarlo todo",
        "guarda una carta que nunca se atrevió a enviar",
        "sobrevivió a un incendio que cambió su forma de ver la vida",
        "heredó un taller de relojes y una deuda imposible",
        "volvió a su ciudad natal tras diez años de silencio",
        "trabaja de noche para pagar el sueño que persigue de día",
        "tiene una hermana gemela a la que no ve desde hace años",
    ]
    goals = ["demostrar que se equivocaron con ella/él", "proteger a quien queda de su familia", "encontrar la verdad sobre su pasado",
             "lanzar el proyecto de su vida", "pedir perdón antes de que sea tarde", "escapar de una rutina que le asfixia"]
    rol = f" ({role})" if role else ""
    base = f"{name}{rol} es {personality_es(personality)}. {r.choice(hooks).capitalize()} y quiere {r.choice(goals)}."
    if brief:
        base += f" Concepto original: «{brief.strip()}»."
    return base


def personality_es(p: str) -> str:
    table = {
        "stubborn but loyal": "terca pero leal", "quietly brilliant": "brillante en silencio", "charismatic risk-taker": "carismática y temeraria",
        "melancholic dreamer": "soñadora melancólica", "warm and funny": "cálida y divertida", "cold strategist": "estratega fría",
        "anxious perfectionist": "perfeccionista ansiosa", "rebellious idealist": "idealista rebelde", "gentle giant": "un gigante bondadoso",
        "sharp-tongued survivor": "superviviente de lengua afilada", "curious optimist": "optimista curiosa", "haunted veteran": "veterana atormentada",
    }
    return table.get(p, p)


def character_turnaround_prompts(c: Character, style: str = "cinematic") -> list[dict]:
    """Prompts para la hoja de referencia del personaje (consistencia)."""
    base = c.identity_prompt
    views = [
        ("frontal", "front-facing neutral expression, looking directly into the camera, passport-style framing"),
        ("tres_cuartos", "three-quarter view, slight smile, looking off-camera"),
        ("perfil", "side profile view, serene expression"),
        ("cuerpo_entero", "full body shot standing, natural relaxed pose"),
        ("emocion", "intense emotional expression, eyes glistening"),
        ("accion", "dynamic mid-action pose, motion in hair and clothes"),
    ]
    out = []
    for vid, view in views:
        out.append({
            "view": vid,
            "prompt": f"character reference photo of {base}, {view}, neutral seamless grey studio backdrop, soft even key light, "
                      "photorealistic, natural skin texture with visible pores, 85mm lens, f/4, sharp focus, 8k detail",
            "negative": V.NEGATIVE_IMAGE,
        })
    return out


# ------------------------------------------------------------------ localizaciones


def design_location(brief: str = "", seed: int | None = None, imagination: float = 0.5) -> Location:
    r = _rng(seed)
    if brief.strip():
        desc = brief.strip()
        hints = to_english_hints(desc)
        base = f"{desc}" + (f" ({hints})" if hints else "")
        tod = next((v for k, v in {"noche": "noche", "night": "noche", "atardecer": "atardecer", "sunset": "atardecer", "amanecer": "amanecer", "dawn": "amanecer"}.items() if k in desc.lower()), r.choice(["día", "atardecer", "noche", "amanecer"]))
        light_key = {"noche": "moonlight", "atardecer": "golden_hour", "amanecer": "golden_hour"}.get(tod, r.choice(["overcast", "volumetric", "soft_window"]))
    else:
        base, tod, light_key = r.choice(V.LOCATIONS)
    era = r.choice(V.ERAS) if imagination > 0.6 else "contemporary"
    weather = r.choice(V.WEATHER)
    palette = r.choice(V.PALETTES)
    props = ", ".join(_pick(r, ["vintage street lamps", "hanging laundry", "stacked wooden crates", "rusted bicycles", "potted lemon trees",
                                   "flickering signage", "graffiti murals", "old telephone booth", "market stalls", "fishing nets",
                                   "marble statues", "scattered newspapers", "steaming food carts"], 3))
    identity = f"{base}, {era} era, {weather}, {V.LIGHTING.get(light_key, light_key)}, {props}, {palette}, rich environmental detail"
    if imagination > 0.5:
        identity += f", {r.choice(V.WONDER)}"
    name = brief.strip()[:40] if brief.strip() else base.split(" in ")[0].replace("a ", "").replace("an ", "")[:40].capitalize()
    return Location(name=name or "Localización", description=base, era=era, time_of_day=tod, weather=weather, lighting=V.LIGHTING.get(light_key, light_key),
                    palette=palette, props=props, ambience=r.choice(V.AMBIENCE), identity_prompt=identity, seed=r.randint(0, 2**31 - 1))


# ------------------------------------------------------------------ composición de planos


def compose_shot_prompt(shot: Shot, characters: list[Character], location: Location | None, sb: Storyboard, kind: str = "image", realism: float = 1.0) -> tuple[str, str]:
    """Prompt final de un plano combinando cámara + personajes + acción + localización + estilo."""
    cam = shot.camera
    parts = [V.SHOT_SIZES.get(cam.shot_size, cam.shot_size.replace("_", " ")), V.ANGLES.get(cam.angle, cam.angle.replace("_", " "))]
    if kind == "video":
        parts.append(V.MOVEMENTS.get(cam.movement, cam.movement.replace("_", " ")))
    chars = [c for c in characters if c.id in shot.characters or c.name in shot.characters]
    action = shot.prompt or shot.description
    if chars:
        who = "; ".join(c.identity_prompt for c in chars)
        parts.append(f"{who}. {action}")
    else:
        parts.append(action)
    hints = to_english_hints(shot.description)
    if hints:
        parts.append(hints)
    if location:
        parts.append(f"setting: {location.identity_prompt}")
    if shot.lighting:
        parts.append(V.LIGHTING.get(shot.lighting, shot.lighting))
    if shot.mood:
        parts.append(f"{shot.mood} mood")
    if sb.style:
        parts.append(sb.style)
    if sb.look:
        parts.append(sb.look.replace("_", " ") + " color grade")
    parts.append(f"{cam.lens} lens")
    parts += (V.REALISM_VIDEO if kind == "video" else V.REALISM)[: 4 + int(realism * 6)]
    negative = shot.negative or (V.NEGATIVE_VIDEO if kind == "video" else V.NEGATIVE_IMAGE)
    return ", ".join(p for p in parts if p), negative


# ------------------------------------------------------------------ storyboards (modo sin LLM)

_AD_BEATS = [
    ("Gancho", "close_up", "push_in", 0.15, "Un instante visual impactante que detiene el scroll"),
    ("Deseo", "medium", "tracking", 0.2, "La persona protagonista vive el problema o el deseo"),
    ("Revelación", "insert", "orbit", 0.25, "El producto aparece como la respuesta, en un plano heroico"),
    ("Beneficio", "medium_close", "dolly_in", 0.25, "La vida mejora gracias al producto: emoción real"),
    ("Cierre", "wide", "crane", 0.15, "Plano final con marca, eslogan y llamada a la acción"),
]


def storyboard_ad(product: str, description: str = "", audience: str = "", tone: str = "premium", duration: float = 20, aspect: str = "16:9",
                  cta: str = "Descúbrelo hoy", brand: str = "", seed: int | None = None, imagination: float = 0.6, character: Character | None = None,
                  language: str = "es", location: Location | None = None) -> tuple[Storyboard, Location]:
    r = _rng(seed)
    loc = location or design_location("", seed=r.randint(0, 99999), imagination=imagination)
    sb = Storyboard(title=f"Anuncio {brand or product}", logline=f"{product}: {description}".strip(": "), format="ad",
                    style={"premium": "luxury commercial, elegant", "divertido": "playful energetic commercial", "emocional": "emotional cinematic commercial",
                           "tecnológico": "sleek tech commercial, futuristic", "natural": "authentic lifestyle commercial"}.get(tone, f"{tone} commercial"),
                    look={"premium": "teal_orange", "divertido": "commercial_pop", "emocional": "warm_film", "tecnológico": "cold_thriller", "natural": "documentary"}.get(tone, "commercial_pop"),
                    language=language, music_prompt=f"{tone} commercial music, {'uplifting corporate' if tone != 'emocional' else 'emotional piano and strings'}")
    t_used = 0.0
    vo_lines = _ad_voiceover(product, description, audience, cta, brand, tone, r)
    for i, (beat, size, move, frac, intent) in enumerate(_AD_BEATS):
        dur = round(max(1.5, duration * frac), 2)
        if i == len(_AD_BEATS) - 1:
            dur = round(max(1.5, duration - t_used), 2)
        t_used += dur
        who = [character.id] if character and beat in ("Deseo", "Beneficio", "Gancho") else []
        if beat == "Revelación" or beat == "Cierre":
            desc = f"hero shot of {product}" + (f", {description}" if description else "") + ", premium materials, perfect reflections"
        elif beat == "Gancho":
            desc = f"striking unexpected visual related to {product}: {r.choice(V.WONDER)}"
        elif beat == "Deseo":
            desc = f"{audience or 'a person'} in everyday life, longing for {product}'s benefit" if not character else f"{character.name} in everyday life, longing for something more"
        else:
            desc = f"{audience or 'the protagonist'} enjoying {product}, genuine joy, natural interaction"
        on_screen = {"Gancho": "", "Revelación": brand or product, "Cierre": cta}.get(beat, "")
        sb.shots.append(Shot(index=i, scene=beat, description=f"{intent}. {desc}", prompt=desc, duration=dur,
                             camera=Camera(shot_size=size, movement=move, angle="low" if beat == "Revelación" else "eye_level", lens=r.choice(["35mm", "50mm", "85mm", "100mm macro"])),
                             lighting="studio_beauty" if beat in ("Revelación", "Cierre") else r.choice(["golden_hour", "soft_window", "rim"]),
                             mood=r.choice(V.MOODS), characters=who, location=None if beat in ("Revelación",) else loc.id,
                             dialogue=[DialogueLine(speaker="narrador", text=vo_lines[i])] if vo_lines[i] else [],
                             on_screen_text=on_screen, transition="fade" if i else "cut"))
    sb.voiceover = " ".join(v for v in vo_lines if v)
    return sb, loc


def _ad_voiceover(product: str, desc: str, audience: str, cta: str, brand: str, tone: str, r: random.Random) -> list[str]:
    hooks = ["¿Y si todo pudiera ser distinto?", "Hay momentos que lo cambian todo.", "Lo extraordinario empieza aquí.", "Nadie te lo había contado así."]
    desire = ["Cada día buscamos algo que esté a nuestra altura.", "Porque mereces más que lo de siempre.", "Lo sabes desde el primer segundo."]
    reveal = [f"Presentamos {product}.", f"{product}. Diseñado para ti.", f"Así es {product}."]
    benefit = [f"{desc.capitalize()}." if desc else "Más fácil. Más tuyo. Más real.", "Sientes la diferencia desde el primer día.", "Hecho para quienes no se conforman."]
    close = [f"{cta}." if cta else "", f"{brand or product}. {cta}." if cta else f"{brand or product}."]
    return [r.choice(hooks), r.choice(desire), r.choice(reveal), r.choice(benefit), r.choice(close)]


_FILM_BEATS = [
    ("Planteamiento", "extreme_wide", "drone", "establece el mundo y el tono", "establishing the world, the protagonist small in the frame"),
    ("Planteamiento", "medium", "tracking", "presenta al protagonista en su rutina", "the protagonist going through their daily routine"),
    ("Detonante", "close_up", "push_in", "algo inesperado rompe la rutina", "the protagonist notices something impossible, eyes widening"),
    ("Conflicto", "over_shoulder", "handheld", "el protagonista se enfrenta al obstáculo", "the protagonist confronts the obstacle, tense body language"),
    ("Conflicto", "wide", "tracking", "la tensión crece, el mundo reacciona", "the world reacts around the protagonist, rising tension"),
    ("Clímax", "extreme_close_up", "static", "el momento de la decisión, en los ojos", "decision moment, extreme detail of the eyes"),
    ("Clímax", "medium_close", "orbit", "la acción decisiva", "the decisive action, emotional peak"),
    ("Resolución", "wide", "crane", "el nuevo equilibrio, plano final memorable", "the new balance, memorable final image"),
]


def storyboard_short(idea: str, genre: str = "drama", duration: float = 60, characters: list[Character] | None = None, seed: int | None = None,
                     imagination: float = 0.6, language: str = "es", location: Location | None = None) -> tuple[Storyboard, Location, list[Character]]:
    r = _rng(seed)
    chars = characters or [design_character(idea, seed=r.randint(0, 99999), imagination=imagination)]
    hero = chars[0]
    loc = location or design_location("", seed=r.randint(0, 99999), imagination=imagination)
    looks = {"drama": "warm_film", "thriller": "cold_thriller", "terror": "horror", "ciencia ficción": "neon_night", "scifi": "neon_night",
             "comedia": "pastel_dream", "romance": "golden_hour", "acción": "teal_orange", "fantasía": "vintage", "noir": "noir"}
    sb = Storyboard(title=idea[:60] or "Cortometraje", logline=f"{hero.name}, {hero.role or 'protagonista'}, {idea}", format="short_film",
                    style=f"{genre} film, cinematic storytelling", look=looks.get(genre.lower(), "warm_film"), language=language,
                    music_prompt=f"{genre} film score, cinematic")
    n = len(_FILM_BEATS)
    per = max(2.5, duration / n)
    lines = _film_dialogue(hero, idea, r)
    for i, (act, size, move, intent, intent_en) in enumerate(_FILM_BEATS):
        desc = f"{hero.name} {intent}: {idea}"
        prev_act = sb.shots[-1].scene if sb.shots else act
        sb.shots.append(Shot(index=i, scene=act, description=desc, prompt=f"{intent_en}, story: {idea} ({to_english_hints(idea)})", duration=round(per, 2),
                             camera=Camera(shot_size=size, movement=move, lens=r.choice(V.LENSES).split()[0]),
                             lighting=r.choice(list(V.LIGHTING)), mood=r.choice(V.MOODS), characters=[hero.id], location=loc.id,
                             dialogue=[DialogueLine(speaker=hero.id, text=lines[i])] if lines[i] else [],
                             transition="fade" if prev_act != act else "cut"))
    return sb, loc, chars


def _film_dialogue(hero: Character, idea: str, r: random.Random) -> list[str]:
    return [
        "",
        r.choice(["Otro día igual que todos.", "Nadie se fija nunca en los detalles.", "Si supieran lo que yo sé..."]),
        r.choice(["¿Qué es esto?", "No puede ser...", "Esto lo cambia todo."]),
        r.choice(["No pienso retroceder.", "Tiene que haber otra forma.", "¿Por qué yo?"]),
        "",
        r.choice(["Ahora o nunca.", "Lo siento.", "Confía en mí."]),
        "",
        r.choice(["Por fin.", "Esto no ha hecho más que empezar.", ""]),
    ]


_SHOWCASE = [
    ("Establecimiento", "extreme_wide", "drone", "the character stands small against the vast location", None),
    ("Presentación", "medium", "dolly_in", "the character slowly turns towards the camera", None),
    ("Mirada", "close_up", "push_in", "the character looks into the lens, subtle emotion appears", None),
    ("Detalle", "extreme_close_up", "static", "macro detail of the eyes, iris texture, eyelashes, natural blink", None),
    ("Acción", "full", "tracking", "the character walks with purpose, clothes moving naturally in the wind", None),
    ("Héroe", "medium_close", "orbit", "heroic final pose, confident expression, wind in the hair", None),
]


def storyboard_character(character: Character, location: Location | None = None, duration: float = 24, seed: int | None = None) -> tuple[Storyboard, Location]:
    r = _rng(seed)
    loc = location or design_location("", seed=r.randint(0, 99999))
    sb = Storyboard(title=f"{character.name} · presentación 4K", logline=character.backstory, format="character", style="hyperrealistic cinematic character reveal",
                    look="teal_orange", music_prompt="epic cinematic character reveal, slow build")
    per = max(2.5, duration / len(_SHOWCASE))
    for i, (scene, size, move, action, _x) in enumerate(_SHOWCASE):
        sb.shots.append(Shot(index=i, scene=scene, description=action, prompt=action, duration=round(per, 2),
                             camera=Camera(shot_size=size, movement=move, lens={"extreme_close_up": "100mm", "close_up": "85mm", "extreme_wide": "24mm"}.get(size, "50mm")),
                             lighting=r.choice(["rim", "golden_hour", "rembrandt", "volumetric"]), mood=r.choice(["awe-inspiring", "intimate", "triumphant", "mysterious"]),
                             characters=[character.id], location=loc.id, transition="fade" if i else "cut"))
    return sb, loc


# ------------------------------------------------------------------ modo LLM

DIRECTOR_SYSTEM = """Eres el equipo creativo de una productora de cine de primer nivel: guionista galardonado, director
con imaginación desbordante, director de fotografía obsesionado con el realismo y diseñador de personajes.
Escribes en español los textos para el público y en inglés los prompts visuales (muy detallados, fotorrealistas,
con cámara, lente, luz, textura y movimiento). Respondes SIEMPRE con JSON válido, sin texto extra."""


def storyboard_schema_hint() -> str:
    return """{
  "title": "string", "logline": "string", "style": "string (estilo visual en inglés)",
  "look": "uno de: teal_orange, bleach_bypass, noir, warm_film, cold_thriller, vintage, pastel_dream, neon_night, golden_hour, documentary, commercial_pop, horror",
  "music_prompt": "string (en inglés)",
  "shots": [{
    "scene": "string", "description": "string (español, qué ocurre)",
    "prompt": "string (inglés, prompt visual detallado del plano SIN describir al personaje, sólo acción, entorno, luz)",
    "duration": number (segundos, 2-8),
    "camera": {"shot_size": "extreme_wide|wide|full|medium|medium_close|close_up|extreme_close_up|insert|over_shoulder|two_shot",
               "angle": "eye_level|low|high|dutch|overhead|pov|profile|three_quarter",
               "movement": "static|dolly_in|dolly_out|pan|tilt|crane|orbit|handheld|drone|tracking|push_in|whip_pan|fpv", "lens": "35mm"},
    "lighting": "string", "mood": "string", "characters": ["nombres"],
    "dialogue": [{"speaker": "nombre o narrador", "text": "string (español)"}],
    "on_screen_text": "string", "transition": "cut|fade|dissolve|wipeleft|slideup|circleopen"
  }]
}"""


async def llm_storyboard(llm, brief: str, fmt: str, duration: float, characters: list[Character], extra: str = "", temperature: float = 1.0) -> Storyboard | None:
    chars = "\n".join(f"- {c.name}: {c.role}, {c.personality}. Aspecto: {c.identity_prompt}" for c in characters) or "(libre: invéntalos tú)"
    user = (
        f"Formato: {fmt}. Duración total objetivo: {duration:.0f} segundos.\n"
        f"Brief del cliente: {brief}\n{extra}\n"
        f"Personajes disponibles:\n{chars}\n\n"
        "Escribe un storyboard sorprendente, emotivo y rodable con modelos de vídeo IA (planos de 2-8 s, acciones simples y claras). "
        "Sé imaginativo: busca una idea visual inesperada que haga memorable la pieza. "
        f"Devuelve JSON con esta forma:\n{storyboard_schema_hint()}"
    )
    data = await llm.chat_json(DIRECTOR_SYSTEM, user, temperature=temperature)
    if not isinstance(data, dict) or not data.get("shots"):
        return None
    sb = Storyboard(title=str(data.get("title", ""))[:120], logline=str(data.get("logline", "")), format=fmt if fmt in ("ad", "short_film", "character", "music_video", "trailer") else "free",
                    style=str(data.get("style", "")), look=data.get("look") if isinstance(data.get("look"), str) else None, music_prompt=str(data.get("music_prompt", "")))
    name_to_id = {c.name.lower(): c.id for c in characters}
    for i, s in enumerate(data["shots"][:40]):
        if not isinstance(s, dict):
            continue
        cam = s.get("camera") or {}
        dialogue = []
        for d in s.get("dialogue") or []:
            if isinstance(d, dict) and d.get("text"):
                spk = str(d.get("speaker", "narrador"))
                dialogue.append(DialogueLine(speaker=name_to_id.get(spk.lower(), spk), text=str(d["text"])))
        chars_ids = []
        for n in s.get("characters") or []:
            cid = name_to_id.get(str(n).lower())
            if cid:
                chars_ids.append(cid)
        try:
            dur = float(s.get("duration", 4))
        except (TypeError, ValueError):
            dur = 4.0
        sb.shots.append(Shot(index=i, scene=str(s.get("scene", "")), description=str(s.get("description", "")), prompt=str(s.get("prompt", "")),
                             duration=max(1.5, min(10.0, dur)),
                             camera=Camera(shot_size=str(cam.get("shot_size", "medium")), angle=str(cam.get("angle", "eye_level")),
                                           movement=str(cam.get("movement", "static")), lens=str(cam.get("lens", "35mm"))),
                             lighting=str(s.get("lighting", "")), mood=str(s.get("mood", "")), characters=chars_ids, dialogue=dialogue,
                             on_screen_text=str(s.get("on_screen_text", "")), transition=str(s.get("transition", "cut"))))
    if not sb.shots:
        return None
    # ajustar duración total
    total = sum(s.duration for s in sb.shots)
    if total > 0 and abs(total - duration) / duration > 0.15:
        k = duration / total
        for s in sb.shots:
            s.duration = round(max(1.5, s.duration * k), 2)
    return sb


async def llm_character(llm, brief: str, inspiration: str = "") -> Character | None:
    user = (
        f"Diseña un personaje original e hiperrealista a partir de este concepto: «{brief}».\n"
        + (f"Rasgos de inspiración (no copies a nadie, crea una persona nueva): {inspiration}\n" if inspiration else "")
        + "Devuelve JSON con: name, role, age (número), gender, heritage, face (inglés), eyes (inglés), skin (inglés, con imperfecciones realistas), "
        "hair (inglés), build (inglés), wardrobe (inglés), signature (inglés), personality (español), mannerisms (español), backstory (español, 3 frases), "
        "voice_description (español), identity_prompt (inglés: descripción visual densa y precisa para mantener la identidad en todas las imágenes)."
    )
    data = await llm.chat_json(DIRECTOR_SYSTEM, user, temperature=1.0)
    if not isinstance(data, dict) or not data.get("identity_prompt"):
        return None
    base = design_character(brief)
    try:
        age = int(data.get("age") or base.age or 30)
    except (TypeError, ValueError):
        age = base.age or 30
    return Character(
        name=str(data.get("name") or base.name), role=str(data.get("role", "")), age=age, gender=str(data.get("gender", "")),
        heritage=str(data.get("heritage", "")), face=str(data.get("face", "")), eyes=str(data.get("eyes", "")), skin=str(data.get("skin", "")),
        hair=str(data.get("hair", "")), build=str(data.get("build", "")), wardrobe=str(data.get("wardrobe", "")), signature=str(data.get("signature", "")),
        personality=str(data.get("personality", "")), mannerisms=str(data.get("mannerisms", "")), backstory=str(data.get("backstory", "")),
        voice=Voice(engine="kokoro", voice_id=base.voice.voice_id, description=str(data.get("voice_description", ""))),
        identity_prompt=str(data["identity_prompt"]), negative=V.NEGATIVE_IMAGE, seed=base.seed,
    )


async def llm_enhance(llm, idea: str, kind: str, imagination: float) -> dict | None:
    user = (
        f"Convierte esta idea en un prompt {'de vídeo (describe movimiento de cámara y del sujeto)' if kind == 'video' else 'de imagen'} "
        f"fotorrealista de nivel cine, en inglés. Nivel de imaginación {imagination:.1f}/1 (alto = añade un elemento visual sorprendente). "
        f"Idea: «{idea}». Devuelve JSON: {{\"prompt\": \"...\", \"negative\": \"...\", \"title\": \"título corto en español\"}}"
    )
    data = await llm.chat_json(DIRECTOR_SYSTEM, user, temperature=0.6 + imagination * 0.6)
    if isinstance(data, dict) and data.get("prompt"):
        return data
    return None


async def describe_face_features(vision_llm, image_path) -> str | None:
    """Describe rasgos generales de un rostro de inspiración (sin identificar a la persona)."""
    sys = "Eres un director de casting y maquillador experto. Nunca identificas a personas reales; sólo describes rasgos físicos generales."
    user = ("Describe en inglés, en una sola línea separada por comas, los rasgos visuales generales de este rostro para inspirar "
            "un personaje NUEVO: forma de la cara, cejas, ojos (forma y color), nariz, labios, piel (tono y textura), pelo, edad aparente. "
            "No digas quién es ni adivines su identidad.")
    try:
        txt = await vision_llm.chat(sys, user, images=[image_path], temperature=0.3, max_tokens=300)
        return txt.strip().strip('"')[:600] or None
    except Exception:
        return None
