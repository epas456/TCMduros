from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def home(tmp_path, monkeypatch):
    """Instancia aislada de durosTCM en una carpeta temporal."""
    monkeypatch.setenv("DUROSTCM_HOME", str(tmp_path / "home"))
    from durostcm import config
    from durostcm.ai import registry
    from durostcm.core import jobs, storage

    cfg = config.AppConfig(tmp_path / "home")
    config.set_config(cfg)
    storage._store = None
    jobs.reset_jobs()
    registry._registry = None
    yield cfg
    config._config = None


@pytest.fixture(scope="session")
def media_dir(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("media")

    def ff(*args):
        subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)

    ff("-f", "lavfi", "-i", "testsrc2=s=640x360:r=25:d=4", "-f", "lavfi", "-i", "sine=f=440:d=4", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(d / "clip_a.mp4"))
    ff("-f", "lavfi", "-i", "smptebars=s=480x360:r=30:d=3", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(d / "clip_b.mp4"))
    ff("-f", "lavfi", "-i", "color=c=0x3366AA:s=800x600:d=1", "-frames:v", "1", str(d / "still.png"))
    ff("-f", "lavfi", "-i", "sine=f=220:d=6", "-ac", "2", str(d / "music.wav"))
    ff("-f", "lavfi", "-i", "testsrc2=s=320x240:r=24:d=2", "-c:v", "prores_ks", str(d / "prores.mov"))
    return d
