import argparse
import json
from pathlib import Path
from renderer.render import INTERPOLATION_MODES, Renderer
from replay_parser import ReplayParser
from renderer.utils import LOGGER


def resolution(value: str) -> tuple[int, int]:
    try:
        width, height = map(int, value.lower().split("x", maxsplit=1))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "resolution must use WIDTHxHEIGHT, for example 1920x1200"
        ) from exc

    if width <= 0 or height <= 0 or width % 2 or height % 2:
        raise argparse.ArgumentTypeError(
            "resolution width and height must be positive even numbers"
        )
    return width, height


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--replay", type=str, required=True)
    parser.add_argument(
        "--fps", type=int, default=60, help="output frame rate (default: 60)"
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=15,
        help="timelapse playback speed (default: 15x)",
    )
    parser.add_argument(
        "--resolution",
        type=resolution,
        default=(1920, 1200),
        metavar="WIDTHxHEIGHT",
        help="output resolution (default: 1920x1200)",
    )
    parser.add_argument(
        "--quality",
        type=int,
        choices=range(1, 11),
        default=8,
        metavar="1-10",
        help="encoding quality (default: 8)",
    )
    parser.add_argument(
        "--interpolation",
        choices=INTERPOLATION_MODES,
        default="blend",
        help="frame interpolation mode (default: blend)",
    )
    namespace = parser.parse_args()
    if namespace.fps <= 0:
        parser.error("--fps must be greater than 0")
    if namespace.speed <= 0:
        parser.error("--speed must be greater than 0")
    path = Path(namespace.replay)
    video_path = path.parent.joinpath(f"{path.stem}.mp4")
    with open(namespace.replay, "rb") as f:
        LOGGER.info("Parsing the replay file...")
        replay_info = ReplayParser(
            f, strict=True, raw_data_output=False
        ).get_info()
        LOGGER.info(f"Replay has version {replay_info['open']['clientVersionFromExe']}")
        LOGGER.info("Rendering the replay file...")
        renderer = Renderer(
            replay_info["hidden"]["replay_data"],
            logs=True,
            enable_chat=True,
            use_tqdm=True,
        )
        with open(path.parent.joinpath(f"{path.stem}-builds.json"), "w") as fp:
            json.dump(renderer.get_player_build(), fp, indent=4)
        renderer.start(
            str(video_path),
            fps=namespace.fps,
            speed=namespace.speed,
            resolution=namespace.resolution,
            quality=namespace.quality,
            interpolation=namespace.interpolation,
        )
        LOGGER.info(f"The video file is at: {str(video_path)}")
        LOGGER.info("Done.")
