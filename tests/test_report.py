import logging
import os
import pytest
from PIL import Image

from replay_parser import ReplayParser
from replay_unpack.core.entity import Entity
from renderer import report as report_mod
from renderer.report import (
    _select_font_path_for_text,
    generate_battle_report,
    parse_replay_report,
    render_battle_report_card,
)

REPLAY_DIR = os.path.join(os.path.dirname(__file__), "..", "replays")
DEFAULT_REPLAY_PATH = os.path.join(REPLAY_DIR, "1510.wowsreplay")
CUSTOM_REPLAY_PATH = r"F:\[工具]\minimap_renderer\20260907_123622_PWSB010-Thor_58_RidgeNew.wowsreplay"
REPLAY_PATH = CUSTOM_REPLAY_PATH if os.path.exists(CUSTOM_REPLAY_PATH) else DEFAULT_REPLAY_PATH


def test_parse_replay_report():
    if not os.path.exists(REPLAY_PATH):
        pytest.skip("Test replay file not found")
    data = parse_replay_report(REPLAY_PATH)
    assert data["has_post_battle"] is True
    assert "owner" in data
    assert data["owner"]["name"] != ""
    assert len(data["players"]) > 0
    assert "tactical" in data
    assert len(data["tactical"]["hp_timeline"]) > 0


def test_generate_battle_report(tmp_path):
    if not os.path.exists(REPLAY_PATH):
        pytest.skip("Test replay file not found")
    out_file = str(tmp_path / "test_report.png")
    result = generate_battle_report(REPLAY_PATH, out_file)
    assert os.path.exists(result)
    assert os.path.getsize(result) > 100000


def test_single_pass_replay_info_reuse_and_no_logging_side_effect(tmp_path, monkeypatch):
    rpath = os.path.join(REPLAY_DIR, "1590.wowsreplay")
    if not os.path.exists(rpath):
        pytest.skip("1590.wowsreplay not found")

    root_logger = logging.getLogger()
    orig_level = root_logger.level
    try:
        root_logger.setLevel(logging.WARNING)
        with open(rpath, "rb") as fp:
            info = ReplayParser(fp).get_info()
        # ReplayParser must not clobber global root logger level
        assert root_logger.level == logging.WARNING
    finally:
        root_logger.setLevel(orig_level)

    assert info["post_battle"] is not None
    assert "playersPublicInfo" in info["post_battle"]
    assert len(info["hidden"]["quick_commands"]) > 0

    def _forbid(*args, **kwargs):
        raise AssertionError("Replay was unexpectedly re-parsed instead of reusing replay_info!")

    monkeypatch.setattr(report_mod, "ReplayParser", _forbid)
    monkeypatch.setattr(report_mod, "extract_post_battle_results", _forbid)

    data = parse_replay_report(rpath, replay_info=info)
    assert data["has_post_battle"] is True
    assert data["owner"]["total_dmg"] == pytest.approx(9388.0, abs=2.0)

    out_png = str(tmp_path / "reused_1590.png")
    res = generate_battle_report(rpath, out_png, replay_info=info)
    assert os.path.exists(res)
    with Image.open(res) as im:
        assert im.width == 2400
        assert im.height > 1800


def test_quick_commands_extraction_and_entity_nested_sub():
    # Verify Entity.subscribe_nested_property_change checks prop_hash (entity_name + prop_path)
    Entity.clear_subscriptions()
    Entity.subscribe_nested_property_change("TestEntityA", "state.hp", lambda *a: None)
    Entity.subscribe_nested_property_change("TestEntityA", "state.hp", lambda *a: None)
    Entity.subscribe_nested_property_change("TestEntityB", "state.hp", lambda *a: None)
    assert len(Entity._nested_properties_subscription["TestEntityA_state.hp"]) == 2
    assert len(Entity._nested_properties_subscription["TestEntityB_state.hp"]) == 1
    Entity.clear_subscriptions()

    r1510 = os.path.join(REPLAY_DIR, "1510.wowsreplay")
    if not os.path.exists(r1510):
        pytest.skip("1510.wowsreplay not found")
    data = parse_replay_report(r1510)
    quick_msgs = [c for c in data["chat"] if c.get("is_quick_cmd")]
    assert len(quick_msgs) >= 10
    texts = [c["message"] for c in quick_msgs]
    assert any("注意扇区" in t for t in texts)
    assert any("优先攻击目标：[" in t for t in texts)
    assert any("正在使用对海搜索" in t or "正在使用监视雷达" in t for t in texts)


def test_operation_mode_multi_ship_layout(tmp_path):
    r_op = os.path.join(REPLAY_DIR, "1410_operation.wowsreplay")
    if not os.path.exists(r_op):
        pytest.skip("1410_operation.wowsreplay not found")

    data = parse_replay_report(r_op)
    allies = [p for p in data["players"] if p["team_id"] == data["owner"]["team_id"]]
    enemies = [p for p in data["players"] if p["team_id"] != data["owner"]["team_id"]]
    assert len(allies) == 9
    assert len(enemies) == 74
    assert data["has_post_battle"] is True
    assert data["owner"]["total_dmg"] > 900000
    assert data["owner"]["planes_killed"] == 9
    assert len(data["tactical"]["hp_timeline"]) > 100

    out_png = str(tmp_path / "op_1410.png")
    render_battle_report_card(data, out_png)
    assert os.path.exists(out_png)
    with Image.open(out_png) as im:
        assert im.width == 2400
        assert im.height > 5000  # Dynamically expanded for 74 enemy rows + tactical panels


def test_multilingual_cjk_and_latin_extended_fonts(tmp_path):
    assert _select_font_path_for_text("藤シア進").endswith("warhelios_bold_jp.ttf")
    assert _select_font_path_for_text("다만. 모든").endswith("warhelios_bold_ko.ttf")
    assert _select_font_path_for_text("战斗胜利").endswith("warhelios_bold_zh.ttf")
    assert _select_font_path_for_text("VIII BŁYSKAWICA '44").endswith("warhelios_bold.ttf")

    r_lang = os.path.join(REPLAY_DIR, "languages.wowsreplay")
    if not os.path.exists(r_lang):
        pytest.skip("languages.wowsreplay not found")
    data = parse_replay_report(r_lang)
    msgs = [c["message"] for c in data["chat"]]
    for expected in ("TESTING LANGUAGES", "望帯宮祝", "藤シア進", "다만. 모든", "русский язык", "ภาษาไทย"):
        assert expected in msgs

    out_png = str(tmp_path / "lang.png")
    render_battle_report_card(data, out_png)
    assert os.path.exists(out_png)
    with Image.open(out_png) as im:
        assert im.width == 2400


def test_13_x_post_battle_stat_shift_consistency():
    r137 = os.path.join(REPLAY_DIR, "137.wowsreplay")
    if not os.path.exists(r137):
        pytest.skip("137.wowsreplay not found")
    data = parse_replay_report(r137)
    assert data["has_post_battle"] is True
    owner_row = next(p for p in data["players"] if p["is_owner"])
    assert data["owner"]["total_dmg"] == pytest.approx(212361.0, abs=2.0)
    assert owner_row["damage_dealt"] == pytest.approx(data["owner"]["total_dmg"], abs=1.0)
    assert owner_row["spotting_damage"] > 60000
    assert sum(p["damage_dealt"] for p in data["players"]) > 1000000
