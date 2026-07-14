from json import JSONDecodeError
from math import ceil
from typing import Any, Callable, Optional, Type, Union
from importlib import import_module
from renderer.base import LayerBase

from renderer.const import LAYERS
from renderer.data import ReplayData
from renderer.utils import draw_grid, LOGGER
from renderer.resman import ResourceManager
from renderer.conman import ConsumableManager
from renderer.exceptions import MapLoadError
from renderer.shipbuilder import ShipBuilder
from renderer.temporal import interpolate_events, native_timeline
from PIL import Image, ImageDraw
from imageio_ffmpeg import write_frames
from tqdm import tqdm

Number = Union[int, float]
INTERPOLATION_MODES = ("native", "blend", "motion", "duplicate")


class RendererBase:
    replay_data: ReplayData
    minimap_fg: Image.Image
    minimap_bg: Image.Image
    minimap_size: int
    minimap_space_size: int
    minimap_scaling: float
    bg_color: tuple[int]
    resman: ResourceManager
    logs: bool
    conman: ConsumableManager

    def __init__(self, replay_data: ReplayData) -> None:
        self.replay_data: ReplayData = replay_data
        self.resman = ResourceManager(self.replay_data.game_version)
        self.conman = ConsumableManager([self.replay_data])
        self.render_scale = 1.0
        self.frame_delta = 1.0
        self.map_origin = (40, 90)

    def px(self, value: Number) -> int:
        return round(value * self.render_scale)

    def xy(self, xy: tuple[Number, Number]) -> tuple[int, int]:
        return self.px(xy[0]), self.px(xy[1])

    def _configure_resolution(
        self, resolution: Optional[tuple[int, int]]
    ) -> None:
        base_size = (1360, 850) if getattr(self, "logs", False) else (800, 850)
        target_size = resolution or base_size
        if any(value <= 0 for value in target_size):
            raise ValueError("resolution dimensions must be greater than 0")
        if target_size[0] * base_size[1] != target_size[1] * base_size[0]:
            raise ValueError(
                f"resolution must preserve the native {base_size[0]}:{base_size[1]} aspect ratio"
            )
        self.render_scale = target_size[0] / base_size[0]
        self.output_size = target_size
        self.map_origin = self.xy((40, 90))
        self.resman.set_render_scale(self.render_scale)

    def get_writer(
        self,
        path: str,
        fps: int,
        quality: int,
        speed: Optional[float] = None,
        resolution: Optional[tuple[int, int]] = None,
        interpolation: str = "blend",
    ):
        if fps <= 0:
            raise ValueError("fps must be greater than 0")
        if speed is not None and speed <= 0:
            raise ValueError("speed must be greater than 0")
        if resolution is not None and any(value <= 0 for value in resolution):
            raise ValueError("resolution dimensions must be greater than 0")
        if interpolation not in INTERPOLATION_MODES:
            raise ValueError(
                f"interpolation must be one of: {', '.join(INTERPOLATION_MODES)}"
            )

        output_params = [
            "-profile:v",
            "high",
            "-movflags",
            "+faststart",
            "-tune",
            "animation",
        ]
        filters = []
        input_fps = fps if interpolation == "native" else (
            speed if speed is not None else fps
        )

        if interpolation != "native" and speed is not None and fps > speed:
            if interpolation == "motion":
                filters.append(
                    f"minterpolate=fps={fps}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir"
                )
            elif interpolation == "blend":
                filters.append(f"framerate=fps={fps}")
            else:
                filters.append(f"fps={fps}")
        elif interpolation != "native" and speed is not None and fps < speed:
            filters.append(f"fps={fps}")

        if resolution is not None and self.minimap_bg.size != resolution:
            raise ValueError("render canvas does not match the requested resolution")

        if filters:
            output_params.extend(["-vf", ",".join(filters)])

        return write_frames(
            path=path,
            fps=input_fps,
            quality=quality,
            pix_fmt_in="rgba",
            macro_block_size=2,
            size=self.minimap_bg.size,
            output_params=output_params,
        )

    def _load_map(self):
        """Loads the map.

        Raises:
            MapLoadError: Raised when an error occurs when loading a map
            resource.
            MapManifestLoadError: Raised when an error occurs when loading maps
            manifest.
        """

        map_name = self.replay_data.game_map

        self._load_map_manifest()
        path = f"spaces.{map_name}"

        try:
            map_legends = self.resman.load_image("minimap_grid_legends.png")
            map_land = self.resman.load_image("minimap.png", path=path)
            map_water = self.resman.load_image("minimap_water.png", path=path)
            size = self.output_size

            self.minimap_bg = map_water.copy().resize(size)
            self.minimap_bg.paste(
                map_legends,
                (
                    0,
                    self.px(50),
                ),
                mask=map_legends,
            )

            self.bg_color = map_water.getpixel((10, 10))
            map_water = Image.alpha_composite(
                map_water,
                draw_grid(self.minimap_size, max(1, self.px(1))),
            )
            self.minimap_fg = Image.alpha_composite(map_water, map_land)
        except (FileNotFoundError, ModuleNotFoundError) as e:
            raise MapLoadError from e

    def _load_map_manifest(self):
        """Loads the map's metadata and checks its values.

        Raises:
            MapManifestLoadError: Raised when there's an error when loading the
            manifest file or the map's metadata is unsuitable.

        Returns:
            str: Package on where the map resources will be loaded.
        """
        map_name = self.replay_data.game_map

        try:
            manifest = self.resman.load_json("manifest.json", "spaces")
            manifest = manifest[map_name]
        except (KeyError, JSONDecodeError):
            manifest = self.resman.load_json("manifest.json", "spaces", True)
            manifest = manifest[map_name]

        minimap_size, self.minimap_space_size, minimap_scaling = manifest
        assert isinstance(minimap_size, int)
        assert isinstance(self.minimap_space_size, int)
        assert isinstance(minimap_scaling, float)
        assert 0 < self.minimap_space_size <= 1600
        assert 760 == minimap_size
        self.minimap_size = self.px(minimap_size)
        self.minimap_scaling = minimap_scaling * self.render_scale

    def get_scaled(
        self, xy: tuple[Number, Number], flip_y=True
    ) -> tuple[int, int]:
        """Scales a coordinate properly.

        Args:
            xy (tuple[Number, Number]): Coordinate.
            flip_y (bool, optional): Flips the y component. Defaults to True.

        Returns:
            tuple[int, int]: Scaled coordinated.
        """
        x, y = xy

        if flip_y:
            y = -y

        x = round(x * self.minimap_scaling + self.minimap_size / 2)
        y = round(y * self.minimap_scaling + self.minimap_size / 2)
        return x, y

    def get_scaled_r(self, r: Number):
        """Scales the radius.

        Args:
            r (Number): Radius.

        Returns:
            _type_: Scaled radius.
        """
        return r * self.minimap_scaling

    def _load_layer(self, layer_name: str) -> Type[LayerBase]:
        assert layer_name in LAYERS
        versioned_layers_pkg = (
            f"{__package__}.versions.{self.replay_data.game_version}"
        )
        try:
            mod = import_module(".layers", versioned_layers_pkg)
            m_layer = getattr(mod, layer_name)
            LOGGER.info(f"Versioned {layer_name} found. Using that instead.")
        except (ModuleNotFoundError, AttributeError):
            mod = import_module(".layers", __package__)
            m_layer = getattr(mod, f"{layer_name}Base")
        return m_layer


