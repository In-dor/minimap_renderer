"""
World of Warships Replay Battle Report Infographic Generator
Generates a modern, ultra-high-definition (2.4K) post-battle scoreboard & tactical summary image,
complete with combat stats, weapon breakdown, medals, ribbons, tactical minimap tracks,
team HP timeline, and adaptive multi-line match communications log.
"""

from __future__ import annotations

from functools import lru_cache
from io import BytesIO
import json
import math
import os
import re
import struct
from typing import Any, Optional

from PIL import Image, ImageDraw, ImageFont

from replay_parser import ReplayParser, CustomReader
from renderer.resman import ResourceManager

# Comprehensive localized map dictionary (covers manifest.json spaces + fallback to global.mo)
MAP_NAMES: dict[str, str] = {
    "00_CO_ocean": "大洋",
    "01_solomon_islands": "所罗门群岛",
    "04_Archipelago": "群岛",
    "05_Ring": "圆环",
    "08_NE_passage": "海峡",
    "10_NE_big_race": "大环礁",
    "13_OC_new_dawn": "新曙光",
    "14_Atlantic": "大西洋",
    "15_NE_north": "北方之水",
    "16_OC_bees_to_honey": "热点",
    "17_NA_fault_line": "断层线",
    "18_NE_ice_islands": "冰海追击",
    "19_OC_prey": "陷阱",
    "20_NE_two_brothers": "双子峡谷",
    "22_tierra_del_fuego": "火地岛",
    "23_Shards": "碎钻群岛",
    "25_sea_hope": "幸运之海",
    "28_naval_mission": "荒漠之泪",
    "33_new_tierra": "极地",
    "34_OC_islands": "列岛",
    "35_NE_north_winter": "北方之水 (雪景)",
    "37_Ridge": "山脉",
    "38_Canada": "碎片",
    "40_Okinawa": "冲绳",
    "41_Conquest": "沙漠之泪",
    "42_Neighbors": "邻界群岛",
    "44_Path_warrior": "勇士之路",
    "45_Zigzag": "八爪群岛",
    "46_Estuary": "河口",
    "47_Sleeping_Giant": "沉睡的巨人",
    "50_Gold_harbor": "黄金港",
    "51_Greece": "希腊",
    "52_Britain": "赫里福德海峡",
    "53_Shoreside": "北方水域",
    "54_Faroe": "法罗群岛",
    "55_Seychelles": "塞舌尔",
    "56_AngelWings": "落日群岛",
    "58_RidgeNew": "山脉",
    "e02_Halloween_2017": "巨龙海湾 (万圣节)",
    "e04_Halloween_2018": "渡鸦海湾 (万圣节)",
    "e09_Halloween_2019": "怪物海湾 (万圣节)",
    "e14_ModernEra": "极地水域 (时空裂隙)",
    "e15_Bermuda_Triangle": "百慕大迷雾群岛",
    "e15_Bermuda_Triangle_2": "百慕大迷雾群岛",
    "e15_Bermuda_Triangle_3": "百慕大迷雾群岛",
    "e15_Bermuda_Triangle_4": "百慕大迷雾群岛",
    "r01_military_navigation": "反击",
    "s01_NavalBase": "虎鲸行动",
    "s02_Naval_Defense": "防守纽波特海军基地",
    "s03_Labyrinth": "宙斯盾行动",
    "s06_Atoll": "终极前沿",
    "s07_Advance": "纳莱行动",
    "s09_LePVE": "赫尔墨斯行动",
    "s10_USS_CL": "樱花行动",
    "s12_WW2_OP1": "巴伦支海 (北极护航)",
    "s13_WW2_OP2": "所罗门海 (东京快车)",
    "s14_WW2_OP3": "环礁 (太平洋攻势)",
}

SCENARIO_NAMES: dict[str, str] = {
    "armsrace": "军备竞赛",
    "domination": "占领模式",
    "domination_2point": "双点占领",
    "domination_3point": "三点占领",
    "domination_3point_revised": "三点占领 (改版)",
    "domination_4point": "四点占领",
    "domination_localweather_3points": "暴风三点占领",
    "domination_special_respawns": "重生占领模式",
    "domination_tournament_3point": "锦标赛三点占领",
    "ranked_domination": "排位占领模式",
    "cvc_domination": "军团战占领模式",
    "standard": "标准战斗",
    "epicenter": "震中模式",
    "airship": "飞艇护航",
    "two_airships": "双飞艇护航",
    "2wagons": "双飞艇护航",
    "convoy_12x12": "护航战 (12v12)",
    "convoypve": "护航行动",
    "1_modernera_pve_attack": "现代裂隙行动",
}

GAME_TYPE_NAMES: dict[str, str] = {
    "RandomBattle": "随机战",
    "RankedBattle": "排位战",
    "ClanBattle": "军团战",
    "CooperativeBattle": "联合人机",
    "PVEBattle": "行动模式",
    "Operation": "行动模式",
    "EventBattle": "限时活动",
    "BrawlBattle": "对决模式",
}

SPECIES_SHORT: dict[str, str] = {
    "Battleship": "BB",
    "Cruiser": "CA",
    "Destroyer": "DD",
    "AirCarrier": "CV",
    "Submarine": "SS",
    "Auxiliary": "AUX",
}

SPECIES_NAMES: dict[str, str] = {
    "Battleship": "战列舰",
    "Cruiser": "巡洋舰",
    "Destroyer": "驱逐舰",
    "AirCarrier": "航空母舰",
    "Submarine": "潜艇",
    "Auxiliary": "支援/护卫舰",
}

NATION_NAMES: dict[str, str] = {
    "USA": "美国",
    "Japan": "日本",
    "Germany": "德国",
    "Russia": "苏联",
    "United_Kingdom": "英国",
    "France": "法国",
    "Italy": "意大利",
    "Pan_Asia": "泛亚",
    "Europe": "欧洲",
    "Netherlands": "荷兰",
    "Commonwealth": "英联邦",
    "Pan_America": "泛美",
    "Spain": "西班牙",
    "Events": "特殊活动",
}

TIER_ROMAN = {
    1: "I", 2: "II", 3: "III", 4: "IV", 5: "V",
    6: "VI", 7: "VII", 8: "VIII", 9: "IX", 10: "X", 11: "★",
}

ACHIEVEMENT_NAMES: dict[str, str] = {
    "AIRDEFENSEEXPERT": "防空专家",
    "AIRKING": "制空权",
    "ARSONIST": "纵火犯",
    "ATBA_CALIBER": "肉搏战专家",
    "BATTLE_HERO": "战斗英雄",
    "BROTHERS_IN_ARMS": "兄弟连",
    "CLASSDESTROY_SQUAD": "协同歼灭",
    "CLEAR_SKY": "晴空万里",
    "CONFEDERATE": "联盟支持",
    "CONTRIBUTOR": "重大贡献",
    "DECISIVE_CONTRIBUTION": "决定性贡献",
    "DETONATED": "殉爆",
    "DIE_HARD": "虎口余生",
    "DOUBLE_KILL": "双重打击",
    "DREADNOUGHT": "坚不可摧",
    "FIREPROOF": "防火能手",
    "FIRESHOW": "纵火狂人",
    "FIRST_BLOOD": "第一滴血",
    "FRAG_SQUAD": "兄弟连",
    "HEADBUTT": "迎头痛击",
    "HIGH_CALIBER": "大口径",
    "INSTANT_KILL": "毁灭打击",
    "KRAKEN": "海怪出没",
    "LIQUIDATOR": "清算者",
    "MAIN_CALIBER": "大口径",
    "MAIN_CALIBER_SQUAD": "分队大口径",
    "MESSENGER": "信使",
    "SOLO_WARRIOR": "孤胆英雄",
    "SUPPORT": "联合火力",
    "SUPPORT_SQUAD": "支援协作",
    "TORPEDOPROOF": "防雷专家",
    "UNSINKABLE": "灭火之王",
    "WARRIOR": "海上勇士",
    "WARRIOR_SQUAD": "联合作战",
    "WITHERING": "凋零之火",
}

WEAPON_CATEGORY_MAP: dict[int, str] = {
    1: "主炮",
    2: "主炮",
    32: "主炮",
    3: "副炮",
    4: "副炮",
    33: "副炮",
    7: "鱼雷",
    12: "鱼雷",
    60: "声导雷",
    41: "火箭弹",
    43: "航弹",
    17: "起火",
    6: "起火",
    20: "进水",
    8: "进水",
    57: "深弹",
    58: "深弹",
    70: "水雷",
    10: "撞击",
    83: "导弹",
}

RIBBON_ORDER: list[str] = [
    "frag",
    "citadel",
    "main_caliber",
    "torpedo",
    "burn",
    "flood",
    "rocket",
    "bomb",
    "plane",
    "splane",
    "secondary_caliber",
    "crit",
    "acoustic_hit",
    "dbomb",
    "dbomb_mine",
    "base_capture",
    "base_capture_assist",
    "base_defense",
    "detected",
    "suppressed",
    "assist",
    "building_kill",
    "drop",
    "missile",
    "phaser_laser",
    "pulse_phaser",
    "shield",
    "wave",
    "acid",
    "mine",
]


def _resources_dir() -> str:
    return os.path.join(os.path.dirname(__file__), "resources")


def _project_resources_dir() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "resources"))


@lru_cache(maxsize=1)
def _load_global_mo_catalog() -> dict[str, str]:
    """Loads resources/global.mo catalog safely with UTF-8 decoding (tolerating malformed MO headers)."""
    mo_path = os.path.join(_project_resources_dir(), "global.mo")
    if not os.path.exists(mo_path):
        return {}
    try:
        with open(mo_path, "rb") as f:
            buf = f.read()
        if len(buf) < 28:
            return {}
        magic = struct.unpack("<I", buf[:4])[0]
        endian = "<" if magic == 0x950412DE else (">" if magic == 0xDE120495 else None)
        if endian is None:
            return {}
        _, _, num_strings, orig_off, trans_off, _, _ = struct.unpack(endian + "IIIIIII", buf[:28])
        catalog: dict[str, str] = {}
        for i in range(num_strings):
            olen, ooff = struct.unpack(endian + "II", buf[orig_off + i * 8: orig_off + i * 8 + 8])
            tlen, toff = struct.unpack(endian + "II", buf[trans_off + i * 8: trans_off + i * 8 + 8])
            if ooff + olen <= len(buf) and toff + tlen <= len(buf):
                orig = buf[ooff: ooff + olen].decode("utf-8", errors="replace")
                trans = buf[toff: toff + tlen].decode("utf-8", errors="replace")
                if orig:
                    catalog[orig] = trans
        return catalog
    except Exception:
        return {}


def _translate_ids(key: str, default: Optional[str] = None) -> str:
    if not key:
        return default if default is not None else ""
    cat = _load_global_mo_catalog()
    val = cat.get(key)
    if val:
        return val
    return default if default is not None else key


def _resolve_map_title(map_code: str) -> str:
    if map_code in MAP_NAMES:
        return MAP_NAMES[map_code]
    for candidate in (f"IDS_SPACES/{map_code.upper()}", f"IDS_SPACES_{map_code.upper()}"):
        mo_val = _load_global_mo_catalog().get(candidate)
        if mo_val:
            return mo_val
    return map_code.replace("_", " ")


def _resolve_scenario_title(scenario_code: str) -> str:
    if not scenario_code:
        return "标准模式"
    if scenario_code in SCENARIO_NAMES:
        return SCENARIO_NAMES[scenario_code]
    low = scenario_code.lower()
    if low in SCENARIO_NAMES:
        return SCENARIO_NAMES[low]
    if "ww2_operation" in low or low.startswith("pcvo") or "_op_" in low:
        mo_val = _load_global_mo_catalog().get(f"IDS_SCENARIO_{scenario_code.upper()}")
        if mo_val:
            return f"行动 · {mo_val}"
        return "行动剧情"
    if "domination" in low:
        return "占领模式"
    if "armsrace" in low:
        return "军备竞赛"
    if "convoy" in low:
        return "护航模式"
    mo_val = _load_global_mo_catalog().get(f"IDS_SCENARIO_{scenario_code.upper()}")
    return mo_val or scenario_code


def _resolve_achievement_title(ach_code: str) -> str:
    if ach_code in ACHIEVEMENT_NAMES:
        return ACHIEVEMENT_NAMES[ach_code]
    mo_val = _load_global_mo_catalog().get(f"IDS_ACHIEVEMENT_{ach_code.upper()}")
    if mo_val:
        return mo_val
    return ach_code.replace("_", " ")


