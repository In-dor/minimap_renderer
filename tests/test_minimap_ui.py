from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from PIL import Image, ImageColor, ImageDraw

from renderer.conman import ConsumableManager
from renderer.data import (
    AcousticTorpedo,
    BattleResult,
    ControlPoint,
    Events,
    Frag,
    Message,
    PlayerInfo,
    ReplayData,
    Score,
    Shot,
    Smoke,
    Torpedo,
    Vehicle,
)
from renderer.layers.capture import LayerCaptureBase
from renderer.layers.chat import LayerChatBase
from renderer.layers.frag import LayerFragBase
from renderer.layers.markers import LayerMarkersBase
from renderer.layers.ribbon import LayerRibbonBase
from renderer.layers.score import LayerScoreBase
from renderer.layers.ship import LayerShipBase
from renderer.layers.shot import SHELL_COLORS, LayerShotBase
from renderer.layers.smoke import LayerSmokeBase
from renderer.layers.timer import LayerTimerBase
from renderer.layers.torpedo import LayerTorpedoBase
from renderer.render import RenderDual, Renderer, _encoder_params
from renderer.resman import ResourceManager
from renderer.utils import draw_grid, draw_health_bar, generate_holder, replace_color


def _make_player(
    pid: int = 1,
    ship_id: int = 1001,
    ship_params_id: int = 4181604144,  # Z-23 in 15.9 / ships.json fallback
    relation: int = -1,
    name: str = "TestPlayer",
    clan_tag: str = "TEST",
    realm: str = "ASIA",
) -> PlayerInfo:
    return PlayerInfo(
        account_db_id=pid,
        id=pid,
        clan_color=0x4CE8AA,
        clan_id=10,
        clan_tag=clan_tag,
        max_health=20000,
        name=name,
        realm=realm,
        ship_id=ship_id,
        team_id=0 if relation in (-1, 0) else 1,
        is_bot=False,
        ship_params_id=ship_params_id,
        relation=relation,
        hull=None,
        abilities=(),
        modernization=(),
        ship_components={"artillery": "", "fireControl": ""},
    )


def _make_vehicle(
    player_id: int = 1,
    vehicle_id: int = 1001,
    health: int = 15000,
    is_alive: bool = True,
    x: int = 0,
    y: int = 0,
    relation: int = -1,
    is_visible: bool = True,
    regeneration_health: float = 0.0,
) -> Vehicle:
    return Vehicle(
        player_id=player_id,
        vehicle_id=vehicle_id,
        health=health,
        is_alive=is_alive,
        x=x,
        y=y,
        yaw=0.0,
        relation=relation,
        is_visible=is_visible,
        not_in_range=False,
        visibility_flag=1,
        burn_flags=0,
        consumables_state={},
        regeneration_health=regeneration_health,
    )


def _make_events(time_left: int = 1000, **overrides) -> Events:
    defaults = dict(
        time_left=time_left,
        evt_vehicle={},
        evt_building={},
        evt_plane={},
        evt_ward={},
        evt_smoke={},
        evt_shot=[],
        evt_torpedo={},
        evt_hits=[],
        evt_consumable={},
        evt_control={},
        evt_score={0: Score(0, 100), 1: Score(1, 200)},
        evt_damage_maps={"Enemy": {}, "Agro": {}, "Spot": {}},
        evt_frag=[],
        evt_ribbon={},
        evt_achievement={},
        evt_times_to_win=(120.0, -1.0),
        evt_chat=[],
        evt_acoustic_torpedo={},
    )
    defaults.update(overrides)
    return Events(**defaults)


