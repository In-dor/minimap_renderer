from typing import Optional
from PIL import Image, ImageDraw
from renderer.base import LayerBase
from renderer.const import COLORS_NORMAL
from renderer.data import Message, ReplayData
from renderer.render import Renderer
from functools import lru_cache

class LayerChatBase(LayerBase):
    """The class for handling in-game chat messages.

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
        self._font = None # to be decided per message
        self._players = self._replay_data.player_info
        self._generated_lines: dict[int, Image.Image] = {}
        self._messages: list[tuple[int, Message]] = []
        self._line_cache: dict[tuple[Optional[int], Message], Image.Image] = {}
        int_keys = [k for k in self._replay_data.events if isinstance(k, int)]
        self._start_time_left = (
            self._replay_data.events[min(int_keys)].time_left
            if int_keys
            else 1200
        )

    def draw(self, game_time: int, image: Image.Image):
        """Draw the in-game chat to the image.

        Args:
            game_time (int): The game time.
            image (Image.Image): The image where the chat will be pasted to,
        """
        evt = self._replay_data.events[game_time]
        if evt.evt_chat:
            if isinstance(game_time, int):
                ts_sec = max(0, game_time)
            else:
                ts_sec = max(0, self._start_time_left - evt.time_left)
            for msg in evt.evt_chat:
                self._messages.append((ts_sec, msg))

        x_pos = self._renderer.px(818)
        y_pos = self._renderer.px(840)
        min_y = self._renderer.px(750)

        for ts_sec, message in reversed(self._messages[-5:]):
            line = self.build(message, ts_sec)
            _, l_h = line.size
            y_pos -= l_h
            if y_pos < min_y:
                break
            image.alpha_composite(line, (x_pos, y_pos))

    def build(
        self, message: Message, timestamp_sec: Optional[int] = None
    ) -> Image.Image:
        """Builds the line message as an image.

        Args:
            message (Message): The message.
            timestamp_sec (Optional[int]): Elapsed battle seconds for [MM:SS].

        Returns:
            Image.Image: Image of the chat message.
        """
        cache_key = (timestamp_sec, message)
        if cached := self._line_cache.get(cache_key):
            return cached

        player = self._players[message.player_id]
        if self._renderer.anon and player.clan_tag:
            clan_tag = "#" * len(player.clan_tag)
        elif player.clan_tag:
            clan_tag = player.clan_tag
        else:
            clan_tag = ""

        if self._renderer.anon:
            name = self._renderer.usernames[player.id]
        else:
            name = player.name

        self._font = self._renderer.resman.load_font_with_text(
            f"{clan_tag}{name}{message.message}", size=12
        )
        line_h = self._renderer.px(18)
        max_w = self._renderer.px(518)
        base = Image.new("RGBA", (max_w, line_h))
        draw = ImageDraw.Draw(base)

        sample_text = f"[00:00] [{clan_tag}]{name}: {message.message}"
        sb = self._font.getbbox(sample_text)
        draw_y = (line_h - (sb[3] - sb[1])) // 2 - sb[1]

        x_pos = 0
        if timestamp_sec is not None:
            ts_str = f"[{timestamp_sec // 60:02d}:{timestamp_sec % 60:02d}] "
            ts_b = self._font.getbbox(ts_str)
            ts_w = ts_b[2] - ts_b[0]
            draw.text((x_pos, draw_y), ts_str, "#9fb2c8", self._font)
            x_pos += ts_w

        if player.clan_tag:
            clan_str = f"[{clan_tag}]"
            c_b = self._font.getbbox(clan_str)
            c_w = c_b[2] - c_b[0]
            draw.text(
                (x_pos, draw_y),
                clan_str,
                self.unpack_color(player.clan_color),
                self._font,
            )
            x_pos += c_w

        n_color = (
            COLORS_NORMAL[0]
            if player.relation in [-1, 0]
            else COLORS_NORMAL[1]
        )

        name_str = f"{name}: "
        n_b = self._font.getbbox(name_str)
        n_w = n_b[2] - n_b[0]
        draw.text((x_pos, draw_y), name_str, n_color, self._font)
        x_pos += n_w

        if message.namespace == "battle_common":
            m_color = "white"
        elif message.namespace == "battle_prebattle":
            m_color = "#ffd24c"
        else:
            m_color = n_color

        text = message.message
        mb = self._font.getbbox(text)
        m_w = mb[2] - mb[0]
        avail_w = max(0, max_w - x_pos)

        if m_w > avail_w and text:
            low, high, best = 0, len(text), 0
            while low <= high:
                mid = (low + high) // 2
                cand = f"{text[:mid]}..."
                cb = self._font.getbbox(cand)
                if (cb[2] - cb[0]) <= avail_w:
                    best = mid
                    low = mid + 1
                else:
                    high = mid - 1
            text = f"{text[:best]}..."

        draw.text((x_pos, draw_y), text, m_color, self._font)
        self._line_cache[cache_key] = base
        return base

    @staticmethod
    def unpack_color(packed_value: int) -> tuple:
        """Unpacks packed color integer as RGB component.

        Args:
            packed_value (int): The packed color integer.

        Returns:
            tuple: RGB component.
        """
        bits = [8, 8, 8]
        values = []
        for bit in bits:
            value = packed_value & (2**bit - 1)
            packed_value = packed_value >> bit
            values.append(value)
        return tuple(reversed(values))
