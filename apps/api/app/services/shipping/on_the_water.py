"""On the water: vessels, lanes, positions and the figures around them (SPEC.md, ON_THE_WATER_20261029).

Pure functions over ``WaterLine`` rows so every rule is testable without a database; the endpoint
(``app/api/v1/endpoints/shipping.py``) loads the rows with the same page scope as the KPI tiles.

Rules (SPEC "Data rules"):

- As of = today. Sea only on the map: ``ship_way`` contains SEA. Air and express in transit are counted in the
  At-sea tile's sub-line, not drawn.
- At sea: line state shipped, on-board date on or before as-of, no arrival date, no POD.
- Overdue arrival: at sea with a port ETA before as-of; drawn at the discharge port, state "overdue".
- Arrived, not delivered: arrival date set, POD empty, split by discharge port.
- Booked, not on board: on-board date after as-of, state shipped or open.
- Value per currency; never summed across currencies. Unit-price-scale-suspect amounts are left out of value.
- Vessel key: vessel name and voyage when present, else (on-board date, port ETA, discharge port, lane), "inferred".
- Position: the share of on-board to port ETA elapsed, along the lane polyline (equirectangular projection).
- Slip per line: current port ETA minus the first port ETA a report carried. Vessel slip is the largest line slip.
"""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any

# ------------------------------------------------------------------------------------------ config
# Defaults for the ASUS ZA tenant (the same numbers as generate_basemap.py in the audit folder). A tenant overrides
# ``hub_lane``, ``stale_report_days`` and ``needs_look_days`` (commercial_tenant_profile key ``on_the_water``).
EXTENT = {"lon_min": -22.0, "lon_max": 136.0, "lat_min": -44.0, "lat_max": 58.0}
SIZE = (1000, 646)