def _pick_two_ships_with_consumables(resman: ResourceManager):
    ships = resman.load_json("ships.json")
    abilities = resman.load_json("abilities.json")
    chosen = []
    seen_icons = set()
    for spid, sdata in ships.items():
        if not isinstance(spid, int):
            continue
        ab = abilities.get(spid, {})
        idx_map = ab.get("id_to_index", {})
        # Find aid=0 or aid=1 with distinct consumable icon
        for aid in (0, 1, 10):
            idx = idx_map.get(aid, idx_map.get(str(aid)))
            if idx and idx not in seen_icons:
                seen_icons.add(idx)
                chosen.append((spid, aid, idx))
                break
        if len(chosen) >= 2:
            break
    return chosen


def test_no_pillow_deprecated_getsize_calls_remain():
    renderer_root = Path("src/renderer")
    offenders = []
    for py_file in renderer_root.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        if ".getsize(" in text:
            offenders.append(str(py_file))
    assert offenders == []


def test_draw_grid_exact_divisions_without_eleventh_column_slit():
    size = 1073  # 760 * 24 / 17 at 1920x1200
    grid = draw_grid(size=size, line_width=1)
    arr = np.array(grid)
    # Check interior vertical grid lines appear ONLY at the 9 exact positions
    expected_positions = {round(size * i / 10) for i in range(1, 10)}
    interior_cols = {
        x
        for x in range(1, size - 1)
        if arr[size // 2, x, 3] > 0 and arr[size // 3, x, 3] > 0
    }
    assert interior_cols == expected_positions
    assert 1070 not in interior_cols


def test_replace_color_matches_rgb_channels_accurately():
    img = Image.new("RGBA", (4, 4), (76, 232, 170, 255))  # #4ce8aa
    out = replace_color(img, "#4ce8aa", "#fe4d2a")
    assert out.getpixel((0, 0))[:3] == ImageColor.getrgb("#fe4d2a")


def test_resman_unicode_font_selection_deterministic():
    resman = ResourceManager("15_9_0")
    assert resman.load_font_with_text("gg", 12) is resman.load_default_font(12)
    assert resman.load_font_with_text("F", 12) is resman.load_default_font(12)
    assert resman.load_font_with_text("русский язык", 12) is resman.load_default_font(12)
    assert resman.load_font_with_text("望帯宮祝", 12) is resman.load_font("warhelios_bold_zh.ttf", size=12)
    assert resman.load_font_with_text("藤シア進", 12) is resman.load_font("warhelios_bold_jp.ttf", size=12)
    assert resman.load_font_with_text("다만. 모든", 12) is resman.load_font("warhelios_bold_ko.ttf", size=12)


def test_encoder_params_quality_8_targets_crf_cq_20():
    assert "-crf" in _encoder_params("libx264", "h264", 8)
    x264 = _encoder_params("libx264", "h264", 8)
    assert x264[x264.index("-crf") + 1] == "20"

    x265 = _encoder_params("libx265", "h265", 8)
    assert x265[x265.index("-crf") + 1] == "20"

    nvenc = _encoder_params("h264_nvenc", "h264", 8)
    assert nvenc[nvenc.index("-cq") + 1] == "20"

    qsv = _encoder_params("h264_qsv", "h264", 8)
    assert qsv[qsv.index("-global_quality") + 1] == "20"

    vaapi = _encoder_params("h264_vaapi", "h264", 8)
    assert vaapi[vaapi.index("-qp") + 1] == "20"

    av1 = _encoder_params("libaom-av1", "av1", 8)
    assert 20 <= int(av1[av1.index("-crf") + 1]) <= 28


def test_generate_holder_and_health_bar_trough_and_regen():
    resman = ResourceManager("15_9_0")
    resman.set_render_scale(24 / 17)
    ships = resman.load_json("ships.json")
    # Pick a ship with a very long name
    long_spid = max(
        (k for k in ships if isinstance(k, int)),
        key=lambda k: len(ships[k]["name"]),
    )
    p = _make_player(pid=1, ship_params_id=long_spid)
    holders = generate_holder({1: p}, resman)
    holder = holders[1]
    assert holder.width >= round(100 * resman.render_scale)
    assert holder.getbbox() is not None

    bar_img = Image.new("RGBA", (141, 141), (0, 0, 0, 0))
    draw_health_bar(bar_img, color="#4ce8aa", hp_per=0.4, regen_per=0.7)
    # Center-right pixel of the bar should show the dark trough / regen fill, not transparent
    y = round(65 * 1.41) + 2
    assert bar_img.getpixel((round(bar_img.width * 0.72), y))[3] > 100


def test_shot_team_tracers_with_secondary_and_ap_sap_colors():
    assert SHELL_COLORS["AP"] == (200, 244, 255)
    assert SHELL_COLORS["CS"] == (255, 92, 200)

    resman = ResourceManager("15_9_0")
    ships = resman.load_json("ships.json")
    proj = resman.load_json("projectiles.json")
    spid = next(k for k in ships if isinstance(k, int))
    sec_pid = next(
        pid for pid, val in proj.items() if isinstance(pid, int) and val in SHELL_COLORS
    )
    p1 = _make_player(pid=1, ship_id=1001, ship_params_id=spid, relation=0)
    rd = ReplayData(
        game_arena_id=1,
        game_version="15_9_0",
        game_map="16_OC_bees_to_honey",
        game_battle_type=1249,
        game_win_score=1000,
        game_result=BattleResult(0, 0),
        owner_avatar_id=1,
        owner_vehicle_id=1001,
        owner_id=1,
        player_info={1: p1},
        building_info={},
        events={
            0: _make_events(
                evt_vehicle={1001: _make_vehicle()},
                evt_shot=[Shot(owner_id=1001, params_id=sec_pid, origin=(-100, -100), destination=(100, 100), shot_id=99, t_time=3)],
            )
        },
    )
    renderer = Renderer(rd, logs=True, team_tracers=True)
    renderer._configure_resolution((1920, 1200))
    renderer._load_map()
    shot_layer = LayerShotBase(renderer)
    canvas = Image.new("RGBA", renderer.minimap_fg.size)
    shot_layer.draw(0, canvas)
    assert canvas.getbbox() is not None


def test_frag_missing_icon_fallback_cjk_and_height_limit():
    resman = ResourceManager("15_9_0")
    ships = resman.load_json("ships.json")
    spid = next(k for k in ships if isinstance(k, int))
    p1 = _make_player(pid=1, ship_id=1001, ship_params_id=spid, relation=0, name="测试舰长", realm="ASIA")
    p2 = _make_player(pid=2, ship_id=1002, ship_params_id=spid, relation=1, name="敵プレイヤー", realm="ASIA")
    frags = [Frag(killed_id=1002, fragger_id=1001, death_type=27) for _ in range(12)]
    rd = ReplayData(
        game_arena_id=1,
        game_version="15_9_0",
        game_map="16_OC_bees_to_honey",
        game_battle_type=1249,
        game_win_score=1000,
        game_result=BattleResult(0, 0),
        owner_avatar_id=1,
        owner_vehicle_id=1001,
        owner_id=1,
        player_info={1: p1, 2: p2},
        building_info={},
        events={0: _make_events(evt_frag=frags)},
    )
    renderer = Renderer(rd, logs=True, enable_chat=True)
    renderer._configure_resolution((1920, 1200))
    frag_layer = LayerFragBase(renderer)
    out = Image.new("RGBA", renderer.output_size)
    frag_layer.draw(0, out)
    bbox = out.getbbox()
    assert bbox is not None
    # Top of frag list must stay cleanly inside Card 3 below min_y=540
    assert bbox[1] >= renderer.px(540)


def test_ship_consumable_cache_isolated_by_params_id_and_holder_lru_cap():
    resman = ResourceManager("15_9_0")
    ships = resman.load_json("ships.json")
    # Find two ships where the same aid maps to DIFFERENT consumable indices
    abilities = resman.load_json("abilities.json")
    pair = None
    by_aid_idx = {}
    from importlib.resources import is_resource

    for spid, ab in abilities.items():
        if not isinstance(spid, int) or spid not in ships:
            continue
        id_to_idx = ab.get("id_to_index", {})
        for aid in (0, 1, 2, 10, 12):
            idx = id_to_idx.get(aid, id_to_idx.get(str(aid)))
            if not idx or not is_resource("renderer.resources.consumables", f"consumable_{idx}.png"):
                continue
            prev = by_aid_idx.get(aid)
            if prev and prev[1] != idx:
                pair = (aid, prev[0], spid)
                break
            by_aid_idx.setdefault(aid, (spid, idx))
        if pair:
            break
    assert pair is not None
    aid, spid_a, spid_b = pair

    p1 = _make_player(pid=1, ship_id=1001, ship_params_id=spid_a, relation=0)
    p2 = _make_player(pid=2, ship_id=1002, ship_params_id=spid_b, relation=1)
    rd = ReplayData(
        game_arena_id=1,
        game_version="15_9_0",
        game_map="16_OC_bees_to_honey",
        game_battle_type=1249,
        game_win_score=1000,
        game_result=BattleResult(0, 0),
        owner_avatar_id=1,
        owner_vehicle_id=1001,
        owner_id=1,
        player_info={1: p1, 2: p2},
        building_info={},
        events={
            0: _make_events(
                evt_vehicle={
                    1001: _make_vehicle(1, 1001, relation=0),
                    1002: _make_vehicle(2, 1002, relation=1),
                }
            )
        },
    )
    renderer = Renderer(rd, logs=True)
    renderer._configure_resolution((1920, 1200))
    renderer._load_map()
    renderer.conman.active_consumables = {1001: {aid: 10}, 1002: {aid: 10}}

    ship_layer = LayerShipBase(renderer)
    h1 = Image.new("RGBA", (141, 141))
    h2 = Image.new("RGBA", (141, 141))
    ship_layer._ship_consumable(h1, 1001, spid_a)
    ship_layer._ship_consumable(h2, 1002, spid_b)

    assert len(ship_layer._consumable_cache) == 2
    assert (spid_a, (aid,)) in ship_layer._consumable_cache
    assert (spid_b, (aid,)) in ship_layer._consumable_cache
    assert np.any(np.array(h1) != np.array(h2))

    # Holder LRU cap <= 512
    for i in range(600):
        v = _make_vehicle(player_id=1, vehicle_id=1001, health=1000 + i)
        ship_layer._get_ship_holder(v, p1, "#4ce8aa", True, i % 5, renderer.px(20))
    assert len(ship_layer._holder_cache) <= 512

    # Overlap resolver shifts second overlapping label
    placed = [(100, 100, 180, 125)]
    nx, ny = ship_layer._resolve_label_position(
        105, 102, 80, 25, 1073, 1073, placed, step=17
    )
    assert ny != 102


def test_smoke_dashed_contour_and_torpedo_acoustic_ring():
    resman = ResourceManager("15_9_0")
    ships = resman.load_json("ships.json")
    spid = next(k for k in ships if isinstance(k, int))
    p1 = _make_player(pid=1, ship_id=1001, ship_params_id=spid, relation=0)
    rd = ReplayData(
        game_arena_id=1,
        game_version="15_9_0",
        game_map="16_OC_bees_to_honey",
        game_battle_type=1249,
        game_win_score=1000,
        game_result=BattleResult(0, 0),
        owner_avatar_id=1,
        owner_vehicle_id=1001,
        owner_id=1,
        player_info={1: p1},
        building_info={},
        events={
            0: _make_events(
                evt_smoke={1: Smoke(entity_id=1, radius=15.0, points=[(0, 0), (10, 0)])},
                evt_torpedo={
                    10: Torpedo(owner_id=1001, params_id=1, origin=(-80, 0), yaw=0.0, speed_bw=1.0, shot_id=10),
                    20: Torpedo(owner_id=1001, params_id=1, origin=(80, 0), yaw=0.0, speed_bw=1.0, shot_id=20),
                },
                evt_acoustic_torpedo={
                    20: AcousticTorpedo(owner_id=1001, shot_id=20, x=80, y=0, yaw=0.0, yaw_speed=0.1)
                },
            )
        },
    )
    renderer = Renderer(rd, logs=True)
    renderer._configure_resolution((1920, 1200))
    renderer._load_map()

    smoke_canvas = Image.new("RGBA", renderer.minimap_fg.size)
    LayerSmokeBase(renderer).draw(0, smoke_canvas)
    center_alpha = smoke_canvas.getpixel((smoke_canvas.width // 2, smoke_canvas.height // 2))[3]
    # Soft mist fill (~34 alpha), NOT the old heavy opaque-ish 64 white block
    assert 20 <= center_alpha <= 45

    torp_canvas = Image.new("RGBA", renderer.minimap_fg.size)
    LayerTorpedoBase(renderer).draw(0, torp_canvas)
    nx, ny = renderer.get_scaled((-80, 0))
    ax, ay = renderer.get_scaled((80, 0))
    normal_patch = np.array(torp_canvas)[ny - 10 : ny + 11, nx - 10 : nx + 11]
    acoustic_patch = np.array(torp_canvas)[ay - 10 : ay + 11, ax - 10 : ax + 11]
    assert np.count_nonzero(acoustic_patch[:, :, 3]) > np.count_nonzero(normal_patch[:, :, 3])


def test_markers_single_ellipse_and_int_str_ability_keys():
    resman = ResourceManager("15_9_0")
    ships = resman.load_json("ships.json")
    abilities = resman.load_json("abilities.json")
    hydro_spid = next(
        k
        for k, v in abilities.items()
        if isinstance(k, int)
        and k in ships
        and 10 in v.get("id_to_index", {})
        and f"{v['id_to_index'][10]}.{v['id_to_subtype'][10]}" in v
        and "distShip" in v[f"{v['id_to_index'][10]}.{v['id_to_subtype'][10]}"]
    )
    p1 = _make_player(pid=1, ship_id=1001, ship_params_id=hydro_spid, relation=0)
    rd = ReplayData(
        game_arena_id=1,
        game_version="15_9_0",
        game_map="16_OC_bees_to_honey",
        game_battle_type=1249,
        game_win_score=1000,
        game_result=BattleResult(0, 0),
        owner_avatar_id=1,
        owner_vehicle_id=1001,
        owner_id=1,
        player_info={1: p1},
        building_info={},
        events={0: _make_events(evt_vehicle={1001: _make_vehicle(1, 1001, relation=0)})},
    )
    renderer = Renderer(rd, logs=True)
    renderer._configure_resolution((1920, 1200))
    renderer._load_map()
    renderer.conman.active_consumables = {1001: {10: 50}}
    canvas = Image.new("RGBA", renderer.minimap_fg.size)
    LayerMarkersBase(renderer).draw(0, canvas)
    assert canvas.getbbox() is not None


def test_timer_score_fleet_bar_chat_and_capture_isolation():
    resman = ResourceManager("15_9_0")
    ships = resman.load_json("ships.json")
    spid = next(k for k in ships if isinstance(k, int))
    p_ally = _make_player(pid=1, ship_id=1001, ship_params_id=spid, relation=-1, name="Ally1")
    p_enemy = _make_player(pid=2, ship_id=1002, ship_params_id=spid, relation=1, name="Enemy1")
    rd = ReplayData(
        game_arena_id=1,
        game_version="15_9_0",
        game_map="16_OC_bees_to_honey",
        game_battle_type=1249,
        game_win_score=1000,
        game_result=BattleResult(0, 0),
        owner_avatar_id=1,
        owner_vehicle_id=1001,
        owner_id=1,
        player_info={1: p_ally, 2: p_enemy},
        building_info={},
        events={
            65: _make_events(
                time_left=1135,
                evt_vehicle={
                    1001: _make_vehicle(1, 1001, is_alive=True, relation=-1),
                    1002: _make_vehicle(2, 1002, is_alive=True, relation=1),
                },
                evt_control={
                    0: ControlPoint((-100, 0), 50, -1, -1, 1, 0.0, False, False, 0, 0.0, -1, True),
                    1: ControlPoint((100, 0), 50, -1, -1, 1, 0.0, False, False, 0, 0.0, -1, True),
                },
                evt_chat=[Message(1, "battle_prebattle", "Division callout!")],
            ),
            70: _make_events(
                time_left=1130,
                evt_vehicle={
                    1001: _make_vehicle(1, 1001, is_alive=True, relation=-1),
                    1002: _make_vehicle(2, 1002, is_alive=False, relation=1),
                },
            ),
        },
    )
    renderer = Renderer(rd, logs=True)
    renderer._configure_resolution((1920, 1200))
    renderer._load_map()
    renderer._draw_header(renderer.minimap_bg)

    # Timer stays strictly positive inside top bar
    timer_img = Image.new("RGBA", renderer.output_size)
    LayerTimerBase(renderer).draw(65, timer_img)
    tb = timer_img.getbbox()
    assert tb is not None and tb[1] >= 4

    # Score fleet strip updates when enemy sinks
    score_layer = LayerScoreBase(renderer)
    s1 = Image.new("RGBA", renderer.output_size)
    s2 = Image.new("RGBA", renderer.output_size)
    score_layer.draw(65, s1)
    score_layer.draw(70, s2)
    assert np.any(np.array(s1) != np.array(s2))

    # Chat displays [01:05] timestamp & gold color for battle_prebattle
    chat_layer = LayerChatBase(renderer)
    c_img = Image.new("RGBA", renderer.output_size)
    chat_layer.draw(65, c_img)
    arr = np.array(c_img)
    gold_rgb = np.array([255, 210, 76])
    assert np.any(np.all(arr[:, :, :3] == gold_rgb, axis=-1))

    # Capture points A & B do not overwrite cached cap_neutral image
    cap_img = Image.new("RGBA", renderer.minimap_fg.size)
    LayerCaptureBase(renderer).draw(65, cap_img)
    cx0, cy0 = renderer.get_scaled((-100, 0))
    cx1, cy1 = renderer.get_scaled((100, 0))
    patch_a = np.array(cap_img)[cy0 - 12 : cy0 + 12, cx0 - 12 : cx0 + 12]
    patch_b = np.array(cap_img)[cy1 - 12 : cy1 + 12, cx1 - 12 : cx1 + 12]
    assert np.any(patch_a != patch_b)


def test_versioned_14_11_0_layers_scale_to_1920x1200():
    resman = ResourceManager("14_11_0")
    ships = resman.load_json("ships.json")
    spid = next(k for k in ships if isinstance(k, int))
    p1 = _make_player(pid=1, ship_id=1001, ship_params_id=spid, relation=-1)
    rd = ReplayData(
        game_arena_id=1,
        game_version="14_11_0",
        game_map="46_Estuary",
        game_battle_type=1029,
        game_win_score=1000,
        game_result=BattleResult(0, 0),
        owner_avatar_id=1,
        owner_vehicle_id=1001,
        owner_id=1,
        player_info={1: p1},
        building_info={},
        events={
            0: _make_events(
                evt_vehicle={1001: _make_vehicle(1, 1001, health=15000)},
                evt_ribbon={1: {15: 5}},
                evt_achievement={1: {}},
            )
        },
    )
    renderer = Renderer(rd, logs=True)
    renderer._configure_resolution((1920, 1200))
    renderer._load_map()

    health_cls = renderer._load_layer("LayerHealth")
    ribbon_cls = renderer._load_layer("LayerRibbon")

    bg = Image.new("RGBA", renderer.output_size)
    health_cls(renderer).draw(0, bg)
    ribbon_cls(renderer).draw(0, bg)
    bbox = bg.getbbox()
    assert bbox is not None
    # Both health bar & ribbons must sit in the right HUD (>= 800 * scale = 1129), never left ocean
    assert bbox[0] >= renderer.px(800)


def test_dual_mode_header_renders_team_tags():
    resman = ResourceManager("15_9_0")
    ships = resman.load_json("ships.json")
    spid = next(k for k in ships if isinstance(k, int))
    p1 = _make_player(pid=1, ship_id=1001, ship_params_id=spid, relation=-1)
    p2 = _make_player(pid=2, ship_id=1002, ship_params_id=spid, relation=1)
    rd = ReplayData(
        game_arena_id=1,
        game_version="15_9_0",
        game_map="16_OC_bees_to_honey",
        game_battle_type=1249,
        game_win_score=1000,
        game_result=BattleResult(0, 0),
        owner_avatar_id=1,
        owner_vehicle_id=1001,
        owner_id=1,
        player_info={1: p1, 2: p2},
        building_info={},
        events={0: _make_events()},
    )
    dual = RenderDual(rd, rd, green_tag="CLAN_A", red_tag="CLAN_B")
    dual.logs = True
    dual._configure_resolution((1920, 1200))
    dual._load_map()
    before = np.array(dual.minimap_bg).copy()
    dual._draw_header(dual.minimap_bg)
    assert np.any(np.array(dual.minimap_bg) != before)


@patch("renderer.render.get_ffmpeg_exe", return_value="ffmpeg")
@patch("renderer.render.subprocess.run")
def test_probe_video_encoder_forces_yuv420p_for_cpu_profiles(run, _ffmpeg):
    from renderer.render import _probe_video_encoder

    _probe_video_encoder.cache_clear()
    run.return_value.returncode = 0

    assert _probe_video_encoder("libx264", "h264", (1920, 1200))
    command = run.call_args.args[0]
    assert "-pix_fmt" in command
    assert "yuv420p" in command


def test_ship_edge_labels_remain_upright_and_flip_above_bottom_border():
    resman = ResourceManager("15_9_0")
    ships = resman.load_json("ships.json")
    spid = next(k for k in ships if isinstance(k, int))
    p_left = _make_player(pid=1, ship_id=1001, ship_params_id=spid, relation=-1)
    p_bottom = _make_player(pid=2, ship_id=1002, ship_params_id=spid, relation=0)
    rd = ReplayData(
        game_arena_id=1,
        game_version="15_9_0",
        game_map="16_OC_bees_to_honey",
        game_battle_type=1249,
        game_win_score=1000,
        game_result=BattleResult(0, 0),
        owner_avatar_id=1,
        owner_vehicle_id=1001,
        owner_id=1,
        player_info={1: p_left, 2: p_bottom},
        building_info={},
        events={
            0: _make_events(
                evt_vehicle={
                    # Left border and bottom border in BigWorld space
                    1001: _make_vehicle(1, 1001, x=-780, y=0, relation=-1),
                    1002: _make_vehicle(2, 1002, x=0, y=-780, relation=0),
                }
            )
        },
    )
    renderer = Renderer(rd, logs=True)
    renderer._configure_resolution((1920, 1200))
    renderer._load_map()

    ship_layer = LayerShipBase(renderer)
    canvas = Image.new("RGBA", renderer.minimap_fg.size)
    ship_layer.draw(0, canvas)

    # Every cached holder drawn by LayerShipBase.draw must have angle=0 (upright horizontal)
    assert all(key[4] == 0 for key in ship_layer._holder_cache.keys())
    _, by = renderer.get_scaled((0, -780))
    # Pixels above the bottom-border ship must contain the flipped upright label/HP bar
    upper_strip = np.array(canvas)[max(0, by - 65) : max(1, by - 14), :, 3]
    assert np.count_nonzero(upper_strip) > 0