@lru_cache(maxsize=64)
def _load_font(font_path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(font_path, size)
    except Exception:
        fallback = os.path.join(_resources_dir(), "warhelios_bold.ttf")
        if os.path.exists(fallback) and fallback != font_path:
            return ImageFont.truetype(fallback, size)
        return ImageFont.load_default()


def _select_font_path_for_text(text: str) -> str:
    res_dir = _resources_dir()
    has_kana = False
    has_hangul = False
    has_hanzi = False
    has_thai = False
    has_cjk_or_special = False
    for ch in text:
        code = ord(ch)
        if 0x3040 <= code <= 0x30FF:
            has_kana = True
            has_cjk_or_special = True
            break
        elif 0xAC00 <= code <= 0xD7AF:
            has_hangul = True
            has_cjk_or_special = True
        elif 0x4E00 <= code <= 0x9FFF:
            has_hanzi = True
            has_cjk_or_special = True
        elif 0x0E00 <= code <= 0x0E7F:
            has_thai = True
        elif 0x2500 <= code <= 0x27BF or 0x3000 <= code <= 0x33FF or 0xFF00 <= code <= 0xFFEF:
            has_cjk_or_special = True

    if has_kana:
        jp_path = os.path.join(res_dir, "warhelios_bold_jp.ttf")
        if os.path.exists(jp_path):
            return jp_path
    elif has_hangul and not has_hanzi:
        ko_path = os.path.join(res_dir, "warhelios_bold_ko.ttf")
        if os.path.exists(ko_path):
            return ko_path
    elif has_thai and not has_cjk_or_special:
        for win_font in (
            r"C:\Windows\Fonts\leelauib.ttf",
            r"C:\Windows\Fonts\leelawui.ttf",
            r"C:\Windows\Fonts\tahomabd.ttf",
            r"C:\Windows\Fonts\tahoma.ttf",
        ):
            if os.path.exists(win_font):
                return win_font

    if not has_cjk_or_special and not has_thai:
        base_path = os.path.join(res_dir, "warhelios_bold.ttf")
        if os.path.exists(base_path):
            return base_path

    zh_path = os.path.join(res_dir, "warhelios_bold_zh.ttf")
    if os.path.exists(zh_path):
        return zh_path
    return os.path.join(res_dir, "warhelios_bold.ttf")


@lru_cache(maxsize=512)
def _select_font_for_text_cached(font_path: str, size: int) -> ImageFont.FreeTypeFont:
    return _load_font(font_path, size)


def select_font_for_text(text: str, size: int) -> ImageFont.FreeTypeFont:
    """Selects JP / KO / ZH font based on script characters with lru_cache."""
    font_path = _select_font_path_for_text(text)
    return _select_font_for_text_cached(font_path, size)


@lru_cache(maxsize=512)
def _load_scaled_icon(icon_path: str, width: int, height: int) -> Optional[Image.Image]:
    if not icon_path or not os.path.exists(icon_path):
        return None
    try:
        with Image.open(icon_path) as im:
            rgba = im.convert("RGBA")
            if rgba.size != (width, height):
                rgba = rgba.resize((width, height), Image.Resampling.LANCZOS)
            return rgba.copy()
    except Exception:
        return None


@lru_cache(maxsize=128)
def _load_tinted_ship_icon(
    species: str,
    color: tuple[int, int, int],
    width: int = 24,
    height: int = 13,
) -> Optional[Image.Image]:
    res_dir = _resources_dir()
    ship_icons_dir = os.path.join(res_dir, "ship_icons")
    icon_file = os.path.join(ship_icons_dir, f"{species}_ally.png")
    if not os.path.exists(icon_file):
        icon_file = os.path.join(ship_icons_dir, "Battleship_ally.png")
    if not os.path.exists(icon_file):
        return None
    try:
        with Image.open(icon_file) as im:
            rot = im.convert("RGBA").rotate(-90, Image.Resampling.BICUBIC, expand=True)
            resized = rot.resize((width, height), Image.Resampling.LANCZOS)
            alpha = resized.getchannel("A")
            tinted = Image.new("RGBA", (width, height), (color[0], color[1], color[2], 255))
            tinted.putalpha(alpha)
            return tinted
    except Exception:
        return None


def unpack_color(color_int: int) -> tuple[int, int, int]:
    """Unpacks ARGB color integer into (R, G, B)."""
    if color_int == 0 or color_int is None:
        return (235, 240, 245)
    r = (color_int >> 16) & 0xFF
    g = (color_int >> 8) & 0xFF
    b = color_int & 0xFF
    return (r, g, b)


def format_datetime_zh(dt_str: str) -> str:
    """Formats date-time string like '07.09.2026 12:36:22' into '2026年09月07日 12:36:22'."""
    try:
        parts = dt_str.strip().split(" ", 1)
        if len(parts) == 2:
            d_parts = parts[0].split(".")
            time_part = parts[1]
            if len(d_parts) == 3:
                day, month, year = d_parts
                if len(year) == 4:
                    return f"{year}年{int(month):02d}月{int(day):02d}日 {time_part}"
                elif len(day) == 4:
                    return f"{day}年{int(month):02d}月{int(year):02d}日 {time_part}"
        elif len(parts) == 1:
            d_parts = parts[0].split(".")
            if len(d_parts) == 3:
                day, month, year = d_parts
                if len(year) == 4:
                    return f"{year}年{int(month):02d}月{int(day):02d}日"
        return dt_str
    except Exception:
        return dt_str


def extract_post_battle_results(replay_path: str) -> Optional[dict[str, Any]]:
    """Fallback extractor for official post-battle settlement results (Packet 0x22) from replay stream."""
    if not replay_path or not os.path.exists(replay_path):
        return None
    try:
        with open(replay_path, "rb") as f:
            reader = CustomReader(f)
            dec = reader.get_replay_data().decrypted_data
        io = BytesIO(dec)
        slen = len(dec)
        while io.tell() < slen:
            hdr = io.read(12)
            if len(hdr) < 12:
                break
            psize, ptype, _ = struct.unpack("IIf", hdr)
            if ptype == 0x22 and psize > 1024:
                jlen_raw = io.read(4)
                if len(jlen_raw) < 4:
                    break
                jlen = struct.unpack("<I", jlen_raw)[0]
                if 0 < jlen <= psize - 4:
                    payload = io.read(jlen)
                    if payload.startswith(b"{"):
                        return json.loads(payload.decode("utf-8", errors="replace"))
                    io.seek(psize - 4 - jlen, 1)
                else:
                    io.seek(psize - 4, 1)
            else:
                io.seek(psize, 1)
    except Exception:
        pass
    return None


def _format_target_ship(
    tp: Any,
    ships_dict: dict[Any, Any],
) -> str:
    if not tp:
        return ""
    s_info = ships_dict.get(tp.ship_params_id) or ships_dict.get(str(tp.ship_params_id), {})
    if isinstance(s_info, dict) and s_info.get("name"):
        tier = TIER_ROMAN.get(s_info.get("level", 0), str(s_info.get("level", "")))
        return f"[{tier} {s_info['name']}]"
    return tp.name or str(tp.ship_id)


def decode_quick_command(
    raw_bytes: bytes,
    players_by_id: dict,
    ships_by_id: dict,
    map_manifest=None,
    ships_dict: Optional[dict[Any, Any]] = None,
    sender_team_id: int = -1,
    control_points: Optional[dict[int, Any]] = None,
) -> str:
    """Decodes BigWorld QUICK_COMMAND binary payload into localized readable tactical messages."""
    if not raw_bytes:
        return "发送了战术无线电指令"
    cid = raw_bytes[0]
    sub_flag = raw_bytes[2] if len(raw_bytes) >= 3 else 0
    ships_dict = ships_dict or {}

    def get_grid(x: float, z: float) -> str:
        if not map_manifest:
            return f"{x:.0f}, {z:.0f}"
        size, _, scaling = map_manifest
        px = x * scaling + size / 2
        py = -z * scaling + size / 2
        c = max(0, min(9, int(px // (size / 10))))
        r = max(1, min(10, int(py // (size / 10)) + 1))
        return f"{'ABCDEFGHIJ'[c]}{r}"

    def resolve_target() -> tuple[int, int, Any]:
        if len(raw_bytes) < 9:
            return (0, 0, None)
        arg1 = struct.unpack("<H", raw_bytes[3:5])[0]
        tid = struct.unpack("<I", raw_bytes[5:9])[0]
        tp = ships_by_id.get(tid) or players_by_id.get(tid)
        return (arg1, tid, tp)

    if cid == 18 and len(raw_bytes) >= 11:
        x, z = struct.unpack("<ff", raw_bytes[3:11])
        return f"注意扇区 [{get_grid(x, z)}]"

    if cid == 2 and len(raw_bytes) >= 9:
        arg1, tid, tp = resolve_target()
        if arg1 == 11:
            letter = chr(65 + tid) if 0 <= tid < 26 else str(tid + 1)
            cp = control_points.get(tid) if control_points else None
            if cp is not None and sender_team_id != -1:
                action = "防守" if getattr(cp, "team_id", -1) == sender_team_id else "占领"
                return f"{action} {letter} 点！"
            return f"占领/防守 {letter} 点！"
        if arg1 == 15:
            return "注意战术任务目标！"
        if tp:
            t_label = _format_target_ship(tp, ships_dict) or str(tid)
            if sender_team_id != -1 and tp.team_id != sender_team_id:
                return f"优先攻击目标：{t_label}"
            return f"保护友军目标：{t_label}"
        if arg1 == 3:
            return "注意战术目标！"
        return "注意当前战术目标！"

    if cid == 3:
        arg1, tid, tp = resolve_target()
        if arg1 == 0 and tp:
            t_label = _format_target_ship(tp, ships_dict) or str(tid)
            return f"{t_label} 战术撤退！"
        return "战术撤退！"

    if cid == 1:
        return "请求空中支援！"
    if cid == 4:
        return "需要烟幕掩护！"
    if cid == 5:
        return "收到！"
    if cid == 6:
        return "拒绝！"
    if cid == 7:
        arg1, tid, tp = resolve_target()
        if arg1 == 0 and tp:
            t_label = _format_target_ship(tp, ships_dict) or str(tid)
            return f"{t_label} 请求支援！"
        if sub_flag == 1:
            return "请求防空火力支援！"
        return "请求支援！"
    if cid == 8:
        return "祝大家好运！"
    if cid == 9:
        return "请求防空火力支援！"
    if cid == 10:
        arg1, tid, tp = resolve_target()
        if arg1 == 0 and tp:
            t_label = _format_target_ship(tp, ships_dict) or str(tid)
            return f"感谢 {t_label}！"
        return "感谢！"
    if cid == 11:
        return "请求侦察 / 救援支援！"
    if cid == 12:
        arg1, tid, tp = resolve_target()
        if arg1 == 0 and tp:
            t_label = _format_target_ship(tp, ships_dict) or str(tid)
            return f"干得漂亮，{t_label}！"
        return "干得漂亮！"
    if cid == 13:
        return "糟糕！($%*#@!)"
    if cid == 14:
        return "十分抱歉！"
    if cid == 15:
        return "正在使用监视雷达！"
    if cid == 16:
        return "正在使用对海搜索！"
    if cid == 17:
        return "需要情报视野！"
    if cid == 19:
        return "正在使用潜艇监视设备！"
    return f"无线电指令 #{cid}"


def _detect_ribbon_base(
    pub: dict[str, Any],
    owner_dbid: int,
    owner_ribbons_raw: dict[int, int],
) -> int:
    """Detects ribbon array base offset relative to d_idx inside 0x22 playersPublicInfo."""
    if not pub:
        return 76
    sample = next(iter(pub.values()))
    d_idx = next((i for i, v in enumerate(sample) if isinstance(v, dict)), None)
    if d_idx is None:
        return 76

    owner_row = None
    for row in pub.values():
        if row and row[0] == owner_dbid:
            owner_row = row
            break

    if owner_row is not None and owner_ribbons_raw:
        non_zero_ribs = [(int(rid), int(cnt)) for rid, cnt in owner_ribbons_raw.items() if int(rid) != 0 and int(cnt) > 0]
        if non_zero_ribs:
            candidates = [76, 41] + [b for b in range(25, len(owner_row) - d_idx) if b not in (76, 41)]
            for base in candidates:
                ok = True
                for rid, cnt in non_zero_ribs:
                    idx = d_idx + base + rid
                    if idx >= len(owner_row) or owner_row[idx] != cnt:
                        ok = False
                        break
                if ok:
                    return base

    tail_len = len(sample) - d_idx
    return 76 if tail_len >= 120 else 41


def _detect_stat_shift(
    pub: dict[str, Any],
    owner_dbid: int,
    owner_total_dmg: float,
    d_idx: int,
) -> int:
    """Detects 0x22 stats field offset shift (0 for >=14.x, 1 for 13.x)."""
    if owner_total_dmg >= 100:
        for row in pub.values():
            if row and row[0] == owner_dbid and len(row) > d_idx + 22:
                v21 = row[d_idx + 21]
                v22 = row[d_idx + 22]
                if isinstance(v22, (int, float)) and abs(v22 - owner_total_dmg) <= 15:
                    if not (isinstance(v21, (int, float)) and abs(v21 - owner_total_dmg) <= 15):
                        return 1
                if isinstance(v21, (int, float)) and abs(v21 - owner_total_dmg) <= 15:
                    return 0

    has_f14 = any(len(r) > d_idx + 14 and isinstance(r[d_idx + 14], float) for r in pub.values())
    has_f11 = any(len(r) > d_idx + 11 and isinstance(r[d_idx + 11], float) for r in pub.values())
    if has_f14 and not has_f11:
        return 1
    if has_f11 and not has_f14:
        return 0
    sample = next(iter(pub.values()))
    return 1 if (len(sample) - d_idx) < 92 else 0


def _determine_finish_reason(
    victory_type: int,
    winner_team_id: int,
    owner_team_id: int,
    s_ally: int,
    s_enemy: int,
    win_score: int,
    ally_alive: int,
    enemy_alive: int,
) -> str:
    if winner_team_id == -2:
        return "回放记录终止 / 未完结"
    if winner_team_id == -1:
        if ally_alive == 0 and enemy_alive == 0:
            return "双方舰队全灭平局"
        if victory_type == 9:
            return "时间耗尽 · 积分平局"
        return "平局结算"
    if victory_type in (1, 10):
        if enemy_alive == 0 and ally_alive > 0:
            return "敌方舰队全灭"
        if ally_alive == 0 and enemy_alive > 0:
            return "友方舰队全灭"
        return "舰队全灭判定"
    if victory_type == 2:
        return "占领基地获胜"
    if victory_type == 9:
        return "时间耗尽 · 积分判定"
    if victory_type == 11:
        return "行动任务目标判定"
    if victory_type == 12:
        return "积分归零判定"
    if victory_type == 13:
        return f"积分率先达到 {win_score} 分"
    if s_ally >= win_score or s_enemy >= win_score:
        return f"积分率先达到 {win_score} 分"
    if enemy_alive == 0 and ally_alive > 0:
        return "敌方舰队全灭"
    if ally_alive == 0 and enemy_alive > 0:
        return "友方舰队全灭"
    return "对局规则判定"


def parse_replay_report(
    replay_path: str,
    replay_info: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Parses replay (or reuses pre-parsed replay_info) and aggregates full battle report data."""
    if replay_info is None:
        with open(replay_path, "rb") as fp:
            info = ReplayParser(fp).get_info()
    else:
        info = replay_info

    open_meta = info["open"]
    hidden = info["hidden"]
    rd = hidden["replay_data"]
    resman = ResourceManager(rd.game_version)
    ships = resman.load_json("ships.json")
    achievements_dict = resman.load_json("achievements.json")

    players = rd.player_info
    v_to_p = {p.ship_id: p for p in players.values()}
    owner = players[rd.owner_id]

    # Map & game info
    map_code = open_meta.get("mapDisplayName", "") or rd.game_map
    map_title = _resolve_map_title(map_code)
    scenario_code = open_meta.get("scenario", "")
    scenario_title = _resolve_scenario_title(scenario_code)
    game_type_code = open_meta.get("gameType", "")
    game_type_title = GAME_TYPE_NAMES.get(game_type_code, game_type_code)
    date_time = format_datetime_zh(open_meta.get("dateTime", ""))
    client_version = open_meta.get("clientVersionFromExe", rd.game_version)

    # Pre-map players, localized names, and their ship names
    player_ship_name: dict[int, str] = {}
    player_display_name: dict[int, str] = {}
    for p in players.values():
        s_info = ships.get(p.ship_params_id) or ships.get(str(p.ship_params_id), {})
        s_name = s_info.get("name", "") if isinstance(s_info, dict) else ""
        player_ship_name[p.id] = s_name
        raw_name = p.name or str(p.id)
        player_display_name[p.id] = _translate_ids(raw_name, raw_name) if raw_name.startswith("IDS_") else raw_name

    dbid_to_player = {p.account_db_id: p for p in players.values()}

    # Raw planesCount fallback from BattleController
    raw_players = hidden.get("players", {})
    raw_planes_by_ship: dict[int, int] = {}
    raw_planes_by_dbid: dict[int, int] = {}
    if isinstance(raw_players, dict):
        for rp in raw_players.values():
            if isinstance(rp, dict):
                pc = int(rp.get("planesCount", 0) or 0)
                if rp.get("shipId"):
                    raw_planes_by_ship[int(rp["shipId"])] = pc
                if rp.get("accountDBID"):
                    raw_planes_by_dbid[int(rp["accountDBID"])] = pc

    # Owner ribbons (extracted early so we can detect 0x22 ribbon_base accurately)
    SOLO_MAP = {
        1: "torpedo",
        3: "plane",
        4: "crit",
        5: "frag",
        6: "burn",
        7: "flood",
        8: "citadel",
        9: "base_defense",
        10: "base_capture",
        11: "base_capture_assist",
        12: "suppressed",
        13: "secondary_caliber",
        18: "building_kill",
        19: "detected",
        27: "splane",
        31: "dbomb",
        33: "drop",
        52: "phaser_laser",
        53: "pulse_phaser",
        54: "assist",
        55: "missile",
    }
    raw_ribbons = hidden.get("ribbons", {})
    owner_ribbons_raw = raw_ribbons.get(rd.owner_avatar_id) or raw_ribbons.get(owner.ship_id, {})
    processed_ribbons: dict[str, int] = {}
    main_caliber_details: dict[str, int] = {}
    if isinstance(owner_ribbons_raw, dict):
        for r_id, count in owner_ribbons_raw.items():
            name = None
            match r_id:
                case 0 | 14 | 15 | 16 | 17 | 28:
                    name = "main_caliber"
                    mc_type = {
                        14: "碎弹",
                        15: "过穿",
                        16: "跳弹",
                        17: "贯穿",
                        28: "未击穿",
                    }.get(r_id, "命中")
                    main_caliber_details[mc_type] = main_caliber_details.get(mc_type, 0) + count
                case 24 | 25 | 26 | 30 | 34 | 35:
                    name = "rocket"
                case 2 | 20 | 21 | 22 | 23 | 29:
                    name = "bomb"
                case 39 | 40 | 41:
                    name = "acoustic_hit"
                case 43 | 44:
                    name = "dbomb"
                case 45:
                    name = "dbomb_mine"
                case _ as solo:
                    name = SOLO_MAP.get(solo, f"unknown_{solo}")
            if name:
                processed_ribbons[name] = processed_ribbons.get(name, 0) + count

    # 0. Check official post-battle settlement packet (Packet 0x22)
    if "post_battle" in info:
        post_battle = info["post_battle"]
    else:
        post_battle = extract_post_battle_results(replay_path)
    has_post_battle = bool(post_battle and post_battle.get("playersPublicInfo"))
    post_stats_by_dbid: dict[int, dict[str, Any]] = {}
    post_stats_by_name: dict[str, dict[str, Any]] = {}
    dbid_to_name: dict[int, str] = {}

    if has_post_battle:
        pub = post_battle["playersPublicInfo"]
        sample = next(iter(pub.values()))
        d_idx = None
        for i, _ in enumerate(sample):
            if any(isinstance(p_list[i], dict) and len(p_list[i]) > 0 for p_list in pub.values()):
                d_idx = i
                break
        if d_idx is None:
            for i, v in enumerate(sample):
                if isinstance(v, dict):
                    d_idx = i
                    break

        if d_idx is not None:
            ribbon_base = _detect_ribbon_base(pub, owner.account_db_id, owner_ribbons_raw)
            stat_shift = _detect_stat_shift(pub, owner.account_db_id, owner_total_dmg_pre := sum(v[1] for v in hidden.get("damage_maps", {}).get("Enemy", {}).values()) if hidden.get("damage_maps", {}).get("Enemy") else 0.0, d_idx)
            for p_data in pub.values():
                raw_n = p_data[1] or ""
                disp_n = _translate_ids(raw_n, raw_n) if raw_n.startswith("IDS_") else raw_n
                dbid_to_name[p_data[0]] = disp_n

            for p_data in pub.values():
                rib_plane_idx = d_idx + ribbon_base + 3
                rib_splane_idx = d_idx + ribbon_base + 27
                pk_aa = int(p_data[rib_plane_idx]) if len(p_data) > rib_plane_idx and isinstance(p_data[rib_plane_idx], (int, float)) else 0
                pk_sp = int(p_data[rib_splane_idx]) if len(p_data) > rib_splane_idx and isinstance(p_data[rib_splane_idx], (int, float)) else 0
                planes_killed = pk_aa + pk_sp
                if planes_killed == 0 and p_data[0] in raw_planes_by_dbid:
                    planes_killed = raw_planes_by_dbid[p_data[0]]

                raw_n = p_data[1] or ""
                disp_n = _translate_ids(raw_n, raw_n) if raw_n.startswith("IDS_") else raw_n
                p_stat = {
                    "account_dbid": p_data[0],
                    "name": disp_n,
                    "raw_name": raw_n,
                    "base_xp": int(p_data[d_idx - 1]),
                    "raw_xp": int(p_data[d_idx - 2]),
                    "damage": int(p_data[d_idx + 21 + stat_shift]),
                    "killer_dbid": int(p_data[d_idx + 3]),
                    "death_reason": int(p_data[d_idx + 5]),
                    "spotting_damage": int(p_data[d_idx + 7 + stat_shift]),
                    "potential_damage": int(
                        p_data[d_idx + 11 + stat_shift]
                        + p_data[d_idx + 12 + stat_shift]
                        + p_data[d_idx + 13 + stat_shift]
                    ),
                    "survival_time": float(p_data[22]),
                    "frags": int(p_data[32]),
                    "planes_killed": planes_killed,
                }
                post_stats_by_dbid[p_stat["account_dbid"]] = p_stat
                if raw_n:
                    post_stats_by_name[raw_n] = p_stat

    # 1. Base direct + visible fire damage from shots_damage_map
    shots_dmg = hidden.get("shots_damage_map", {})
    attacker_damage = {p.ship_id: 0.0 for p in players.values()}
    victim_direct = {p.ship_id: 0.0 for p in players.values()}
    for victim_id, attackers in shots_dmg.items():
        for att_id, dmg in attackers.items():
            attacker_damage[att_id] = attacker_damage.get(att_id, 0.0) + dmg
            victim_direct[victim_id] = victim_direct.get(victim_id, 0.0) + dmg

    # 2. HP drops, chat messages, tactical trajectories & HP timeline
    hp_last_active: dict[int, float] = {}
    hp_total_drops = {p.ship_id: 0.0 for p in players.values()}
    prev_hp: dict[int, float] = {}
    time_keys = sorted(k for k in rd.events.keys() if isinstance(k, int))
    last_t = time_keys[-1] if time_keys else 0

    chat_items: list[dict[str, Any]] = []

    map_manifest = None
    try:
        manifest_data = resman.load_json("manifest.json", "spaces")
        map_manifest = manifest_data.get(map_code)
    except Exception:
        pass

    # Tactical data collection structures
    ally_team_id = owner.team_id
    all_allies = [p for p in players.values() if p.team_id == ally_team_id]
    all_enemies = [p for p in players.values() if p.team_id != ally_team_id]

    ship_max_hp: dict[int, float] = {p.ship_id: float(max(1, p.max_health or 1)) for p in players.values()}
    ally_max_hp = float(sum(ship_max_hp[p.ship_id] for p in all_allies))
    enemy_max_hp = float(sum(ship_max_hp[p.ship_id] for p in all_enemies))
    cur_hp: dict[int, float] = dict(ship_max_hp)
    is_dead_track: dict[int, bool] = {p.ship_id: False for p in players.values()}

    last_known_pos: dict[int, tuple[int, int, int]] = {}  # vid -> (t, x, y)
    owner_track: list[tuple[int, int, int]] = []
    other_tracks_raw: dict[int, list[list[tuple[int, int]]]] = {p.ship_id: [] for p in players.values() if p.ship_id != owner.ship_id}
    active_seg: dict[int, list[tuple[int, int]]] = {}
    last_seg_t: dict[int, int] = {}

    hp_timeline: list[tuple[int, float, float]] = []
    hp_frags: list[tuple[int, int, str]] = []
    frag_coords: dict[int, tuple[int, int, int]] = {}  # killed_vid -> (t, x, y)

    MAX_STEP_DIST_WORLD = 140.0

    for t in time_keys:
        evt = rd.events[t]
        for vid, v in evt.evt_vehicle.items():
            if vid not in prev_hp:
                prev_hp[vid] = v.health
            else:
                diff = prev_hp[vid] - v.health
                if diff > 0:
                    hp_total_drops[vid] = hp_total_drops.get(vid, 0.0) + diff
                prev_hp[vid] = v.health
            if v.health > 0:
                hp_last_active[vid] = v.health

            # HP curve update
            if not v.is_alive:
                is_dead_track[vid] = True
                cur_hp[vid] = 0.0
            elif not is_dead_track.get(vid, False):
                if v.is_visible or v.relation in (-1, 0) or v.health < cur_hp.get(vid, float("inf")):
                    cur_hp[vid] = max(0.0, min(float(v.health), ship_max_hp.get(vid, float(v.health))))

            # Trajectory tracking
            valid_pos = v.is_alive and v.is_visible and (v.x != -2500 or v.y != -2500)
            if valid_pos:
                last_known_pos[vid] = (t, int(v.x), int(v.y))
                if vid == owner.ship_id:
                    if not owner_track or owner_track[-1][1] != v.x or owner_track[-1][2] != v.y:
                        owner_track.append((t, int(v.x), int(v.y)))
                elif vid in other_tracks_raw:
                    seg = active_seg.get(vid)
                    prev_t_s = last_seg_t.get(vid, t)
                    if seg:
                        px0, py0 = seg[-1]
                        jump = math.hypot(v.x - px0, v.y - py0)
                        if (t - prev_t_s) > 4 or jump > MAX_STEP_DIST_WORLD:
                            if len(seg) >= 2:
                                other_tracks_raw[vid].append(seg)
                            seg = [(int(v.x), int(v.y))]
                            active_seg[vid] = seg
                        elif px0 != v.x or py0 != v.y:
                            seg.append((int(v.x), int(v.y)))
                    else:
                        active_seg[vid] = [(int(v.x), int(v.y))]
                    last_seg_t[vid] = t
            else:
                if vid in active_seg:
                    seg = active_seg.pop(vid)
                    if len(seg) >= 2:
                        other_tracks_raw[vid].append(seg)

        # Frags at time t
        if evt.evt_frag:
            for fr in evt.evt_frag:
                is_dead_track[fr.killed_id] = True
                cur_hp[fr.killed_id] = 0.0
                kp = v_to_p.get(fr.killed_id)
                if kp is not None:
                    v_rel = 0 if kp.team_id == ally_team_id else 1
                    ks_name = player_ship_name.get(kp.id, "") or player_display_name.get(kp.id, "")
                    hp_frags.append((t, v_rel, ks_name))
                v_cur = evt.evt_vehicle.get(fr.killed_id)
                if v_cur and (v_cur.x != -2500 or v_cur.y != -2500):
                    frag_coords[fr.killed_id] = (t, int(v_cur.x), int(v_cur.y))
                elif fr.killed_id in last_known_pos:
                    _, lx, ly = last_known_pos[fr.killed_id]
                    frag_coords[fr.killed_id] = (t, lx, ly)

        # Record team HP snapshot
        ally_cur = sum(cur_hp.get(p.ship_id, 0.0) for p in all_allies)
        enemy_cur = sum(cur_hp.get(p.ship_id, 0.0) for p in all_enemies)
        ally_pct = (100.0 * ally_cur / ally_max_hp) if ally_max_hp > 0 else 0.0
        enemy_pct = (100.0 * enemy_cur / enemy_max_hp) if enemy_max_hp > 0 else 0.0
        hp_timeline.append((t, ally_pct, enemy_pct))

        # Chat messages
        if evt.evt_chat:
            for m in evt.evt_chat:
                speaker = players.get(m.player_id)
                chat_items.append({
                    "time_sec": t,
                    "player_id": m.player_id,
                    "player_name": player_display_name.get(m.player_id, str(m.player_id)) if speaker else str(m.player_id),
                    "ship_name": player_ship_name.get(m.player_id, ""),
                    "clan": speaker.clan_tag if speaker else "",
                    "clan_color": getattr(speaker, "clan_color", 0) if speaker else 0,
                    "team_id": speaker.team_id if speaker else -1,
                    "namespace": m.namespace,
                    "message": m.message,
                    "is_quick_cmd": False,
                })

    # Flush remaining open trajectory segments
    for vid, seg in active_seg.items():
        if len(seg) >= 2 and vid in other_tracks_raw:
            other_tracks_raw[vid].append(seg)

    ally_tracks = [segs for vid, segs in other_tracks_raw.items() if segs and vid in v_to_p and v_to_p[vid].team_id == ally_team_id]
    enemy_tracks = [segs for vid, segs in other_tracks_raw.items() if segs and vid in v_to_p and v_to_p[vid].team_id != ally_team_id]

    # Final visible control points
    final_cps_dict = {}
    for t in reversed(time_keys):
        if rd.events[t].evt_control:
            final_cps_dict = rd.events[t].evt_control
            break
    tactical_cps = [
        {
            "index": cid,
            "x": cp.position[0],
            "y": cp.position[1],
            "radius": cp.radius,
            "relation": cp.relation,
            "type": cp.control_point_type,
            "is_visible": bool(cp.is_visible),
        }
        for cid, cp in sorted(final_cps_dict.items())
        if cp.is_visible
    ]

    # Decode and append tactical quick radio commands (natively unpacked in ReplayPlayer)
    raw_cmd_events = hidden.get("quick_commands", [])
    battle_start_time = hidden.get("battle_start_time")
    ships_by_id = {p.ship_id: p for p in players.values()}

    for t_sec, p_id, cmd_blob in raw_cmd_events:
        speaker = players.get(p_id)
        if battle_start_time is not None:
            cmd_t = max(0, min(last_t if last_t > 0 else 99999, int(round(t_sec - battle_start_time))))
        else:
            cmd_t = max(0, int(round(t_sec)))
        msg_text = decode_quick_command(
            cmd_blob,
            players,
            ships_by_id,
            map_manifest,
            ships_dict=ships,
            sender_team_id=speaker.team_id if speaker else -1,
            control_points=final_cps_dict,
        )
        chat_items.append({
            "time_sec": cmd_t,
            "player_id": p_id,
            "player_name": player_display_name.get(p_id, str(p_id)) if speaker else str(p_id),
            "ship_name": player_ship_name.get(p_id, ""),
            "clan": speaker.clan_tag if speaker else "",
            "clan_color": getattr(speaker, "clan_color", 0) if speaker else 0,
            "team_id": speaker.team_id if speaker else -1,
            "namespace": "battle_quick",
            "message": msg_text,
            "is_quick_cmd": True,
        })

    chat_items.sort(key=lambda c: c["time_sec"])

    # 3. Frags and death reasons
    death_info = hidden.get("death_info", {})
    frags = {p.ship_id: 0 for p in players.values()}
    killed_by: dict[int, tuple[int, str]] = {}
    for vid, d_data in death_info.items():
        k_id = d_data.get("killer_id", 0)
        killed_by[vid] = (k_id, d_data.get("name", ""))
        if k_id in frags:
            frags[k_id] += 1
    for t in time_keys:
        for fr in rd.events[t].evt_frag:
            if fr.killed_id not in killed_by:
                killed_by[fr.killed_id] = (fr.fragger_id, str(fr.death_type))
                if fr.fragger_id in frags:
                    frags[fr.fragger_id] += 1

    # 4. Compensate fire/flood tick damage for remaining unaccounted HP drops
    for vid in players:
        if vid in killed_by:
            killer_id, _ = killed_by[vid]
            accounted = victim_direct.get(vid, 0.0)
            lost = hp_total_drops.get(vid, 0.0)
            unaccounted = max(0.0, lost - accounted)
            if unaccounted > 50 and killer_id in attacker_damage and killer_id != vid:
                attacker_damage[killer_id] += unaccounted

    # 5. Owner specific stats
    damage_maps = hidden.get("damage_maps", {})
    owner_dmg_enemy = damage_maps.get("Enemy", {})
    owner_total_dmg = sum(v[1] for v in owner_dmg_enemy.values()) if owner_dmg_enemy else 0.0

    # Aggregate damage breakdown by weapon category (no duplicate labels, unknown -> "其他")
    agg_breakdown: dict[str, float] = {}
    if isinstance(owner_dmg_enemy, dict):
        for w_id, (_, dmg_val) in owner_dmg_enemy.items():
            cat_name = WEAPON_CATEGORY_MAP.get(int(w_id), "其他")
            agg_breakdown[cat_name] = agg_breakdown.get(cat_name, 0.0) + float(dmg_val)
    aggregated_breakdown = sorted(agg_breakdown.items(), key=lambda kv: kv[1], reverse=True)

    spot_map = damage_maps.get("Spot", {})
    owner_spot_dmg = sum(v[1] for v in spot_map.values()) if spot_map else 0.0

    agro_map = damage_maps.get("Agro", {})
    owner_agro_dmg = sum(v[1] for v in agro_map.values()) if agro_map else 0.0

    # Achievements
    owner_achievements: list[tuple[int, str, int]] = []
    raw_achs = hidden.get("achievements", {})
    owner_achs_raw = raw_achs.get(rd.owner_id) or raw_achs.get(rd.owner_avatar_id, {})
    if isinstance(owner_achs_raw, dict):
        for ach_id, count in owner_achs_raw.items():
            ach_val = (
                achievements_dict.get(ach_id)
                or achievements_dict.get(int(ach_id))
                or achievements_dict.get(str(ach_id))
            )
            if isinstance(ach_val, dict):
                ach_code = str(ach_val.get("name", f"ACH_{ach_id}"))
            elif isinstance(ach_val, str):
                ach_code = ach_val
            else:
                ach_code = f"ACH_{ach_id}"
            owner_achievements.append((int(ach_id), ach_code, int(count)))

    # Match outcome & scores (Note: evt_score is keyed by relation: 0=ally, 1=enemy!)
    gr = rd.game_result
    winner_team_id = gr.team_id if gr else -2
    victory_type = gr.victory_type if gr else 0
    is_unfinished = winner_team_id == -2
    is_draw = winner_team_id == -1
    is_victory = (not is_unfinished and not is_draw and winner_team_id == owner.team_id)

    final_score = {0: 0, 1: 0}
    for t in reversed(time_keys):
        if rd.events[t].evt_score:
            for rel_id, sc in rd.events[t].evt_score.items():
                final_score[rel_id] = sc.score
            break

    # Extract Division (pre-battle squad) info
    player_division_info: dict[int, dict[str, Any]] = {}
    team_div_counts: dict[int, int] = {0: 0, 1: 0}

    if raw_players:
        team_squad_groups: dict[int, dict[int, list[Any]]] = {0: {}, 1: {}}
        for rp in raw_players.values():
            tid = rp.get("teamId", 0)
            pre_id = rp.get("preBattleIdOnStart", 0) or rp.get("prebattleId", 0)
            if pre_id > 0:
                team_squad_groups.setdefault(tid, {}).setdefault(pre_id, []).append(rp)

        owner_raw_pre_id = 0
        for rp in raw_players.values():
            if rp.get("shipId") == owner.ship_id:
                owner_raw_pre_id = rp.get("preBattleIdOnStart", 0) or rp.get("prebattleId", 0)
                break

        for tid in (0, 1):
            valid_squads = [
                (s_id, mems) for s_id, mems in team_squad_groups.get(tid, {}).items()
                if len(mems) >= 2
            ]
            valid_squads.sort(key=lambda item: min(m.get("shipId", 0) for m in item[1]))
            team_div_counts[tid] = len(valid_squads)

            for squad_num, (s_id, mems) in enumerate(valid_squads, start=1):
                mem_names = [m.get("name", "") for m in mems]
                is_owner_div = (s_id == owner_raw_pre_id and owner_raw_pre_id > 0)
                for rp in mems:
                    v_id = rp.get("shipId", 0)
                    player_division_info[v_id] = {
                        "division_num": squad_num,
                        "division_raw_id": s_id,
                        "is_owner_division": is_owner_div,
                        "is_leader": rp.get("isPreBattleOwner", False),
                        "division_members": mem_names,
                    }

    # Owner unified planes killed fallback
    owner_fallback_planes = max(
        raw_planes_by_ship.get(owner.ship_id, 0),
        processed_ribbons.get("plane", 0) + processed_ribbons.get("splane", 0),
    )

    # Compile player list
    player_rows: list[dict[str, Any]] = []
    sunk_markers: list[dict[str, Any]] = []

    for p in players.values():
        vid = p.ship_id
        ship_info = ships.get(p.ship_params_id) or ships.get(str(p.ship_params_id), {})
        if not isinstance(ship_info, dict):
            ship_info = {}
        s_name = ship_info.get("name", "Unknown")
        s_species = ship_info.get("species", "Battleship")
        s_level = ship_info.get("level", 10)
        disp_name = player_display_name.get(p.id, p.name)

        d_out = owner_total_dmg if (vid == owner.ship_id and owner_total_dmg > 0) else attacker_damage.get(vid, 0.0)
        d_in = victim_direct.get(vid, 0.0)
        tot_hp_lost = hp_total_drops.get(vid, 0.0)
        k = frags.get(vid, 0)
        is_sunk = vid in killed_by
        killer_vid = killed_by.get(vid, (0, ""))[0] if is_sunk else 0
        killer_name = ""
        killer_ship_name = ""
        if is_sunk and killer_vid in v_to_p:
            killer_name = player_display_name.get(v_to_p[killer_vid].id, v_to_p[killer_vid].name)
            killer_ship_name = player_ship_name.get(v_to_p[killer_vid].id, "")

        # Official post-battle stats (match primarily by unique account_db_id!)
        stat = post_stats_by_dbid.get(p.account_db_id)
        if stat is None and p.account_db_id == 0:
            stat = post_stats_by_name.get(p.name)

        if stat:
            d_out = float(stat["damage"])
            k = stat["frags"]
            is_sunk = (stat["killer_dbid"] != 0) or is_sunk
            if stat["killer_dbid"] != 0:
                k_dbid = stat["killer_dbid"]
                killer_name = dbid_to_name.get(k_dbid, killer_name)
                k_p = dbid_to_player.get(k_dbid)
                if k_p:
                    killer_ship_name = player_ship_name.get(k_p.id, killer_ship_name)
            base_xp = stat["base_xp"]
            raw_xp = stat["raw_xp"]
            spot_dmg = stat["spotting_damage"]
            potential_dmg = stat["potential_damage"]
            survival_sec = stat["survival_time"]
            planes_killed = stat.get("planes_killed", 0)
        else:
            base_xp = 0
            raw_xp = 0
            spot_dmg = 0
            potential_dmg = 0
            survival_sec = float(last_t)
            if vid == owner.ship_id:
                planes_killed = owner_fallback_planes
            else:
                planes_killed = raw_planes_by_ship.get(vid, 0)

        div_info = player_division_info.get(vid, {
            "division_num": 0,
            "division_raw_id": 0,
            "is_owner_division": False,
            "is_leader": False,
            "division_members": [],
        })

        # Collect player achievements
        p_achs: list[tuple[int, str]] = []
        p_achs_raw = raw_achs.get(p.id) or raw_achs.get(getattr(p, "avatar_id", 0), {})
        if isinstance(p_achs_raw, dict):
            for a_id, cnt in p_achs_raw.items():
                a_val = (
                    achievements_dict.get(a_id)
                    or achievements_dict.get(int(a_id))
                    or achievements_dict.get(str(a_id))
                )
                if a_val:
                    for _ in range(int(cnt)):
                        p_achs.append((int(a_id), str(a_val)))

        player_rows.append({
            "player_id": p.id,
            "ship_id": vid,
            "name": disp_name,
            "clan": p.clan_tag,
            "clan_color": getattr(p, "clan_color", 0),
            "team_id": p.team_id,
            "is_owner": (vid == owner.ship_id),
            "ship_name": s_name,
            "species": s_species,
            "level": s_level,
            "frags": k,
            "planes_killed": planes_killed,
            "damage_dealt": d_out,
            "damage_taken": max(d_in, tot_hp_lost),
            "base_xp": base_xp,
            "raw_xp": raw_xp,
            "spotting_damage": spot_dmg,
            "potential_damage": potential_dmg,
            "survival_sec": survival_sec,
            "is_sunk": is_sunk,
            "killer_name": killer_name,
            "killer_ship_name": killer_ship_name,
            "division_num": div_info["division_num"],
            "division_raw_id": div_info["division_raw_id"],
            "is_owner_division": div_info["is_owner_division"],
            "is_division_leader": div_info["is_leader"],
            "division_members": div_info["division_members"],
            "achievements": p_achs,
        })

        if is_sunk:
            pos_t = frag_coords.get(vid) or last_known_pos.get(vid)
            if pos_t is not None:
                st, sx, sy = pos_t
                sunk_markers.append({
                    "x": sx,
                    "y": sy,
                    "relation": -1 if vid == owner.ship_id else (0 if p.team_id == ally_team_id else 1),
                    "ship_name": s_name,
                    "tier": TIER_ROMAN.get(s_level, str(s_level)),
                    "time_sec": st,
                    "killed_by_owner": (killer_vid == owner.ship_id) or (
                        bool(stat and stat["killer_dbid"] == owner.account_db_id and owner.account_db_id != 0)
                    ),
                })

    owner_div_info = player_division_info.get(owner.ship_id, {})
    owner_post = post_stats_by_dbid.get(owner.account_db_id)
    if owner_post is None and owner.account_db_id == 0:
        owner_post = post_stats_by_name.get(owner.name)

    owner_ship_info = ships.get(owner.ship_params_id) or ships.get(str(owner.ship_params_id), {})
    if not isinstance(owner_ship_info, dict):
        owner_ship_info = {}

    owner_row = next((r for r in player_rows if r["is_owner"]), None)
    owner_unified_dmg = owner_row["damage_dealt"] if owner_row else (float(owner_post["damage"]) if owner_post else owner_total_dmg)
    owner_unified_planes = owner_row["planes_killed"] if owner_row else owner_fallback_planes

    ally_alive_end = sum(1 for r in player_rows if r["team_id"] == ally_team_id and not r["is_sunk"])
    enemy_alive_end = sum(1 for r in player_rows if r["team_id"] != ally_team_id and not r["is_sunk"])

    finish_reason = _determine_finish_reason(
        victory_type=victory_type,
        winner_team_id=winner_team_id,
        owner_team_id=owner.team_id,
        s_ally=final_score.get(0, 0),
        s_enemy=final_score.get(1, 0),
        win_score=rd.game_win_score,
        ally_alive=ally_alive_end,
        enemy_alive=enemy_alive_end,
    )

    owner_killer_name = ""
    if owner_row and owner_row["is_sunk"]:
        owner_killer_name = owner_row["killer_name"]
    elif owner_post and owner_post["killer_dbid"] != 0:
        owner_killer_name = dbid_to_name.get(owner_post["killer_dbid"], "")

    return {
        "map_code": map_code,
        "map_title": map_title,
        "scenario_title": scenario_title,
        "game_type_title": game_type_title,
        "date_time": date_time,
        "client_version": client_version,
        "game_version": rd.game_version,
        "duration_sec": last_t,
        "is_victory": is_victory,
        "is_draw": is_draw,
        "is_unfinished": is_unfinished,
        "victory_type": victory_type,
        "finish_reason": finish_reason,
        "win_score": rd.game_win_score,
        "final_score": final_score,
        "has_post_battle": has_post_battle,
        "team_division_counts": team_div_counts,
        "owner": {
            "name": player_display_name.get(owner.id, owner.name),
            "clan": owner.clan_tag,
            "clan_color": getattr(owner, "clan_color", 0),
            "ship_name": owner_ship_info.get("name", "Unknown"),
            "species": owner_ship_info.get("species", "Battleship"),
            "level": owner_ship_info.get("level", 10),
            "nation": owner_ship_info.get("nation", ""),
            "team_id": owner.team_id,
            "total_dmg": owner_unified_dmg,
            "base_xp": owner_post["base_xp"] if owner_post else 0,
            "raw_xp": owner_post["raw_xp"] if owner_post else 0,
            "spot_dmg": owner_post["spotting_damage"] if owner_post else owner_spot_dmg,
            "agro_dmg": owner_post["potential_damage"] if owner_post else owner_agro_dmg,
            "frags": owner_post["frags"] if owner_post else frags.get(owner.ship_id, 0),
            "planes_killed": owner_unified_planes,
            "damage_breakdown": owner_dmg_enemy,
            "damage_breakdown_agg": aggregated_breakdown,
            "ribbons": processed_ribbons,
            "main_caliber_details": main_caliber_details,
            "achievements": owner_achievements,
            "is_sunk": bool(owner_row["is_sunk"]) if owner_row else (owner.ship_id in killed_by),
            "killer_name": owner_killer_name,
            "division_num": owner_div_info.get("division_num", 0),
            "division_members": owner_div_info.get("division_members", []),
            "is_division_leader": owner_div_info.get("is_leader", False),
        },
        "players": player_rows,
        "chat": chat_items,
        "tactical": {
            "map_manifest": map_manifest,
            "control_points": tactical_cps,
            "owner_track": owner_track,
            "ally_tracks": ally_tracks,
            "enemy_tracks": enemy_tracks,
            "sunk_markers": sunk_markers,
            "hp_timeline": hp_timeline,
            "hp_frags": hp_frags,
            "ally_alive_end": ally_alive_end,
            "enemy_alive_end": enemy_alive_end,
        },
    }


def draw_rounded_rect(
    draw: ImageDraw.Draw,
    xy,
    radius=10,
    fill=None,
    outline=None,
    width=1,
    corners=None,
):
    """Draws a rounded rectangle (supports Pillow 11 corners tuple)."""
    kwargs: dict[str, Any] = {"radius": radius, "fill": fill, "outline": outline, "width": width}
    if corners is not None:
        kwargs["corners"] = corners
    draw.rounded_rectangle(xy, **kwargs)


def draw_rounded_rect_aa(
    base_img: Image.Image,
    xy: tuple[int, int, int, int],
    radius: int = 10,
    fill=None,
    outline=None,
    width: int = 1,
    corners: Optional[tuple[bool, bool, bool, bool]] = None,
):
    """Draws a crisp 2x supersampled anti-aliased rounded rectangle onto base_img."""
    x0, y0, x1, y1 = map(int, xy)
    w = x1 - x0
    h = y1 - y0
    if w <= 0 or h <= 0:
        return
    scale = 2
    overlay = Image.new("RGBA", (w * scale, h * scale), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    kwargs: dict[str, Any] = {
        "radius": max(0, radius * scale),
        "fill": fill,
        "outline": outline,
        "width": max(1, width * scale) if outline else 0,
    }
    if corners is not None:
        kwargs["corners"] = corners
    odraw.rounded_rectangle((0, 0, w * scale - 1, h * scale - 1), **kwargs)
    aa = overlay.resize((w, h), Image.Resampling.LANCZOS)
    base_img.alpha_composite(aa, (x0, y0))


def _text_width(text: str, font: ImageFont.FreeTypeFont) -> int:
    if not text:
        return 0
    bbox = font.getbbox(text)
    return max(0, bbox[2] - bbox[0])


def fit_text_ellipsis(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> str:
    """Safely sanitizes and truncates text with ellipsis if it exceeds max_width."""
    cleaned = text.replace("\r\n", " ").replace("\n", " ").strip()
    if max_width <= 0:
        return ""
    if _text_width(cleaned, font) <= max_width:
        return cleaned

    ellipsis = "..."
    ell_w = _text_width(ellipsis, font)
    avail = max_width - ell_w
    if avail <= 0:
        return ellipsis

    low, high = 0, len(cleaned)
    best = 0
    while low <= high:
        mid = (low + high) // 2
        if _text_width(cleaned[:mid], font) <= avail:
            best = mid
            low = mid + 1
        else:
            high = mid - 1
    return cleaned[:best].rstrip() + ellipsis


def _wrap_text_two_lines(
    text: str,
    font: ImageFont.FreeTypeFont,
    first_w: int,
    second_w: int,
) -> list[str]:
    """Wraps text across up to 2 lines cleanly (word-aware for Latin, char-aware for CJK)."""
    cleaned = text.replace("\r\n", " ").replace("\n", " ").strip()
    if not cleaned:
        return [""]
    if _text_width(cleaned, font) <= first_w:
        return [cleaned]

    # Binary search split index for line 1
    low, high = 1, len(cleaned)
    split_idx = 1
    while low <= high:
        mid = (low + high) // 2
        if _text_width(cleaned[:mid], font) <= first_w:
            split_idx = mid
            low = mid + 1
        else:
            high = mid - 1

    # Prefer breaking at whitespace if nearby for Latin text
    if split_idx < len(cleaned) and not cleaned[split_idx].isspace():
        space_pos = cleaned.rfind(" ", max(1, split_idx - 16), split_idx)
        if space_pos > 0:
            split_idx = space_pos + 1

    line1 = cleaned[:split_idx].rstrip()
    rest = cleaned[split_idx:].lstrip()
    if not rest:
        return [line1]
    line2 = fit_text_ellipsis(rest, font, second_w)
    return [line1, line2]


def _render_tactical_minimap_card(
    base_img: Image.Image,
    card_x: int,
    card_y: int,
    card_w: int,
    data: dict[str, Any],
) -> int:
    """Renders Left Tactical Card (760px wide): 10x10 minimap, caps, ghost tracks, 2x AA owner track, kill markers & legend."""
    MAP_SIZE = 720
    PAD_X = (card_w - MAP_SIZE) // 2  # 20px
    HEADER_H = 48
    TOP_RULER_PAD = 12
    LEGEND_H = 44
    CARD_H = HEADER_H + TOP_RULER_PAD + MAP_SIZE + LEGEND_H + 10

    draw_rounded_rect_aa(
        base_img,
        (card_x, card_y, card_x + card_w, card_y + CARD_H),
        radius=12,
        fill=(18, 26, 38, 240),
        outline=(32, 48, 68, 255),
        width=1,
    )
    draw_rounded_rect_aa(
        base_img,
        (card_x, card_y, card_x + card_w, card_y + HEADER_H),
        radius=12,
        fill=(24, 36, 52, 255),
        corners=(True, True, False, False),
    )
    draw_rounded_rect_aa(
        base_img,
        (card_x, card_y, card_x + 8, card_y + HEADER_H),
        radius=12,
        fill=(0, 206, 201, 255),
        corners=(True, False, False, False),
    )

    draw = ImageDraw.Draw(base_img)
    f_hdr = select_font_for_text("战术态势", 19)
    draw.text((card_x + 22, card_y + 12), "战术态势与高光航迹复盘 (Tactical Map)", fill=(255, 255, 255), font=f_hdr)

    tactical = data.get("tactical", {})
    map_manifest = tactical.get("map_manifest")
    map_code = data.get("map_code", "")
    game_version = data.get("game_version", "15_10_0")

    # 1. Load minimap_water + minimap land, or graceful ocean grid fallback
    map_canvas = None
    try:
        resman = ResourceManager(game_version)
        water = resman.load_image("minimap_water.png", path=f"spaces.{map_code}").resize(
            (MAP_SIZE, MAP_SIZE), Image.Resampling.LANCZOS
        )
        land = resman.load_image("minimap.png", path=f"spaces.{map_code}").resize(
            (MAP_SIZE, MAP_SIZE), Image.Resampling.LANCZOS
        )
        map_canvas = Image.alpha_composite(water, land)
    except Exception:
        map_canvas = Image.new("RGBA", (MAP_SIZE, MAP_SIZE), (14, 28, 46, 255))

    # 15% dark tactical overlay so trajectories and markers pop cleanly
    dark_mask = Image.new("RGBA", (MAP_SIZE, MAP_SIZE), (4, 10, 18, 38))
    map_canvas = Image.alpha_composite(map_canvas, dark_mask)

    # 2. Exact 9 interior lines (10x10 grid) + border + edge A-J / 1-10 micro coordinates
    grid_overlay = Image.new("RGBA", (MAP_SIZE, MAP_SIZE), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(grid_overlay)
    f_grid = select_font_for_text("A1", 11)
    cell_sz = MAP_SIZE / 10.0
    for i in range(1, 10):
        pos = round(i * cell_sz)
        gdraw.line([(pos, 0), (pos, MAP_SIZE - 1)], fill=(255, 255, 255, 42), width=1)
        gdraw.line([(0, pos), (MAP_SIZE - 1, pos)], fill=(255, 255, 255, 42), width=1)
    gdraw.rectangle((0, 0, MAP_SIZE - 1, MAP_SIZE - 1), outline=(72, 102, 134, 160), width=1)
    for i in range(10):
        col_ch = "ABCDEFGHIJ"[i]
        row_ch = str(i + 1)
        cx_lbl = round(i * cell_sz + cell_sz / 2)
        cy_lbl = round(i * cell_sz + cell_sz / 2)
        cw = _text_width(col_ch, f_grid)
        gdraw.text((cx_lbl - cw // 2, 3), col_ch, fill=(195, 215, 235, 165), font=f_grid)
        gdraw.text((4, cy_lbl - 6), row_ch, fill=(195, 215, 235, 165), font=f_grid)
    map_canvas = Image.alpha_composite(map_canvas, grid_overlay)

    # World -> map_canvas pixel transform matching RendererBase.get_scaled
    if map_manifest and len(map_manifest) >= 3:
        m_size, _, m_scaling = map_manifest
    else:
        m_size, m_scaling = 760, 0.475
    scale_factor = MAP_SIZE / float(m_size)

    def to_map_xy(wx: float, wy: float) -> tuple[float, float]:
        px = (wx * m_scaling + m_size / 2.0) * scale_factor
        py = (-wy * m_scaling + m_size / 2.0) * scale_factor
        return (px, py)

    # 3. Capture circles (evt_control)
    cap_overlay = Image.new("RGBA", (MAP_SIZE, MAP_SIZE), (0, 0, 0, 0))
    cdraw = ImageDraw.Draw(cap_overlay)
    f_cap = select_font_for_text("A", 16)
    for idx_cp, cp in enumerate(tactical.get("control_points", [])):
        cx, cy = to_map_xy(cp["x"], cp["y"])
        cr = max(10.0, float(cp["radius"]) * m_scaling * scale_factor)
        rel = cp.get("relation", -1)
        if rel == 0:
            c_col = (46, 213, 115)
        elif rel == 1:
            c_col = (255, 71, 87)
        else:
            c_col = (210, 222, 235)
        cdraw.ellipse((cx - cr, cy - cr, cx + cr, cy + cr), fill=(*c_col, 32), outline=(*c_col, 175), width=2)
        cp_idx = cp.get("index", idx_cp)
        lbl = chr(65 + cp_idx) if 0 <= cp_idx < 26 else str(cp_idx + 1)
        lw = _text_width(lbl, f_cap)
        cdraw.text((cx - lw / 2, cy - 9), lbl, fill=(*c_col, 235), font=f_cap)
    map_canvas = Image.alpha_composite(map_canvas, cap_overlay)

    # 4. All-team ghost trajectories (only continuous visible segments!)
    ghost_overlay = Image.new("RGBA", (MAP_SIZE, MAP_SIZE), (0, 0, 0, 0))
    ghdraw = ImageDraw.Draw(ghost_overlay)
    for segs in tactical.get("ally_tracks", []):
        for seg in segs:
            pts = [to_map_xy(x, y) for x, y in seg]
            if len(pts) >= 2:
                ghdraw.line(pts, fill=(46, 213, 115, 62), width=2)
    for segs in tactical.get("enemy_tracks", []):
        for seg in segs:
            pts = [to_map_xy(x, y) for x, y in seg]
            if len(pts) >= 2:
                ghdraw.line(pts, fill=(255, 71, 87, 56), width=2)
    map_canvas = Image.alpha_composite(map_canvas, ghost_overlay)

    # 5. Owner time-gradient highlight track (2x supersampled AA)
    owner_track = tactical.get("owner_track", [])
    placed_boxes: list[tuple[int, int, int, int]] = []

    if len(owner_track) >= 2:
        SS = 2
        track_2x = Image.new("RGBA", (MAP_SIZE * SS, MAP_SIZE * SS), (0, 0, 0, 0))
        tdraw = ImageDraw.Draw(track_2x)
        pts_2x = [(to_map_xy(x, y)[0] * SS, to_map_xy(x, y)[1] * SS) for _, x, y in owner_track]

        # Dark halo outline pass
        for i in range(len(pts_2x) - 1):
            p0, p1 = pts_2x[i], pts_2x[i + 1]
            if math.hypot(p1[0] - p0[0], p1[1] - p0[1]) > 140 * SS:
                continue
            tdraw.line([p0, p1], fill=(8, 14, 22, 215), width=10)
            tdraw.ellipse((p0[0] - 5, p0[1] - 5, p0[0] + 5, p0[1] + 5), fill=(8, 14, 22, 215))

        # Segmented gradient pass: #38bdf8 -> #00ebff -> #ffd32a
        total_seg = max(1, len(pts_2x) - 1)
        for i in range(total_seg):
            p0, p1 = pts_2x[i], pts_2x[i + 1]
            if math.hypot(p1[0] - p0[0], p1[1] - p0[1]) > 140 * SS:
                continue
            u = i / total_seg
            if u <= 0.5:
                k = u / 0.5
                c = (
                    round(56 + (0 - 56) * k),
                    round(189 + (235 - 189) * k),
                    round(248 + (255 - 248) * k),
                )
            else:
                k = (u - 0.5) / 0.5
                c = (
                    round(0 + (255 - 0) * k),
                    round(235 + (211 - 235) * k),
                    round(255 + (42 - 255) * k),
                )
            tdraw.line([p0, p1], fill=(*c, 245), width=5)
            tdraw.ellipse((p0[0] - 2.5, p0[1] - 2.5, p0[0] + 2.5, p0[1] + 2.5), fill=(*c, 245))

        track_aa = track_2x.resize((MAP_SIZE, MAP_SIZE), Image.Resampling.LANCZOS)
        map_canvas = Image.alpha_composite(map_canvas, track_aa)

    # 6. Sunk crosses & owner kill anchors with collision-avoiding tags
    marker_overlay = Image.new("RGBA", (MAP_SIZE, MAP_SIZE), (0, 0, 0, 0))
    mdraw = ImageDraw.Draw(marker_overlay)

    sunk_markers = tactical.get("sunk_markers", [])
    for sm in sunk_markers:
        if sm.get("killed_by_owner") or sm.get("relation") == -1:
            continue
        sx, sy = to_map_xy(sm["x"], sm["y"])
        col = (46, 213, 115, 145) if sm.get("relation") == 0 else (255, 71, 87, 155)
        mdraw.line([(sx - 4, sy - 4), (sx + 4, sy + 4)], fill=col, width=2)
        mdraw.line([(sx - 4, sy + 4), (sx + 4, sy - 4)], fill=col, width=2)

    # Owner START & END markers
    f_pill = select_font_for_text("START", 11)
    if owner_track:
        _, sx0, sy0 = owner_track[0]
        m_sx, m_sy = to_map_xy(sx0, sy0)
        mdraw.ellipse((m_sx - 6, m_sy - 6, m_sx + 6, m_sy + 6), fill=(56, 189, 248, 255), outline=(255, 255, 255, 240), width=2)
        st_lbl = "START"
        sw = _text_width(st_lbl, f_pill) + 10
        sh = 16
        lx = max(6, min(MAP_SIZE - sw - 6, round(m_sx - sw / 2)))
        ly = round(m_sy - 24) if m_sy > 28 else round(m_sy + 10)
        mdraw.rounded_rectangle((lx, ly, lx + sw, ly + sh), radius=4, fill=(14, 24, 38, 220), outline=(56, 189, 248, 220), width=1)
        mdraw.text((lx + 5, ly + 1), st_lbl, fill=(140, 225, 255, 255), font=f_pill)
        placed_boxes.append((lx, ly, lx + sw, ly + sh))

        _, ex0, ey0 = owner_track[-1]
        m_ex, m_ey = to_map_xy(ex0, ey0)
        if data.get("owner", {}).get("is_sunk"):
            mdraw.ellipse((m_ex - 7, m_ey - 7, m_ex + 7, m_ey + 7), fill=(255, 71, 87, 235), outline=(255, 211, 42, 255), width=2)
            mdraw.line([(m_ex - 4, m_ey - 4), (m_ex + 4, m_ey + 4)], fill=(255, 255, 255, 255), width=2)
            mdraw.line([(m_ex - 4, m_ey + 4), (m_ex + 4, m_ey - 4)], fill=(255, 255, 255, 255), width=2)
        else:
            mdraw.ellipse((m_ex - 7, m_ey - 7, m_ex + 7, m_ey + 7), fill=(255, 211, 42, 255), outline=(255, 255, 255, 255), width=2)

    # Owner kill anchors (highlighted red-gold badge + collision-avoiding [MM:SS] Ship label)
    owner_kills = sorted([sm for sm in sunk_markers if sm.get("killed_by_owner")], key=lambda s: s["time_sec"])
    for km in owner_kills:
        kx, ky = to_map_xy(km["x"], km["y"])
        mdraw.ellipse((kx - 8, ky - 8, kx + 8, ky + 8), fill=(215, 42, 58, 240), outline=(255, 211, 42, 255), width=2)
        mdraw.line([(kx - 4, ky), (kx + 4, ky)], fill=(255, 255, 255, 245), width=2)
        mdraw.line([(kx, ky - 4), (kx, ky + 4)], fill=(255, 255, 255, 245), width=2)

        kt = km["time_sec"]
        k_txt = f"[{kt // 60:02d}:{kt % 60:02d}] {km['ship_name']}"
        f_ktag = select_font_for_text(k_txt, 11)
        k_txt = fit_text_ellipsis(k_txt, f_ktag, 145)
        tw = _text_width(k_txt, f_ktag) + 10
        th = 17
        # Multi-ring spiral candidate search around (kx, ky) for zero tag overlap
        candidates = []
        for rad in (12, 26, 42, 58):
            candidates.extend([
                (round(kx + rad), round(ky - th / 2)),
                (round(kx + rad * 0.75), round(ky - th - rad * 0.6)),
                (round(kx + rad * 0.75), round(ky + rad * 0.6)),
                (round(kx - tw - rad), round(ky - th / 2)),
                (round(kx - tw - rad * 0.75), round(ky - th - rad * 0.6)),
                (round(kx - tw - rad * 0.75), round(ky + rad * 0.6)),
                (round(kx - tw / 2), round(ky - th - rad)),
                (round(kx - tw / 2), round(ky + rad)),
            ])
        chosen = None
        for cx_c, cy_c in candidates:
            bx0 = max(4, min(MAP_SIZE - tw - 4, cx_c))
            by0 = max(16, min(MAP_SIZE - th - 4, cy_c))
            box = (bx0, by0, bx0 + tw, by0 + th)
            if not any(not (box[2] < pb[0] - 2 or box[0] > pb[2] + 2 or box[3] < pb[1] - 2 or box[1] > pb[3] + 2) for pb in placed_boxes):
                chosen = box
                break
        if chosen is None:
            bx0 = max(4, min(MAP_SIZE - tw - 4, candidates[0][0]))
            by0 = max(16, min(MAP_SIZE - th - 4, candidates[0][1]))
            chosen = (bx0, by0, bx0 + tw, by0 + th)
        placed_boxes.append(chosen)
        tag_cx = (chosen[0] + chosen[2]) / 2
        tag_cy = (chosen[1] + chosen[3]) / 2
        if math.hypot(tag_cx - kx, tag_cy - ky) > 38:
            mdraw.line([(kx, ky), (tag_cx, tag_cy)], fill=(255, 195, 42, 140), width=1)
        mdraw.rounded_rectangle(chosen, radius=4, fill=(22, 14, 20, 225), outline=(255, 195, 42, 220), width=1)
        mdraw.text((chosen[0] + 5, chosen[1] + 2), k_txt, fill=(255, 225, 130, 255), font=f_ktag)

    map_canvas = Image.alpha_composite(map_canvas, marker_overlay)
    base_img.alpha_composite(map_canvas, (card_x + PAD_X, card_y + HEADER_H + TOP_RULER_PAD))

    # 7. Bottom legend strip
    leg_y = card_y + HEADER_H + TOP_RULER_PAD + MAP_SIZE + 12
    f_leg = select_font_for_text("轨迹", 13)
    draw = ImageDraw.Draw(base_img)
    lx = card_x + 22
    # Owner gradient line
    draw.line([(lx, leg_y + 9), (lx + 14, leg_y + 9)], fill=(56, 189, 248), width=3)
    draw.line([(lx + 14, leg_y + 9), (lx + 28, leg_y + 9)], fill=(255, 211, 42), width=3)
    draw.text((lx + 34, leg_y + 1), "己方高光航迹", fill=(215, 232, 248), font=f_leg)
    lx += 135
    draw.line([(lx, leg_y + 9), (lx + 22, leg_y + 9)], fill=(46, 213, 115, 180), width=2)
    draw.text((lx + 28, leg_y + 1), "友军轨迹", fill=(160, 180, 200), font=f_leg)
    lx += 105
    draw.line([(lx, leg_y + 9), (lx + 22, leg_y + 9)], fill=(255, 71, 87, 180), width=2)
    draw.text((lx + 28, leg_y + 1), "敌军轨迹", fill=(160, 180, 200), font=f_leg)
    lx += 105
    draw.line([(lx + 2, leg_y + 5), (lx + 10, leg_y + 13)], fill=(255, 71, 87), width=2)
    draw.line([(lx + 2, leg_y + 13), (lx + 10, leg_y + 5)], fill=(255, 71, 87), width=2)
    draw.text((lx + 17, leg_y + 1), "舰船沉没", fill=(160, 180, 200), font=f_leg)
    lx += 95
    draw.ellipse((lx, leg_y + 3, lx + 12, leg_y + 15), fill=(215, 42, 58), outline=(255, 211, 42), width=2)
    draw.text((lx + 18, leg_y + 1), "本人亲手击沉", fill=(255, 215, 110), font=f_leg)

    return CARD_H


def _render_hp_timeline_card(
    base_img: Image.Image,
    card_x: int,
    card_y: int,
    card_w: int,
    card_h: int,
    data: dict[str, Any],
) -> None:
    """Renders Top-Right Card (1545x330): Team HP Advantage Envelope & Frag Inflection Chart."""
    draw_rounded_rect_aa(
        base_img,
        (card_x, card_y, card_x + card_w, card_y + card_h),
        radius=12,
        fill=(18, 26, 38, 240),
        outline=(32, 48, 68, 255),
        width=1,
    )
    HEADER_H = 46
    draw_rounded_rect_aa(
        base_img,
        (card_x, card_y, card_x + card_w, card_y + HEADER_H),
        radius=12,
        fill=(24, 36, 52, 255),
        corners=(True, True, False, False),
    )
    draw_rounded_rect_aa(
        base_img,
        (card_x, card_y, card_x + 8, card_y + HEADER_H),
        radius=12,
        fill=(46, 213, 115, 255),
        corners=(True, False, False, False),
    )

    draw = ImageDraw.Draw(base_img)
    f_hdr = select_font_for_text("双方", 19)
    f_sub = select_font_for_text("终局血量", 14)
    f_axis = select_font_for_text("00:00", 13)
    f_end_lbl = select_font_for_text("友敌", 13)
    draw.text((card_x + 22, card_y + 11), "双方总血量优劣势曲线 & 击杀拐点 (Team HP Timeline)", fill=(255, 255, 255), font=f_hdr)

    tactical = data.get("tactical", {})
    hp_timeline = tactical.get("hp_timeline", [])
    hp_frags = tactical.get("hp_frags", [])

    if not hp_timeline:
        draw.text((card_x + card_w // 2 - 120, card_y + card_h // 2), "暂无血量时序记录", fill=(110, 128, 148), font=f_sub)
        return

    final_ally_pct = hp_timeline[-1][1]
    final_enemy_pct = hp_timeline[-1][2]
    diff_pct = final_ally_pct - final_enemy_pct
    ally_alive = tactical.get("ally_alive_end", 0)
    enemy_alive = tactical.get("enemy_alive_end", 0)
    summary_str = (
        f"终局血量: 友方 {final_ally_pct:.1f}% ({ally_alive}存活)   vs   "
        f"敌方 {final_enemy_pct:.1f}% ({enemy_alive}存活)   |   血量差 {diff_pct:+.1f}%"
    )
    sw = _text_width(summary_str, f_sub)
    sum_col = (46, 213, 115) if diff_pct >= 0 else (255, 107, 129)
    draw.text((card_x + card_w - 22 - sw, card_y + 14), summary_str, fill=sum_col, font=f_sub)

    # Plot rectangle
    px0 = card_x + 62
    py0 = card_y + HEADER_H + 18
    px1 = card_x + card_w - 64
    py1 = card_y + card_h - 36
    pw = px1 - px0
    ph = py1 - py0

    # Grid lines (0..100%)
    for pct in (0, 25, 50, 75, 100):
        gy = round(py1 - (pct / 100.0) * ph)
        draw.line([(px0, gy), (px1, gy)], fill=(38, 54, 74, 180) if pct > 0 else (65, 88, 116, 220), width=1)
        lbl = f"{pct}%"
        lw = _text_width(lbl, f_axis)
        draw.text((px0 - lw - 10, gy - 8), lbl, fill=(125, 142, 162), font=f_axis)

    t_min = hp_timeline[0][0]
    t_max = max(t_min + 1, hp_timeline[-1][0])
    dur = t_max - t_min
    step_sec = 60 if dur <= 360 else (120 if dur <= 720 else 180)
    tick_t = 0
    while tick_t <= t_max:
        gx = round(px0 + ((tick_t - t_min) / dur) * pw)
        if px0 <= gx <= px1:
            draw.line([(gx, py0), (gx, py1)], fill=(30, 44, 62, 140), width=1)
            tlbl = f"{tick_t // 60:02d}:{tick_t % 60:02d}"
            tw = _text_width(tlbl, f_axis)
            draw.text((gx - tw // 2, py1 + 7), tlbl, fill=(125, 142, 162), font=f_axis)
        tick_t += step_sec

    # Draw curves & advantage envelope in 2x supersampling for crisp AA
    SS = 2
    plot_2x = Image.new("RGBA", (pw * SS, ph * SS), (0, 0, 0, 0))
    pdraw = ImageDraw.Draw(plot_2x)

    def to_px_2x(t_val: float, pct_val: float) -> tuple[float, float]:
        x = ((t_val - t_min) / dur) * (pw * SS - 1)
        y = (1.0 - max(0.0, min(100.0, pct_val)) / 100.0) * (ph * SS - 1)
        return (x, y)

    # Envelope polygons with exact crossover splitting
    for i in range(len(hp_timeline) - 1):
        t0, a0, e0 = hp_timeline[i]
        t1, a1, e1 = hp_timeline[i + 1]
        xa0, ya0 = to_px_2x(t0, a0)
        _, ye0 = to_px_2x(t0, e0)
        xa1, ya1 = to_px_2x(t1, a1)
        _, ye1 = to_px_2x(t1, e1)

        d0 = a0 - e0
        d1 = a1 - e1
        if (d0 >= 0 and d1 >= 0) or (d0 <= 0 and d1 <= 0):
            col = (46, 213, 115, 44) if (d0 + d1) >= 0 else (255, 71, 87, 44)
            pdraw.polygon([(xa0, ya0), (xa1, ya1), (xa1, ye1), (xa0, ye0)], fill=col)
        else:
            denom = d0 - d1
            alpha = d0 / denom if denom != 0 else 0.5
            xc = xa0 + (xa1 - xa0) * alpha
            yc = ya0 + (ya1 - ya0) * alpha
            col0 = (46, 213, 115, 44) if d0 >= 0 else (255, 71, 87, 44)
            col1 = (46, 213, 115, 44) if d1 >= 0 else (255, 71, 87, 44)
            pdraw.polygon([(xa0, ya0), (xc, yc), (xa0, ye0)], fill=col0)
            pdraw.polygon([(xc, yc), (xa1, ya1), (xa1, ye1)], fill=col1)

    enemy_pts = [to_px_2x(t, e) for t, _, e in hp_timeline]
    ally_pts = [to_px_2x(t, a) for t, a, _ in hp_timeline]
    if len(enemy_pts) >= 2:
        pdraw.line(enemy_pts, fill=(255, 71, 87, 235), width=5)
    if len(ally_pts) >= 2:
        pdraw.line(ally_pts, fill=(46, 213, 115, 245), width=6)

    # Frag inflection stems & dots
    tl_by_t = {t: (a, e) for t, a, e in hp_timeline}
    for ft, v_rel, _ in hp_frags:
        if ft not in tl_by_t:
            continue
        fa, fe = tl_by_t[ft]
        fx, fy_a = to_px_2x(ft, fa)
        _, fy_e = to_px_2x(ft, fe)
        if v_rel == 1:
            # Enemy killed (good inflection)
            pdraw.line([(fx, fy_e), (fx, ph * SS - 1)], fill=(46, 213, 115, 65), width=2)
            pdraw.ellipse((fx - 6, fy_e - 6, fx + 6, fy_e + 6), fill=(46, 213, 115, 240), outline=(14, 24, 36, 255), width=2)
        else:
            # Ally killed (bad inflection)
            pdraw.line([(fx, fy_a), (fx, ph * SS - 1)], fill=(255, 71, 87, 65), width=2)
            pdraw.ellipse((fx - 6, fy_a - 6, fx + 6, fy_a + 6), fill=(255, 71, 87, 240), outline=(14, 24, 36, 255), width=2)

    plot_aa = plot_2x.resize((pw, ph), Image.Resampling.LANCZOS)
    base_img.alpha_composite(plot_aa, (px0, py0))

    # End-of-line percentage callouts on right edge
    draw = ImageDraw.Draw(base_img)
    end_ay = round(py1 - (max(0.0, min(100.0, final_ally_pct)) / 100.0) * ph)
    end_ey = round(py1 - (max(0.0, min(100.0, final_enemy_pct)) / 100.0) * ph)
    if abs(end_ay - end_ey) < 18:
        if end_ay <= end_ey:
            end_ay -= 9
            end_ey += 9
        else:
            end_ey -= 9
            end_ay += 9
    end_ay = max(py0 + 6, min(py1 - 8, end_ay))
    end_ey = max(py0 + 6, min(py1 - 8, end_ey))
    draw.text((px1 + 8, end_ay - 8), f"友 {final_ally_pct:.0f}%", fill=(46, 213, 115), font=f_end_lbl)
    draw.text((px1 + 8, end_ey - 8), f"敌 {final_enemy_pct:.0f}%", fill=(255, 71, 87), font=f_end_lbl)


def _compute_chat_layout(
    chat_list: list[dict[str, Any]],
    col_w: int,
    player_by_id: dict[int, dict[str, Any]],
    player_by_name: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Pre-computes adaptive 1-or-2-line layout and exact row heights for chronological dual-column chat."""
    rendered_items: list[dict[str, Any]] = []
    for item in chat_list:
        ns = item["namespace"]
        is_div = ns in ("battle_division", "battle_prebattle")
        is_all = ns == "battle_common"
        is_quick = item.get("is_quick_cmd", False)
        tag_label = "无线电" if is_quick else ("分队" if is_div else ("全体" if is_all else "团队"))
        badge_w = 48 if len(tag_label) == 3 else 42

        speaker_p = player_by_id.get(item.get("player_id", -1)) or player_by_name.get(item.get("player_name", ""))
        sx_offset = 14 + 58 + badge_w + 8  # time + badge + gap

        div_tag = ""
        if speaker_p and speaker_p.get("division_num", 0) > 0:
            div_tag = f"[队{speaker_p['division_num']}] "
            sx_offset += _text_width(div_tag, select_font_for_text(div_tag, 13))

        clan_tag_str = ""
        if item.get("clan"):
            clan_tag_str = f"[{item['clan']}] "
            sx_offset += _text_width(clan_tag_str, select_font_for_text(clan_tag_str, 14))

        p_name_str = f"{item.get('player_name', '')}"
        f_name = select_font_for_text(p_name_str, 14)
        p_name_str = fit_text_ellipsis(p_name_str, f_name, max(60, col_w - sx_offset - 180))
        sx_offset += _text_width(p_name_str, f_name)

        s_ship = item.get("ship_name") or (speaker_p.get("ship_name") if speaker_p else "")
        ship_tag = f" ({s_ship}): " if s_ship else ": "
        f_ship = select_font_for_text(ship_tag, 13)
        sx_offset += _text_width(ship_tag, f_ship)

        msg_font = select_font_for_text(item.get("message", ""), 14)
        first_w = max(80, col_w - sx_offset - 12)
        second_w = max(140, col_w - 84 - 12)
        lines = _wrap_text_two_lines(item.get("message", ""), msg_font, first_w, second_w)
        bubble_h = 56 if len(lines) >= 2 else 36

        rendered_items.append({
            "item": item,
            "speaker_p": speaker_p,
            "tag_label": tag_label,
            "badge_w": badge_w,
            "div_tag": div_tag,
            "clan_tag_str": clan_tag_str,
            "p_name_str": p_name_str,
            "ship_tag": ship_tag,
            "lines": lines,
            "bubble_h": bubble_h,
            "sx_offset": sx_offset,
        })

    # Pair rows chronologically: (0,1), (2,3), (4,5)...
    row_heights: list[int] = []
    for i in range(0, len(rendered_items), 2):
        h_l = rendered_items[i]["bubble_h"]
        h_r = rendered_items[i + 1]["bubble_h"] if (i + 1) < len(rendered_items) else 0
        row_heights.append(max(h_l, h_r))

    total_rows_h = sum(row_heights) + max(0, len(row_heights) - 1) * 8
    return rendered_items, total_rows_h


def _render_chat_card(
    base_img: Image.Image,
    card_x: int,
    card_y: int,
    card_w: int,
    min_h: int,
    data: dict[str, Any],
) -> int:
    """Renders Bottom-Right Card: Adaptive multi-line chronological dual-column chat & radio log."""
    chat_list = data.get("chat", [])
    ally_team_id = data["owner"]["team_id"]
    player_by_id = {p["player_id"]: p for p in data["players"]}
    player_by_name = {p["name"]: p for p in data["players"]}

    HEADER_H = 46
    INNER_PAD = 18
    COL_GAP = 16
    col_w = (card_w - 2 * INNER_PAD - COL_GAP) // 2

    rendered_items, total_rows_h = _compute_chat_layout(chat_list, col_w, player_by_id, player_by_name)
    natural_h = HEADER_H + 14 + (total_rows_h if chat_list else 60) + 16
    card_h = max(min_h, natural_h)

    draw_rounded_rect_aa(
        base_img,
        (card_x, card_y, card_x + card_w, card_y + card_h),
        radius=12,
        fill=(18, 26, 38, 240),
        outline=(32, 48, 68, 255),
        width=1,
    )
    draw_rounded_rect_aa(
        base_img,
        (card_x, card_y, card_x + card_w, card_y + HEADER_H),
        radius=12,
        fill=(24, 36, 52, 255),
        corners=(True, True, False, False),
    )
    draw_rounded_rect_aa(
        base_img,
        (card_x, card_y, card_x + 8, card_y + HEADER_H),
        radius=12,
        fill=(0, 206, 201, 255),
        corners=(True, False, False, False),
    )

    draw = ImageDraw.Draw(base_img)
    f_hdr = select_font_for_text("战局通讯", 19)
    draw.text(
        (card_x + 22, card_y + 11),
        f"战局通讯与战术无线电日志 (共 {len(chat_list)} 条)",
        fill=(255, 255, 255),
        font=f_hdr,
    )

    # Compact legend in header right
    f_leg = select_font_for_text("无线电", 12)
    leg_items = [
        ("全体", (235, 240, 245), (40, 50, 65)),
        ("团队", (46, 213, 115), (18, 55, 34)),
        ("分队", (255, 204, 0), (55, 42, 15)),
        ("无线电", (0, 215, 235), (18, 45, 58)),
    ]
    lx = card_x + card_w - 310
    for lbl, fg, bg in leg_items:
        bw = 48 if len(lbl) == 3 else 42
        draw.rounded_rectangle((lx, card_y + 12, lx + bw, card_y + 34), radius=4, fill=bg)
        tw = _text_width(lbl, f_leg)
        draw.text((lx + (bw - tw) // 2, card_y + 14), lbl, fill=fg, font=f_leg)
        lx += bw + 12

    if not rendered_items:
        f_empty = select_font_for_text("未记录", 16)
        empty_msg = "本场对局未记录到局内通讯或战术无线电指令"
        ew = _text_width(empty_msg, f_empty)
        draw.text((card_x + (card_w - ew) // 2, card_y + HEADER_H + (card_h - HEADER_H) // 2 - 10), empty_msg, fill=(100, 120, 140), font=f_empty)
        return card_h

    col_left_x = card_x + INNER_PAD
    col_right_x = col_left_x + col_w + COL_GAP
    cur_y = card_y + HEADER_H + 14

    for i in range(0, len(rendered_items), 2):
        pair = rendered_items[i: i + 2]
        row_h = max(p["bubble_h"] for p in pair)
        for col_idx, ri in enumerate(pair):
            start_cx = col_left_x if col_idx == 0 else col_right_x
            bubble_end_x = start_cx + col_w
            bh = ri["bubble_h"]
            item = ri["item"]
            is_ally = item["team_id"] == ally_team_id
            ns = item["namespace"]
            is_div = ns in ("battle_division", "battle_prebattle")
            is_all = ns == "battle_common"
            is_quick = item.get("is_quick_cmd", False)

            if is_quick:
                accent_col = (0, 206, 201)
                tag_bg, tag_col = (18, 45, 58), (0, 215, 235)
                name_col = (46, 213, 115) if is_ally else (255, 120, 130)
                msg_col = (145, 238, 248)
            elif is_div:
                accent_col = (255, 204, 0)
                tag_bg, tag_col = (55, 42, 15), (255, 204, 0)
                name_col = (255, 204, 0)
                msg_col = (255, 218, 72)
            elif is_all:
                accent_col = (210, 220, 232) if is_ally else (255, 71, 87)
                tag_bg, tag_col = (40, 50, 65), (235, 240, 245)
                name_col = (46, 213, 115) if is_ally else (255, 120, 130)
                msg_col = (245, 248, 252)
            else:
                accent_col = (46, 213, 115)
                tag_bg, tag_col = (18, 55, 34), (46, 213, 115)
                name_col = (46, 213, 115)
                msg_col = (120, 238, 165)

            draw.rounded_rectangle(
                (start_cx, cur_y, bubble_end_x, cur_y + bh),
                radius=6,
                fill=(24, 34, 48, 220),
                outline=(36, 52, 72, 255),
                width=1,
            )
            draw.rounded_rectangle(
                (start_cx, cur_y, start_cx + 5, cur_y + bh),
                radius=6,
                fill=accent_col,
                corners=(True, False, False, True),
            )

            # Time
            tm, ts = item["time_sec"] // 60, item["time_sec"] % 60
            time_str = f"[{tm:02d}:{ts:02d}]"
            f_time = select_font_for_text(time_str, 13)
            draw.text((start_cx + 12, cur_y + 9), time_str, fill=(0, 206, 201), font=f_time)

            # Channel badge
            bw = ri["badge_w"]
            bx = start_cx + 70
            draw.rounded_rectangle((bx, cur_y + 7, bx + bw, cur_y + 27), radius=4, fill=tag_bg)
            tl_w = _text_width(ri["tag_label"], f_leg)
            draw.text((bx + (bw - tl_w) // 2, cur_y + 8), ri["tag_label"], fill=tag_col, font=f_leg)

            sx = bx + bw + 8
            if ri["div_tag"]:
                speaker_p = ri["speaker_p"]
                s_div_col = (
                    (255, 215, 60)
                    if (speaker_p and speaker_p.get("is_owner_division"))
                    else ((46, 213, 115) if is_ally else (255, 110, 120))
                )
                f_div = select_font_for_text(ri["div_tag"], 13)
                draw.text((sx, cur_y + 9), ri["div_tag"], fill=s_div_col, font=f_div)
                sx += _text_width(ri["div_tag"], f_div)

            if ri["clan_tag_str"]:
                c_col = unpack_color(item.get("clan_color", 0))
                f_clan = select_font_for_text(ri["clan_tag_str"], 14)
                draw.text((sx, cur_y + 8), ri["clan_tag_str"], fill=c_col, font=f_clan)
                sx += _text_width(ri["clan_tag_str"], f_clan)

            f_pname = select_font_for_text(ri["p_name_str"], 14)
            draw.text((sx, cur_y + 8), ri["p_name_str"], fill=name_col, font=f_pname)
            sx += _text_width(ri["p_name_str"], f_pname)

            f_ship = select_font_for_text(ri["ship_tag"], 13)
            draw.text((sx, cur_y + 9), ri["ship_tag"], fill=(150, 178, 205), font=f_ship)
            sx += _text_width(ri["ship_tag"], f_ship)

            f_msg = select_font_for_text(item["message"], 14)
            lines = ri["lines"]
            if lines:
                draw.text((sx, cur_y + 8), lines[0], fill=msg_col, font=f_msg)
            if len(lines) >= 2:
                draw.text((start_cx + 76, cur_y + 30), lines[1], fill=msg_col, font=f_msg)

        cur_y += row_h + 8

    return card_h


def render_battle_report_card(data: dict[str, Any], output_path: str) -> str:
    """Renders the 2.4K Ultra-HD battle report graphic card and saves it to output_path."""
    W = 2400

    HEADER_Y = 28
    HEADER_H = 136

    HERO_Y = 180
    HERO_H = 320

    PANEL_Y = 518

    ow = data["owner"]
    ally_team_id = ow["team_id"]
    enemy_team_id = 1 - ally_team_id

    allies = [p for p in data["players"] if p["team_id"] == ally_team_id]
    enemies = [p for p in data["players"] if p["team_id"] != ally_team_id]

    has_pb = data.get("has_post_battle", False)
    if has_pb:
        allies.sort(key=lambda p: (p.get("base_xp", 0), p["damage_dealt"]), reverse=True)
        enemies.sort(key=lambda p: (p.get("base_xp", 0), p["damage_dealt"]), reverse=True)
    else:
        allies.sort(key=lambda p: p["damage_dealt"], reverse=True)
        enemies.sort(key=lambda p: p["damage_dealt"], reverse=True)

    max_rows = max(len(allies), len(enemies), 1)
    if max_rows <= 8:
        row_h = 68
    elif max_rows <= 12:
        row_h = 63
    else:
        row_h = 56

    PANEL_H = 94 + max_rows * row_h + 18

    TACTIC_Y = PANEL_Y + PANEL_H + 20
    LEFT_COL_W = 760
    RIGHT_COL_W = 1545  # 760 + 25 + 1545 = 2330 (x: 35 .. 2365)
    LEFT_CARD_H = 846
    HP_CARD_H = 330
    CHAT_MIN_H = LEFT_CARD_H - HP_CARD_H - 18  # 498px aligns cleanly with left minimap bottom

    # Pre-compute chat height so final image height is exact
    chat_list = data.get("chat", [])
    p_by_id = {p["player_id"]: p for p in data["players"]}
    p_by_name = {p["name"]: p for p in data["players"]}
    _, chat_rows_h = _compute_chat_layout(chat_list, (RIGHT_COL_W - 36 - 16) // 2, p_by_id, p_by_name)
    chat_card_h = max(CHAT_MIN_H, 46 + 14 + (chat_rows_h if chat_list else 60) + 16)
    tactic_total_h = max(LEFT_CARD_H, HP_CARD_H + 18 + chat_card_h)

    FOOTER_Y = TACTIC_Y + tactic_total_h + 18
    H = FOOTER_Y + 48

    img = Image.new("RGBA", (W, H), (12, 17, 24, 255))
    draw = ImageDraw.Draw(img)
    res_dir = _resources_dir()

    def f(size: int, text: str = ""):
        return select_font_for_text(text, size) if text else _load_font(
            os.path.join(res_dir, "warhelios_bold_zh.ttf"), size
        )

    # Subtle background tactical grid
    for y in range(0, H, 50):
        draw.line([(0, y), (W, y)], fill=(16, 23, 33, 255), width=1)
    for x in range(0, W, 50):
        draw.line([(x, 0), (x, H)], fill=(16, 23, 33, 255), width=1)

    # -------------------------------------------------------------
    # 1. TOP HEADER BAR (y: 28 .. 164)
    # -------------------------------------------------------------
    header_box = (35, HEADER_Y, W - 35, HEADER_Y + HEADER_H)
    draw_rounded_rect_aa(img, header_box, radius=14, fill=(18, 27, 39, 235), outline=(32, 48, 68, 255), width=1)
    draw = ImageDraw.Draw(img)

    # Left: Map & Real Game Mode + Team Counts
    map_text = fit_text_ellipsis(f"{data['map_title']} · {data['map_code']}", f(30, data["map_title"]), 880)
    draw.text((65, HEADER_Y + 22), map_text, fill=(255, 255, 255), font=f(30, map_text))
    mode_text = fit_text_ellipsis(
        f"{data['scenario_title']} · {data['game_type_title']} ({len(allies)} vs {len(enemies)})   |   对局时间: {data['date_time']}",
        f(18),
        900,
    )
    draw.text((65, HEADER_Y + 76), mode_text, fill=(145, 165, 185), font=f(18))

    # Center: VICTORY / DEFEAT / DRAW / INCOMPLETE Badge (2x AA)
    is_vic = data["is_victory"]
    is_draw = data["is_draw"]
    is_unfin = data.get("is_unfinished", False)
    if is_unfin:
        res_title = "INCOMPLETE · 未完结"
        res_color = (175, 195, 218)
        res_bg = (30, 42, 58, 230)
    elif is_draw:
        res_title = "DRAW · 平局"
        res_color = (241, 196, 15)
        res_bg = (50, 42, 15, 225)
    elif is_vic:
        res_title = "VICTORY · 战斗胜利"
        res_color = (46, 213, 115)
        res_bg = (18, 55, 34, 225)
    else:
        res_title = "DEFEAT · 战斗失败"
        res_color = (255, 71, 87)
        res_bg = (58, 22, 28, 225)

    res_badge_box = (W // 2 - 210, HEADER_Y + 18, W // 2 + 210, HEADER_Y + 78)
    draw_rounded_rect_aa(img, res_badge_box, radius=10, fill=res_bg, outline=res_color, width=2)
    draw = ImageDraw.Draw(img)
    tw = _text_width(res_title, f(30))
    draw.text((W // 2 - tw // 2, HEADER_Y + 28), res_title, fill=res_color, font=f(30))

    dur_m = data["duration_sec"] // 60
    dur_s = data["duration_sec"] % 60
    finish_reason = data.get("finish_reason", "对局规则判定")
    dur_text = f"战斗用时 {dur_m:02d}:{dur_s:02d} · {finish_reason}"
    draw.text((W // 2 - _text_width(dur_text, f(15)) // 2, HEADER_Y + 92), dur_text, fill=(125, 142, 162), font=f(15))

    # Right: Scores mirrored around colon `:` (relation 0 = ally, relation 1 = enemy)
    s_ally = data["final_score"].get(0, data["final_score"].get("0", 0))
    s_enemy = data["final_score"].get(1, data["final_score"].get("1", 0))
    colon_cx = W - 210
    colon_w = _text_width(":", f(30))
    draw.text((colon_cx - colon_w // 2, HEADER_Y + 22), ":", fill=(160, 170, 180), font=f(30))
    ally_sc_str = f"{s_ally}"
    enemy_sc_str = f"{s_enemy}"
    ally_sc_w = _text_width(ally_sc_str, f(36))
    draw.text((colon_cx - 18 - ally_sc_w, HEADER_Y + 18), ally_sc_str, fill=(46, 213, 115), font=f(36))
    draw.text((colon_cx + 18, HEADER_Y + 18), enemy_sc_str, fill=(255, 71, 87), font=f(36))
    lbl_sc = "比分"
    draw.text((colon_cx - 18 - max(ally_sc_w, 72) - 52, HEADER_Y + 28), lbl_sc, fill=(140, 158, 178), font=f(18))

    ver_text = f"客户端版本: {data['client_version']}"
    draw.text((W - 65 - _text_width(ver_text, f(15)), HEADER_Y + 78), ver_text, fill=(105, 122, 142), font=f(15))

    # -------------------------------------------------------------
    # 2. OWNER SPOTLIGHT HERO CARD (y: 180 .. 500)
    # -------------------------------------------------------------
    card_box = (35, HERO_Y, W - 35, HERO_Y + HERO_H)
    draw_rounded_rect_aa(img, card_box, radius=14, fill=(20, 30, 44, 240), outline=(0, 206, 201, 165), width=1)
    draw = ImageDraw.Draw(img)

    # Left Column: Identity (x: 65 .. 600)
    tier_str = TIER_ROMAN.get(ow["level"], str(ow["level"]))
    spec_str = SPECIES_NAMES.get(ow["species"], ow["species"])
    nation_str = NATION_NAMES.get(ow.get("nation", ""), ow.get("nation", ""))
    tag_ship = fit_text_ellipsis(f"[{tier_str} {spec_str} · {nation_str}]", f(17), 535)
    draw.text((65, HERO_Y + 25), tag_ship, fill=(0, 206, 201), font=f(17))

    ship_font = f(44, ow["ship_name"])
    safe_hero_ship = fit_text_ellipsis(ow["ship_name"], ship_font, 535)
    draw.text((65, HERO_Y + 54), safe_hero_ship, fill=(255, 255, 255), font=ship_font)

    px = 65
    if ow["clan"]:
        c_col = unpack_color(ow.get("clan_color", 0))
        c_tag = f"[{ow['clan']}] "
        f_clan = f(24, c_tag)
        draw.text((px, HERO_Y + 120), c_tag, fill=c_col, font=f_clan)
        px += _text_width(c_tag, f_clan)
    name_font = f(24, ow["name"])
    safe_owner_name = fit_text_ellipsis(ow["name"], name_font, max(60, 600 - px))
    draw.text((px, HERO_Y + 120), safe_owner_name, fill=(240, 244, 248), font=name_font)

    if ow["is_sunk"]:
        st_text = fit_text_ellipsis(f"战斗损毁 (击沉者: {ow['killer_name']})", f(17, ow["killer_name"]), 535)
        st_color = (255, 107, 129)
    else:
        st_text = "整场存活 (Survive)"
        st_color = (46, 213, 115)
    draw.text((65, HERO_Y + 162), st_text, fill=st_color, font=f(17, st_text))

    # Owner Division Badge in Hero card (pixel-clamped)
    if ow.get("division_num", 0) > 0:
        div_no = ow["division_num"]
        mates = [m for m in ow.get("division_members", []) if m != ow["name"]]
        mates_txt = f" · 搭档: {', '.join(mates)}" if mates else ""
        div_title = fit_text_ellipsis(f"★ 组队出战 [分队 {div_no}]{mates_txt}", f(14, mates_txt), 510)
        bw = _text_width(div_title, f(14, div_title))
        draw_rounded_rect_aa(
            img,
            (65, HERO_Y + 196, 65 + bw + 24, HERO_Y + 228),
            radius=6,
            fill=(48, 38, 14, 225),
            outline=(255, 195, 18, 220),
            width=1,
        )
        draw = ImageDraw.Draw(img)
        draw.text((77, HERO_Y + 202), div_title, fill=(255, 215, 60), font=f(14, div_title))

    # Divider 1
    draw.line([(620, HERO_Y + 20), (620, HERO_Y + HERO_H - 20)], fill=(32, 48, 68, 255), width=1)

    # Middle Column: Performance (x: 645 .. 1560)
    draw.text((645, HERO_Y + 20), "造成对敌总伤害 (TOTAL DAMAGE)", fill=(140, 158, 178), font=f(16))
    dmg_num = f"{ow['total_dmg']:,.0f}"
    draw.text((645, HERO_Y + 45), dmg_num, fill=(0, 235, 255), font=f(56))

    # Aggregated weapon breakdown (sorted descending, no duplicate tags)
    bd_agg = ow.get("damage_breakdown_agg", [])
    bd_parts = [f"{cat} {dmg:,.0f}" for cat, dmg in bd_agg if dmg > 0]
    bd_str = "   ·   ".join(bd_parts) if bd_parts else "直接火力全额输出"
    bd_str = fit_text_ellipsis(bd_str, f(15), 915)
    draw.text((645, HERO_Y + 120), bd_str, fill=(160, 178, 198), font=f(15))

    stats_data = [
        ("击沉战舰", f"{ow['frags']}", "frags.png", (255, 71, 87)),
        ("击落战机", f"{ow['planes_killed']}", "caused_avia_damage.png", (255, 211, 42)),
        ("协助点亮", f"{ow['spot_dmg']:,.0f}", "assisted_damage.png", (0, 206, 201)),
        ("潜在承伤", f"{ow['agro_dmg']:,.0f}", "blocked_damage.png", (112, 161, 255)),
    ]

    for idx, (label, val, icon_name, color) in enumerate(stats_data):
        bx = 645 + idx * 228
        by = HERO_Y + 172
        draw_rounded_rect_aa(
            img,
            (bx, by, bx + 215, by + 105),
            radius=10,
            fill=(26, 38, 54, 220),
            outline=(42, 60, 84, 255),
            width=1,
        )
        draw = ImageDraw.Draw(img)
        draw.text((bx + 16, by + 14), label, fill=(130, 148, 168), font=f(15))
        draw.text((bx + 16, by + 46), val, fill=color, font=f(30))

        icon_path = os.path.join(res_dir, "counter_icons", icon_name)
        if not os.path.exists(icon_path):
            icon_path = os.path.join(res_dir, "frag_icons", icon_name)
        ic = _load_scaled_icon(icon_path, 34, 34)
        if ic is not None:
            img.paste(ic, (bx + 165, by + 14), ic)

    # Divider 2
    draw.line([(1580, HERO_Y + 20), (1580, HERO_Y + HERO_H - 20)], fill=(32, 48, 68, 255), width=1)

    # Right Column: Achievements & Ribbons (x: 1605 .. 2345, width 740px)
    avail_right_w = 740
    # Normalize achievements list to (id, code, count)
    raw_ach_items = ow.get("achievements", [])
    norm_achs: list[tuple[int, str, int]] = []
    for item in raw_ach_items:
        if len(item) >= 3:
            norm_achs.append((item[0], item[1], item[2]))
        elif len(item) == 2:
            norm_achs.append((item[0], item[1], 1))

    has_ach = bool(norm_achs)
    if has_ach:
        draw.text((1605, HERO_Y + 20), "当局勋章 & 战功勋带", fill=(140, 158, 178), font=f(16))
        n_achs = len(norm_achs)
        if n_achs <= 7:
            icon_sz = 60
            slot_w = min(98, max(76, avail_right_w // n_achs))
            for idx, (_, ach_code, cnt) in enumerate(norm_achs):
                ach_file = os.path.join(res_dir, "achievement_icons", f"icon_achievement_{ach_code}.png")
                ach_img = _load_scaled_icon(ach_file, icon_sz, icon_sz)
                slot_x = 1605 + idx * slot_w
                icon_x = slot_x + (slot_w - icon_sz) // 2
                icon_cx = icon_x + icon_sz // 2
                if ach_img is not None:
                    img.paste(ach_img, (icon_x, HERO_Y + 48), ach_img)
                if cnt > 1:
                    cnt_str = f"×{cnt}"
                    cw = _text_width(cnt_str, f(12))
                    draw.rounded_rectangle((icon_x + icon_sz - cw - 6, HERO_Y + 48 + icon_sz - 16, icon_x + icon_sz, HERO_Y + 48 + icon_sz), radius=4, fill=(14, 22, 34, 220))
                    draw.text((icon_x + icon_sz - cw - 3, HERO_Y + 48 + icon_sz - 16), cnt_str, fill=(255, 220, 60), font=f(12))
                ach_title = fit_text_ellipsis(_resolve_achievement_title(ach_code), f(13), slot_w - 4)
                tw_a = _text_width(ach_title, f(13))
                draw.text((icon_cx - tw_a // 2, HERO_Y + 114), ach_title, fill=(255, 204, 0), font=f(13))
            r_y = HERO_Y + 148
        elif n_achs <= 9:
            icon_sz = 50
            slot_w = avail_right_w // n_achs
            for idx, (_, ach_code, cnt) in enumerate(norm_achs):
                ach_file = os.path.join(res_dir, "achievement_icons", f"icon_achievement_{ach_code}.png")
                ach_img = _load_scaled_icon(ach_file, icon_sz, icon_sz)
                slot_x = 1605 + idx * slot_w
                icon_x = slot_x + (slot_w - icon_sz) // 2
                icon_cx = icon_x + icon_sz // 2
                if ach_img is not None:
                    img.paste(ach_img, (icon_x, HERO_Y + 48), ach_img)
                if cnt > 1:
                    draw.text((icon_x + icon_sz - 16, HERO_Y + 48 + icon_sz - 14), f"×{cnt}", fill=(255, 220, 60), font=f(11))
                ach_title = fit_text_ellipsis(_resolve_achievement_title(ach_code), f(12), slot_w - 4)
                tw_a = _text_width(ach_title, f(12))
                draw.text((icon_cx - tw_a // 2, HERO_Y + 104), ach_title, fill=(255, 204, 0), font=f(12))
            r_y = HERO_Y + 138
        else:
            # 2-row compact medal grid for >9 medals
            cols_m = min(9, math.ceil(n_achs / 2))
            icon_sz = 42
            slot_w = avail_right_w // cols_m
            for idx, (_, ach_code, cnt) in enumerate(norm_achs[: cols_m * 2]):
                mr, mc = divmod(idx, cols_m)
                ach_file = os.path.join(res_dir, "achievement_icons", f"icon_achievement_{ach_code}.png")
                ach_img = _load_scaled_icon(ach_file, icon_sz, icon_sz)
                slot_x = 1605 + mc * slot_w
                slot_y = HERO_Y + 46 + mr * 60
                icon_x = slot_x + (slot_w - icon_sz) // 2
                icon_cx = icon_x + icon_sz // 2
                if ach_img is not None:
                    img.paste(ach_img, (icon_x, slot_y), ach_img)
                if cnt > 1:
                    draw.text((icon_x + icon_sz - 14, slot_y + icon_sz - 13), f"×{cnt}", fill=(255, 220, 60), font=f(11))
                ach_title = fit_text_ellipsis(_resolve_achievement_title(ach_code), f(11), slot_w - 4)
                tw_a = _text_width(ach_title, f(11))
                draw.text((icon_cx - tw_a // 2, slot_y + 43), ach_title, fill=(255, 204, 0), font=f(11))
            r_y = HERO_Y + 172
    else:
        draw.text((1605, HERO_Y + 20), "战功勋带 & 战术表现", fill=(140, 158, 178), font=f(16))
        draw_rounded_rect(draw, (1780, HERO_Y + 17, 1945, HERO_Y + 41), radius=4, fill=(24, 34, 46, 220), outline=(45, 65, 88, 220), width=1)
        draw.text((1790, HERO_Y + 21), "本场未触发成就勋章", fill=(130, 150, 170), font=f(13))
        r_y = HERO_Y + 56

    # Collect all non-zero ribbons in priority order + any unknown remaining ribbons
    ow_ribbons = ow.get("ribbons", {})
    active_ribbons: list[tuple[str, int]] = []
    seen_r = set()
    for r_key in RIBBON_ORDER:
        cnt = ow_ribbons.get(r_key, 0)
        if cnt > 0:
            active_ribbons.append((r_key, cnt))
            seen_r.add(r_key)
    for r_key, cnt in ow_ribbons.items():
        if r_key not in seen_r and cnt > 0:
            active_ribbons.append((r_key, cnt))

    r_x = 1605
    n_ribs = len(active_ribbons)
    if n_ribs <= 10:
        cols_r = 5
        chip_w, chip_h, gap_x, gap_y = 138, 44, 12, 10
    elif n_ribs <= 12:
        cols_r = 6
        chip_w, chip_h, gap_x, gap_y = 115, 40, 10, 8
    else:
        cols_r = 6
        chip_w, chip_h, gap_x, gap_y = 115, 34, 10, 6

    max_rows_r = max(1, (HERO_Y + HERO_H - 36 - r_y) // (chip_h + gap_y))
    max_chips = cols_r * max_rows_r
    last_row_used = 0
    for idx_r, (r_key, r_cnt) in enumerate(active_ribbons[:max_chips]):
        row_idx, col_idx = divmod(idx_r, cols_r)
        last_row_used = row_idx + 1
        cx = r_x + col_idx * (chip_w + gap_x)
        cy = r_y + row_idx * (chip_h + gap_y)

        draw_rounded_rect(draw, (cx, cy, cx + chip_w, cy + chip_h), radius=8, fill=(26, 38, 54, 220), outline=(42, 60, 84, 255), width=1)

        r_file = os.path.join(res_dir, "ribbon_icons", f"ribbon_{r_key}.png")
        if not os.path.exists(r_file):
            r_file = os.path.join(res_dir, "ribbon_icons", "ribbon_unknown.png")
        r_icon_w = 54 if cols_r == 6 else 60
        r_icon_h = 22 if chip_h <= 36 else 26
        r_img = _load_scaled_icon(r_file, r_icon_w, r_icon_h)
        if r_img is not None:
            img.paste(r_img, (cx + 6, cy + (chip_h - r_icon_h) // 2), r_img)
        txt_r = f"×{r_cnt}"
        f_rib = f(15 if cols_r == 6 else 17)
        draw.text((cx + r_icon_w + 10, cy + (chip_h - 18) // 2), txt_r, fill=(245, 245, 245), font=f_rib)

    detail_y = r_y + last_row_used * (chip_h + gap_y) + 6
    if not has_ach and ow.get("planes_killed", 0) > 0 and detail_y + 24 < HERO_Y + HERO_H - 12:
        pk_info = f"防空拦截战果: 累计击落敌机 {ow['planes_killed']} 架"
        draw.text((r_x, detail_y), pk_info, fill=(0, 206, 201), font=f(14))
        detail_y += 22

    if ow.get("main_caliber_details") and detail_y + 18 < HERO_Y + HERO_H - 8:
        mc_parts = [f"{k} {v}" for k, v in ow["main_caliber_details"].items()]
        mc_text = fit_text_ellipsis("主炮命中明细: " + " · ".join(mc_parts), f(14), avail_right_w)
        draw.text((r_x, detail_y), mc_text, fill=(130, 148, 168), font=f(14))

    # -------------------------------------------------------------
    # 3. FULL TEAM SCOREBOARDS (y: PANEL_Y .. PANEL_Y + PANEL_H)
    # -------------------------------------------------------------
    HALF_W = (W - 70 - 25) // 2  # 1152px

    tot_ally_dmg = sum(p["damage_dealt"] for p in allies)
    tot_ally_k = sum(p["frags"] for p in allies)
    tot_enemy_dmg = sum(p["damage_dealt"] for p in enemies)
    tot_enemy_k = sum(p["frags"] for p in enemies)
    max_match_dmg = max([p["damage_dealt"] for p in data["players"]] + [1.0])

    def render_team_panel(
        start_x: int,
        team_name: str,
        team_color: tuple[int, int, int],
        team_dmg: float,
        team_k: int,
        plist: list[dict[str, Any]],
        num_divs: int = 0,
        is_winning_side: bool = False,
    ):
        p_box = (start_x, PANEL_Y, start_x + HALF_W, PANEL_Y + PANEL_H)
        draw_rounded_rect_aa(img, p_box, radius=12, fill=(18, 26, 38, 240), outline=(32, 48, 68, 255), width=1)

        # Panel Header (h: 52, clean top corners only + clipped left accent stripe)
        draw_rounded_rect_aa(
            img,
            (start_x, PANEL_Y, start_x + HALF_W, PANEL_Y + 52),
            radius=12,
            fill=(24, 36, 52, 255),
            corners=(True, True, False, False),
        )
        draw_rounded_rect_aa(
            img,
            (start_x, PANEL_Y, start_x + 8, PANEL_Y + 52),
            radius=12,
            fill=(*team_color, 255),
            corners=(True, False, False, False),
        )
        pdraw = ImageDraw.Draw(img)

        pdraw.text((start_x + 25, PANEL_Y + 14), team_name, fill=(255, 255, 255), font=f(21))
        team_pk = sum(p.get("planes_killed", 0) for p in plist)
        div_str = f"   组队: {num_divs} 组" if num_divs > 0 else ""
        team_summary = f"击沉: {team_k}   击落: {team_pk}   总输出: {team_dmg:,.0f}{div_str}"
        sum_w = _text_width(team_summary, f(16))
        pdraw.text((start_x + HALF_W - 22 - sum_w, PANEL_Y + 16), team_summary, fill=team_color, font=f(16))

        # Column Subheaders
        col_y = PANEL_Y + 60
        if has_pb:
            pdraw.text((start_x + 18, col_y), "战舰型号", fill=(110, 128, 148), font=f(15))
            pdraw.text((start_x + 222, col_y), "玩家昵称", fill=(110, 128, 148), font=f(15))
            pdraw.text((start_x + 457, col_y), "击杀", fill=(110, 128, 148), font=f(15))
            pdraw.text((start_x + 498, col_y), "飞机", fill=(110, 128, 148), font=f(15))
            pdraw.text((start_x + 568, col_y), "造成伤害", fill=(110, 128, 148), font=f(15))
            pdraw.text((start_x + 654, col_y), "协助点亮", fill=(110, 128, 148), font=f(15))
            pdraw.text((start_x + 738, col_y), "承受伤害", fill=(110, 128, 148), font=f(15))
            pdraw.text((start_x + 830, col_y), "潜在伤害", fill=(110, 128, 148), font=f(15))
            xp_hdr = "基础经验*" if is_winning_side else "基础经验"
            pdraw.text((start_x + 902, col_y), xp_hdr, fill=(215, 195, 110) if is_winning_side else (110, 128, 148), font=f(15))
            pdraw.text((start_x + 978, col_y), "状态与荣誉", fill=(110, 128, 148), font=f(15))
        else:
            pdraw.text((start_x + 18, col_y), "战舰型号", fill=(110, 128, 148), font=f(15))
            pdraw.text((start_x + 275, col_y), "玩家昵称", fill=(110, 128, 148), font=f(15))
            pdraw.text((start_x + 585, col_y), "击杀", fill=(110, 128, 148), font=f(15))
            pdraw.text((start_x + 642, col_y), "飞机", fill=(110, 128, 148), font=f(15))
            pdraw.text((start_x + 748, col_y), "造成伤害", fill=(110, 128, 148), font=f(15))
            pdraw.text((start_x + 885, col_y), "承受伤害", fill=(110, 128, 148), font=f(15))
            pdraw.text((start_x + 980, col_y), "状态与荣誉", fill=(110, 128, 148), font=f(15))

        pdraw.line([(start_x + 20, col_y + 26), (start_x + HALF_W - 20, col_y + 26)], fill=(28, 42, 60, 255), width=1)

        row_y = col_y + 34

        for idx, p in enumerate(plist):
            ry = row_y + idx * row_h
            div_num = p.get("division_num", 0)
            is_own_div = p.get("is_owner_division", False)
            row_box = (start_x + 10, ry - 3, start_x + HALF_W - 10, ry + row_h - 7)

            if p["is_owner"]:
                draw_rounded_rect_aa(img, row_box, radius=8, fill=(20, 48, 62, 235), outline=(0, 235, 255, 255), width=1)
                pdraw = ImageDraw.Draw(img)
            elif is_own_div:
                draw_rounded_rect_aa(img, row_box, radius=8, fill=(35, 30, 16, 185), outline=(243, 156, 18, 170), width=1)
                pdraw = ImageDraw.Draw(img)
            elif idx % 2 == 1:
                pdraw.rounded_rectangle(row_box, radius=8, fill=(20, 29, 42, 160))

            if div_num > 0:
                if is_own_div:
                    strip_col = (255, 195, 18)
                elif p["team_id"] == ally_team_id:
                    strip_col = (46, 213, 115)
                else:
                    enemy_strip_cols = [(255, 71, 87), (218, 92, 235), (243, 156, 18)]
                    strip_col = enemy_strip_cols[(div_num - 1) % len(enemy_strip_cols)]
                pdraw.rounded_rectangle((start_x + 10, ry + 4, start_x + 15, ry + row_h - 14), radius=2, fill=strip_col)

            tier = TIER_ROMAN.get(p["level"], str(p["level"]))
            ship_label = f"{tier} {p['ship_name']}"

            if p["is_sunk"]:
                name_color = (175, 185, 195)
                ship_color = (155, 168, 180)
            else:
                name_color = (255, 255, 255)
                ship_color = (235, 242, 250)

            if p["is_owner"]:
                name_color = (0, 235, 255)
                icon_tint = (0, 235, 255)
            elif is_own_div:
                name_color = (255, 215, 60) if not p["is_sunk"] else (210, 180, 80)
                icon_tint = (255, 205, 50)
            else:
                icon_tint = team_color if not p["is_sunk"] else tuple(max(40, int(c * 0.68)) for c in team_color)

            # Ship species silhouette icon + pixel-safe ship name
            sp_icon = _load_tinted_ship_icon(p["species"], icon_tint, 24, 13)
            if sp_icon is not None:
                img.paste(sp_icon, (start_x + 20, ry + 13), sp_icon)
            else:
                spec_fb = SPECIES_SHORT.get(p["species"], "SH")
                pdraw.text((start_x + 20, ry + 10), spec_fb, fill=icon_tint, font=f(13))

            ship_max_w = 166 if has_pb else 218
            f_ship = f(16 if has_pb else 17, ship_label)
            safe_ship = fit_text_ellipsis(ship_label, f_ship, ship_max_w)
            pdraw.text((start_x + 48, ry + 8), safe_ship, fill=ship_color, font=f_ship)

            # Player name slot (pixel-clamped end boundary!)
            px_cur = start_x + (222 if has_pb else 275)
            name_slot_end = start_x + (446 if has_pb else 575)

            if div_num > 0:
                badge_w = 36
                badge_h = 22
                badge_box = (px_cur, ry + 7, px_cur + badge_w, ry + 7 + badge_h)
                if is_own_div:
                    b_fill, b_out, t_col = (65, 48, 12, 240), (255, 195, 18, 255), (255, 215, 50)
                elif p["team_id"] == ally_team_id:
                    b_fill, b_out, t_col = (15, 52, 35, 240), (46, 213, 115, 255), (46, 213, 115)
                else:
                    enemy_badges = [
                        ((60, 20, 26, 240), (255, 71, 87, 255), (255, 110, 120)),
                        ((52, 20, 58, 240), (218, 92, 235, 255), (230, 130, 240)),
                        ((58, 36, 12, 240), (243, 156, 18, 255), (250, 175, 45)),
                    ]
                    b_fill, b_out, t_col = enemy_badges[(div_num - 1) % len(enemy_badges)]

                pdraw.rounded_rectangle(badge_box, radius=4, fill=b_fill, outline=b_out, width=1)
                b_text = f"队{div_num}"
                bw = _text_width(b_text, f(13))
                pdraw.text((px_cur + (badge_w - bw) // 2, ry + 9), b_text, fill=t_col, font=f(13))
                px_cur += badge_w + 6

            if p["clan"]:
                c_col = unpack_color(p.get("clan_color", 0))
                c_tag = f"[{p['clan']}] "
                f_clan = f(15, c_tag)
                c_w = _text_width(c_tag, f_clan)
                if px_cur + c_w + 35 < name_slot_end:
                    pdraw.text((px_cur, ry + 8), c_tag, fill=c_col, font=f_clan)
                    px_cur += c_w

            f_pname = f(16, p["name"])
            safe_pname = fit_text_ellipsis(p["name"], f_pname, max(24, name_slot_end - px_cur))
            pdraw.text((px_cur, ry + 8), safe_pname, fill=name_color, font=f_pname)

            # Frags
            k = p["frags"]
            frag_x = start_x + (456 if has_pb else 585)
            if k > 0:
                k_box = (frag_x, ry + 7, frag_x + 28, ry + 35)
                k_bg = (255, 71, 87) if k >= 2 else (230, 126, 34)
                pdraw.rounded_rectangle(k_box, radius=5, fill=k_bg)
                kw = _text_width(f"{k}", f(15))
                pdraw.text((frag_x + 14 - kw // 2, ry + 9), f"{k}", fill=(255, 255, 255), font=f(15))
            else:
                pdraw.text((frag_x + 10, ry + 8), "-", fill=(75, 90, 110), font=f(16))

            # Planes Killed (unified for both has_pb=True and has_pb=False!)
            pk = p.get("planes_killed", 0)
            plane_x = start_x + (496 if has_pb else 640)
            if pk > 0:
                pk_box = (plane_x, ry + 7, plane_x + 30, ry + 35)
                pk_bg = (16, 52, 68, 240)
                pk_out = (0, 206, 201, 240) if pk >= 15 else (0, 160, 180, 180)
                pk_col = (0, 235, 255) if pk >= 15 else (180, 230, 245)
                pdraw.rounded_rectangle(pk_box, radius=5, fill=pk_bg, outline=pk_out, width=1)
                pkw = _text_width(f"{pk}", f(14))
                pdraw.text((plane_x + 15 - pkw // 2, ry + 9), f"{pk}", fill=pk_col, font=f(14))
            else:
                pdraw.text((plane_x + 11, ry + 8), "-", fill=(75, 90, 110), font=f(16))

            # Damage Dealt + subtle bottom normalized Data Bar
            dmg_right_x = start_x + (630 if has_pb else 820)
            dmg_bar_left = start_x + (542 if has_pb else 700)
            dmg_ratio = max(0.0, min(1.0, p["damage_dealt"] / max_match_dmg))
            if dmg_ratio > 0:
                bar_w = max(3, round((dmg_right_x - dmg_bar_left) * dmg_ratio))
                bar_col = (0, 225, 255, 115) if p["is_owner"] else ((*team_color, 90))
                pdraw.rounded_rectangle((dmg_bar_left, ry + 32, dmg_right_x, ry + 36), radius=2, fill=(28, 40, 56, 120))
                pdraw.rounded_rectangle((dmg_right_x - bar_w, ry + 32, dmg_right_x, ry + 36), radius=2, fill=bar_col)

            d_val = f"{p['damage_dealt']:,.0f}"
            d_col = (0, 235, 255) if p["damage_dealt"] > 100000 else ((245, 245, 245) if p["damage_dealt"] > 50000 else (165, 180, 195))
            dw = _text_width(d_val, f(16))
            pdraw.text((dmg_right_x - dw, ry + 7), d_val, fill=d_col, font=f(16))

            if has_pb:
                # Spotting Damage (right-aligned at start_x + 714)
                sp_dmg = p.get("spotting_damage", 0)
                sp_val = f"{sp_dmg:,d}" if sp_dmg > 0 else "-"
                sp_col = (0, 215, 210) if sp_dmg >= 60000 else (145, 172, 195)
                spw = _text_width(sp_val, f(16))
                pdraw.text((start_x + 714 - spw, ry + 7), sp_val, fill=sp_col, font=f(16))

                # Damage Taken (right-aligned at start_x + 798)
                t_val = f"{p['damage_taken']:,.0f}"
                tw = _text_width(t_val, f(16))
                pdraw.text((start_x + 798 - tw, ry + 7), t_val, fill=(150, 165, 180), font=f(16))

                # Potential Damage (right-aligned at start_x + 892)
                agro_dmg = p.get("potential_damage", 0)
                agro_val = f"{agro_dmg:,d}" if agro_dmg > 0 else "-"
                agro_col = (130, 185, 235) if agro_dmg >= 1000000 else (145, 165, 185)
                agrow = _text_width(agro_val, f(16))
                pdraw.text((start_x + 892 - agrow, ry + 7), agro_val, fill=agro_col, font=f(16))

                # Base XP (right-aligned at start_x + 964)
                bxp = p.get("base_xp", 0)
                xp_val = f"{bxp:,d}" if bxp > 0 else "-"
                xp_col = (255, 215, 60) if bxp >= 1500 else ((245, 245, 245) if bxp >= 1000 else (185, 200, 215))
                xpw = _text_width(xp_val, f(16))
                pdraw.text((start_x + 964 - xpw, ry + 7), xp_val, fill=xp_col, font=f(16))

                status_x = start_x + 978
            else:
                t_val = f"{p['damage_taken']:,.0f}"
                tw = _text_width(t_val, f(16))
                pdraw.text((start_x + 950 - tw, ry + 7), t_val, fill=(150, 165, 180), font=f(16))
                status_x = start_x + 980

            # Status & Killer info
            if p["is_sunk"]:
                pdraw.text((status_x, ry + 4), "沉没", fill=(255, 107, 129), font=f(14))
                k_ship = p.get("killer_ship_name", "")
                k_user = p.get("killer_name", "")
                if k_ship and k_user:
                    k_str = f"by {k_ship} ({k_user})"
                elif k_ship:
                    k_str = f"by {k_ship}"
                elif k_user:
                    k_str = f"by {k_user}"
                else:
                    k_str = ""

                if k_str:
                    max_k_w = start_x + HALF_W - 14 - status_x
                    f_killer = f(12, k_str)
                    safe_k = fit_text_ellipsis(k_str, f_killer, max_k_w)
                    pdraw.text((status_x, ry + 26), safe_k, fill=(145, 158, 172), font=f_killer)
            else:
                pdraw.text((status_x, ry + 7), "● 存活", fill=(46, 213, 115), font=f(15))

            p_medals = p.get("achievements", [])
            if p_medals:
                medals_to_show = p_medals[:4]
                icon_size = 22
                icon_gap = 3
                tot_medals_w = len(medals_to_show) * icon_size + (len(medals_to_show) - 1) * icon_gap
                m_start_x = (start_x + HALF_W - 16) - tot_medals_w
                for _, a_code in medals_to_show:
                    a_file = os.path.join(res_dir, "achievement_icons", f"icon_achievement_{a_code}.png")
                    a_icon = _load_scaled_icon(a_file, icon_size, icon_size)
                    if a_icon is not None:
                        img.paste(a_icon, (m_start_x, ry + 4), a_icon)
                    m_start_x += icon_size + icon_gap

        # If one side has far fewer rows (e.g. Operation mode 9 vs 74), show clean summary footnote
        if len(plist) < max_rows:
            empty_top = row_y + len(plist) * row_h + 12
            if PANEL_Y + PANEL_H - empty_top >= 48:
                note = f"共 {len(plist)} 艘参战舰船 · 已完整列出（对局存在波次增援，两侧面板等高对齐）"
                nw = _text_width(note, f(13))
                pdraw.text((start_x + (HALF_W - nw) // 2, empty_top + 10), note, fill=(85, 105, 128), font=f(13))

    ally_div_count = data.get("team_division_counts", {}).get(ally_team_id, 0)
    enemy_div_count = data.get("team_division_counts", {}).get(enemy_team_id, 0)

    ally_panel_title = f"友方舰队 (Allies · {len(allies)} 艘战舰)"
    render_team_panel(
        35,
        ally_panel_title,
        (46, 213, 115),
        tot_ally_dmg,
        tot_ally_k,
        allies,
        ally_div_count,
        is_winning_side=bool(is_vic and has_pb),
    )

    enemy_panel_title = f"敌方舰队 (Enemies · {len(enemies)} 艘战舰)"
    render_team_panel(
        35 + HALF_W + 25,
        enemy_panel_title,
        (255, 71, 87),
        tot_enemy_dmg,
        tot_enemy_k,
        enemies,
        enemy_div_count,
        is_winning_side=bool((not is_vic) and (not is_draw) and (not is_unfin) and has_pb),
    )

    # -------------------------------------------------------------
    # 4. DUAL-COLUMN TACTICAL REVIEW SECTION (y: TACTIC_Y ..)
    # -------------------------------------------------------------
    _render_tactical_minimap_card(img, 35, TACTIC_Y, LEFT_COL_W, data)

    right_x = 35 + LEFT_COL_W + 25
    _render_hp_timeline_card(img, right_x, TACTIC_Y, RIGHT_COL_W, HP_CARD_H, data)
    _render_chat_card(img, right_x, TACTIC_Y + HP_CARD_H + 18, RIGHT_COL_W, CHAT_MIN_H, data)

    # -------------------------------------------------------------
    # 5. BOTTOM FOOTER BAR (y: FOOTER_Y .. H)
    # -------------------------------------------------------------
    draw = ImageDraw.Draw(img)
    draw.text((45, FOOTER_Y + 6), "Minimap Renderer · 战舰世界战局分析与小地图视频渲染引擎", fill=(95, 115, 138), font=f(15))
    right_foot = "数据源自 BigWorld Replay 原始数据包流单次解析"
    draw.text((W - 45 - _text_width(right_foot, f(15)), FOOTER_Y + 6), right_foot, fill=(95, 115, 138), font=f(15))

    out_dir = os.path.dirname(os.path.abspath(output_path))
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    img.save(output_path, "PNG")
    print(f"Ultra-HD Battle report successfully saved to: {output_path} ({W}x{H})")
    return output_path


def generate_battle_report(
    replay_path: str,
    output_path: Optional[str] = None,
    replay_info: Optional[dict[str, Any]] = None,
) -> str:
    """Convenience helper: parses replay (or reuses replay_info) and renders battle report card."""
    if output_path is None:
        output_path = os.path.splitext(replay_path)[0] + "-report.png"
    data = parse_replay_report(replay_path, replay_info=replay_info)
    return render_battle_report_card(data, output_path)
