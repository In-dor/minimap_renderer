from PIL import Image, ImageDraw
from math import ceil, floor, pi
import numpy as np
from renderer.base import LayerBase
from renderer.render import Renderer
from typing import Optional
from renderer.data import ReplayData


class LayerSmokeBase(LayerBase):
    """The class that handles/draws smokes to the minimap.

    Args:
        LayerBase (_type_): _description_
    """

    def __init__(
        self, renderer: Renderer, replay_data: Optional[ReplayData] = None
    ):
        """Initializes this class.

        Args:
            renderer (Renderer): _description_
        """
        self._renderer = renderer
        self._replay_data = (
            replay_data if replay_data else self._renderer.replay_data
        )
        self._cached_smokes = None
        self._cached_sig = None
        self._cached_overlay = None

    def draw(self, game_time: int, image: Image.Image):
        """Draws the smokes to the minimap.

        Args:
            game_time (int): Game time.
            image (Image.Image): Image to paste the smokes to.
        """
        events = self._replay_data.events
        evt_smoke = events[game_time].evt_smoke
        smokes = evt_smoke.values()

        if not smokes:
            return

        smoke_sig = tuple(
            (sid, s.radius, tuple(s.points)) for sid, s in evt_smoke.items()
        )
        if evt_smoke is self._cached_smokes or smoke_sig == self._cached_sig:
            overlay, position = self._cached_overlay
            image.alpha_composite(overlay, position)
            return

        assert self._renderer.minimap_fg
        circles = []
        for smoke in smokes:
            r = self._renderer.get_scaled_r(smoke.radius)
            for point in smoke.points:
                x, y = self._renderer.get_scaled(point)
                circles.append((x, y, r))

        if not circles:
            return

        ring_w = max(1, self._renderer.px(1.5))
        pad = ring_w + 2
        left = max(0, floor(min(x - r for x, _, r in circles)) - pad)
        top = max(0, floor(min(y - r for _, y, r in circles)) - pad)
        right = min(
            image.width, ceil(max(x + r for x, _, r in circles)) + pad + 1
        )
        bottom = min(
            image.height, ceil(max(y + r for _, y, r in circles)) + pad + 1
        )
        if right <= left or bottom <= top:
            return

        w, h = right - left, bottom - top
        aa = 2
        aw, ah = w * aa, h * aa
        aring_w = ring_w * aa

        fill_mask = Image.new("L", (aw, ah), 0)
        fill_draw = ImageDraw.Draw(fill_mask)
        inner_mask = Image.new("L", (aw, ah), 0)
        inner_draw = ImageDraw.Draw(inner_mask)
        ring_img = Image.new("RGBA", (aw, ah), (0, 0, 0, 0))
        ring_draw = ImageDraw.Draw(ring_img)

        for x, y, r in circles:
            cx = (x - left) * aa
            cy = (y - top) * aa
            ar = r * aa
            fill_draw.ellipse([(cx - ar, cy - ar), (cx + ar, cy + ar)], fill=255)
            ir = max(0.0, ar - aring_w * 1.1)
            if ir > 0:
                inner_draw.ellipse(
                    [(cx - ir, cy - ir), (cx + ir, cy + ir)], fill=255
                )
            dash_count = max(14, round(2 * pi * r / max(4, self._renderer.px(9))))
            step = 360.0 / dash_count
            arc_span = step * 0.56
            bbox = [(cx - ar, cy - ar), (cx + ar, cy + ar)]
            for idx in range(dash_count):
                start = idx * step
                ring_draw.arc(
                    bbox,
                    start=start,
                    end=start + arc_span,
                    fill=(220, 234, 248, 175),
                    width=aring_w,
                )

        # Erase interior overlapping arcs so only the outer perimeter is dashed
        ring_arr = np.array(ring_img)
        inner_arr = np.array(inner_mask)
        ring_arr[:, :, 3] = np.where(inner_arr > 128, 0, ring_arr[:, :, 3])
        ring_clean = Image.fromarray(ring_arr, mode="RGBA")

        base_hi = Image.new("RGBA", (aw, ah), (0, 0, 0, 0))
        mist_layer = Image.new("RGBA", (aw, ah), (220, 232, 245, 34))  # #dce8f522
        base_hi.paste(mist_layer, (0, 0), mask=fill_mask)
        base_hi = Image.alpha_composite(base_hi, ring_clean)
        base = base_hi.resize((w, h), Image.Resampling.LANCZOS)

        position = (left, top)
        self._cached_smokes = evt_smoke
        self._cached_sig = smoke_sig
        self._cached_overlay = (base, position)
        image.alpha_composite(base, position)
