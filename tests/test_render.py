from __future__ import annotations

import asyncio
import json
import subprocess

import pytest

from durostcm.core.media import import_file, needs_proxy
from durostcm.core.project import Clip, Effect, Keyframe, Motion, TextStyle, Transition
from durostcm.core.render import RenderSettings, export_srt, render_frame, render_project
from durostcm.core.storage import get_store


def ffprobe(path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


@pytest.fixture()
def project(home, media_dir):
    store = get_store()
    p = store.create("Test", width=1280, height=720, fps=25)
    a = import_file(store, p, media_dir / "clip_a.mp4")
    b = import_file(store, p, media_dir / "clip_b.mp4")
    still = import_file(store, p, media_dir / "still.png")
    music = import_file(store, p, media_dir / "music.wav")
    v1, v2, titles, a1, a2 = p.tracks
    v1.clips += [
        Clip(media_id=a.id, start=0, duration=3, in_point=0.5),
        Clip(media_id=b.id, start=2.5, duration=2.5, transition_in=Transition(type="wipeleft", duration=0.5)),
        Clip(media_id=still.id, start=5, duration=2, motion=Motion(preset="push_in"), transition_in=Transition(type="fade", duration=0.4)),
    ]
    pip = Clip(media_id=a.id, start=1, duration=2, speed=1.5, effects=[Effect(type="bw")])
    pip.transform.scale = 0.35
    pip.transform.x = 0.8
    pip.transform.rotation = 5
    pip.keyframes["opacity"] = [Keyframe(t=0, value=0), Keyframe(t=1, value=1)]
    pip.keyframes["y"] = [Keyframe(t=0, value=0.2), Keyframe(t=2, value=0.4, easing="ease_in_out")]
    v2.clips.append(pip)
    titles.clips.append(Clip(kind="text", start=0.5, duration=2, text=TextStyle(content="Hola durosTCM", animation="slide_up")))
    subs = type(titles)(name="Subtítulos", kind="text")
    subs.clips.append(Clip(kind="text", start=1, duration=1.5, text=TextStyle(content="Primera línea", animation="none")))
    p.tracks.insert(3, subs)
    a2.clips.append(Clip(media_id=music.id, start=0, duration=7, volume=0.5, audio_fade_out=1,
                         keyframes={"volume": [Keyframe(t=0, value=1), Keyframe(t=2, value=0.3)]}))
    store.save(p)
    return p


def test_media_probe(project):
    kinds = sorted(m.kind for m in project.media)
    assert kinds == ["audio", "image", "video", "video"]
    vid = next(m for m in project.media if m.name == "clip_a.mp4")
    assert vid.has_audio and vid.width == 640 and abs(vid.duration - 4) < 0.2
    assert vid.thumbnail and vid.waveform


def test_proxy_detection(home, media_dir):
    store = get_store()
    p = store.create("P")
    m = import_file(store, p, media_dir / "prores.mov")
    assert needs_proxy(m)


def test_render_full(project):
    store = get_store()
    res = asyncio.run(render_project(store, project, RenderSettings(format="mp4_h264", quality="draft")))
    out = store.resolve(project.id, res["path"])
    info = ffprobe(out)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    a = next(s for s in info["streams"] if s["codec_type"] == "audio")
    assert (v["width"], v["height"]) == (1280, 720)
    assert abs(float(info["format"]["duration"]) - project.duration) < 0.15
    assert a["codec_name"] == "aac"
    assert any(e.endswith(".provenance.json") for e in res["extras"])
    assert any(e.endswith(".srt") for e in res["extras"])


@pytest.mark.parametrize("fmt", ["mov_prores_4444", "webm_vp9", "gif", "png_still", "wav", "png_sequence", "mxf_dnxhr_hq"])
def test_render_formats(project, fmt):
    store = get_store()
    s = RenderSettings(format=fmt, quality="draft", start=1, end=2.2, width=640, height=360, transparent=fmt == "mov_prores_4444")
    res = asyncio.run(render_project(store, project, s))
    out = store.resolve(project.id, res["path"])
    assert out.exists() and out.stat().st_size > 1000
    if fmt == "mov_prores_4444":
        v = ffprobe(out)["streams"][0]
        assert "a" in v["pix_fmt"].replace("yuv", "")  # yuva444p…


def test_render_reframe_vertical(project):
    store = get_store()
    s = RenderSettings(format="mp4_h264", quality="draft", width=720, height=1280, reframe="blur_fill", end=1.5, loudness=-14)
    res = asyncio.run(render_project(store, project, s))
    v = ffprobe(store.resolve(project.id, res["path"]))["streams"][0]
    assert (v["width"], v["height"]) == (720, 1280)


def test_render_frame(project):
    store = get_store()
    p = asyncio.run(render_frame(store, project, 2.7, max_h=360))
    assert p.exists() and p.stat().st_size > 1000


def test_srt(project, tmp_path):
    out = export_srt(project, tmp_path / "x.srt")
    assert out is not None
    txt = out.read_text()
    assert "Primera línea" in txt and "00:00:01,000 --> 00:00:02,500" in txt