class RenderDual(RendererBase):
    def __init__(
        self,
        green_replay_data: ReplayData,
        red_replay_data: ReplayData,
        green_tag: Optional[str] = None,
        red_tag: Optional[str] = None,
        team_tracers: bool = False,
        use_tqdm: bool = True,
    ):
        super().__init__(green_replay_data)
        self.conman = ConsumableManager([green_replay_data, red_replay_data])
        self.replay_r: ReplayData = red_replay_data
        assert self.replay_data.game_arena_id == self.replay_r.game_arena_id
        assert self.replay_data.game_version == self.replay_r.game_version
        self.dual_mode: bool = True
        self.green_tag = green_tag
        self.red_tag = red_tag
        self.team_tracers = team_tracers
        self.use_tqdm = use_tqdm

    def start(
        self,
        path: str,
        fps: int = 20,
        quality: int = 7,
        progress_cb: Optional[Callable[[float], Any]] = None,
        speed: Optional[float] = None,
        resolution: Optional[tuple[int, int]] = None,
        interpolation: str = "blend",
    ):
        if interpolation == "native":
            raise ValueError("native interpolation is not supported for dual renders")
        self._configure_resolution(resolution)
        self._load_map()

        assert self.minimap_fg
        assert self.minimap_bg

        # green
        g_ship = self._load_layer("LayerShip")(self, self.replay_data, "green")
        g_shot = self._load_layer("LayerShot")(self, self.replay_data, "green")
        g_torpedo = self._load_layer("LayerTorpedo")(
            self, self.replay_data, "green"
        )
        g_plane = self._load_layer("LayerPlane")(
            self, self.replay_data, "green"
        )
        g_ward = self._load_layer("LayerWard")(self, self.replay_data, "green")

        g_smoke = self._load_layer("LayerSmoke")(self, self.replay_data)
        g_capture = self._load_layer("LayerCapture")(self, self.replay_data)
        g_score = self._load_layer("LayerScore")(
            self,
            self.replay_data,
            green_tag=self.green_tag,
            red_tag=self.red_tag,
        )
        g_timer = self._load_layer("LayerTimer")(self, self.replay_data)
        g_markers = self._load_layer("LayerMarkers")(
            self, self.replay_data, "green"
        )

        # red
        r_ship = self._load_layer("LayerShip")(self, self.replay_r, "red")
        r_shot = self._load_layer("LayerShot")(self, self.replay_r, "red")
        r_torpedo = self._load_layer("LayerTorpedo")(
            self, self.replay_r, "red"
        )
        r_plane = self._load_layer("LayerPlane")(self, self.replay_r, "red")
        r_ward = self._load_layer("LayerWard")(self, self.replay_r, "red")

        r_markers = self._load_layer("LayerMarkers")(
            self, self.replay_r, "red"
        )

        video_writer = self.get_writer(
            path, fps, quality, speed, resolution, interpolation
        )
        video_writer.send(None)

        shared_events = sorted(
            set(self.replay_data.events).intersection(self.replay_r.events)
        )
        if self.use_tqdm:
            prog = tqdm(shared_events)
        else:
            prog = shared_events

        total = len(prog)
        last_per = 0.0

        for idx, i in enumerate(prog):
            if progress_cb:
                per = round((idx + 1) / total, 1)
                if per > last_per:
                    last_per = per
                    progress_cb(per)

            self.conman.update(i)

            minimap_img = self.minimap_fg.copy()
            minimap_bg = self.minimap_bg.copy()
            draw = ImageDraw.Draw(minimap_img)

            g_capture.draw(i, minimap_img)
            g_smoke.draw(i, minimap_img)
            g_score.draw(i, minimap_bg)
            g_timer.draw(i, minimap_bg)

            g_ward.draw(i, minimap_img)
            r_ward.draw(i, minimap_img)

            g_markers.draw(i, minimap_img)
            r_markers.draw(i, minimap_img)

            g_torpedo.draw(i, draw)
            r_torpedo.draw(i, draw)

            g_shot.draw(i, minimap_img)
            r_shot.draw(i, minimap_img)

            g_ship.draw(i, minimap_img)
            r_ship.draw(i, minimap_img)

            g_plane.draw(i, minimap_img)
            r_plane.draw(i, minimap_img)

            self.conman.tick()

            minimap_bg.paste(minimap_img, self.map_origin)
            video_writer.send(minimap_bg.tobytes())
        video_writer.close()


