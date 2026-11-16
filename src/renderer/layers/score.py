from typing import Optional
import numpy as np
from ..data import ReplayData
from renderer.render import Renderer
from renderer.base import LayerBase
from renderer.const import COLORS_NORMAL, SPECIES_ORDER
from PIL import Image, ImageDraw


ALLY_TIMER_POS = (20, 14)
ENEMY_TIMER_POS = (20, 32)
SPECIES_RANK = {species: idx for idx, species in enumerate(SPECIES_ORDER)}


class LayerScoreBase(LayerBase):
    """The class that handles team scores, score timer, and fleet ship-class bar.

    Args:
        LayerBase (_type_): _description_
    """

    def __init__(
        self,
        renderer: Renderer,
        replay_data: Optional[ReplayData] = None,
        green_tag: Optional[str] = None,
        red_tag: Optional[str] = None,
    ):
        self._renderer = renderer
        self._replay_data = (
            replay_data if replay_data else self._renderer.replay_data
        )
        self._green_tag = green_tag
        self._red_tag = red_tag
        self._font = self._renderer.resman.load_font(
            filename="warhelios_bold.ttf", size=24
        )
        self._timers_font = self._renderer.resman.load_font(
            filename="warhelios_bold.ttf", size=17
        )
        self._base = Image.new("RGBA", self._renderer.xy((714, 60)))
        self._timers_base = Image.new("RGBA", self._renderer.xy((40, 48)))
        draw = ImageDraw.Draw(self._timers_base)
        draw.text(
            self._renderer.xy(ALLY_TIMER_POS),
            ":",
            COLORS_NORMAL[0],
            self._timers_font,
            anchor="mm",
        )
        draw.text(
            self._renderer.xy(ENEMY_TIMER_POS),
            ":",
            COLORS_NORMAL[1],
            self._timers_font,
            anchor="mm",
        )

        self._ships = self._renderer.resman.load_json("ships.json")
        self._ally_players = sorted(
            (p for p in self._replay_data.player_info.values() if p.relation in (-1, 0)),
            key=lambda p: (SPECIES_RANK.get(self._player_species(p), 99), p.id),
        )
        self._enemy_players = sorted(
            (p for p in self._replay_data.player_info.values() if p.relation == 1),
            key=lambda p: (SPECIES_RANK.get(self._player_species(p), 99), p.id),
        )
        self._ship_icon_cache: dict[tuple, Image.Image] = {}
        self._fleet_strip_sig: Optional[tuple] = None
        self._fleet_strip_img: Optional[Image.Image] = None

    def _player_species(self, player) -> str:
        ship = self._ships.get(player.ship_params_id, {})
        return ship.get("species", "Cruiser")

    def _get_fleet_icon(
        self, species: str, side: str, is_alive: bool, target_w: int, target_h: int
    ) -> Image.Image:
        key = (species, side, is_alive, target_w, target_h)
        if cached := self._ship_icon_cache.get(key):
            return cached

        rot = -90 if side == "ally" else 90
        suffix = side if is_alive else "dead"
        try:
            icon = self._renderer.resman.load_image(
                f"{species}_{suffix}.png", rot=rot, path="ship_icons"
            )
        except (FileNotFoundError, ModuleNotFoundError):
            icon = self._renderer.resman.load_image(
                f"Cruiser_{suffix}.png", rot=rot, path="ship_icons"
            )
        if icon.size != (target_w, target_h):
            icon = icon.resize((target_w, target_h), Image.Resampling.LANCZOS)
        if not is_alive:
            arr = np.array(icon)
            arr[:, :, 3] = (arr[:, :, 3].astype(np.float32) * 0.30).astype(np.uint8)
            icon = Image.fromarray(arr, mode="RGBA")
        self._ship_icon_cache[key] = icon
        return icon

    def _build_fleet_strip(
        self,
        ally_states: tuple[tuple[str, bool], ...],
        enemy_states: tuple[tuple[str, bool], ...],
        bar_bounds: tuple[int, int, int, int],
        base_size: tuple[int, int],
    ) -> Image.Image:
        sig = (ally_states, enemy_states, bar_bounds)
        if sig == self._fleet_strip_sig and self._fleet_strip_img is not None:
            return self._fleet_strip_img

        x1, x2, x3, x4 = bar_bounds
        strip = Image.new("RGBA", base_size, (0, 0, 0, 0))
        sdraw = ImageDraw.Draw(strip)
        y_top = self._renderer.px(37)
        y_bot = self._renderer.px(58)
        slot_h = y_bot - y_top
        pill_r = max(2, self._renderer.px(4))
        pad = self._renderer.px(6)
        default_w = max(4, self._renderer.px(18))
        default_h = max(3, self._renderer.px(10))
        default_step = max(default_w + 1, self._renderer.px(21))

        # Ally fleet strip (left bar, right-aligned inward toward center score)
        if ally_states:
            sdraw.rounded_rectangle(
                [(x1, y_top), (x2, y_bot)],
                radius=pill_r,
                fill=(8, 16, 28, 165),
                outline=(76, 232, 170, 75),
                width=max(1, self._renderer.px(1)),
            )
            avail_w = max(1, int(x2 - x1) - pad * 2)
            n_ally = len(ally_states)
            step = min(default_step, max(4, avail_w // n_ally))
            icon_w = min(default_w, max(4, step - max(1, self._renderer.px(2))))
            icon_h = max(3, round(default_h * icon_w / default_w))
            iy = y_top + max(0, (slot_h - icon_h) // 2)
            # Order: CV, BB, CA, DD, SS (alive closer to center within each class)
            ordered = sorted(
                ally_states,
                key=lambda item: (SPECIES_RANK.get(item[0], 99), 0 if not item[1] else 1),
            )
            total_w = (n_ally - 1) * step + icon_w
            start_x = int(x2) - pad - total_w
            for idx, (species, is_alive) in enumerate(ordered):
                ic = self._get_fleet_icon(species, "ally", is_alive, icon_w, icon_h)
                strip.alpha_composite(ic, (start_x + idx * step, iy))

        # Enemy fleet strip (right bar, left-aligned inward mirrored: SS, DD, CA, BB, CV)
        if enemy_states:
            sdraw.rounded_rectangle(
                [(x3, y_top), (x4, y_bot)],
                radius=pill_r,
                fill=(8, 16, 28, 165),
                outline=(254, 77, 42, 75),
                width=max(1, self._renderer.px(1)),
            )
            avail_w = max(1, int(x4 - x3) - pad * 2)
            n_enemy = len(enemy_states)
            step = min(default_step, max(4, avail_w // n_enemy))
            icon_w = min(default_w, max(4, step - max(1, self._renderer.px(2))))
            icon_h = max(3, round(default_h * icon_w / default_w))
            iy = y_top + max(0, (slot_h - icon_h) // 2)
            ordered = sorted(
                enemy_states,
                key=lambda item: (-SPECIES_RANK.get(item[0], 99), 0 if item[1] else 1),
            )
            start_x = int(x3) + pad
            for idx, (species, is_alive) in enumerate(ordered):
                ic = self._get_fleet_icon(species, "enemy", is_alive, icon_w, icon_h)
                strip.alpha_composite(ic, (start_x + idx * step, iy))

        self._fleet_strip_sig = sig
        self._fleet_strip_img = strip
        return strip

    @staticmethod
    def _ttw_label(time_to_win: float) -> tuple[str, str]:
        """Formats the time.

        Args:
            time_to_win (float): Time to win.

        Returns:
            tuple[str, str]: The formatted time.
        """
        if time_to_win == -1:
            return "--", "--"

        minutes, seconds = int(time_to_win // 60), int(time_to_win % 60)
        return f"{minutes:02d}", f"{seconds:02d}"

    def draw(self, game_time: int, image: Image.Image):
        """Draws the score bar, score text, fleet status bar, and score timer into the image.

        Args:
            game_time (int): _description_
            image (Image.Image): _description_
        """
        evt = self._replay_data.events[game_time]
        evt_score = evt.evt_score
        base = self._base.copy()

        sc1 = evt_score[0]
        sc2 = evt_score[1]

        win_score = max(1, self._replay_data.game_win_score)
        per1 = max(0.0, min(1.0, 1 - sc1.score / win_score))
        per2 = max(0.0, min(1.0, 1 - sc2.score / win_score))

        draw = ImageDraw.Draw(base)
        mid = base.width / 2
        space_width = self._renderer.px(150)
        margin = self._renderer.px(5)
        y1 = self._renderer.px(4)
        y2 = self._renderer.px(34)

        st = f"{sc1.score} : {sc2.score}"
        draw.text(
            (mid, round((y1 + y2) / 2)),
            text=st,
            font=self._font,
            fill="white",
            anchor="mm",
        )

        x1 = margin
        x2 = mid - space_width / 2
        draw.rectangle(((x1, y1), (x2, y2)), outline=COLORS_NORMAL[0])
        x3 = mid + space_width / 2
        x4 = base.width - margin
        draw.rectangle(((x3, y1), (x4, y2)), outline=COLORS_NORMAL[1])
        a1 = margin + (x2 * per1) - (margin * per1)
        draw.rectangle(((a1, y1), (x2, y2)), fill=COLORS_NORMAL[0])
        a4 = x4 - (base.width / 2 - space_width / 2) * per2 + (margin * per2)
        draw.rectangle(((x3, y1), (a4, y2)), fill=COLORS_NORMAL[1])

        if self._green_tag:
            self._draw_tag(draw, self._green_tag, (x1, x2), (y1, y2))

        if self._red_tag:
            self._draw_tag(draw, self._red_tag, (x3, x4), (y1, y2))

        # Symmetrical alive/sunk ship-class strip below the score bars
        evt_vehicles = evt.evt_vehicle
        ally_states = tuple(
            (
                self._player_species(p),
                evt_vehicles[p.ship_id].is_alive if p.ship_id in evt_vehicles else True,
            )
            for p in self._ally_players
        )
        enemy_states = tuple(
            (
                self._player_species(p),
                evt_vehicles[p.ship_id].is_alive if p.ship_id in evt_vehicles else True,
            )
            for p in self._enemy_players
        )
        fleet_strip = self._build_fleet_strip(
            ally_states,
            enemy_states,
            (round(x1), round(x2), round(x3), round(x4)),
            base.size,
        )
        base = Image.alpha_composite(base, fleet_strip)

        image.alpha_composite(base, self._renderer.xy((40, 0)))

        ttw = evt.evt_times_to_win
        if ttw is None:
            ally_label, enemy_label = ("--", "--"), ("--", "--")
        else:
            ally_label, enemy_label = self._ttw_label(ttw[0]), self._ttw_label(
                ttw[1]
            )
        timers_base = self._timers_base.copy()
        draw = ImageDraw.Draw(timers_base)

        draw.text(
            self._renderer.xy((ALLY_TIMER_POS[0] - 3, ALLY_TIMER_POS[1])),
            ally_label[0],
            COLORS_NORMAL[0],
            self._timers_font,
            anchor="rm",
        )
        draw.text(
            self._renderer.xy((ALLY_TIMER_POS[0] + 2, ALLY_TIMER_POS[1])),
            ally_label[1],
            COLORS_NORMAL[0],
            self._timers_font,
            anchor="lm",
        )
        draw.text(
            self._renderer.xy((ENEMY_TIMER_POS[0] - 3, ENEMY_TIMER_POS[1])),
            enemy_label[0],
            COLORS_NORMAL[1],
            self._timers_font,
            anchor="rm",
        )
        draw.text(
            self._renderer.xy((ENEMY_TIMER_POS[0] + 2, ENEMY_TIMER_POS[1])),
            enemy_label[1],
            COLORS_NORMAL[1],
            self._timers_font,
            anchor="lm",
        )
        image.alpha_composite(timers_base, self._renderer.xy((757, 0)))

    def _draw_tag(
        self,
        draw: ImageDraw.ImageDraw,
        tag: str,
        bar_xs: tuple,
        bar_ys: tuple,
    ):
        x1, x2 = bar_xs
        y1, y2 = bar_ys
        bbox = self._font.getbbox(tag)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        bar_mid = x1 + (x2 - x1) / 2
        ty = y1 + (y2 - y1) / 2 - th / 2 - bbox[1]
        draw.text(
            (bar_mid - tw / 2 - bbox[0], ty),
            tag,
            "white",
            self._font,
            stroke_fill=self._renderer.bg_color,
            stroke_width=max(1, self._renderer.px(2)),
        )