LANES: dict[str, list[tuple[float, float]]] = {
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
SEA_LANES = ("asia_durban", "europe_durban")
DEFAULT_LANE = "asia_durban"
# Shipping Method hub code -> sea lane. An unknown hub uses the default lane, labelled "route assumed".
HUB_LANE = {"sha": "asia_durban", "szx": "asia_durban", "ckg": "asia_durban", "c": "asia_durban", "nl": "europe_durban"}
HUB_LABEL = {"sha": "Shanghai", "szx": "Shenzhen", "ckg": "Chongqing", "c": "China", "nl": "Rotterdam"}

PORTS: dict[str, tuple[float, float]] = {
    "SHANGHAI": (121.5, 31.2), "SHENZHEN": (114.1, 22.4), "CHONGQING": (106.5, 29.6),
    "SINGAPORE": (103.8, 1.3), "ROTTERDAM": (4.3, 51.95), "PORT LOUIS": (57.5, -20.16),
    "CITY DEEP": (28.1, -26.2), "DURBAN": (31.0, -29.9),
}
# UN/LOCODE -> label, and where the cargo is drawn on the sea map (City Deep is a rail leg from Durban).
PORT_LABEL = {"ZADUR": "Durban", "ZAJNB": "City Deep", "MUPLU": "Port Louis", "ZACPT": "Cape Town"}
PORT_DRAW = {"ZAJNB": "DURBAN", "ZADUR": "DURBAN", "MUPLU": "PORT LOUIS"}
# Lane waypoints kept before turning for a port that is not Durban (index is exclusive end).
PORT_LANE_CUT: dict[tuple[str, str], int | None] = {("MUPLU", "asia_durban"): 10, ("MUPLU", "europe_durban"): None}

DEFAULT_STALE_REPORT_DAYS = 7
DEFAULT_NEEDS_LOOK_DAYS = 7
CLUSTER_RADIUS_PCT = 4.0


@dataclass
class WaterConfig:
    hub_lane: dict[str, str] = field(default_factory=lambda: dict(HUB_LANE))
    stale_report_days: int = DEFAULT_STALE_REPORT_DAYS
    needs_look_days: int = DEFAULT_NEEDS_LOOK_DAYS


def config_from_overrides(raw: Any) -> WaterConfig:
    """Tenant ``on_the_water`` override over the defaults; unusable parts are ignored."""
    cfg = WaterConfig()
    if not isinstance(raw, dict):
        return cfg
    hub = raw.get("hub_lane")
    if isinstance(hub, dict):
        for code, lane in hub.items():
            if isinstance(code, str) and lane in SEA_LANES:
                cfg.hub_lane[code.strip().lower()] = lane
    for key, attr in (("stale_report_days", "stale_report_days"), ("needs_look_days", "needs_look_days")):
        v = raw.get(key)
        if isinstance(v, int) and not isinstance(v, bool) and 0 < v <= 365:
            setattr(cfg, attr, v)
    return cfg


# ------------------------------------------------------------------------------------------ geometry
def project_pct(lon: float, lat: float) -> tuple[float, float]:
    e = EXTENT
    return (
        (lon - e["lon_min"]) / (e["lon_max"] - e["lon_min"]) * 100.0,
        (e["lat_max"] - lat) / (e["lat_max"] - e["lat_min"]) * 100.0,
    )


def project_px(lon: float, lat: float) -> tuple[float, float]:
    x, y = project_pct(lon, lat)
    return x / 100.0 * SIZE[0], y / 100.0 * SIZE[1]


def point_along(lane: list[tuple[float, float]], fraction: float) -> tuple[float, float]:
    """Point at ``fraction`` (0..1) of the polyline's length, in lon/lat."""
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


def route_to_port(lane_id: str, deliver_port: str | None) -> tuple[list[tuple[float, float]], bool]:
    """(polyline, port_known). A port that is not Durban turns off the lane before it."""
    lane = LANES[lane_id]
    code = (deliver_port or "").strip().upper()
    draw = PORT_DRAW.get(code)
    if draw is None:
        return lane, False
    if draw == "DURBAN":
        return lane, True
    cut = PORT_LANE_CUT.get((code, lane_id), None)
    base = lane if cut is None else lane[:cut]
    return [*base, PORTS[draw]], True


def lane_paths() -> list[dict[str, str]]:
    out = []
    for lane_id, pts in LANES.items():
        d = " ".join(("M" if i == 0 else "L") + "%.1f %.1f" % project_px(*p) for i, p in enumerate(pts))
        out.append({"id": lane_id, "kind": "sea" if lane_id in SEA_LANES else "leg", "d": d})
    return out


# Which side of its dot a port's name sits on. A port not listed here is named to the right, unless it is near the right
# edge of the map (the page then flips it). Chongqing and Shanghai sit close together: Chongqing's name goes to the left.
PORT_LABEL_SIDE: dict[str, str] = {"CHONGQING": "left", "SHANGHAI": "above"}


def port_markers() -> list[dict[str, Any]]:
    out = []
    for name, (lon, lat) in PORTS.items():
        x, y = project_pct(lon, lat)
        marker: dict[str, Any] = {"id": name, "label": name, "x": round(x, 2), "y": round(y, 2)}
        if name in PORT_LABEL_SIDE:
            marker["label_side"] = PORT_LABEL_SIDE[name]
        out.append(marker)
    return out


# ------------------------------------------------------------------------------------------ rows
@dataclass
class WaterLine:
    id: int
    quantity: float = 0.0
    amount: float | None = None
    currency: str | None = None
    amount_suspect: bool = False
    line_state: str = "shipped"
    report_type: str | None = None
    ship_way: str | None = None
    on_board: date | None = None
    port_eta: date | None = None
    port_ata: date | None = None
    pod: date | None = None
    ship_confirm: date | None = None
    exwork: date | None = None
    forwarder: str | None = None
    hub: str | None = None
    deliver_port: str | None = None
    vessel_name: str | None = None
    voyage_no: str | None = None
    delivery_no: str | None = None
    model: str | None = None
    distributor: str | None = None
    # From the report history (observations of this line across reports):
    first_eta: date | None = None
    first_eta_report: date | None = None
    first_on_board: date | None = None
    first_seen_report: date | None = None


def is_sea(line: WaterLine) -> bool:
    return "SEA" in (line.ship_way or "").upper()


def classify(line: WaterLine, as_of: date) -> str | None:
    """at_sea | arrived | booked | None."""
    if line.line_state not in ("shipped", "open_order"):
        return None
    if line.port_ata is not None and line.pod is None:
        return "arrived"
    if line.pod is not None or line.port_ata is not None:
        return None
    if line.on_board is None:
        return None
    if line.on_board > as_of:
        return "booked"
    if line.line_state == "shipped":
        return "at_sea"
    return None


def lane_for(hub: str | None, cfg: WaterConfig) -> tuple[str, bool]:
    """(lane id, route_assumed)."""
    code = (hub or "").strip().lower()
    if code in cfg.hub_lane:
        return cfg.hub_lane[code], False
    return DEFAULT_LANE, True


def _day(d: date | None) -> str | None:
    return d.isoformat() if d else None


def _ranked(units: dict[str, float], limit: int | None = None) -> list[dict[str, Any]]:
    rows = sorted(units.items(), key=lambda kv: (-kv[1], kv[0]))
    if limit is not None:
        rows = rows[:limit]
    return [{"name": k, "units": v} for k, v in rows]


def _money(lines: list[WaterLine]) -> list[dict[str, Any]]:
    """Value per currency. Unit-price-scale-suspect amounts and lines with no amount are left out."""
    by: dict[str, float] = defaultdict(float)
    for ln in lines:
        if ln.amount is None or ln.amount_suspect:
            continue
        by[(ln.currency or "").upper() or "?"] += float(ln.amount)
    return [{"currency": c, "amount": round(a, 2)} for c, a in sorted(by.items())]


def vessel_key(line: WaterLine, lane_id: str) -> str:
    if (line.vessel_name or "").strip():
        return f"n:{line.vessel_name.strip().lower()}|{(line.voyage_no or '').strip().lower()}"
    return f"i:{_day(line.on_board)}|{_day(line.port_eta)}|{(line.deliver_port or '').strip().upper()}|{lane_id}"


def vessel_id(key: str) -> str:
    return "v" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:8]


