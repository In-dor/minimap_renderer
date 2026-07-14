from renderer.data import Events, Plane, Vehicle
from renderer.temporal import interpolate_events, native_timeline


def vehicle(vehicle_id=1, x=0, y=0, yaw=0, is_visible=True):
    return Vehicle(
        player_id=vehicle_id,
        vehicle_id=vehicle_id,
        health=100,
        is_alive=True,
        x=x,
        y=y,
        yaw=yaw,
        relation=0,
        is_visible=is_visible,
        not_in_range=False,
        visibility_flag=0,
        burn_flags=0,
        consumables_state={},
    )


def event(vehicle_value, plane_value=None, **overrides):
    values = dict(
        time_left=100,
        evt_vehicle={vehicle_value.vehicle_id: vehicle_value},
        evt_building={},
        evt_plane={} if plane_value is None else {plane_value.plane_id: plane_value},
        evt_ward={},
        evt_smoke={},
        evt_shot=["shot"],
        evt_torpedo={1: "torpedo"},
        evt_hits=[1],
        evt_consumable={1: ["consumable"]},
        evt_control={},
        evt_score={},
        evt_damage_maps={},
        evt_frag=["frag"],
        evt_ribbon={},
        evt_achievement={},
        evt_times_to_win=None,
        evt_chat=["chat"],
        evt_acoustic_torpedo={1: "acoustic"},
    )
    values.update(overrides)
    return Events(**values)


def test_native_timeline_emits_output_rate_samples():
    samples = list(native_timeline([10, 11, 12], fps=60, speed=15))

    assert len(samples) == 8
    assert samples[:4] == [
        (0, 10, 11, 0.0, True),
        (1, 10, 11, 0.25, False),
        (2, 10, 11, 0.5, False),
        (3, 10, 11, 0.75, False),
    ]
    assert samples[4] == (4, 11, 12, 0.0, True)


def test_interpolates_vehicle_position_and_shortest_yaw():
    current = event(vehicle(x=10, y=20, yaw=170))
    following = event(vehicle(x=30, y=60, yaw=-170))

    result = interpolate_events(current, following, 0.5, True)

    sampled = result.evt_vehicle[1]
    assert sampled.x == 20
    assert sampled.y == 40
    assert sampled.yaw == 180


def test_does_not_interpolate_visibility_transition():
    current = event(vehicle(x=10, is_visible=True))
    following = event(vehicle(x=30, is_visible=False))

    result = interpolate_events(current, following, 0.75, True)

    assert result.evt_vehicle[1] == current.evt_vehicle[1]


def test_interpolates_matching_plane_and_clears_repeated_transients():
    current_plane = Plane(1, 1, 2, 3, 0, 1, 0, (10, 20))
    following_plane = current_plane._replace(position=(30, 60))

    result = interpolate_events(
        event(vehicle(), current_plane),
        event(vehicle(), following_plane),
        0.5,
        include_transients=False,
    )

    assert result.evt_plane[1].position == (20, 40)
    assert result.evt_shot == []
    assert result.evt_torpedo == {}
    assert result.evt_frag == []
    assert result.evt_chat == []
