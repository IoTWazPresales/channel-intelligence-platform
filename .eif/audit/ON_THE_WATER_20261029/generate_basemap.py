"""Regenerate basemap.svg and the lane / port coordinates for the "On the water" map.

Reference tool, not product code. It needs ``global-land-mask`` (pip, dev only, in a
throwaway venv); the product must not take that dependency. Run it only when a
tenant's map extent changes, and commit the regenerated SVG path data.

Projection: equirectangular. Extent and output size below are the default (ASUS ZA)
values; the product reads them from tenant config.
"""

from __future__ import annotations

import json
import math
import sys

EXTENT = {"lon_min": -22.0, "lon_max": 136.0, "lat_min": -44.0, "lat_max": 58.0}
WIDTH = 1000  # height follows the extent: round(WIDTH * 102 / 158) = 646
DOT_STEP_DEG = 1.75

# Default lanes (lon, lat waypoints). Tenant config owns these in the product.
LANES = {
    "asia_durban": [
        (121.5, 31.2), (122.5, 27), (119.5, 22.5), (114.5, 14), (109, 6), (104.3, 1.2),
        (98, 5.5), (88, 5.5), (78, 3), (62, -8), (48, -21), (37, -28.5), (31.0, -29.9),
    ],
    "south_china_feeder": [(114.1, 22.4), (114.5, 14)],
    "europe_durban": [
        (4.3, 51.95), (-3, 48.5), (-11, 42), (-16, 30), (-19.5, 18), (-16, 6), (-5, -1),
        (5, -12), (11, -26), (17.5, -35.3), (24, -35.6), (31.0, -29.9),
    ],
    "durban_city_deep_rail": [(31.0, -29.9), (28.1, -26.2)],
    "chongqing_truck": [(106.5, 29.6), (114.1, 22.4)],
}
# Shipping Method hub code -> lane. Unknown codes use asia_durban, labelled "route assumed".
HUB_LANE = {"sha": "asia_durban", "szx": "asia_durban", "ckg": "asia_durban", "c": "asia_durban", "nl": "europe_durban"}
PORTS = {
    "SHANGHAI": (121.5, 31.2), "SHENZHEN": (114.1, 22.4), "CHONGQING": (106.5, 29.6),
    "SINGAPORE": (103.8, 1.3), "ROTTERDAM": (4.3, 51.95), "PORT LOUIS": (57.5, -20.16),
    "CITY DEEP": (28.1, -26.2), "DURBAN": (31.0, -29.9),
}


def height() -> int:
    e = EXTENT
    return round(WIDTH * (e["lat_max"] - e["lat_min"]) / (e["lon_max"] - e["lon_min"]))


def project(lon: float, lat: float) -> tuple[float, float]:
    e = EXTENT
    x = (lon - e["lon_min"]) / (e["lon_max"] - e["lon_min"]) * WIDTH
    y = (e["lat_max"] - lat) / (e["lat_max"] - e["lat_min"]) * height()
    return x, y


def point_along(lane: list[tuple[float, float]], fraction: float) -> tuple[float, float]:
    """Point at ``fraction`` (0..1) of the lane's length, in lon/lat."""
    f = max(0.0, min(1.0, fraction))
    seg = [math.dist(lane[i], lane[i + 1]) for i in range(len(lane) - 1)]
    t = f * sum(seg)
    for i, length in enumerate(seg):
        if t <= length:
            a, b = lane[i], lane[i + 1]
            u = t / length if length else 0.0
            return a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u
        t -= length
    return lane[-1]


def dots_path() -> str:
    from global_land_mask import globe  # dev-only dependency

    e = EXTENT
    out = []
    lat = e["lat_max"] - DOT_STEP_DEG / 2
    while lat > e["lat_min"]:
        lon = e["lon_min"] + DOT_STEP_DEG / 2
        while lon < e["lon_max"]:
            if globe.is_land(lat, lon):
                x, y = project(lon, lat)
                out.append(f"M{x:.0f} {y:.0f}h0")
            lon += DOT_STEP_DEG
        lat -= DOT_STEP_DEG
    return "".join(out)


def lane_path(points: list[tuple[float, float]]) -> str:
    return " ".join(("M" if i == 0 else "L") + "%.1f %.1f" % project(*p) for i, p in enumerate(points))


def main() -> None:
    if "--coords" in sys.argv:
        json.dump(
            {
                "extent": EXTENT,
                "size": [WIDTH, height()],
                "lanes": {k: lane_path(v) for k, v in LANES.items()},
                "ports_pct": {k: [round(project(*v)[0] / WIDTH * 100, 2), round(project(*v)[1] / height() * 100, 2)] for k, v in PORTS.items()},
            },
            sys.stdout,
            indent=1,
        )
        return
    print(dots_path())


if __name__ == "__main__":
    main()
