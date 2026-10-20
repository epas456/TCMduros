"""Intercambio con otros programas: EDL (CMX3600), FCPXML (Final Cut / DaVinci Resolve) y OpenTimelineIO."""

from __future__ import annotations

import json
from fractions import Fraction
from xml.sax.saxutils import escape, quoteattr

from .project import Project
from .storage import ProjectStore


def _fps_frac(fps: float) -> Fraction:
    for nominal in (24, 30, 60):
        if abs(fps - nominal * 1000 / 1001) < 0.005:
            return Fraction(nominal * 1000, 1001)
    return Fraction(fps).limit_denominator(1000)


def _tc(t: float, fps: float) -> str:
    nfps = int(round(fps))
    frames = int(round(t * fps))
    f = frames % nfps
    s = frames // nfps
    return f"{s // 3600:02d}:{(s // 60) % 60:02d}:{s % 60:02d}:{f:02d}"


def export_edl(p: Project) -> str:
    fps = p.settings.fps
    lines = [f"TITLE: {p.name[:60]}", "FCM: NON-DROP FRAME", ""]
    n = 0
    for t in p.tracks:
        if t.kind not in ("video", "audio"):
            continue
        kind = "V" if t.kind == "video" else "AA"
        for c in sorted(t.clips, key=lambda c: c.start):
            if c.kind != "media":
                continue
            m = p.media_by_id(c.media_id)
            if m is None:
                continue
            n += 1
            src_in = c.in_point
            src_out = c.in_point + c.source_duration
            lines.append(f"{n:03d}  AX       {kind:<5} C        {_tc(src_in, fps)} {_tc(src_out, fps)} {_tc(c.start, fps)} {_tc(c.end, fps)}")
            lines.append(f"* FROM CLIP NAME: {m.name}")
            if abs(c.speed - 1) > 1e-3:
                lines.append(f"M2   AX       {c.speed * fps:05.1f}                {_tc(src_in, fps)}")
            lines.append("")
    return "\n".join(lines)


def export_fcpxml(p: Project, store: ProjectStore) -> str:
    fr = _fps_frac(p.settings.fps)

    def rt(t: float) -> str:
        frames = int(round(t * float(fr)))
        v = Fraction(frames) / fr
        return f"{v.numerator}/{v.denominator}s" if v.denominator != 1 else f"{v.numerator}s"

    fd = 1 / fr
    res = [f'<format id="r0" name="durosTCM {p.settings.width}x{p.settings.height}" frameDuration="{fd.numerator}/{fd.denominator}s" width="{p.settings.width}" height="{p.settings.height}"/>']
    asset_ids: dict[str, str] = {}
    for i, m in enumerate(p.media):
        aid = f"a{i + 1}"
        asset_ids[m.id] = aid
        src = store.resolve(p.id, m.path).as_uri()
        dur = rt(m.duration or 3600)
        res.append(
            f'<asset id="{aid}" name={quoteattr(m.name)} start="0s" duration="{dur}" hasVideo="{1 if m.kind != "audio" else 0}" '
            f'hasAudio="{1 if m.has_audio else 0}" format="r0" src={quoteattr(src)}/>'
        )
    total = p.duration or 1
    lane_v, lane_a = 0, 0
    clips_xml = []
    for t in p.tracks:
        if t.kind == "text":
            continue
        if t.kind == "video":
            lane_v += 1
            lane = lane_v
        else:
            lane_a -= 1
            lane = lane_a
        for c in sorted(t.clips, key=lambda c: c.start):
            if c.kind != "media" or c.media_id not in asset_ids:
                continue
            m = p.media_by_id(c.media_id)
            start = rt(c.in_point) if m and m.kind != "image" else "0s"
            clips_xml.append(
                f'<asset-clip ref="{asset_ids[c.media_id]}" lane="{lane}" offset="{rt(c.start)}" duration="{rt(c.duration)}" start="{start}" name={quoteattr(c.name or (m.name if m else ""))}/>'
            )
    titles = []
    for t in p.tracks:
        if t.kind != "text":
            continue
        for c in t.clips:
            if c.text:
                titles.append(f"<!-- Rótulo {rt(c.start)}: {escape(c.text.content[:80])} -->")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n<fcpxml version="1.9">\n'
        f'  <resources>\n    {chr(10).join("    " + r for r in res).strip()}\n  </resources>\n'
        f'  <library>\n    <event name="durosTCM">\n      <project name={quoteattr(p.name)}>\n'
        f'        <sequence format="r0" duration="{rt(total)}" tcStart="0s" tcFormat="NDF" audioLayout="stereo" audioRate="48k">\n'
        f'          <spine>\n            <gap name="Base" offset="0s" duration="{rt(total)}" start="0s">\n'
        + "\n".join("              " + x for x in clips_xml + titles)
        + "\n            </gap>\n          </spine>\n        </sequence>\n      </project>\n    </event>\n  </library>\n</fcpxml>\n"
    )


def export_otio_json(p: Project, store: ProjectStore) -> str:
    rate = p.settings.fps

    def rt(t: float) -> dict:
        return {"OTIO_SCHEMA": "RationalTime.1", "rate": rate, "value": round(t * rate, 3)}

    def tr(start: float, dur: float) -> dict:
        return {"OTIO_SCHEMA": "TimeRange.1", "start_time": rt(start), "duration": rt(dur)}

    tracks = []
    for t in p.tracks:
        if t.kind == "text":
            continue
        children = []
        cursor = 0.0
        for c in sorted(t.clips, key=lambda c: c.start):
            if c.kind != "media":
                continue
            m = p.media_by_id(c.media_id)
            if m is None:
                continue
            if c.start > cursor + 1e-6:
                children.append({"OTIO_SCHEMA": "Gap.1", "name": "", "source_range": tr(0, c.start - cursor), "effects": [], "markers": [], "metadata": {}})
            ref = {"OTIO_SCHEMA": "ExternalReference.1", "target_url": store.resolve(p.id, m.path).as_uri(),
                   "available_range": tr(0, m.duration or c.source_duration), "metadata": {}}
            effects = []
            if abs(c.speed - 1) > 1e-3:
                effects.append({"OTIO_SCHEMA": "LinearTimeWarp.1", "name": "", "effect_name": "LinearTimeWarp", "time_scalar": c.speed, "metadata": {}})
            children.append({"OTIO_SCHEMA": "Clip.2", "name": c.name or m.name, "source_range": tr(c.in_point, c.duration),
                             "media_references": {"DEFAULT_MEDIA": ref}, "active_media_reference_key": "DEFAULT_MEDIA",
                             "effects": effects, "markers": [], "metadata": {"durostcm": {"clip_id": c.id}}})
            cursor = c.end
        tracks.append({"OTIO_SCHEMA": "Track.1", "name": t.name, "kind": "Video" if t.kind == "video" else "Audio", "children": children,
                       "source_range": None, "effects": [], "markers": [], "metadata": {}})
    timeline = {"OTIO_SCHEMA": "Timeline.1", "name": p.name, "global_start_time": None, "metadata": {"durostcm": {"project_id": p.id}},
                "tracks": {"OTIO_SCHEMA": "Stack.1", "name": "tracks", "children": tracks, "source_range": None, "effects": [], "markers": [], "metadata": {}}}
    return json.dumps(timeline, ensure_ascii=False, indent=1)