def _lane_label(hubs: set[str], deliver_port: str) -> str:
    origins = sorted({HUB_LABEL.get(h.lower(), h.upper()) for h in hubs if h}) or ["Origin not on the report"]
    port = (deliver_port or "").upper()
    dest = {"ZAJNB": "Durban → City Deep", "ZADUR": "Durban"}.get(port) or PORT_LABEL.get(port) or (port or "Durban")
    return f"{' / '.join(origins)} → {dest}"


def build_vessels(lines: list[WaterLine], *, as_of: date, report_date: date | None, cfg: WaterConfig) -> list[dict[str, Any]]:
    groups: dict[str, list[tuple[WaterLine, str, bool]]] = defaultdict(list)
    for ln in lines:
        if classify(ln, as_of) != "at_sea" or not is_sea(ln):
            continue
        lane_id, assumed = lane_for(ln.hub, cfg)
        groups[vessel_key(ln, lane_id)].append((ln, lane_id, assumed))

    vessels: list[dict[str, Any]] = []
    for key, members in groups.items():
        rows = [m[0] for m in members]
        lane_id = members[0][1]
        assumed = any(m[2] for m in members)
        deliver = next((r.deliver_port for r in rows if r.deliver_port), "") or ""
        etas = [r.port_eta for r in rows if r.port_eta]
        eta = max(etas) if etas else None
        on_board = min((r.on_board for r in rows if r.on_board), default=None)
        overdue = eta is not None and eta < as_of
        if eta and on_board and eta > on_board:
            elapsed = (as_of - on_board).days / (eta - on_board).days
        else:
            elapsed = 1.0
        elapsed = max(0.0, min(1.0, elapsed))
        route, port_known = route_to_port(lane_id, deliver)
        lon, lat = point_along(route, 1.0 if overdue else elapsed)
        x, y = project_pct(lon, lat)

        # Slip: current port ETA minus the first ETA a report carried, per line; the vessel takes the largest.
        slip_line: WaterLine | None = None
        slip = 0
        for r in rows:
            if r.first_eta and r.port_eta:
                d = (r.port_eta - r.first_eta).days
                if slip_line is None or d > slip:
                    slip, slip_line = d, r
        slip = max(slip, 0)
        first_eta = (slip_line.first_eta if slip_line else None)
        first_report = (slip_line.first_eta_report if slip_line else None)
        if first_eta is None:
            firsts = [r for r in rows if r.first_eta]
            if firsts:
                first_eta = min(r.first_eta for r in firsts if r.first_eta)
                first_report = min((r.first_eta_report for r in firsts if r.first_eta_report), default=None)

        units: dict[str, float] = defaultdict(float)
        dists: dict[str, float] = defaultdict(float)
        for r in rows:
            units[(r.model or "Model not named")] += r.quantity
            dists[(r.distributor or "Distributor not matched")] += r.quantity
        products = _ranked(units)
        forwarders = sorted({r.forwarder for r in rows if r.forwarder})
        hubs = {r.hub or "" for r in rows}
        total = float(sum(r.quantity for r in rows))
        vessels.append(
            {
                "id": vessel_id(key),
                "key": key,
                "inferred": not key.startswith("n:"),
                "vessel_name": next((r.vessel_name for r in rows if r.vessel_name), None),
                "forwarder": " + ".join(forwarders) if forwarders else "Forwarder not on the report",
                "lane_id": lane_id,
                "lane_label": _lane_label(hubs, deliver),
                "route_assumed": assumed or not port_known and bool(deliver),
                "deliver_port": deliver or None,
                "on_board": _day(on_board),
                "eta": _day(eta),
                "days_to_eta": (eta - as_of).days if eta else None,
                "overdue": overdue,
                "days_overdue": (as_of - eta).days if overdue and eta else 0,
                "pct": round(elapsed * 100.0, 1),
                "units": total,
                "lines": len(rows),
                "deliveries": len({r.delivery_no for r in rows if r.delivery_no}),
                "amount": _money(rows),
                "distributors": _ranked(dists),
                "products": products[:4],
                "more_models": max(0, len(products) - 4),
                "slip_days": slip,
                "history": {
                    "first_eta": _day(first_eta),
                    "first_report": _day(first_report),
                    "current_eta": _day(eta),
                    "latest_report": _day(report_date),
                },
                "x": round(x, 2),
                "y": round(y, 2),
            }
        )
    vessels.sort(key=lambda v: (v["eta"] or "9999", v["id"]))
    return vessels


