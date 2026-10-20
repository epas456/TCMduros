"""Vocabulario cinematográfico para construir prompts fotorrealistas (en inglés, el idioma
en el que mejor responden los modelos) y su traducción de términos frecuentes del español."""

from __future__ import annotations

SHOT_SIZES = {
    "extreme_wide": "extreme wide establishing shot",
    "wide": "wide shot",
    "full": "full body shot",
    "medium": "medium shot",
    "medium_close": "medium close-up",
    "close_up": "close-up portrait",
    "extreme_close_up": "extreme close-up",
    "insert": "macro insert shot",
    "over_shoulder": "over-the-shoulder shot",
    "two_shot": "two-shot",
}
SHOT_LABELS_ES = {
    "extreme_wide": "Gran plano general", "wide": "Plano general", "full": "Plano entero", "medium": "Plano medio",
    "medium_close": "Plano medio corto", "close_up": "Primer plano", "extreme_close_up": "Primerísimo primer plano",
    "insert": "Plano detalle", "over_shoulder": "Plano sobre el hombro", "two_shot": "Plano de dos",
}
ANGLES = {
    "eye_level": "eye-level angle", "low": "low angle looking up, heroic", "high": "high angle looking down",
    "dutch": "dutch angle, tilted horizon", "overhead": "top-down overhead view", "pov": "first-person POV",
    "profile": "side profile", "three_quarter": "three-quarter view",
}
MOVEMENTS = {
    "static": "locked-off static camera",
    "dolly_in": "slow dolly-in towards the subject",
    "dolly_out": "slow dolly-out revealing the scene",
    "pan": "smooth horizontal pan",
    "tilt": "slow tilt up",
    "crane": "sweeping crane shot rising up",
    "orbit": "slow 180-degree orbit around the subject",
    "handheld": "subtle handheld camera with natural micro-shake",
    "drone": "aerial drone flyover",
    "tracking": "lateral tracking shot following the subject",
    "push_in": "dramatic push-in",
    "whip_pan": "fast whip pan",
    "fpv": "dynamic FPV drone dive",
}
MOVEMENT_LABELS_ES = {
    "static": "Fija", "dolly_in": "Travelling de acercamiento", "dolly_out": "Travelling de alejamiento", "pan": "Panorámica",
    "tilt": "Tilt", "crane": "Grúa", "orbit": "Órbita", "handheld": "Cámara en mano", "drone": "Dron", "tracking": "Seguimiento",
    "push_in": "Empuje dramático", "whip_pan": "Barrido rápido", "fpv": "Dron FPV",
}
LENSES = ["14mm ultra-wide", "24mm wide-angle", "35mm", "40mm anamorphic", "50mm", "85mm portrait", "100mm macro", "135mm telephoto"]
CAMERAS = ["ARRI Alexa 65", "ARRI Alexa Mini LF", "RED V-Raptor 8K", "Sony Venice 2", "Panavision Millennium DXL2", "Blackmagic URSA Cine 12K"]
FILM_STOCKS = ["Kodak Vision3 500T", "Kodak Vision3 250D", "Kodak Portra 400", "Fujifilm Eterna 500", "Cinestill 800T", "Kodak Ektachrome"]
APERTURES = ["f/1.4 shallow depth of field", "f/2.0 creamy bokeh", "f/2.8", "f/5.6 deep focus", "T1.5 dreamy falloff"]

