from collections import OrderedDict
from typing import Optional
from ..data import ReplayData
from renderer.render import Renderer
from renderer.base import LayerBase
from renderer.const import RELATION_NORMAL_STR, COLORS_NORMAL
from renderer.utils import (
    generate_holder,
    draw_health_bar,
    LOGGER,
)

from PIL import Image, ImageDraw
from math import hypot
from functools import lru_cache

_HOLDER_CACHE_MAX = 512
_CONSUMABLE_CACHE_MAX = 512

MIN_VIEW_DISTANCES = {
    1: 15000,
    2: 15000,
    3: 17000,
    4: 20000,
    5: 23000,
    6: 26000,
    7: 27000,
    8: 30000,
    9: 33000,
    10: 35000,
    11: 35000,
}


UNKNOWN_CONSUMABLE_INDEX_BY_ID: dict[int, str] = {
    # 15.2 replay may emit aid=42 for submarine state consumable,
    # while abilities.json has no id_to_index entry for 42.
    42: "PCY042_SubmarineFourthState",
    # 15.7 行动模式 (WW2_OP1 等) 会给舰船额外配置消耗品槽位,
    # 这些槽位不在 GameParams 的 ShipAbilities 中, 但 typeId 全局一致.
    36: "PCY046_FastDeepRudders",
}

# 已知类型但游戏未提供图标的 typeId:
# 渲染时跳过且不告警 (避免对行动模式临时消耗品刷警告).
KNOWN_NO_ICON_CONSUMABLE_IDS: set[int] = {38}


