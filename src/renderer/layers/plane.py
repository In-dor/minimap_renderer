from typing import Optional
import numpy as np

from renderer.data import ReplayData
from renderer.render import Renderer
from renderer.base import LayerBase
from renderer.const import RELATION_NORMAL_STR

from PIL import Image
from functools import lru_cache


class LayerPlaneBase(LayerBase):
    """A class that handles/draws planes.

    Args:
        LayerBase (_type_): _description_
    """

    def __init__(
        self,
        renderer: Renderer,
        replay_data: Optional[ReplayData] = None,
        color: Optional[str] = None,
    ):
        """Initiates this class.

        Args:
            renderer (Renderer): The renderer.
        """
        self._renderer = renderer
        self._replay_data = (
            replay_data if replay_data else self._renderer.replay_data
        )
        self._color = color
        self._planes = renderer.resman.load_json("planes.json")
        self._vehicle_id_to_player = {
            v.ship_id: v for v in self._replay_data.player_info.values()
        }

    def draw(self, game_time: int, image: Image.Image):
        """Draws the planes to the minimap image.

        Args:
            game_time (int): Game time.
            image (Image.Image): The minimap image.
        """
        planes = self._replay_data.events[game_time].evt_plane

        if not planes:
            return

        for plane in planes.values():
            if plane.relation == 1 and self._renderer.dual_mode:
                continue

            x, y = self._renderer.get_scaled(plane.position)
            icon = self._get_plane_icon(
                plane.owner_id,
                plane.params_id,
                plane.purpose,
                plane.relation,
            )
            m1 = round(icon.width / 2)
            m2 = round(icon.height / 2)
            image.alpha_composite(icon, (x - m1, y - m2))

    @lru_cache
    def _get_plane_icon(
        self, owner_id: int, params_id: int, purpose: int, plane_relation: int
    ) -> Image.Image:
        """Loads the plane icon from the resources.

        Args:
            owner_id (int): Owner vehicle id.
            params_id (int): Plane resource id.
            purpose (int): Plane role.
            plane_relation (int): Relation to the replay owner.

        Returns:
            Image.Image: The image of the plane.
        """
        try:
            player = self._vehicle_id_to_player[owner_id]
            try:
                upgrade = 22 in player.skills.AirCarrier
            except IndexError:
                upgrade = False
        except KeyError:
            upgrade = False
        ptype, ammo = self._planes[params_id]

        if self._color:
            relation = "ally" if self._color == "green" else "enemy"
        else:
            relation = RELATION_NORMAL_STR[plane_relation]

        icon_res = f"plane_icons.{relation}"

        if purpose in [0, 1]:
            if ptype == "Dive":
                filename = f"Dive_{ammo}.png"
                icon = self._renderer.resman.load_image(
                    filename, path=icon_res
                )
            else:
                filename = f"{ptype}.png"
                icon = self._renderer.resman.load_image(
                    filename, path=icon_res
                )
        elif purpose in [2, 3]:
            relation = "ally" if plane_relation == -1 else relation
            icon_res = f"plane_icons.{relation}"

            if purpose == 2 and upgrade:
                icon = self._renderer.resman.load_image(
                    "Cap_upgrade.png", path=icon_res
                )
            else:
                icon = self._renderer.resman.load_image(
                    "Cap.png", path=icon_res
                )
        else:
            if purpose == 6:
                filename = f"Airstrike_{ammo}.png"
                icon = self._renderer.resman.load_image(
                    filename, path=icon_res
                )
            else:
                filename = "Scout.png"
                icon = self._renderer.resman.load_image(
                    filename, path=icon_res
                )

        if purpose == 1:
            icon_px = np.array(icon)
            icon_px[icon_px[:, :, 3] == 255, 3] = 64
            icon = Image.fromarray(icon_px, mode="RGBA")

        return icon
