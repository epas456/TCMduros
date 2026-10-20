// Tipos espejo de los modelos del backend (durostcm/core/project.py, library.py…)

export interface Credit {
  title: string;
  creator: string;
  license: string;
  license_url: string;
  source_url: string;
  provider: string;
  attribution: string;
}

export interface Generation {
  engine: string;
  model: string;
  capability: string;
  prompt: string;
  negative: string;
  seed: number | null;
  params: Record<string, unknown>;
  created: number;
}

export type MediaKind = "video" | "image" | "audio";

export interface MediaItem {
  id: string;
  name: string;
  kind: MediaKind;
  path: string;
  duration: number | null;
  width: number | null;
  height: number | null;
  fps: number | null;
  has_audio: boolean;
  has_video: boolean;
  vcodec: string | null;
  acodec: string | null;
  size_bytes: number | null;
  proxy: string | null;
  thumbnail: string | null;
  waveform: string | null;
  source: string;
  ai_generated: boolean;
  generation: Generation | null;
  credit: Credit | null;
  tags: string[];
  created: number;
}

export interface Crop {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

export interface Transform {
  x: number;
  y: number;
  scale: number;
  rotation: number;
  opacity: number;
  fit: "cover" | "contain" | "stretch" | "none";
  flip_h: boolean;
  flip_v: boolean;
  crop: Crop;
}

export interface ColorGrade {
  exposure: number;
  contrast: number;
  saturation: number;
  gamma: number;
  temperature: number;
  tint: number;
  shadows: number;
  highlights: number;
  vignette: number;
  grain: number;
  sharpen: number;
  blur: number;
  look: string | null;
  lut: string | null;
  lut_intensity: number;
}

export interface Effect {
  type: string;
  enabled: boolean;
  params: Record<string, unknown>;
}

export interface Transition {
  type: string;
  duration: number;
}

export type MotionPreset = "none" | "push_in" | "pull_out" | "pan_left" | "pan_right" | "tilt_up" | "tilt_down" | "handheld" | "drift";

export interface Motion {
  preset: MotionPreset;
  intensity: number;
}

export type Easing = "linear" | "ease_in" | "ease_out" | "ease_in_out" | "hold";

export interface Keyframe {
  t: number;
  value: number;
  easing: Easing;
}

export interface TextStyle {
  content: string;
  font: string;
  size: number;
  weight: "normal" | "bold";
  color: string;
  stroke_color: string;
  stroke_width: number;
  shadow: boolean;
  background: string | null;
  align: "left" | "center" | "right";
  line_spacing: number;
  letter_spacing: number;
  max_width: number;
  animation: "none" | "fade" | "slide_up" | "slide_down" | "zoom" | "typewriter";
  uppercase: boolean;
}

export type ClipKind = "media" | "text" | "color" | "adjustment";

export interface Clip {
  id: string;
  kind: ClipKind;
  media_id: string | null;
  name: string;
  start: number;
  duration: number;
  in_point: number;
  speed: number;
  reverse: boolean;
  volume: number;
  muted: boolean;
  audio_fade_in: number;
  audio_fade_out: number;
  fade_in: number;
  fade_out: number;
  transform: Transform;
  color: ColorGrade;
  effects: Effect[];
  transition_in: Transition | null;
  motion: Motion;
  keyframes: Record<string, Keyframe[]>;
  text: TextStyle | null;
  fill: string;
  label_color: string | null;
  locked: boolean;
}

export type TrackKind = "video" | "audio" | "text";

export interface Track {
  id: string;
  name: string;
  kind: TrackKind;
  clips: Clip[];
  muted: boolean;
  hidden: boolean;
  locked: boolean;
  solo: boolean;
  volume: number;
}

export interface Marker {
  id: string;
  t: number;
  label: string;
  color: string;
}

export interface Camera {
  shot_size: string;
  angle: string;
  movement: string;
  lens: string;
}

export interface DialogueLine {
  speaker: string;
  text: string;
  voice: string | null;
}

export interface Shot {
  id: string;
  index: number;
  scene: string;
  description: string;
  prompt: string;
  negative: string;
  duration: number;
  camera: Camera;
  lighting: string;
  mood: string;
  characters: string[];
  location: string | null;
  dialogue: DialogueLine[];
  on_screen_text: string;
  sfx: string;
  transition: string;
  seed: number | null;
  image_media_id: string | null;
  video_media_id: string | null;
  audio_media_ids: string[];
  status: "draft" | "image" | "video" | "done" | "error";
}

export interface Storyboard {
  title: string;
  logline: string;
  format: string;
  style: string;
  look: string | null;
  language: string;
  music_prompt: string;
  voiceover: string;
  shots: Shot[];
}

export interface ProjectSettings {
  width: number;
  height: number;
  fps: number;
  sample_rate: number;
  background: string;
}

export interface Project {
  id: string;
  name: string;
  version: number;
  rev: number;
  created: number;
  updated: number;
  settings: ProjectSettings;
  media: MediaItem[];
  tracks: Track[];
  markers: Marker[];
  storyboard: Storyboard | null;
  characters: string[];
  locations: string[];
  credits: Credit[];
  notes: string;
}

export interface ProjectSummary {
  id: string;
  name: string;
  updated: number;
  created: number;
  width: number;
  height: number;
  fps: number;
  media_count: number;
  thumbnail: string | null;
}

export type JobStatus = "queued" | "running" | "done" | "error" | "cancelled";

export interface Job {
  id: string;
  kind: string;
  title: string;
  project_id: string | null;
  pool: string;
  status: JobStatus;
  progress: number;
  stage: string;
  created: number;
  started: number | null;
  finished: number | null;
  eta: number | null;
  result: any;
  error: string | null;
  logs: string[];
  parent_id: string | null;
}

export interface Voice {
  engine: string;
  voice_id: string;
  description: string;
  speed: number;
}

export interface Character {
  id: string;
  name: string;
  role: string;
  age: number | null;
  gender: string;
  heritage: string;
  face: string;
  skin: string;
  hair: string;
  eyes: string;
  build: string;
  wardrobe: string;
  signature: string;
  personality: string;
  mannerisms: string;
  backstory: string;
  voice: Voice;
  identity_prompt: string;
  negative: string;
  seed: number | null;
  reference_images: string[];
  hero_image: string | null;
  lora: string | null;
  inspiration: Credit[];
  consent_id: string | null;
  is_real_person: boolean;
  tags: string[];
  created: number;
  updated: number;
}

export interface Location {
  id: string;
  name: string;
  description: string;
  era: string;
  time_of_day: string;
  weather: string;
  lighting: string;
  palette: string;
  props: string;
  ambience: string;
  identity_prompt: string;
  seed: number | null;
  reference_images: string[];
  hero_image: string | null;
  tags: string[];
}

export interface FaceResult {
  id: string;
  provider: string;
  title: string;
  thumb_url: string;
  url: string;
  landing_url: string;
  creator: string;
  license: string;
  license_url: string;
  attribution: string;
  width: number | null;
  height: number | null;
  commercial_ok: boolean;
  modification_ok: boolean;
  requires_attribution: boolean;
}

export interface FaceRef {
  id: string;
  file: string;
  thumb: string | null;
  credit: Credit;
  description: string;
  tags: string[];
  consent_id: string | null;
  created: number;
}

export interface Consent {
  id: string;
  person_name: string;
  document: string;
  scope: string;
  valid_until: string;
  signed_on: string;
  notes: string;
}

export interface EngineInfo {
  id: string;
  name: string;
  description: string;
  capabilities: string[];
  quality: string;
  status: { available: boolean; detail: string; models: string[]; quality: string };
}

export interface CapabilityInfo {
  label: string;
  engines: string[];
  best: string | null;
  quality: string | null;
}

export interface FormatInfo {
  id: string;
  label: string;
  ext: string;
  kind: string;
  alpha: boolean;
  description: string;
  available: boolean;
}

export interface Presets {
  formats: FormatInfo[];
  resolutions: { id: string; label: string; w: number; h: number }[];
  aspects: { id: string; label: string; ratio: number }[];
  platforms: { id: string; label: string; format: string; w: number; h: number; fps: number | null; loudness: number | null; quality: string; no_audio?: boolean }[];
  fps: number[];
  qualities: string[];
  looks: { id: string; label: string; grade: Partial<ColorGrade> }[];
  effects: { id: string; label: string; params: Record<string, unknown> }[];
  audio_effects: { id: string; label: string; params: Record<string, unknown> }[];
  transitions: string[];
}

export interface WorkflowInfo {
  id: string;
  label: string;
  capability: string;
  tier?: number;
  vram?: number;
  available: boolean | null;
  missing: string[];
  license?: string;
  builtin?: boolean;
}