LIGHTING = {
    "golden_hour": "warm golden hour sunlight, long soft shadows",
    "blue_hour": "cool blue hour ambient light, city lights coming on",
    "rembrandt": "Rembrandt lighting with a triangle of light on the cheek",
    "rim": "strong rim light separating the subject from the background",
    "chiaroscuro": "dramatic chiaroscuro, deep shadows",
    "soft_window": "soft diffused window light",
    "neon": "practical neon signs casting magenta and cyan light",
    "overcast": "soft overcast daylight, even exposure",
    "candle": "flickering candlelight, warm intimate glow",
    "volumetric": "volumetric god rays through haze",
    "studio_beauty": "high-key beauty dish lighting with soft fill",
    "moonlight": "silver moonlight with deep blue shadows",
    "fire": "firelight with dancing orange highlights",
    "practical": "motivated practical lighting from lamps in frame",
}
MOODS = ["melancholic", "triumphant", "mysterious", "intimate", "tense", "serene", "euphoric", "nostalgic", "ominous", "hopeful", "bittersweet", "awe-inspiring"]
PALETTES = [
    "teal and orange color grade", "muted earth tones", "desaturated cold palette", "warm amber and deep brown palette",
    "pastel palette", "high-contrast monochrome", "emerald and gold palette", "crimson and black palette", "sun-bleached film tones",
]
REALISM = [
    "photorealistic", "hyperrealistic", "natural skin texture with visible pores", "subsurface scattering",
    "fine peach fuzz", "realistic imperfections", "true-to-life proportions", "accurate anatomy", "sharp focus on the eyes",
    "natural catchlights in the eyes", "film grain", "high dynamic range", "8k detail",
]
REALISM_VIDEO = [
    "photorealistic", "natural lifelike motion", "realistic physics", "consistent identity", "cinematic motion blur",
    "subtle micro-expressions", "natural blinking", "film grain", "high detail",
]
WONDER = [
    "drifting golden embers in the air", "bioluminescent particles floating around", "a flock of birds crossing the sky in slow motion",
    "rain droplets frozen in mid-air", "petals carried by the wind", "shafts of light breaking through dust", "reflections in a puddle",
    "aurora shimmering above", "steam rising from the ground", "snow falling upwards", "glowing paper lanterns",
    "a giant moon low on the horizon", "mirror-like wet streets", "floating islands in the distance", "an ancient statue half-buried in sand",
    "fireflies lighting the dusk", "sparks from a welder nearby", "a lighthouse beam sweeping the fog", "origami birds coming alive",
    "holographic advertisements flickering", "a whale silhouette swimming through the clouds",
]
ENVIRONMENT_DETAILS = [
    "rich environmental storytelling", "lived-in details", "atmospheric haze", "layered depth with foreground elements",
    "weathered textures", "natural clutter", "wet surfaces reflecting light", "subtle wind movement",
]

NEGATIVE_IMAGE = (
    "cartoon, anime, illustration, painting, 3d render, cgi, plastic skin, wax skin, airbrushed, doll, deformed, disfigured, "
    "bad anatomy, extra fingers, fused fingers, mutated hands, extra limbs, cross-eyed, asymmetric eyes, watermark, text, logo, "
    "signature, lowres, blurry, oversaturated, overexposed, jpeg artifacts, uncanny"
)
NEGATIVE_VIDEO = (
    "static image, frozen frame, jittery, flickering, morphing face, identity drift, deformed hands, extra fingers, warped background, "
    "watermark, subtitles, text, low quality, blurry, cartoon, cgi, oversaturated"
)