def build_payload(
    lines: list[WaterLine],
    *,
    as_of: date,
    report_date: date | None,
    reports: dict[str, Any],
    port_conditions: list[dict[str, Any]],
    needs_look_lines: list[WaterLine],
    cfg: WaterConfig,
) -> dict[str, Any]:
    vessels = build_vessels(lines, as_of=as_of, report_date=report_date, cfg=cfg)

    at_sea_all = [ln for ln in lines if classify(ln, as_of) == "at_sea"]
    sea = [ln for ln in at_sea_all if is_sea(ln)]
    air = [ln for ln in at_sea_all if not is_sea(ln)]
    arrived = [ln for ln in lines if classify(ln, as_of) == "arrived"]
    booked = [ln for ln in lines if classify(ln, as_of) == "booked"]

    by_port: dict[str, float] = defaultdict(float)
    waiting_by_code: dict[str, float] = defaultdict(float)
    for ln in arrived:
        code = (ln.deliver_port or "").upper()
        by_port[PORT_LABEL.get(code) or code or "Port not on the report"] += ln.quantity
        waiting_by_code[code] += ln.quantity
    # Ports listed under "Port conditions": where cargo is waiting or heading, and any port with a manual figure.
    condition_by_code = {str(c["port_code"]).upper(): c for c in port_conditions}
    codes = (
        {c for c in waiting_by_code if c}
        | {str(v["deliver_port"]).upper() for v in vessels if v["deliver_port"]}
        | set(condition_by_code)
    )
    port_rows = [
        {
            "code": code,
            "label": PORT_LABEL.get(code) or code,
            "waiting_units": waiting_by_code.get(code, 0.0),
            "condition": condition_by_code.get(code),
        }
        for code in sorted(codes)
    ]

    moved = [v for v in vessels if v["slip_days"] > 0]
    since = min(
        (ln.first_eta_report for ln in sea if ln.first_eta_report),
        default=None,
    )
    stale_days = (as_of - report_date).days if report_date else None
    needs = None
    if needs_look_lines:
        by_dist: dict[str, float] = defaultdict(float)
        for ln in needs_look_lines:
            by_dist[ln.distributor or "Distributor not matched"] += ln.quantity
        moved_ob = [
            ln for ln in needs_look_lines if ln.first_on_board and ln.on_board and ln.first_on_board != ln.on_board
        ]
        top = max(moved_ob, key=lambda ln: ln.quantity) if moved_ob else None
        needs = {
            "lines": len(needs_look_lines),
            "units": float(sum(ln.quantity for ln in needs_look_lines)),
            "distributors": _ranked(by_dist, 6),
            "since": _day(min((ln.first_seen_report for ln in needs_look_lines if ln.first_seen_report), default=None)),
            "days": cfg.needs_look_days,
            "on_board_moved": (
                {"from": _day(top.first_on_board), "to": _day(top.on_board)} if top else None
            ),
        }

    return {
        "as_of": as_of.isoformat(),
        "report_date": _day(report_date),
        "report_age_days": stale_days,
        "report_stale": bool(stale_days is not None and stale_days > cfg.stale_report_days),
        "stale_report_days": cfg.stale_report_days,
        "reports": reports,
        "tiles": {
            "at_sea": {
                "units": float(sum(ln.quantity for ln in sea)),
                "lines": len(sea),
                "vessels": len(vessels),
                "amount": _money(sea),
                "air_units": float(sum(ln.quantity for ln in air)),
                "overdue_vessels": sum(1 for v in vessels if v["overdue"]),
            },
            "arrived": {
                "units": float(sum(ln.quantity for ln in arrived)),
                "lines": len(arrived),
                "by_port": _ranked(by_port),
            },
            "booked": {"units": float(sum(ln.quantity for ln in booked)), "lines": len(booked)},
            "eta_moved": {
                "vessels_moved": len(moved),
                "vessels": len(vessels),
                "min_days": min((v["slip_days"] for v in moved), default=0),
                "max_days": max((v["slip_days"] for v in moved), default=0),
                "since": _day(since),
            },
        },
        "vessels": vessels,
        "map": {"size": list(SIZE), "lanes": lane_paths(), "ports": port_markers(), "cluster_radius_pct": CLUSTER_RADIUS_PCT},
        "port_rows": port_rows,
        "needs_look": needs,
    }