class Renderer(RendererBase):
    def __init__(
        self,
        replay_data: ReplayData,
        logs: bool = True,
        anon: bool = False,
        enable_chat: bool = True,
        team_tracers: bool = False,
        use_tqdm: bool = False,
    ):
        """Orchestrates the rendering process.

        Args:
            replay_data (ReplayData): Replay data.
        """
        super().__init__(replay_data)
        # MAP INFO
        self.logs: bool = logs
        self.is_operations: bool = False
        self.anon: bool = anon
        self.enable_chat: bool = enable_chat
        self.team_tracers: bool = team_tracers
        self.usernames: dict[int, str] = {}
        self.dual_mode: bool = False
        self.bg_color: tuple[int, int, int] = (0, 0, 0)
        self.use_tqdm = use_tqdm
        self._builder = ShipBuilder(self.resman)

        if self.anon:
            for i, (pid, pi) in enumerate(
                self.replay_data.player_info.items(), 1
            ):
                name = f"Player {i}"
                self.usernames[pid] = name

    def _check_if_operations(self):
        self.is_operations = self.replay_data.game_map.startswith('s')

    def get_player_build(self) -> list[dict]:
        ships = self.resman.load_json("ships.json")
        url = "https://app.wowssb.com/ship?shipIndexes="
        builds = []

        for player in self.replay_data.player_info.values():
            if player.relation not in [-1, 0]:
                continue

            try:
                index, build_str = self._builder.get_build(player)
                build_url = f"{url}{index}&build={build_str}"
            except Exception:
                build_url = ""
            builds.append(
                {
                    "name": player.name,
                    "ship": ships[player.ship_params_id]["name"],
                    "clan": player.clan_tag,
                    "relation": player.relation,
                    "build_url": build_url,
                }
            )
        return builds

    def start(
        self,
        path: str,
        fps: int = 20,
        quality: int = 7,
        progress_cb: Optional[Callable[[float], Any]] = None,
        speed: Optional[float] = None,
        resolution: Optional[tuple[int, int]] = None,
        interpolation: str = "native",
    ):
        """Starts the rendering process"""
        self._check_if_operations()
        self._configure_resolution(resolution)
        if interpolation == "native" and speed is not None and fps < speed:
            raise ValueError("native interpolation requires fps to be at least speed")
        self._load_map()

        assert self.minimap_fg
        assert self.minimap_bg

        layer_ship = self._load_layer("LayerShip")(self)
        layer_shot = self._load_layer("LayerShot")(self)
        layer_torpedo = self._load_layer("LayerTorpedo")(self)
        layer_smoke = self._load_layer("LayerSmoke")(self)
        layer_plane = self._load_layer("LayerPlane")(self)
        layer_ward = self._load_layer("LayerWard")(self)
        layer_building = self._load_layer("LayerBuilding")(self)
        layer_capture = self._load_layer("LayerCapture")(self)
        layer_health = self._load_layer("LayerHealth")(self)
        layer_score = self._load_layer("LayerScore")(self)
        layer_counter = self._load_layer("LayerCounter")(self)
        layer_frag = self._load_layer("LayerFrag")(self)
        layer_timer = self._load_layer("LayerTimer")(self)
        layer_ribbon = self._load_layer("LayerRibbon")(self)
        layer_chat = self._load_layer("LayerChat")(self)
        layer_markers = self._load_layer("LayerMarkers")(self)

        video_writer = self.get_writer(
            path, fps, quality, speed, resolution, interpolation
        )
        video_writer.send(None)

        self._draw_header(self.minimap_bg)
        event_keys = sorted(self.replay_data.events)
        last_key = event_keys[-1]
        last_per = 0.0

        def update_progress(index: int, total: int):
            nonlocal last_per
            if progress_cb:
                per = round((index + 1) / total, 1)
                if per > last_per:
                    last_per = per
                    progress_cb(per)

        def draw_frame(game_time):
            minimap_img = self.minimap_fg.copy()
            minimap_bg = self.minimap_bg.copy()

            if not self.is_operations:
                layer_capture.draw(game_time, minimap_img)
                layer_score.draw(game_time, minimap_bg)

            layer_building.draw(game_time, minimap_img)
            layer_ward.draw(game_time, minimap_img)
            layer_markers.draw(game_time, minimap_img)
            layer_shot.draw(game_time, minimap_img)
            layer_torpedo.draw(game_time, ImageDraw.Draw(minimap_img))
            layer_ship.draw(game_time, minimap_img)
            layer_smoke.draw(game_time, minimap_img)
            layer_plane.draw(game_time, minimap_img)
            layer_timer.draw(game_time, minimap_bg)

            if self.logs:
                layer_health.draw(game_time, minimap_bg)
                layer_counter.draw(game_time, minimap_bg)
                layer_frag.draw(game_time, minimap_bg)

                layer_ribbon.draw(game_time, minimap_bg)
                if self.enable_chat:
                    layer_chat.draw(game_time, minimap_bg)

            return minimap_img, minimap_bg

        if interpolation == "native":
            source_speed = speed if speed is not None else fps
            self.frame_delta = source_speed / fps
            timeline = native_timeline(event_keys, fps, source_speed)
            normal_frame_count = max(
                0, ceil((len(event_keys) - 1) * fps / source_speed)
            )
            prog = tqdm(timeline, total=normal_frame_count) if self.use_tqdm else timeline
            has_active_interval = False

            for frame_index, current_key, next_key, alpha, first in prog:
                update_progress(frame_index, normal_frame_count + 1)
                if first:
                    if has_active_interval:
                        self.conman.tick()
                    self.conman.update(current_key)
                    has_active_interval = True

                sample_key = ("native", frame_index)
                self.replay_data.events[sample_key] = interpolate_events(
                    self.replay_data.events[current_key],
                    self.replay_data.events[next_key],
                    alpha,
                    include_transients=first,
                )
                try:
                    minimap_img, minimap_bg = draw_frame(sample_key)
                    minimap_bg.paste(minimap_img, self.map_origin)
                    video_writer.send(minimap_bg.tobytes())
                finally:
                    self.replay_data.events.pop(sample_key)

            if has_active_interval:
                self.conman.tick()
            self.conman.update(last_key)
            update_progress(normal_frame_count, normal_frame_count + 1)
            minimap_img, minimap_bg = draw_frame(last_key)
            self._write_ending(
                video_writer, minimap_img, minimap_bg, fps
            )
            video_writer.close()
            return

        prog = tqdm(event_keys) if self.use_tqdm else event_keys
        total = len(event_keys)

        for idx, game_time in enumerate(prog):
            update_progress(idx, total)
            self.conman.update(game_time)
            minimap_img, minimap_bg = draw_frame(game_time)

            self.conman.tick()

            if game_time == last_key:
                timeline_fps = speed if speed is not None else fps
                self._write_ending(
                    video_writer, minimap_img, minimap_bg, timeline_fps
                )
            else:
                minimap_bg.paste(minimap_img, self.map_origin)
                video_writer.send(minimap_bg.tobytes())
        video_writer.close()

    def _write_ending(self, video_writer, minimap_img, minimap_bg, timeline_fps):
        img_win = Image.new("RGBA", self.minimap_fg.size)
        font = self.resman.load_font("warhelios_bold.ttf", size=48)
        player = self.replay_data.player_info[self.replay_data.owner_id]
        team_id = self.replay_data.game_result.team_id

        match team_id:
            case a if a == player.team_id and a != -1:
                text = "VICTORY"
            case a if a != player.team_id and a != -1:
                text = "DEFEAT"
            case _:
                text = "DRAW"

        tw, th = map(lambda i: i / 2, font.getbbox(text)[2:])
        mid_x, mid_y = map(lambda i: i / 2, minimap_img.size)
        px, py = mid_x - tw, mid_y - th - self.px(6)
        end_frame_count = round(3 * timeline_fps)
        fade_frame_count = 1.5 * timeline_fps
        for i in range(end_frame_count):
            per = min(1, i / fade_frame_count)
            frame_overlay = img_win.copy()
            frame_draw = ImageDraw.Draw(frame_overlay)
            frame_draw.text(
                (px, py),
                text=text,
                font=font,
                fill=(255, 255, 255, round(255 * per)),
                stroke_width=max(1, self.px(4)),
                stroke_fill=(*self.bg_color[:3], round(255 * per)),
            )
            frame = Image.alpha_composite(minimap_img, frame_overlay)
            output = minimap_bg.copy()
            output.paste(frame, self.map_origin)
            video_writer.send(output.tobytes())

    def _draw_header(self, image: Image.Image):
        draw = ImageDraw.Draw(image)

        logo = self.resman.load_image("logo.png")
        image.paste(logo, self.xy((840, 25)), logo)

        font_large = self.resman.load_font("warhelios_bold.ttf", size=35)
        draw.text(self.xy((945, 30)), "Minimap Renderer", "white", font_large)

        font_large = self.resman.load_font("warhelios_bold.ttf", size=16)
        draw.text(
            self.xy((945, 75)),
            "https://github.com/WoWs-Builder-Team",
            "white",
            font_large,
        )
