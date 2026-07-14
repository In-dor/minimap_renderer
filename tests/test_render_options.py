from unittest.mock import patch

import pytest
from PIL import Image

from renderer.render import RendererBase


def make_renderer():
    renderer = RendererBase.__new__(RendererBase)
    renderer.minimap_bg = Image.new("RGBA", (1360, 850))
    renderer.logs = True
    return renderer


@patch("renderer.render.write_frames")
def test_writer_separates_frame_rate_speed_and_resolution(write_frames):
    renderer = make_renderer()

    renderer.get_writer(
        "output.mp4", fps=60, quality=8, speed=15, resolution=(1920, 1200)
    )

    kwargs = write_frames.call_args.kwargs
    assert kwargs["fps"] == 15
    assert kwargs["size"] == (1360, 850)
    filter_value = kwargs["output_params"][kwargs["output_params"].index("-vf") + 1]
    assert "minterpolate=fps=60" in filter_value
    assert "scale=1920:1200:flags=lanczos" in filter_value


@patch("renderer.render.write_frames")
def test_writer_keeps_legacy_behavior_without_speed(write_frames):
    renderer = make_renderer()

    renderer.get_writer("output.mp4", fps=20, quality=7)

    kwargs = write_frames.call_args.kwargs
    assert kwargs["fps"] == 20
    assert "-vf" not in kwargs["output_params"]


@pytest.mark.parametrize(
    ("option", "value"),
    [("fps", 0), ("speed", 0), ("resolution", (1920, 0))],
)
def test_writer_rejects_invalid_video_options(option, value):
    renderer = make_renderer()
    options = {
        "fps": 60,
        "quality": 8,
        "speed": 15,
        "resolution": (1920, 1200),
    }
    options[option] = value

    with pytest.raises(ValueError):
        renderer.get_writer("output.mp4", **options)