class LayerShipBase(LayerBase):
    """A class that handles/draws ships to the minimap.

    Args:
        LayerBase (_type_): _description_
    """

    def __init__(
        self,
        renderer: Renderer,
        replay_data: Optional[ReplayData] = None,
        color: Optional[str] = None,
    ):
        """Initializes this class.

        Args:
            renderer (Renderer): The renderer.
        """
        self._renderer = renderer
        self._replay_data = replay_data if replay_data else self._renderer.replay_data
        self._color = color
        self._holders = generate_holder(
            self._replay_data.player_info, renderer.resman, color
        )
        self._abilities = renderer.resman.load_json("abilities.json")
        self._ships = renderer.resman.load_json("ships.json")
        self._consumable_cache: OrderedDict[tuple, Optional[Image.Image]] = OrderedDict()
        self._unknown_consumables: set[tuple[int, int]] = set()
        self._missing_consumable_icons: set[str] = set()
        self._holder_cache: OrderedDict[
            tuple, tuple[Optional[Image.Image], int, int]
        ] = OrderedDict()
        self._owner = self._replay_data.player_info[self._replay_data.owner_id]
        self._owner_view_range = self._get_max_dist()
        self._deads: list[int] = []
        self._image_dead = Image.new(
            renderer.minimap_fg.mode, renderer.minimap_fg.size
        )
        # Bounding box of the dead-ship overlay. Compositing the full overlay
        # on every frame after the first death is a major render cost, so the
        # cached box lets us composite only the region that actually contains
        # sprites while keeping the exact same pixels.
        self._dead_bbox: Optional[tuple[int, int, int, int]] = None

    @staticmethod
    def _mapping_get(mapping: dict, aid: int):
        return mapping.get(aid, mapping.get(str(aid)))

    def _get_consumable_index(self, params_id: int, aid: int):
        abilities = self._abilities.get(params_id, {})
        id_to_index = abilities.get("id_to_index", {})
        clan = self._abilities.get("clan", {})

        index = self._mapping_get(id_to_index, aid)
        if index is not None:
            return index

        if known_unknown := UNKNOWN_CONSUMABLE_INDEX_BY_ID.get(aid):
            return known_unknown

        # Some replays report transient / internal consumable ids not present in
        # abilities.json (e.g. submarine aid=42). In that case, try to map to a
        # known consumable icon from the same ship by adjacent id.
        if aid == 42:
            for fallback_aid in (41, 37, 36, 35):
                fallback = self._mapping_get(id_to_index, fallback_aid)
                if fallback is not None:
                    return fallback

        return self._mapping_get(clan, aid)

    def _get_max_dist(self):
        ship = self._ships[self._owner.ship_params_id]
        if ship["species"] in ["AirCarrier", "Submarine"]:
            return -1

        artillery_comp = self._owner.ship_components["artillery"]
        fire_control_comp = self._owner.ship_components["fireControl"]
        ship_comp = ship["components"]
        try:
            max_dist = ship_comp[artillery_comp]["maxDist"]
        except KeyError:
            max_dist = 999999

        try:
            max_dist_coef = ship_comp[fire_control_comp]["maxDistCoef"]
        except KeyError:
            max_dist_coef = 1

        max_dist = max_dist * max_dist_coef
        modernizations = self._renderer.resman.load_json("modernizations.json")

        if mods := set(self._owner.modernization).intersection(
            modernizations["mb_range_modifiers"]
        ):
            for mod_id in mods:
                max_dist *= modernizations["modernizations"][mod_id]["modifiers"][
                    "GMMaxDist"
                ]
        return max_dist

    def draw(self, game_time: int, image: Image.Image):
        """Draws the ship icons to the minimap image.

        Args:
            game_time (int): The game time.
            image (Image.Image): The minimap image.
        """
        player_info = self._replay_data.player_info
        events = self._replay_data.events
        owner_vehicle = events[game_time].evt_vehicle[self._owner.ship_id]

        if self._dead_bbox is not None:
            image.alpha_composite(
                self._image_dead,
                dest=self._dead_bbox[:2],
                source=self._dead_bbox,
            )

        placed_rects: list[tuple[int, int, int, int]] = []
        overlap_step = max(6, self._renderer.px(12))

        for vehicle in sorted(
            events[game_time].evt_vehicle.values(),
        ):
            if self._renderer.dual_mode and vehicle.relation == 1:
                continue

            if vehicle.vehicle_id in self._deads:
                continue

            holder = self._holders[vehicle.player_id]
            player = self._replay_data.player_info[vehicle.player_id]
            ship = self._ships[player.ship_params_id]

            owner_view_range = self._owner_view_range

            if acs := self._renderer.conman.active_consumables.get(
                owner_vehicle.vehicle_id, None
            ):
                if 1 in acs:
                    owner_abilities = self._abilities[self._owner.ship_params_id]
                    index = owner_abilities["id_to_index"][1]
                    subtype = owner_abilities["id_to_subtype"][1]
                    owner_view_range *= owner_abilities[f"{index}.{subtype}"][
                        "artilleryDistCoeff"
                    ]

            is_in_view_range = False

            if vehicle.is_visible and vehicle != owner_vehicle:
                distance_bw = hypot(
                    vehicle.x - owner_vehicle.x, vehicle.y - owner_vehicle.y
                )
                owner_ship = self._ships[self._owner.ship_params_id]
                owner_view_range *= 1.25
                owner_view_range = max(
                    owner_view_range, MIN_VIEW_DISTANCES[owner_ship["level"]]
                )
                distance_m = distance_bw * 30
                is_in_view_range = owner_view_range >= distance_m
            elif vehicle.is_visible and vehicle == owner_vehicle:
                is_in_view_range = True

            if self._color:
                relation = 0 if self._color == "green" else 1
                color = COLORS_NORMAL[0 if self._color == "green" else 1]
            else:
                relation = player.relation
                color = (
                    COLORS_NORMAL[0]
                    if vehicle.relation == -1
                    else COLORS_NORMAL[vehicle.relation]
                )

            player = player_info[vehicle.player_id]

            icon_name = self._ship_icon_name(
                vehicle.is_alive,
                vehicle.is_visible,
                ship["species"],
                relation,
                is_in_view_range,
                vehicle.visibility_flag,
            )
            angle = round(-vehicle.yaw * 2) / 2
            icon = self._get_rotated_ship_icon(icon_name, angle)
            x, y = self._renderer.get_scaled((vehicle.x, vehicle.y))

            if vehicle.is_alive and not self._renderer.dual_mode:
                if (
                    not vehicle.is_visible
                    or relation == 1
                    and not vehicle.visibility_flag
                    and is_in_view_range
                ):
                    image.alpha_composite(
                        icon,
                        dest=(x - round(icon.width / 2), y - round(icon.height / 2)),
                    )
                    continue

            if vehicle.is_alive:
                if vehicle.is_visible:
                    edge_distance = self._renderer.px(34)
                    near_top = y <= edge_distance
                    c_y_pos = (
                        self._renderer.px(94)
                        if near_top
                        else self._renderer.px(20)
                    )

                    cropped_holder, ox, oy = self._get_ship_holder(
                        vehicle,
                        player,
                        color,
                        is_in_view_range,
                        0,
                        c_y_pos,
                    )
                    if cropped_holder is not None:
                        cw, ch = cropped_holder.size
                        margin = max(2, self._renderer.px(2))
                        raw_dx = max(
                            margin,
                            min(max(margin, image.width - cw - margin), x + ox),
                        )
                        raw_dy = y + oy
                        if raw_dy + ch > image.height - margin:
                            raw_dy = (
                                y
                                - round(icon.height / 2)
                                - ch
                                - max(2, self._renderer.px(3))
                            )
                        dest_x, dest_y = self._resolve_label_position(
                            raw_dx,
                            raw_dy,
                            cw,
                            ch,
                            image.width,
                            image.height,
                            placed_rects,
                            overlap_step,
                        )
                        placed_rects.append(
                            (dest_x, dest_y, dest_x + cw, dest_y + ch)
                        )
                        image.alpha_composite(
                            cropped_holder,
                            dest=(dest_x, dest_y),
                        )
            if not vehicle.is_alive and vehicle.vehicle_id not in self._deads:
                self._deads.append(vehicle.vehicle_id)
                dest_x = x - round(icon.width / 2)
                dest_y = y - round(icon.height / 2)
                self._image_dead.alpha_composite(icon, dest=(dest_x, dest_y))
                self._expand_dead_bbox(dest_x, dest_y, icon.size)

            image.alpha_composite(
                icon,
                dest=(x - round(icon.width / 2), y - round(icon.height / 2)),
            )

    def _expand_dead_bbox(self, x: int, y: int, size: tuple[int, int]) -> None:
        """Expands the cached dead-overlay bounding box with a sprite rect."""
        left = max(0, x)
        top = max(0, y)
        right = min(self._image_dead.width, x + size[0])
        bottom = min(self._image_dead.height, y + size[1])
        if right <= left or bottom <= top:
            return
        if self._dead_bbox is None:
            self._dead_bbox = (left, top, right, bottom)
            return
        bl, bt, br, bb = self._dead_bbox
        self._dead_bbox = (
            min(bl, left),
            min(bt, top),
            max(br, right),
            max(bb, bottom),
        )

    @staticmethod
    def _resolve_label_position(
        dest_x: int,
        dest_y: int,
        cw: int,
        ch: int,
        canvas_w: int,
        canvas_h: int,
        placed_rects: list[tuple[int, int, int, int]],
        step: int,
    ) -> tuple[int, int]:
        """Nudges overlapping ship holders vertically inside canvas bounds."""
        cx = max(0, min(max(0, canvas_w - cw), dest_x))
        base_cy = max(0, min(max(0, canvas_h - ch), dest_y))
        if not placed_rects or step <= 0:
            return cx, base_cy

        shifts = (0, -step, step, -2 * step, 2 * step)
        min_threshold = 0.12 * cw * ch
        best_pos = (cx, base_cy)
        best_area = float("inf")

        for dy in shifts:
            cy = max(0, min(max(0, canvas_h - ch), dest_y + dy))
            area = 0
            for px0, py0, px1, py1 in placed_rects:
                ix0 = max(cx, px0)
                iy0 = max(cy, py0)
                ix1 = min(cx + cw, px1)
                iy1 = min(cy + ch, py1)
                if ix1 > ix0 and iy1 > iy0:
                    area += (ix1 - ix0) * (iy1 - iy0)
            if area <= min_threshold:
                return cx, cy
            if area < best_area:
                best_area = area
                best_pos = (cx, cy)

        return best_pos

    def _get_ship_holder(
        self,
        vehicle,
        player,
        color,
        is_in_view_range: bool,
        angle: int,
        c_y_pos: int,
    ) -> tuple[Optional[Image.Image], int, int]:
        acs = self._renderer.conman.active_consumables.get(vehicle.vehicle_id)
        ac_key = tuple(sorted(acs.keys())) if acs else ()
        hp_key = (
            round(vehicle.health / player.max_health, 2)
            if is_in_view_range and player.max_health > 0
            else None
        )
        regen_raw = getattr(vehicle, "regeneration_health", 0.0)
        regen_key = (
            round((vehicle.health + regen_raw) / player.max_health, 2)
            if is_in_view_range and regen_raw > 0 and player.max_health > 0
            else 0.0
        )
        vis_key = (
            vehicle.visibility_flag > 0
            and vehicle.relation in [-1, 0]
        )
        cache_key = (
            vehicle.player_id,
            hp_key,
            regen_key,
            ac_key,
            angle,
            c_y_pos,
            vis_key,
            color,
        )

        cached = self._holder_cache.get(cache_key)
        if cached is not None:
            self._holder_cache.move_to_end(cache_key)
            return cached

        holder = self._holders[vehicle.player_id].copy()

        if vis_key:
            vx = max(0, round(holder.width / 2 - self._renderer.px(35)))
            vy = self._renderer.px(65)
            marker_size = max(1, self._renderer.px(5))
            draw = ImageDraw.Draw(holder)
            draw.rectangle(
                ((vx, vy), (vx + marker_size, vy + marker_size)),
                fill="orange",
            )

        if is_in_view_range and hp_key is not None:
            draw_health_bar(
                holder,
                color=color,
                hp_per=hp_key,
                regen_per=regen_key,
            )

        orig_w, orig_h = holder.size
        icon_size = max(1, self._renderer.px(20))
        if ac_key and c_y_pos + icon_size > holder.height:
            expanded = Image.new(
                "RGBA", (holder.width, c_y_pos + icon_size + max(2, self._renderer.px(2)))
            )
            expanded.paste(holder, (0, 0))
            holder = expanded

        self._ship_consumable(
            holder,
            vehicle.vehicle_id,
            player.ship_params_id,
            c_y_pos,
        )

        if holder and angle:
            holder = holder.rotate(
                angle, Image.Resampling.BICUBIC, expand=True
            )
            center_x = round(holder.width / 2)
            center_y = round(holder.height / 2)
        else:
            center_x = round(orig_w / 2)
            center_y = round(orig_h / 2)

        bbox = holder.getbbox()
        if bbox is None:
            res = (None, 0, 0)
        else:
            cropped = holder.crop(bbox)
            res = (
                cropped,
                bbox[0] - center_x,
                bbox[1] - center_y,
            )

        self._holder_cache[cache_key] = res
        if len(self._holder_cache) > _HOLDER_CACHE_MAX:
            self._holder_cache.popitem(last=False)
        return res

    def _ship_consumable(
        self, image: Image.Image, vehicle_id: int, params_id: int, y=None
    ):
        """Draws the currently in used consumable(s) to the ship's icon holder.

        Args:
            image (Image.Image): The icon holder.
            vehicle_id (int): The vehicle id.
            params_id (int): The vehicle's game params id.
        """
        y = self._renderer.px(20) if y is None else y
        if ac := self._renderer.conman.active_consumables.get(vehicle_id, None):
            cache_key = (params_id, tuple(sorted(ac.keys())))

            if cache_key in self._consumable_cache:
                c_image = self._consumable_cache[cache_key]
                self._consumable_cache.move_to_end(cache_key)
                if c_image is not None:
                    x = int(image.width / 2 - c_image.width / 2)
                    image.alpha_composite(c_image, (x, y))
            else:
                icon_size = max(1, self._renderer.px(20))
                c_icons_holder = Image.new(
                    "RGBA", (icon_size * len(ac), icon_size)
                )
                x_pos = 0

                for aid in sorted(ac.keys()):
                    index = self._get_consumable_index(params_id, aid)
                    if index is None:
                        # 已知类型但游戏未提供图标 (如行动模式临时消耗品),
                        # 静默跳过, 不视为未知能力.
                        if aid in KNOWN_NO_ICON_CONSUMABLE_IDS:
                            continue
                        unknown = (params_id, aid)
                        if unknown not in self._unknown_consumables:
                            LOGGER.warning(
                                "Unknown consumable ability id=%s for params_id=%s. Skipping icon.",
                                aid,
                                params_id,
                            )
                            self._unknown_consumables.add(unknown)
                        continue

                    filename = f"consumable_{index}.png"
                    try:
                        c_image = self._renderer.resman.load_image(
                            filename,
                            path="consumables",
                            size=(icon_size, icon_size),
                        )
                    except (FileNotFoundError, ModuleNotFoundError):
                        if filename not in self._missing_consumable_icons:
                            LOGGER.warning(
                                "Missing consumable icon '%s' for aid=%s (params_id=%s).",
                                filename,
                                aid,
                                params_id,
                            )
                            self._missing_consumable_icons.add(filename)
                        continue

                    c_icons_holder.alpha_composite(c_image, (x_pos, 0))
                    x_pos += icon_size

                if x_pos > 0:
                    c_icons_holder = c_icons_holder.crop(
                        (0, 0, x_pos, icon_size)
                    )
                    self._consumable_cache[cache_key] = c_icons_holder
                    image.alpha_composite(
                        c_icons_holder,
                        (int(image.width / 2 - c_icons_holder.width / 2), y),
                    )
                else:
                    self._consumable_cache[cache_key] = None
                if len(self._consumable_cache) > _CONSUMABLE_CACHE_MAX:
                    self._consumable_cache.popitem(last=False)

    @lru_cache(maxsize=256)
    def _ship_icon_name(
        self,
        is_alive: bool,
        is_visible: bool,
        species: str,
        relation: int,
        is_in_view_range: bool,
        visibility_flag: int,
    ) -> str:
        relation_str = RELATION_NORMAL_STR[relation]
        filename_parts: list[str] = []
        state = (is_alive, is_visible, is_in_view_range)

        if relation == -1:
            if is_alive:
                filename_parts.append("alive")
            else:
                filename_parts.append("dead")
        else:
            filename_parts.append(species)

            if not state[0]:
                filename_parts.append("dead")
            elif self._renderer.dual_mode:
                filename_parts.append(relation_str)
            elif state == (True, True, False):
                filename_parts.append(relation_str)
                filename_parts.append("outside")
            elif (state[0], state[1]) == (True, False) or (
                relation == 1 and is_alive and not visibility_flag
            ):
                filename_parts.append("hidden")
            else:
                filename_parts.append(relation_str)

        filename = "_".join(filename_parts)
        return f"{filename}.png"

    @lru_cache(maxsize=4096)
    def _get_rotated_ship_icon(
        self, icon_name: str, angle: float
    ) -> Image.Image:
        icon = self._renderer.resman.load_image(icon_name, "ship_icons")
        return icon.rotate(angle, Image.Resampling.BICUBIC, expand=True)

    def _ship_icon(
        self,
        is_alive: bool,
        is_visible: bool,
        species: str,
        relation: int,
        is_in_view_range: bool,
        visibility_flag: int,
    ) -> Image.Image:
        """Returns an image associated with ship's state.

        Args:
            is_alive (bool): Ship's status.
            is_visible (bool): Ship's visibility.
            species (str): Ship's type.
            relation (int): Ship's relation to player.
            not_in_range (bool): If the ship is in player's render range.
            visibility_flag (int): Integer representing status of various detection reasons.

        Returns:
            Image.Image: An icon associated with the ship's state.
        """
        filename = self._ship_icon_name(
            is_alive,
            is_visible,
            species,
            relation,
            is_in_view_range,
            visibility_flag,
        )
        return self._renderer.resman.load_image(filename, "ship_icons")
