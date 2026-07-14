from unittest.mock import patch

import pytest
from PIL import Image

from renderer.render import AsyncFrameWriter, RenderDual, RendererBase


def make_renderer():
    renderer = RendererBase.__new__(RendererBase)
    renderer.minimap_bg = Image.new("RGBA", (1360, 850))
    renderer.logs = True
    renderer.render_scale = 1
    renderer.output_size = (1360, 850)
    return renderer


@patch("renderer.render.write_frames")
def test_writer_encodes_directly_at_render_resolution(write_frames):
    renderer = make_renderer()
    renderer.minimap_bg = Image.new("RGBA", (1920, 1200))

    renderer.get_writer(
        "output.mp4",
        fps=60,
        quality=8,
        speed=15,
        resolution=(1920, 1200),
        interpolation="native",
    )

    kwargs = write_frames.call_args.kwargs
    assert kwargs["fps"] == 60
    assert kwargs["size"] == (1920, 1200)
    assert kwargs["pix_fmt_in"] == "rgb24"
    assert "-vf" not in kwargs["output_params"]


@patch("renderer.render.write_frames")
@pytest.mark.parametrize(
    ("interpolation", "expected_filter"),
    [
        ("native", None),
        ("blend", "framerate=fps=60"),
        ("motion", "minterpolate=fps=60"),
        ("duplicate", "fps=60"),
    ],
)
def test_writer_supports_interpolation_modes(
    write_frames, interpolation, expected_filter
):
    renderer = make_renderer()

    renderer.get_writer(
        "output.mp4",
        fps=60,
        quality=8,
        speed=15,
        interpolation=interpolation,
    )

    kwargs = write_frames.call_args.kwargs
    if expected_filter is None:
        assert kwargs["fps"] == 60
        assert "-vf" not in kwargs["output_params"]
    else:
        filter_value = kwargs["output_params"][
            kwargs["output_params"].index("-vf") + 1
        ]
        assert expected_filter in filter_value


@patch("renderer.render.write_frames")
def test_writer_keeps_legacy_behavior_without_speed(write_frames):
    renderer = make_renderer()

    renderer.get_writer("output.mp4", fps=20, quality=7)

    kwargs = write_frames.call_args.kwargs
    assert kwargs["fps"] == 20
    assert "-vf" not in kwargs["output_params"]


def test_resolution_configures_native_canvas_scale():
    renderer = make_renderer()
    renderer.resman = type(
        "Resources", (), {"set_render_scale": lambda _, scale: None}
    )()

    renderer._configure_resolution((1920, 1200))

    assert renderer.render_scale == pytest.approx(24 / 17)
    assert renderer.output_size == (1920, 1200)
    assert renderer.map_origin == (56, 127)


def test_resolution_rejects_non_native_aspect_ratio():
    renderer = make_renderer()
    renderer.resman = type(
        "Resources", (), {"set_render_scale": lambda _, scale: None}
    )()

    with pytest.raises(ValueError, match="aspect ratio"):
        renderer._configure_resolution((1920, 1080))


def test_dual_render_rejects_unimplemented_native_mode():
    renderer = RenderDual.__new__(RenderDual)

    with pytest.raises(ValueError, match="dual renders"):
        renderer.start("output.mp4", interpolation="native")


@pytest.mark.parametrize(
    ("option", "value"),
    [
        ("fps", 0),
        ("speed", 0),
        ("resolution", (1920, 0)),
        ("interpolation", "invalid"),
    ],
)
def test_writer_rejects_invalid_video_options(option, value):
    renderer = make_renderer()
    options = {
        "fps": 60,
        "quality": 8,
        "speed": 15,
        "resolution": (1920, 1200),
        "interpolation": "blend",
    }
    options[option] = value

    with pytest.raises(ValueError):
        renderer.get_writer("output.mp4", **options)


def test_async_writer_preserves_frame_order_and_closes():
    received = []

    class Writer:
        def send(self, frame):
            received.append(frame)

        def close(self):
            received.append("closed")

    writer = AsyncFrameWriter(Writer(), queue_size=1)
    writer.send(None)
    writer.send(b"first")
    writer.send(b"second")
    writer.close()

    assert received == [None, b"first", b"second", "closed"]


def test_async_writer_propagates_worker_errors():
    class Writer:
        def send(self, frame):
            if frame is not None:
                raise OSError("write failed")

        def close(self):
            pass

    writer = AsyncFrameWriter(Writer(), queue_size=1)
    writer.send(None)
    writer.send(b"frame")

    with pytest.raises(OSError, match="write failed"):
        writer.close()


def test_async_writer_snapshots_images_before_enqueue():
    received = []

    class Writer:
        def send(self, frame):
            if frame is not None:
                received.append(frame)

        def close(self):
            pass

    image = Image.new("RGBA", (1, 1), (10, 20, 30, 255))
    writer = AsyncFrameWriter(Writer(), queue_size=1)
    writer.send(None)
    writer.send_image(image)
    image.putpixel((0, 0), (200, 210, 220, 255))
    writer.close()

    assert received == [bytes((10, 20, 30))]