# ------------------------------------------------------------------ personajes
HERITAGE = [
    "Andalusian Spanish", "Basque", "Catalan", "Galician", "Mexican", "Colombian", "Argentinian", "Peruvian Andean", "Afro-Caribbean",
    "Nigerian", "Senegalese", "Ethiopian", "Moroccan", "Egyptian", "Persian", "Turkish", "Indian", "Pakistani", "Vietnamese",
    "Korean", "Japanese", "Han Chinese", "Filipino", "Indonesian", "Polynesian", "Maori", "Inuit", "Navajo", "Nordic", "Irish",
    "Scottish", "Italian", "Greek", "Slavic", "Brazilian of mixed heritage", "Afro-Brazilian", "Cuban", "Lebanese", "Somali",
]
FACE_SHAPES = ["oval face", "heart-shaped face", "square jawline", "round face", "long face with defined cheekbones", "diamond-shaped face", "soft angular face"]
EYE_SHAPES = ["almond-shaped", "deep-set", "hooded", "upturned", "downturned", "wide-set", "monolid", "round"]
EYE_COLORS = ["dark brown", "hazel", "amber", "green", "grey-blue", "steel blue", "honey brown", "almost black", "olive green"]
BROWS = ["thick straight brows", "softly arched brows", "bold dark brows", "sparse light brows", "expressive angled brows"]
NOSES = ["straight nose", "slightly aquiline nose", "button nose", "broad nose", "Roman nose", "narrow refined nose", "nose with a slight bump"]
LIPS = ["full lips", "thin lips", "wide expressive mouth", "cupid's-bow lips", "slightly asymmetric smile"]
SKIN_TONES = ["porcelain", "fair", "light olive", "olive", "golden tan", "warm beige", "medium brown", "deep brown", "rich ebony", "sun-weathered"]
SKIN_MARKS = [
    "subtle freckles across the nose", "a small beauty mark under the left eye", "faint laugh lines", "a thin scar on the eyebrow",
    "light acne scars", "crow's feet when smiling", "sun spots on the cheekbones", "a dimple on one cheek", "a chipped front tooth",
    "vitiligo patches on the jaw", "a faded tattoo on the neck", "rosy cheeks", "faint stubble shadow",
]
HAIR_STYLES = [
    "shoulder-length wavy hair", "short textured crop", "long straight hair", "tight curls", "buzz cut", "messy bun",
    "slicked-back undercut", "braids", "pixie cut", "loose afro", "shaved sides with a top knot", "long locs", "salt-and-pepper short hair",
    "bob with bangs", "ponytail",
]
HAIR_COLORS = ["jet black", "dark brown", "chestnut", "auburn", "copper red", "dirty blonde", "platinum blonde", "silver grey", "ash brown"]
BUILDS = ["slim build", "athletic build", "stocky build", "tall and lanky", "petite frame", "broad-shouldered", "average build", "muscular build"]
PERSONALITY = [
    "stubborn but loyal", "quietly brilliant", "charismatic risk-taker", "melancholic dreamer", "warm and funny", "cold strategist",
    "anxious perfectionist", "rebellious idealist", "gentle giant", "sharp-tongued survivor", "curious optimist", "haunted veteran",
]
MANNERISMS = [
    "touches the scar on their brow when thinking", "hums old boleros", "always rolls up their sleeves", "never makes eye contact first",
    "taps their ring against tables", "laughs before delivering bad news", "collects bottle caps", "talks to stray cats",
]
ROLE_WARDROBE = {
    "detective": "rumpled trench coat over a dark sweater",
    "chef": "stained white chef jacket with rolled sleeves",
    "astronaut": "worn white EVA suit with mission patches",
    "doctor": "light blue scrubs with a stethoscope",
    "warrior": "battle-worn leather armor with hand-stitched details",
    "ceo": "tailored charcoal suit, no tie",
    "musician": "vintage band t-shirt under a denim jacket",
    "farmer": "faded flannel shirt and work gloves",
    "scientist": "lab coat over a knitted cardigan",
    "athlete": "technical running gear with sweat marks",
    "pilot": "leather flight jacket",
    "nurse": "navy nurse uniform",
    "student": "oversized hoodie and canvas backpack",
    "explorer": "sun-faded field jacket with many pockets",
    "watchmaker": "leather apron over a crisp white shirt, jeweler's loupe on the forehead",
    "police officer": "dark police uniform with a reflective vest",
    "lawyer": "sharp navy suit with a silk tie",
    "painter": "paint-splattered overalls",
    "waiter": "black vest and white shirt with a bow tie",
    "soldier": "dusty combat fatigues",
    "dancer": "flowing rehearsal clothes",
}
DEFAULT_WARDROBE = [
    "linen shirt with rolled sleeves", "oversized wool coat", "fitted black turtleneck", "denim jacket over a white tee",
    "earth-toned knit sweater", "minimalist tailored blazer", "vintage leather jacket", "flowing silk dress", "utility jumpsuit",
]

NAMES = {
    "f": ["Lucía", "Martina", "Valeria", "Aitana", "Noa", "Carmen", "Ximena", "Amara", "Leire", "Inés", "Zuri", "Mei", "Nadia", "Olivia", "Rocío", "Yara", "Aiko", "Elena", "Paloma", "Sofía"],
    "m": ["Mateo", "Hugo", "Iker", "Darío", "Bruno", "Joel", "Kenji", "Omar", "Rafael", "Teo", "Malik", "Andrés", "Santiago", "Luca", "Nicolás", "Adrián", "Tomás", "Ibrahim", "Pau", "Diego"],
    "n": ["Alex", "Sam", "Noor", "Ari", "Robin", "Eli", "Kai", "Sasha", "Andy", "Cris"],
}
SURNAMES = ["Vidal", "Okafor", "Morales", "Arrieta", "Nakamura", "Ferrer", "Haddad", "Quispe", "Lindqvist", "Ramírez", "Castells", "Mbeki", "Duarte", "Iglesias", "Park", "Varela", "Santos", "Echeverría", "Rossi", "Kowalski"]

