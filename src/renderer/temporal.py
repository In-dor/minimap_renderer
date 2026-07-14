from math import ceil
from typing import Iterator

from renderer.data import Events, Plane, Vehicle


TRANSIENT_FIELDS = {
    "evt_shot": [],
    "evt_torpedo": {},
    "evt_hits": [],
    "evt_consumable": {},
    "evt_frag": [],
    "evt_chat": [],
    "evt_acoustic_torpedo": {},
}


def native_timeline(
    event_keys: list[int], fps: int, speed: float
) -> Iterator[tuple[int, int, int, float, bool]]:
    """Yield output frame, adjacent event keys, interpolation and interval edge."""
    interval_count = max(0, len(event_keys) - 1)
    frame_count = ceil(interval_count * fps / speed)
    previous_interval = -1

    for frame_index in range(frame_count):
        source_position = frame_index * speed / fps
        interval = min(int(source_position), interval_count - 1)
        alpha = source_position - interval
        first_in_interval = interval != previous_interval
        previous_interval = interval
        yield (
            frame_index,
            event_keys[interval],
            event_keys[interval + 1],
            alpha,
            first_in_interval,
        )


def _lerp(a: float, b: float, alpha: float) -> float:
    return a + (b - a) * alpha


def _interpolate_vehicle(a: Vehicle, b: Vehicle, alpha: float) -> Vehicle:
    stable = (
        a.player_id == b.player_id
        and a.vehicle_id == b.vehicle_id
        and a.is_alive == b.is_alive
        and a.is_visible == b.is_visible
        and a.not_in_range == b.not_in_range
    )
    if not stable:
        return a

    yaw_delta = (b.yaw - a.yaw + 180) % 360 - 180
    return a._replace(
        x=_lerp(a.x, b.x, alpha),
        y=_lerp(a.y, b.y, alpha),
        yaw=a.yaw + yaw_delta * alpha,
    )


def _interpolate_plane(a: Plane, b: Plane, alpha: float) -> Plane:
    if a[:-1] != b[:-1]:
        return a
    return a._replace(
        position=(
            _lerp(a.position[0], b.position[0], alpha),
            _lerp(a.position[1], b.position[1], alpha),
        )
    )


def interpolate_events(
    current: Events,
    following: Events,
    alpha: float,
    include_transients: bool,
) -> Events:
    vehicles = {
        vehicle_id: _interpolate_vehicle(
            vehicle, following.evt_vehicle[vehicle_id], alpha
        )
        if vehicle_id in following.evt_vehicle
        else vehicle
        for vehicle_id, vehicle in current.evt_vehicle.items()
    }
    planes = {
        plane_id: _interpolate_plane(plane, following.evt_plane[plane_id], alpha)
        if plane_id in following.evt_plane
        else plane
        for plane_id, plane in current.evt_plane.items()
    }
    values = {"evt_vehicle": vehicles, "evt_plane": planes, "last_frame": False}
    if not include_transients:
        values.update(TRANSIENT_FIELDS)
    return current._replace(**values)
