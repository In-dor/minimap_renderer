from typing import Optional, Union

from PIL import Image, ImageDraw
from renderer.base import LayerBase
from renderer.const import (
    COLORS_NORMAL,
    DEATH_TYPES,
    TIER_ROMAN,
)
from renderer.data import Frag, ReplayData
from renderer.render import Renderer


class LayerFragBase(LayerBase):
    """The class for handling frag logs.

    Args:
        LayerBase (_type_): _description_
    """

    def __init__(
        self, renderer: Renderer, replay_data: Optional[ReplayData] = None
    ):
        self._renderer = renderer
        self._replay_data = (
            replay_data if replay_data else self._renderer.replay_data
        )
        self._font = self._renderer.resman.load_default_font(size=12)
        self._frags: list[Frag] = []
        self._ships = self._renderer.resman.load_json("ships.json")
        self._players = self._replay_data.player_info
        self._buildings = self._replay_data.building_info
        self._vehicle_id_to_player = {
            v.ship_id: v for k, v in self._players.items()
        }
        self._vehicle_id_to_building = {
            v.id: v for k, v in self._buildings.items()
        }
        self._allies = [
            p.ship_id for p in self._players.values() if p.relation in [-1, 0]
        ]
        self._allies.extend(
            p.id for p in self._buildings.values() if p.relation in [-1, 0]
        )
        self._generated_lines: dict[tuple, Image.Image] = {}

    def draw(self, game_time: int, image: Image.Image):
        """Draws the frags on the image.

        Args:
            game_time (int): The game time.
            image (Image.Image): The image where the logs will be drawn into.
        """
        evt_flag = self._replay_data.events[game_time].evt_frag
        self._frags.extend(evt_flag)

        if not getattr(self._renderer, "enable_chat", True):
            y_pos = self._renderer.px(838)
        else:
            y_pos = self._renderer.px(744)
        min_y = self._renderer.px(540)

        for frag in reversed(self._frags[-5:]):
            is_fragger_building = False
            is_killed_building = False

            try:
                fragger_info = self._vehicle_id_to_player[frag.fragger_id]
            except KeyError:
                fragger_info = self._vehicle_id_to_building[frag.fragger_id]
                is_fragger_building = True

            try:
                killed_info = self._vehicle_id_to_player[frag.killed_id]
            except KeyError:
                killed_info = self._vehicle_id_to_building[frag.killed_id]
                is_killed_building = True

            frag_entry = DEATH_TYPES.get(frag.death_type, DEATH_TYPES[0])
            frag_fname = f"{frag_entry['icon']}.png"
            try:
                death_icon = self._renderer.resman.load_image(
                    frag_fname, path="frag_icons"
                )
            except (FileNotFoundError, ModuleNotFoundError):
                death_icon = self._renderer.resman.load_image(
                    "frags.png", path="frag_icons"
                )

            if self._renderer.anon:
                fr_name = self._renderer.usernames[fragger_info.id]
                kd_name = self._renderer.usernames[killed_info.id]

                if fragger_info.clan_tag:
                    fr_ctag = "#" * len(fragger_info.clan_tag)
                else:
                    fr_ctag = ""

                if killed_info.clan_tag:
                    kd_ctag = "#" * len(killed_info.clan_tag)
                else:
                    kd_ctag = ""

                if fragger_info.relation == -1:
                    fr_name = fragger_info.name

                if killed_info.relation == -1:
                    kd_name = killed_info.name
            else:
                fr_name = fragger_info.name
                kd_name = killed_info.name
                fr_ctag = fragger_info.clan_tag
                kd_ctag = killed_info.clan_tag

            try:
                f_ship = self._ships[fragger_info.ship_params_id]
                f_name = f_ship["name"]
                f_species = f_ship["species"]
                f_level = f_ship["level"]
            except KeyError:
                f_name, f_species, f_level = "", "", 0

            try:
                k_ship = self._ships[killed_info.ship_params_id]
                k_name = k_ship["name"]
                k_species = k_ship["species"]
                k_level = k_ship["level"]
            except KeyError:
                k_name, k_species, k_level = "", "", 0

            line = []

            if is_fragger_building:
                fr_name = "FORT"

            if is_killed_building:
                kd_name = "FORT"

            f_tier = (
                TIER_ROMAN[f_level - 1]
                if 1 <= f_level <= len(TIER_ROMAN)
                else ""
            )
            k_tier = (
                TIER_ROMAN[k_level - 1]
                if 1 <= k_level <= len(TIER_ROMAN)
                else ""
            )

            if frag.fragger_id in self._allies:
                if fr_ctag:
                    line.append((f"[{fr_ctag}]{fr_name}", COLORS_NORMAL[0]))
                else:
                    line.append((fr_name, COLORS_NORMAL[0]))

                line.append(5)

                if not is_fragger_building:
                    line.append(
                        (
                            self._renderer.resman.load_image(
                                f"{f_species}_ally.png",
                                rot=-90,
                                path="ship_icons",
                            ),
                            4,
                            1,
                        )
                    )
                    line.append(5)
                    line.append((f_tier, COLORS_NORMAL[0]))
                    line.append(5)
                    line.append((f_name, COLORS_NORMAL[0]))
                    line.append(5)
                line.append((death_icon, -3, 1))
                line.append("after")
                line.append(5)

                if kd_ctag:
                    line.append((f"[{kd_ctag}]{kd_name}", COLORS_NORMAL[1]))
                else:
                    line.append((kd_name, COLORS_NORMAL[1]))

                line.append(5)
                if not is_killed_building:
                    line.append(
                        (
                            self._renderer.resman.load_image(
                                f"{k_species}_enemy.png",
                                rot=90,
                                path="ship_icons",
                            ),
                            4,
                            1,
                        )
                    )
                    line.append(5)
                    line.append((k_tier, COLORS_NORMAL[1]))
                    line.append(5)
                    line.append((k_name, COLORS_NORMAL[1]))
            else:
                if fr_ctag:
                    line.append((f"[{fr_ctag}]{fr_name}", COLORS_NORMAL[1]))
                else:
                    line.append((fr_name, COLORS_NORMAL[1]))

                line.append(5)

                if not is_fragger_building:
                    line.append(
                        (
                            self._renderer.resman.load_image(
                                f"{f_species}_enemy.png",
                                rot=90,
                                path="ship_icons",
                            ),
                            4,
                            1,
                        )
                    )
                    line.append(5)
                    line.append((f_tier, COLORS_NORMAL[1]))
                    line.append(5)
                    line.append((f_name, COLORS_NORMAL[1]))
                    line.append(5)
                line.append((death_icon, -3, 1))
                line.append("after")
                line.append(5)

                if kd_ctag:
                    line.append((f"[{kd_ctag}]{kd_name}", COLORS_NORMAL[0]))
                else:
                    line.append((kd_name, COLORS_NORMAL[0]))

                line.append(5)

                if not is_killed_building:
                    line.append(
                        (
                            self._renderer.resman.load_image(
                                f"{k_species}_ally.png",
                                rot=-90,
                                path="ship_icons",
                            ),
                            4,
                            1,
                        )
                    )
                    line.append(5)
                    line.append((k_tier, COLORS_NORMAL[0]))
                    line.append(5)
                    line.append((k_name, COLORS_NORMAL[0]))

            built_imgs = list(self.build(line))
            needed_h = sum(im.height for im in built_imgs)
            if y_pos - needed_h < min_y:
                break
            for img in built_imgs:
                y_pos -= img.height
                x_pos = (image.width - self._renderer.px(24)) - img.width
                image.alpha_composite(img, (x_pos, y_pos))

    def _hash(self, line):
        """Returns an immutable cache key for the line."""
        hashables = []
        for el in line:
            if isinstance(el, (tuple, list)):
                for sel in el:
                    if isinstance(sel, (str, int)):
                        hashables.append(sel)
            elif isinstance(el, int):
                hashables.append(el)
        return tuple(hashables)

    def _fit_icon(self, icon: Image.Image, scale_factor: int) -> Image.Image:
        line_h = self._renderer.px(19)
        nw = max(1, round(icon.width * scale_factor))
        nh = max(1, round(icon.height * scale_factor))
        max_h = max(1, line_h - self._renderer.px(1))
        if nh > max_h:
            nw = max(1, round(nw * max_h / nh))
            nh = max_h
        if (nw, nh) != icon.size:
            return icon.resize((nw, nh), Image.Resampling.LANCZOS)
        return icon

    def build(self, line: list[Union[int, str, Image.Image]]):
        """Builds the line or loads it from the cache.

        Args:
            line (list[Union[int, str, Image.Image]]): The line.

        Returns:
            _type_: The image of the line.
        """

        parts: dict[int, list] = {}
        total_width = 0
        idx = 0

        for el in line:
            part = parts.setdefault(idx, [])
            match el:
                case (a, b) if isinstance(a, str) and isinstance(b, str):
                    font = self._renderer.resman.load_font_with_text(a, size=12)
                    bbox = font.getbbox(a)
                    str_w = bbox[2] - bbox[0]
                    total_width += str_w
                    part.append(el)
                case (a, b, c) if isinstance(a, Image.Image) and isinstance(
                    b, int
                ) and isinstance(c, int):
                    a_fit = self._fit_icon(a, c)
                    total_width += a_fit.width
                    part.append(el)
                case a if isinstance(a, int):
                    total_width += self._renderer.px(a)
                    part.append(el)
                case "after":
                    idx += 1

        is_long = total_width > self._renderer.px(516)

        part_a = parts[0]
        part_b = parts[1]

        if not is_long:
            part_a.extend(part_b)
            yield self._part_to_image(part_a)
        else:
            for part in [part_b, part_a]:
                yield self._part_to_image(part)
        return

    def _part_to_image(self, part):
        line_key = self._hash(part)

        if line_key in self._generated_lines:
            return self._generated_lines[line_key]

        line_h = self._renderer.px(19)
        base = Image.new("RGBA", (self._renderer.px(516), line_h))
        base_draw = ImageDraw.Draw(base)
        pos_x = 0

        for el in part:
            match el:
                case (a, b) if isinstance(a, str) and isinstance(b, str):
                    font = self._renderer.resman.load_font_with_text(a, size=12)
                    bbox = font.getbbox(a)
                    str_w = bbox[2] - bbox[0]
                    str_h = bbox[3] - bbox[1]
                    ty = (line_h - str_h) // 2 - bbox[1]
                    base_draw.text((pos_x - bbox[0], ty), a, b, font)
                    pos_x += str_w
                case (a, b, c) if isinstance(a, Image.Image) and isinstance(
                    b, int
                ) and isinstance(c, int):
                    a_fit = self._fit_icon(a, c)
                    iy = max(0, (line_h - a_fit.height) // 2)
                    if pos_x < base.width:
                        base.alpha_composite(a_fit, (pos_x, iy))
                    pos_x += a_fit.width
                case a if isinstance(a, int):
                    pos_x += self._renderer.px(a)
        crop_w = max(1, min(base.width, pos_x))
        base = base.crop((0, 0, crop_w, line_h))
        self._generated_lines[line_key] = base
        return base