# ------------------------------------------------------------------------------------------ grid filter
def vessel_filter_parts(key: str | None, cfg: WaterConfig) -> dict[str, Any] | None:
    """The line filter behind a vessel key, or None when the key is not one of ours.

    ``{"vessel_name", "voyage_no"}`` for a named vessel; for an inferred one the on-board date, port ETA, discharge
    port and the hubs that belong to the lane (``other_hubs`` set: the default lane also takes unknown hubs).
    """
    if not key:
        return None
    if key.startswith("n:"):
        name, _, voyage = key[2:].partition("|")
        return {"vessel_name": name, "voyage_no": voyage}
    if key.startswith("i:"):
        parts = key[2:].split("|")
        if len(parts) != 4:
            return None
        ob, eta, port, lane = parts
        try:
            on_board = date.fromisoformat(ob) if ob != "None" else None
            port_eta = date.fromisoformat(eta) if eta != "None" else None
        except ValueError:
            return None
        if lane not in SEA_LANES:
            return None
        hubs = sorted(h for h, l in cfg.hub_lane.items() if l == lane)
        return {
            "on_board": on_board,
            "port_eta": port_eta,
            "deliver_port": port,
            "lane": lane,
            "hubs": hubs,
            "include_unknown_hubs": lane == DEFAULT_LANE,
            "known_hubs": sorted(cfg.hub_lane),
        }
    return None


def vessel_clause(key: str, cfg: WaterConfig):
    """SQL predicate for the lines of one vessel (the grid filter behind a click on a vessel)."""
    from sqlalchemy import and_, false, func, or_

    from app.models.facts import FactInboundShipment as F

    parts = vessel_filter_parts(key, cfg)
    if parts is None:
        return false()
    if "vessel_name" in parts:
        return and_(
            func.lower(func.trim(F.vessel_name)) == parts["vessel_name"],
            func.lower(func.coalesce(F.voyage_no, "")) == parts["voyage_no"],
        )
    hub = func.lower(func.coalesce(F.origin_hub, ""))
    hub_ok = hub.in_(parts["hubs"]) if parts["hubs"] else false()
    if parts["include_unknown_hubs"]:
        hub_ok = or_(hub_ok, hub.not_in(parts["known_hubs"]))
    return and_(
        F.line_state == "shipped",
        F.pod_date.is_(None),
        F.port_ata_date.is_(None),
        F.ship_way.ilike("%SEA%"),
        func.upper(func.coalesce(F.deliver_port, "")) == parts["deliver_port"],
        hub_ok,
        F.on_board_date.is_(None) if parts["on_board"] is None else F.on_board_date == parts["on_board"],
        F.port_eta_date.is_(None) if parts["port_eta"] is None else F.port_eta_date == parts["port_eta"],
    )