# ------------------------------------------------------------------ localizaciones
LOCATIONS = [
    ("a rain-soaked neon alley in a dense Asian megacity", "noche", "neon"),
    ("a whitewashed Andalusian village clinging to a cliff", "atardecer", "golden_hour"),
    ("a brutalist concrete library with endless shelves", "día", "volumetric"),
    ("an abandoned Art Deco train station reclaimed by plants", "mañana", "volumetric"),
    ("a misty Basque coastline with jagged rock formations", "amanecer", "overcast"),
    ("a high-altitude Andean salt flat mirroring the sky", "día", "overcast"),
    ("a luxury penthouse overlooking Madrid at night", "noche", "practical"),
    ("a bustling Moroccan spice market", "día", "soft_window"),
    ("an underground jazz club filled with smoke", "noche", "practical"),
    ("a frozen Nordic fjord under the aurora", "noche", "moonlight"),
    ("a sun-drenched vineyard in La Rioja", "atardecer", "golden_hour"),
    ("a futuristic research lab with holographic displays", "noche", "neon"),
    ("an old fishing harbor with weathered boats", "amanecer", "golden_hour"),
    ("a mossy ancient forest with giant redwoods", "mañana", "volumetric"),
    ("a minimalist white photo studio with a cyclorama", "estudio", "studio_beauty"),
    ("a desert highway motel with a flickering sign", "anochecer", "neon"),
]
ERAS = ["contemporary", "1970s", "1980s", "1920s", "near future 2049", "medieval", "Victorian era", "1950s", "post-apocalyptic future"]
WEATHER = ["light drizzle", "heavy rain", "dense fog", "clear sky", "scattered clouds", "snowfall", "dust storm", "humid heat haze", "strong wind"]
AMBIENCE = ["distant traffic hum", "waves crashing", "crickets and wind", "crowd murmur", "rain on metal roofs", "birdsong", "low electrical buzz", "church bells far away"]

# ------------------------------------------------------------------ español → inglés
ES_EN = {
    # personas
    "mujer": "woman", "hombre": "man", "chica": "young woman", "chico": "young man", "niña": "little girl", "niño": "little boy",
    "anciana": "elderly woman", "anciano": "elderly man", "persona": "person", "personaje": "character", "señora": "middle-aged woman", "señor": "middle-aged man",
    # pelo
    "rubia": "blonde", "rubio": "blonde", "morena": "dark-haired", "moreno": "dark-haired", "pelirroja": "red-haired", "pelirrojo": "red-haired",
    "castaña": "chestnut-haired", "castaño": "chestnut-haired", "canosa": "grey-haired", "canoso": "grey-haired", "calvo": "bald", "barba": "beard",
    "rizos": "curly hair", "rizado": "curly", "pelo largo": "long hair", "pelo corto": "short hair", "trenzas": "braids",
    # ojos
    "ojos azules": "blue eyes", "ojos verdes": "green eyes", "ojos marrones": "brown eyes", "ojos negros": "dark eyes", "ojos grises": "grey eyes", "ojos miel": "honey-colored eyes",
    # roles
    "detective": "detective", "cocinero": "chef", "cocinera": "chef", "astronauta": "astronaut", "médico": "doctor", "médica": "doctor", "doctora": "doctor",
    "guerrera": "warrior", "guerrero": "warrior", "empresaria": "businesswoman", "empresario": "businessman", "científica": "scientist", "científico": "scientist",
    "piloto": "pilot", "enfermera": "nurse", "enfermero": "nurse", "estudiante": "student", "exploradora": "explorer", "explorador": "explorer",
    "música": "musician", "músico": "musician", "agricultor": "farmer", "agricultora": "farmer", "deportista": "athlete", "bailarina": "dancer", "bailarín": "dancer",
    "pescador": "fisherman", "relojero": "watchmaker", "relojera": "watchmaker", "camarero": "waiter", "camarera": "waitress", "policía": "police officer", "abogada": "lawyer", "abogado": "lawyer", "pintora": "painter", "pintor": "painter", "soldado": "soldier", "reina": "queen", "rey": "king", "bruja": "witch", "mago": "wizard",
    # lugares
    "ciudad": "city", "calle": "street", "playa": "beach", "mar": "sea", "montaña": "mountain", "bosque": "forest", "desierto": "desert", "selva": "jungle",
    "oficina": "office", "cocina": "kitchen", "casa": "house", "pueblo": "village", "puerto": "harbor", "estación": "station", "espacio": "outer space",
    "lluvia": "rain", "nieve": "snow", "niebla": "fog", "noche": "night", "atardecer": "sunset", "amanecer": "dawn", "tormenta": "storm",
    # acciones
    "camina": "walks", "corre": "runs", "mira": "looks", "sonríe": "smiles", "llora": "cries", "baila": "dances", "habla": "talks", "gira": "turns",
    "conduce": "drives", "bebe": "drinks", "come": "eats", "lucha": "fights", "salta": "jumps", "vuela": "flies", "abraza": "hugs",
    # estilo
    "épico": "epic", "épica": "epic", "oscuro": "dark", "oscura": "dark", "elegante": "elegant", "futurista": "futuristic", "antiguo": "ancient",
    "realista": "realistic", "hiperrealista": "hyperrealistic", "cinematográfico": "cinematic", "lujo": "luxury", "moderno": "modern",
}
