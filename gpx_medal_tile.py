# //ai
#!/usr/bin/env python3
"""
GPX Medal Tile - turns a GPX track into a 3D-printable, wall-mounted hex tile that
shows the route and holds the finisher medal.

Tile:
  * raised route in orange (GPS noise smoothed), start ring / finish dot
  * race name, date, distance, athlete name, finish time and pace
  * ribbon slot for medals of any shape (up to approx. 95 mm, ribbons 20-40 mm)
  * 6 corner holes for the locating pins and 4 snap pockets for the wall frame
Accessories (one set per tile):
  * wall frame: 3 countersunk screw holes, 6 pins, 4 snap latches, dovetail pockets
    on the front side to join neighbouring frames into an expandable honeycomb wall
  * ribbon clamp (stepless medal height), ribbon winder with 2 spring clips
  * dovetail connector keys

Output: STL files per part and a ready Bambu Studio project (.3mf, 2 plates).
Designed for the Bambu Lab P1S (256 x 256 mm bed): tile 239.4 mm across the corners
on a 240 mm honeycomb grid (0.5 mm gap between neighbours).

Usage:
  python gpx_medal_tile.py run.gpx --race "Vienna City Marathon" --name "Alex" --time 3:28:45
Missing values are asked for interactively (handy with drag & drop onto the .bat).
"""
import argparse
import math
import os
import sys
import zipfile
import datetime as dt
import xml.etree.ElementTree as ET
from xml.sax.saxutils import quoteattr, escape

import numpy as np
import trimesh
from shapely.geometry import Polygon, LineString, Point, box, MultiPolygon
from shapely.ops import unary_union
from shapely import affinity
from matplotlib.textpath import TextPath
from matplotlib.font_manager import FontProperties

# --------------------------------------------------------------------------
# Parameters (mm)
# --------------------------------------------------------------------------
P = dict(
    grid_R=120.0,       # honeycomb grid: hex radius of one cell (across corners / 2) -> 240 mm
    R=119.7,            # tile radius: 0.3 mm smaller than the grid -> 0.5 mm gap to neighbours (print tolerance)
    base_t=5.0,         # base plate thickness (anthracite)
    text_h=0.8,         # raised text (white)          -> top at 5.8
    orange_h=2.0,       # raised route & time (orange) -> top at 7.0
    route_w=2.4,        # route line width (>= 6 extrusion widths with a 0.4 nozzle)
    smooth=0.9,         # GPS track smoothing in mm (0 = off)
    route_box=(-76, 22, 76, 71),   # area for the route (xmin, ymin, xmax, ymax)
    slot_y=14.0, slot_w=45.0, slot_h=4.0,          # ribbon slot
    medal_max=95.0,     # medal diameter the free area is designed for (preview only)
    # dovetail (bowtie) pocket on every edge
    dt_len=10.0, dt_end=14.0, dt_waist=7.0, dt_depth=3.0, key_t=2.7, key_clear=0.15,
    # locating: 6 holes in the tile corners, matching pins on the frame (no magnets)
    loc_r=110.0,                        # radius of hole / pin centres (in the corners)
    loc_hole_d=6.2, loc_hole_depth=3.6,  # hole in the back of the tile (corners, no text above)
    loc_pin_d=5.6, loc_pin_h=3.0,        # pin: 0.3 mm per side, 0.6 mm in depth; taller than the latches (2.6)
    loc_pin_chamfer=0.8,                # lead-in chamfer at the pin tip
    # ribbon clamp: pins pressed into blind holes below the slot
    pin_hole_d=4.0, pin_hole_depth=3.0, pin_dx=29.0, clamp_y=3.0,
    pin_d=4.3, pin_len=3.4, pin_slit=0.9,   # slotted press-fit pins: 4.3 mm, squeezed into the 4.0 mm hole
    clamp_len=68.0, clamp_w=8.0, clamp_t=4.0,
    # ribbon winder: flat card, the excess ribbon loop is rolled up on its waist
    winder_len=60.0, winder_w=56.0, winder_waist_len=48.0, winder_waist_w=44.0, winder_t=3.0,
    # spring clip that is pushed over the wound card so the ribbon cannot unwind
    clip_gap=3.0, clip_arm=28.0, clip_t=1.6, clip_w=10.0, clip_bump=0.6,
    # snap latches: 4 flexible arms on the frame, pockets with an undercut in the tile back
    snap_u=20.0,                        # offset along the top and bottom edge from the middle
    snap_w=10.0, snap_t=1.8, snap_base=2.0,  # arm width, thickness, height where the arm starts
    snap_gap=0.8,                       # slot that frees the arm from the frame rim
    snap_barb=0.9, snap_top=2.6,        # barb depth, arm height above the frame top
    snap_clear=0.25, snap_flex=1.2, snap_side=0.4,  # pocket clearances: outer face, flex room, sides
    snap_lip=1.0, snap_pocket=3.2,      # lip height and pocket depth in the tile
    # wall frame
    frame_Ro=119.7, frame_Ri=104.0, frame_h=14.0,   # outer size = tile size (flush), same grid gap
    # wall mounting: 3 countersunk screws (frame doubles as drilling template)
    screw_d=4.5, screw_head_d=8.6, flange_t=4.0,
)
FONT_BOLD = FontProperties(family="DejaVu Sans", weight="bold")
FONT_REG = FontProperties(family="DejaVu Sans", weight="normal")
CAP = 0.73  # cap height / font size ratio for DejaVu Sans

# display colours of the three parts (used in the 3MF and the preview)
COL_BASE, COL_TEXT, COL_ORANGE = "#2B2D31", "#ECEBE6", "#FC4C02"


# --------------------------------------------------------------------------
# Geometry helpers
# --------------------------------------------------------------------------
def hexagon(R, cx=0.0, cy=0.0):
    """Flat-top hexagon (corners at 0, 60, ... degrees)."""
    return Polygon([(cx + R * math.cos(math.radians(a)), cy + R * math.sin(math.radians(a)))
                    for a in range(0, 360, 60)])


def stadium(cx, cy, length, width, angle=0.0):
    """Slot shape (rounded rectangle); length runs along x before rotation."""
    half = max(length - width, 0.0) / 2
    s = LineString([(cx - half, cy), (cx + half, cy)]).buffer(width / 2, resolution=24) if half > 0 \
        else Point(cx, cy).buffer(width / 2, resolution=24)
    return affinity.rotate(s, angle, origin=(cx, cy)) if angle else s


def bowtie(offset=0.0):
    """Dovetail key outline centred on an edge, waist on the edge line."""
    L, E, W = P["dt_len"], P["dt_end"] / 2, P["dt_waist"] / 2
    poly = Polygon([(-L, -E), (0, -W), (L, -E), (L, E), (0, W), (-L, E)])
    return poly.buffer(offset, join_style=2) if offset else poly


def locator_positions():
    """Hole / pin centres in the 6 corners."""
    return [(P["loc_r"] * math.cos(math.radians(60 * k)), P["loc_r"] * math.sin(math.radians(60 * k)))
            for k in range(6)]


def edge_transform(theta_deg, apothem):
    """4x4 matrix: local edge coordinates -> world.
    u runs along the edge, v points inwards from the outer edge, z stays z."""
    s, c = math.sin(math.radians(theta_deg)), math.cos(math.radians(theta_deg))
    return np.array([[-s, -c, 0, c * apothem],
                     [c, -s, 0, s * apothem],
                     [0, 0, 1, 0],
                     [0, 0, 0, 1]], dtype=float)


def snap_sites():
    """(edge angle, offset along the edge) of the 4 snap latches: top and bottom edge."""
    u = P["snap_u"]
    return [(90, u), (90, -u), (270, u), (270, -u)]


def extrude_vz(profile, w):
    """Extrude a (v, z) profile along u from -w to +w (edge-local coordinates)."""
    m = trimesh.creation.extrude_polygon(Polygon(profile), 2 * w)   # X = v, Y = z, Z = u + w
    m.apply_transform(np.array([[0, 0, 1, -w], [1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1]], dtype=float))
    return m


def snap_arm_parts(v_in, H):
    """Frame side of one latch in edge-local coordinates: (cut, arm).
    The cut frees a block of the rim; the arm (one solid incl. barb) is added back,
    anchored 0.5 mm deep in the solid rim below snap_base."""
    w, t, g, b = P["snap_w"] / 2, P["snap_t"], P["snap_gap"], P["snap_barb"]
    v_out = v_in - t                                   # outer face of the arm
    z0, top = P["snap_base"], H + P["snap_top"]
    cut = trimesh.creation.box(bounds=[[-w - g, v_out - g, z0], [w + g, v_in + 1, H + 1]])
    # arm profile (v, z) incl. barb: 45 degree retention face below, lead-in chamfer on top
    arm = extrude_vz([(v_out, z0 - 0.5), (v_in - 0.05, z0 - 0.5), (v_in - 0.05, top), (v_out, top),
                      (v_out - b, H + 1.1 + b), (v_out - b, H + 0.8 + b), (v_out, H + 0.8)], w)
    return [cut], [arm]


def snap_pocket(v_in):
    """Tile side of one latch (edge-local, tile back at z = 0): neck + wider catch zone
    above the lip, as one solid."""
    w = P["snap_w"] / 2 + P["snap_side"]
    v_out = v_in - P["snap_t"]
    v_neck = v_out - P["snap_clear"]
    v_catch = v_out - P["snap_barb"] - 0.3
    v_far = v_in + P["snap_flex"]
    lip, depth = P["snap_lip"], P["snap_pocket"]
    return [extrude_vz([(v_neck, -1), (v_far, -1), (v_far, depth), (v_catch, depth),
                        (v_catch, lip), (v_neck, lip)], w)]


def chamfered_pin(cx, cy, d, z0, h, ch, sections=48):
    """Vertical pin with a 45 degree lead-in chamfer at the top."""
    r = d / 2
    prof = np.array([[0, 0], [r, 0], [r, h - ch], [r - ch, h], [0, h]], dtype=float)
    m = trimesh.creation.revolve(prof, sections=sections)
    m.apply_translation([cx, cy, z0])
    return m


def as_polys(geom):
    """Return the polygons contained in any shapely geometry."""
    if geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms)
    return [g for g in getattr(geom, "geoms", []) if isinstance(g, Polygon)]


def extrude(geom, z0, z1):
    """Shapely area -> trimesh prism from z0 to z1."""
    meshes = []
    for p in as_polys(geom):
        if p.area < 1e-4:
            continue
        m = trimesh.creation.extrude_polygon(p, z1 - z0)
        m.apply_translation([0, 0, z0])
        meshes.append(m)
    if not meshes:
        return None
    return trimesh.util.concatenate(meshes) if len(meshes) > 1 else meshes[0]


def boolean(op, a, b):
    """Boolean difference or union using the manifold engine. b may be one mesh or a list.
    Never pass overlapping meshes merged with trimesh.util.concatenate: their overlap is
    counted twice and stays solid (e.g. a plug inside a countersunk hole)."""
    if b is None:
        return a
    bs = [m for m in (b if isinstance(b, (list, tuple)) else [b]) if m is not None]
    if not bs:
        return a
    if op == "diff":
        return trimesh.boolean.difference([a] + bs, engine="manifold")
    return trimesh.boolean.union([a] + bs, engine="manifold")


def cylinder_xy(cx, cy, d, z0, z1, sections=48):
    """Vertical cylinder with diameter d from z0 to z1."""
    return extrude(Point(cx, cy).buffer(d / 2, resolution=sections // 4), z0, z1)


# --------------------------------------------------------------------------
# Text
# --------------------------------------------------------------------------
def text_geom(s, cap_h, cx, cy, max_w=None, bold=True):
    """Text as a shapely area with cap height cap_h, centred horizontally on cx
    and with the capitals centred vertically on cy. Shrinks to fit max_w."""
    if not s:
        return Polygon()
    tp = TextPath((0, 0), s, size=1.0, prop=FONT_BOLD if bold else FONT_REG)
    geom = Polygon()
    for ring in tp.to_polygons(closed_only=True):
        if len(ring) < 3:
            continue
        pg = Polygon(ring).buffer(0)
        geom = geom.symmetric_difference(pg)      # even-odd fill -> holes in O, A, 0 ...
    geom = geom.buffer(0)
    size = cap_h / CAP
    minx, _, maxx, _ = geom.bounds
    if max_w and (maxx - minx) * size > max_w:
        size = max_w / (maxx - minx)
    geom = affinity.scale(geom, size, size, origin=(0, 0))
    minx, _, maxx, _ = geom.bounds
    cap = CAP * size
    return affinity.translate(geom, cx - (minx + maxx) / 2, cy - cap / 2)


# --------------------------------------------------------------------------
# GPX
# --------------------------------------------------------------------------
def read_gpx(path):
    """Read track and route points (lat, lon, ele) plus timestamps."""
    root = ET.parse(path).getroot()
    pts, times = [], []
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag in ("trkpt", "rtept"):
            lat, lon = float(el.get("lat")), float(el.get("lon"))
            ele, t = None, None
            for ch in el:
                ct = ch.tag.split("}")[-1]
                if ct == "ele":
                    try:
                        ele = float(ch.text)
                    except (TypeError, ValueError):
                        pass
                elif ct == "time" and ch.text:
                    t = ch.text.strip()
            pts.append((lat, lon, ele))
            times.append(t)
    if len(pts) < 2:
        sys.exit(f"No track points found in {path}.")
    return pts, times


def haversine(a, b):
    """Great-circle distance in metres."""
    R = 6371000.0
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def gpx_stats(pts, times):
    """Distance, date and duration of the track."""
    # only count points at least 8 m apart -> GPS jitter is not added to the distance
    dist, last = 0.0, pts[0]
    for p in pts[1:]:
        d = haversine(last, p)
        if d >= 8.0:
            dist += d
            last = p
    dist += haversine(last, pts[-1])
    date, duration = None, None
    t_valid = [t for t in times if t]
    if t_valid:
        try:
            parse = lambda s: dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
            t0, t1 = parse(t_valid[0]), parse(t_valid[-1])
            date, duration = t0.date(), (t1 - t0).total_seconds()
        except ValueError:
            pass
    return dist, date, duration


def project(pts, rotate_deg=0.0):
    """Equirectangular projection to metres around the track centre, optional rotation."""
    lat0 = sum(p[0] for p in pts) / len(pts)
    k = math.cos(math.radians(lat0))
    xy = np.array([((p[1]) * 111320.0 * k, p[0] * 110540.0) for p in pts])
    xy -= xy.mean(axis=0)
    if rotate_deg:
        a = math.radians(rotate_deg)
        rot = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
        xy = xy @ rot.T
    return xy


def smooth_path(xy, step=0.25, sigma=0.9):
    """Remove GPS noise: resample evenly (step mm) and smooth with a
    Gaussian kernel (sigma mm). Works in model millimetres."""
    seg = np.hypot(*np.diff(xy, axis=0).T)
    keep = np.concatenate([[True], seg > 1e-6])
    xy = xy[keep]
    cum = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(xy, axis=0).T))])
    L = cum[-1]
    if L < 1:
        return xy
    s = np.linspace(0, L, max(int(L / step), 4))
    res = np.column_stack([np.interp(s, cum, xy[:, 0]), np.interp(s, cum, xy[:, 1])])
    r = max(int(3 * sigma / step), 1)
    kern = np.exp(-0.5 * (np.arange(-r, r + 1) * step / sigma) ** 2)
    kern /= kern.sum()
    pad = np.pad(res, ((r, r), (0, 0)), mode="edge")
    return np.column_stack([np.convolve(pad[:, i], kern, mode="valid") for i in range(2)])


def fit_route(xy, rb):
    """Scale and centre the projected track into the route box (keeps aspect ratio)."""
    xmin, ymin, xmax, ymax = rb
    w, h = np.ptp(xy[:, 0]), np.ptp(xy[:, 1])
    s = min((xmax - xmin) / max(w, 1e-9), (ymax - ymin) / max(h, 1e-9))
    c_box = np.array([(xmin + xmax) / 2, (ymin + ymax) / 2])
    c_xy = np.array([(xy[:, 0].min() + xy[:, 0].max()) / 2, (xy[:, 1].min() + xy[:, 1].max()) / 2])
    return (xy - c_xy) * s + c_box


# --------------------------------------------------------------------------
# Formatting
# --------------------------------------------------------------------------
def parse_time(s):
    """'h:mm:ss', 'mm:ss' or 'ss' -> seconds."""
    parts = [int(x) for x in s.strip().split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, sec = parts
    return h * 3600 + m * 60 + sec


def fmt_time(sec):
    sec = int(round(sec))
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_pace(sec, dist_m):
    if not sec or dist_m < 100:
        return ""
    p = sec / (dist_m / 1000)
    m, s = divmod(int(round(p)), 60)
    return f"{m}:{s:02d} /km"


def fmt_date(d):
    """Locale-independent English date, e.g. '12 Apr 2026'."""
    months = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
    return f"{d.day} {months[d.month - 1]} {d.year}"


def fmt_km(dist_m):
    km = dist_m / 1000
    return (f"{km:.1f}" if km < 100 else f"{km:.0f}") + " km"


# --------------------------------------------------------------------------
# Parts
# --------------------------------------------------------------------------
def build_tile(route_xy, fields):
    """Return (base, text, orange) meshes plus the 2D shapes for the preview."""
    R, T = P["R"], P["base_t"]
    hexg = hexagon(R)
    z_text = T + P["text_h"]
    z_or = T + P["orange_h"]

    # ---- route + start/finish ----------------------------------------------
    if P["smooth"] > 0:
        route_xy = smooth_path(route_xy, sigma=P["smooth"])
    line = LineString(route_xy).simplify(0.08)
    rw = P["route_w"] / 2
    route = line.buffer(rw, resolution=12, join_style=1, cap_style=1)
    # morphological closing: merges nearly parallel tracks (out-and-back, pauses)
    # into one clean line and fills tiny gaps
    route = route.buffer(0.6, resolution=12).buffer(-0.6, resolution=12)
    route = route.buffer(-0.3, resolution=12).buffer(0.3, resolution=12)   # remove tiny spikes
    start, end = Point(route_xy[0]), Point(route_xy[-1])
    # start marker: ring. For loops (start = finish) the ring is the only marker.
    ring = start.buffer(3.6, 32).difference(start.buffer(1.8, 32))
    orange = unary_union([route.difference(start.buffer(3.6, 32)), ring])
    if start.distance(end) > 8.0:
        # point-to-point course: finish as a filled dot
        orange = unary_union([orange, end.buffer(3.6, 32)])

    # ---- texts -------------------------------------------------------------
    white = []
    title = text_geom(fields["race"], 9.0, 0, 90, max_w=118)      # race title is orange
    white.append(text_geom(fields["sub"], 5.0, 0, 77.5, max_w=135, bold=False))
    fx = 69.0
    white.append(text_geom("ATHLETE", 3.6, -fx, -31))
    white.append(text_geom(fields["name"], 7.0, -fx, -43, max_w=32))
    white.append(text_geom("TIME", 3.6, fx, -31))
    if fields.get("pace"):
        white.append(text_geom(fields["pace"], 3.8, fx, -54, max_w=32))
    if fields.get("extra"):
        white.append(text_geom(fields["extra"], 3.8, -fx, -54, max_w=32))
    orange = unary_union([orange, title, text_geom(fields["time"], 7.0, fx, -43, max_w=32)])
    white = unary_union(white).difference(orange.buffer(0.3))

    # keep everything inside the tile
    inner = hexg.buffer(-2.0)
    orange = orange.intersection(inner)
    white = white.intersection(inner)

    # ---- base plate --------------------------------------------------------
    base = extrude(hexg, 0, T)
    cuts = [extrude(stadium(0, P["slot_y"], P["slot_w"], P["slot_h"]), -1, T + 1)]
    # corner holes for the frame's locating pins
    for x, y in locator_positions():
        cuts.append(cylinder_xy(x, y, P["loc_hole_d"], -1, P["loc_hole_depth"]))
    for sx in (-1, 1):
        cuts.append(cylinder_xy(sx * P["pin_dx"], P["clamp_y"], P["pin_hole_d"], -1, P["pin_hole_depth"]))
    # pockets with undercut for the 4 snap latches of the frame
    apo = P["frame_Ro"] * math.cos(math.radians(30))           # same reference as the latches
    v_in = (P["frame_Ro"] - P["frame_Ri"]) * math.cos(math.radians(30))
    for theta, u in snap_sites():
        M = edge_transform(theta, apo) @ trimesh.transformations.translation_matrix([u, 0, 0])
        for p in snap_pocket(v_in):
            p.apply_transform(M)
            cuts.append(p)
    base = boolean("diff", base, cuts)

    text_mesh = extrude(white, T, z_text)
    orange_mesh = extrude(orange, T, z_or)
    return base, text_mesh, orange_mesh, (orange, white)


def build_frame():
    """Hex ring that is screwed to the wall, same outer size as the tile.
    - 6 chamfered pins fit into the corner holes of the tile and carry its weight
    - 4 snap latches hold the tile against the frame (pull hard to remove it)
    - dovetail pockets on the front side: neighbouring frames are joined with keys
    - 3 countersunk screw holes in flat flanges on the wall side"""
    Ro, Ri, H = P["frame_Ro"], P["frame_Ri"], P["frame_h"]
    apo = Ro * math.cos(math.radians(30))
    v_in = (Ro - Ri) * math.cos(math.radians(30))
    ring = hexagon(Ro).difference(hexagon(Ri))
    # flat flanges on the wall side (2 top, 1 bottom) with countersunk screw holes. Without
    # keyholes the frame does not have to slide when hung, so it can be keyed to its neighbour
    # first and then used as drilling template.
    ia = Ri * math.cos(math.radians(30))
    ft = P["flange_t"]
    flanges = [box(sx * 45 - 11, 68, sx * 45 + 11, ia + 1) for sx in (-1, 1)] + [box(-11, -ia - 1, 11, -68)]
    frame = extrude(ring, 0, H)
    frame = boolean("union", frame, extrude(unary_union([f.intersection(hexagon(Ro)) for f in flanges]), 0, ft))
    cuts, adds = [], []
    rs, rh = P["screw_d"] / 2, P["screw_head_d"] / 2
    for cx, cy in ((-45, 80), (45, 80), (0, -80)):
        cuts.append(cylinder_xy(cx, cy, P["screw_d"], -1, ft + 1))
        cs = trimesh.creation.revolve(np.array([[0, ft - (rh - rs)], [rs, ft - (rh - rs)], [rh, ft],
                                                [rh, ft + 1], [0, ft + 1]], dtype=float), sections=48)
        cs.apply_translation([cx, cy, 0])                     # 90 degree countersink
        cuts.append(cs)
    # dovetail pockets on the FRONT side (under the tile): keys can be inserted while the frames
    # hang on the wall. Waist exactly on the grid edge, so both neighbours share the key.
    a = P["grid_R"] * math.cos(math.radians(30))
    W2 = P["dt_waist"] / 2 + 0.2
    pocket = unary_union([bowtie(), box(-0.2, -W2, P["dt_len"], W2)])
    for k in range(6):
        th = 30 + 60 * k
        bt = affinity.rotate(pocket, th, origin=(0, 0))
        bt = affinity.translate(bt, a * math.cos(math.radians(th)), a * math.sin(math.radians(th)))
        cuts.append(extrude(bt, H - P["dt_depth"], H + 1))
    # snap latches
    for theta, u in snap_sites():
        M = edge_transform(theta, apo) @ trimesh.transformations.translation_matrix([u, 0, 0])
        c, ad = snap_arm_parts(v_in, H)
        for m in c + ad:
            m.apply_transform(M)
        cuts += c
        adds += ad
    frame = boolean("diff", frame, cuts)
    # locating pins on top (slightly overlapping the frame so the union is solid)
    adds += [chamfered_pin(x, y, P["loc_pin_d"], H - 0.01, P["loc_pin_h"] + 0.01, P["loc_pin_chamfer"])
             for x, y in locator_positions()]
    return boolean("union", frame, adds)


def build_clamp():
    """Bar that pinches both ribbon plies against the back of the tile, right below the
    slot. Two slotted pins are pressed into the holes; two ridges improve the grip."""
    L, W, T = P["clamp_len"], P["clamp_w"], P["clamp_t"]
    bar = extrude(stadium(0, 0, L, W), 0, T)
    ridges = [extrude(box(-24, y - 0.5, 24, y + 0.5), T - 0.01, T + 0.5) for y in (-2.0, 2.0)]
    pins = []
    for sx in (-1, 1):
        pin = chamfered_pin(sx * P["pin_dx"], 0, P["pin_d"], T - 0.01, P["pin_len"] + 0.01, 0.6)
        slit = trimesh.creation.box(bounds=[[sx * P["pin_dx"] - P["pin_slit"] / 2, -3, T + 0.6],
                                            [sx * P["pin_dx"] + P["pin_slit"] / 2, 3, T + P["pin_len"] + 1]])
        pins.append(boolean("diff", pin, slit))
    return boolean("union", bar, ridges + pins)


def build_winder():
    """Flat card for the excess ribbon: put it into the end of the ribbon loop and roll the
    loop up on the narrow waist; the wide ends keep the ribbon from slipping off."""
    hl, hw = P["winder_len"] / 2, P["winder_w"] / 2
    wl, ww = P["winder_waist_len"] / 2, P["winder_waist_w"] / 2
    shape = unary_union([box(-hl, -hw, -wl, hw), box(wl, -hw, hl, hw), box(-wl, -ww, wl, ww)])
    shape = shape.buffer(1.0, join_style=1).buffer(-2.0, join_style=1).buffer(1.0, join_style=1)  # round corners
    return extrude(shape, 0, P["winder_t"])


def build_winder_clips(n=2):
    """U-shaped spring clips. After rolling the ribbon onto the winder card, push a clip
    over the card from its long edge: the arms press the wound ribbon onto the card, so it
    cannot unwind. The arms open from 3 mm (bare card) to about 10 mm of wound ribbon.
    Printed lying flat (U-shape on the bed), no supports."""
    g, L, t, b = P["clip_gap"], P["clip_arm"], P["clip_t"], P["clip_bump"]
    h = g / 2
    # U-profile in the print plane: x = along the arms, y = across (card thickness)
    spine = box(-t, -h - t, 0, h + t)
    arms = [box(0, h, L, h + t), box(0, -h - t, L, -h)]
    bumps = [Polygon([(L - 4, h), (L - 2, h - b), (L - 1, h - b), (L, h)]),          # pressure bumps
             Polygon([(L - 4, -h), (L - 2, -h + b), (L - 1, -h + b), (L, -h)])]
    flares = [Polygon([(L, h), (L, h + t), (L + 2.5, h + t + 1.2), (L + 2.5, h + 1.2)]),  # lead-in
              Polygon([(L, -h), (L, -h - t), (L + 2.5, -h - t - 1.2), (L + 2.5, -h - 1.2)])]
    shape = unary_union([spine] + arms + bumps + flares).buffer(0.2, join_style=1).buffer(-0.2, join_style=1)
    clip = extrude(shape, 0, P["clip_w"])
    clips = []
    for i in range(n):
        m = clip.copy()
        m.apply_translation([0, i * (g + 2 * t + 6), 0])
        clips.append(m)
    return trimesh.util.concatenate(clips)


def build_keys(n=6):
    """n dovetail keys with clearance, laid out in a grid."""
    k = extrude(bowtie(-P["key_clear"]), 0, P["key_t"])
    keys = []
    for i in range(n):
        m = k.copy()
        m.apply_translation([(i % 3) * 25 - 25, (i // 3) * 20 - 10, 0])
        keys.append(m)
    return trimesh.util.concatenate(keys)


# --------------------------------------------------------------------------
# 3MF export (one object, several parts, a colour and filament per part)
# --------------------------------------------------------------------------
def _mesh_xml(oid, mesh, pid, pindex):
    """One 3MF mesh object; the whole object uses material pindex of group pid."""
    vs = "".join(f'<vertex x="{x:.4f}" y="{y:.4f}" z="{z:.4f}"/>' for x, y, z in mesh.vertices)
    ts = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in mesh.faces)
    return (f'<object id="{oid}" type="model" pid="{pid}" pindex="{pindex}"><mesh>'
            f'<vertices>{vs}</vertices><triangles>{ts}</triangles></mesh></object>\n')


def write_multicolor_3mf(path, name, parts, bed=(256.0, 256.0)):
    """Write a standard 3MF that Bambu Studio / OrcaSlicer load as ONE object with
    several parts. parts: list of (part name, trimesh, filament no., '#RRGGBB').

    Each part gets
      * a display colour via the core-spec <basematerials> (Bambu Studio imports
        these as filament colours for non-Bambu 3MF files), and
      * its filament number via Metadata/model_settings.config, which Bambu Studio
        reads for every 3MF and keeps even when it loads "geometry only".

    Important: the file must NOT claim to be written by BambuStudio (Application
    metadata). Otherwise Bambu Studio expects a complete project_settings.config
    with printer/filament presets and reports "invalid config, geometry only"."""
    parts = [p for p in parts if p[1] is not None]
    # common centre -> place the object in the middle of the bed
    allv = np.vstack([m.vertices for _, m, _, _ in parts])
    lo, hi = allv.min(axis=0), allv.max(axis=0)
    ctr = np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]])

    mat_id = 1
    first_obj = 2
    asm_id = first_obj + len(parts)
    bases = "".join(f'<base name={quoteattr(pname)} displaycolor="{col.upper()}FF"/>'
                    for pname, _, _, col in parts)
    objs, comps, cfg_parts = [], [], []
    for i, (pname, m, ext, _) in enumerate(parts):
        oid = first_obj + i
        mm = m.copy()
        mm.apply_translation(-ctr)
        objs.append(_mesh_xml(oid, mm, mat_id, i))
        comps.append(f'<component objectid="{oid}" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>')
        cfg_parts.append(
            f'    <part id="{oid}" subtype="normal_part">\n'
            f'      <metadata key="name" value={quoteattr(pname)}/>\n'
            f'      <metadata key="extruder" value="{ext}"/>\n'
            f'    </part>\n')
    tx = f"1 0 0 0 1 0 0 0 1 {bed[0]/2:.3f} {bed[1]/2:.3f} 0"
    model = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<model unit="millimeter" xml:lang="en-US" '
        'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">\n'
        '<metadata name="Application">gpx_medal_tile</metadata>\n'
        f'<metadata name="Title">{escape(name)}</metadata>\n'
        '<resources>\n'
        f'<basematerials id="{mat_id}">{bases}</basematerials>\n' + "".join(objs) +
        f'<object id="{asm_id}" type="model"><components>{"".join(comps)}</components></object>\n'
        '</resources>\n'
        f'<build><item objectid="{asm_id}" transform="{tx}"/></build>\n'
        '</model>\n')
    config = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<config>\n'
        f'  <object id="{asm_id}">\n'
        f'    <metadata key="name" value={quoteattr(name)}/>\n'
        '    <metadata key="extruder" value="1"/>\n' + "".join(cfg_parts) +
        '  </object>\n'
        '</config>\n')
    ctypes = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
        ' <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
        ' <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>\n'
        ' <Default Extension="config" ContentType="text/xml"/>\n'
        '</Types>\n')
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        ' <Relationship Target="/3D/3dmodel.model" Id="rel-1" '
        'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n'
        '</Relationships>\n')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ctypes)
        z.writestr("_rels/.rels", rels)
        z.writestr("3D/3dmodel.model", model)
        z.writestr("Metadata/model_settings.config", config)


def write_bambu_project(path, objects, template_cfg, title, wipe_tower_xy=(4.0, 213.0),
                        bed=(256.0, 256.0)):
    """Write a native Bambu Studio project 3MF, mirroring the structure Bambu Studio
    itself saves (production extension, one mesh file per object in 3D/Objects/).

    objects: list of dicts
        name   - object name shown in Bambu Studio
        plate  - 0-based plate index
        pos    - (x, y) of the object centre on its plate in mm
        parts  - list of (part name, trimesh, filament no.)
    template_cfg: Metadata/project_settings.config from a project saved in Bambu Studio
        (printer, process and filament presets incl. colours). With a complete Bambu
        project config, Bambu Studio loads the file as a regular project without warning.
    wipe_tower_xy: lower-left corner of the prime tower on every plate."""
    import json
    with open(template_cfg, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    version = cfg.get("version", "02.08.02.61")
    n_plates = max(o["plate"] for o in objects) + 1

    # prime tower position per plate (moved away from the tile, see README)
    cfg["wipe_tower_x"] = [f"{wipe_tower_xy[0]:g}"] * n_plates
    cfg["wipe_tower_y"] = [f"{wipe_tower_xy[1]:g}"] * n_plates
    cfg_text = json.dumps(cfg, indent=4, ensure_ascii=False)

    # plates are laid out in a grid: cols = ceil(sqrt(n)), stride = bed size * 1.2
    cols = math.ceil(math.sqrt(n_plates) - 1e-9)
    def plate_origin(i):
        return (i % cols) * bed[0] * 1.2, -(i // cols) * bed[1] * 1.2

    ns = ('xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
          'xmlns:BambuStudio="http://schemas.bambulab.com/package/2021" '
          'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" requiredextensions="p"')
    ident = "1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"   # row-major 4x4 for model_settings
    zero_tx = "1 0 0 0 1 0 0 0 1 0 0 0"

    files = {}
    root_objs, build_items, cfg_objs, plate_insts, asm = [], [], [], {}, []
    sub_id = 0
    asm_base = sum(len(o["parts"]) for o in objects)
    for k, obj in enumerate(objects, start=1):
        parts = [p for p in obj["parts"] if p[1] is not None]
        allv = np.vstack([m.vertices for _, m, _ in parts])
        lo, hi = allv.min(axis=0), allv.max(axis=0)
        ctr = np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]])
        asm_id = asm_base + k
        obj_file = f"/3D/Objects/object_{k}.model"
        meshes, comps, cfg_parts = [], [], []
        for j, (pname, m, ext) in enumerate(parts):
            sub_id += 1
            mm = m.copy()
            mm.apply_translation(-ctr)
            vs = "".join(f'<vertex x="{x:.6g}" y="{y:.6g}" z="{z:.6g}"/>' for x, y, z in mm.vertices)
            ts = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in mm.faces)
            meshes.append(f' <object id="{sub_id}" p:UUID="{k:04x}{j:04x}-81cb-4c03-9d28-80fed5dfa1dc" type="model">\n'
                          f'  <mesh><vertices>{vs}</vertices><triangles>{ts}</triangles></mesh>\n </object>\n')
            comps.append(f'    <component p:path="{obj_file}" objectid="{sub_id}" '
                         f'p:UUID="{k:04x}{j:04x}-b206-40ff-9872-83e8017abed1" transform="{zero_tx}"/>\n')
            cfg_parts.append(
                f'    <part id="{sub_id}" subtype="normal_part">\n'
                f'      <metadata key="name" value={quoteattr(pname)}/>\n'
                f'      <metadata key="matrix" value="{ident}"/>\n'
                f'      <metadata key="extruder" value="{ext}"/>\n'
                f'      <mesh_stat face_count="{len(mm.faces)}" edges_fixed="0" degenerate_facets="0" '
                f'facets_removed="0" facets_reversed="0" backwards_edges="0"/>\n'
                f'    </part>\n')
            asm.append(f'   <assemble_item object_id="{asm_id}" volume_id="{j}" transform="{zero_tx}" />\n')
        files[obj_file[1:]] = (f'<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" {ns}>\n'
                               ' <metadata name="BambuStudio:3mfVersion">1</metadata>\n'
                               ' <resources>\n' + "".join(meshes) + ' </resources>\n <build/>\n</model>\n')

        ox, oy = plate_origin(obj["plate"])
        tx = f"1 0 0 0 1 0 0 0 1 {ox + obj['pos'][0]:g} {oy + obj['pos'][1]:g} 0"
        root_objs.append(f'  <object id="{asm_id}" p:UUID="{k:08x}-61cb-4c03-9d28-80fed5dfa1dc" type="model">\n'
                         '   <components>\n' + "".join(comps) + '   </components>\n  </object>\n')
        build_items.append(f'  <item objectid="{asm_id}" p:UUID="{k:08x}-b1ec-4553-aec9-835e5b724bb4" '
                           f'transform="{tx}" printable="1"/>\n')
        cfg_objs.append(f'  <object id="{asm_id}">\n'
                        f'    <metadata key="name" value={quoteattr(obj["name"])}/>\n'
                        f'    <metadata key="extruder" value="{parts[0][2]}"/>\n' + "".join(cfg_parts) +
                        '  </object>\n')
        plate_insts.setdefault(obj["plate"], []).append(asm_id)
        asm.insert(len(asm) - len(parts),
                   f'   <assemble_item object_id="{asm_id}" instance_id="0" transform="{tx}" offset="0 0 0" />\n')

    plates = []
    ident_id = 1
    for pi in range(n_plates):
        insts = ""
        for oid in plate_insts.get(pi, []):
            insts += ('    <model_instance>\n'
                      f'      <metadata key="object_id" value="{oid}"/>\n'
                      '      <metadata key="instance_id" value="0"/>\n'
                      f'      <metadata key="identify_id" value="{ident_id}"/>\n'
                      '    </model_instance>\n')
            ident_id += 1
        plates.append('  <plate>\n'
                      f'    <metadata key="plater_id" value="{pi + 1}"/>\n'
                      '    <metadata key="plater_name" value=""/>\n'
                      '    <metadata key="locked" value="false"/>\n' + insts + '  </plate>\n')

    today = dt.date.today().isoformat()
    files["3D/3dmodel.model"] = (
        f'<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" {ns}>\n'
        f' <metadata name="Application">BambuStudio-{version}</metadata>\n'
        ' <metadata name="BambuStudio:3mfVersion">1</metadata>\n'
        f' <metadata name="CreationDate">{today}</metadata>\n'
        f' <metadata name="ModificationDate">{today}</metadata>\n'
        f' <metadata name="Title">{escape(title)}</metadata>\n'
        ' <resources>\n' + "".join(root_objs) + ' </resources>\n'
        ' <build p:UUID="2c7c17d8-22b5-4d84-8835-1976022ea369">\n' + "".join(build_items) + ' </build>\n</model>\n')
    files["Metadata/model_settings.config"] = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<config>\n' + "".join(cfg_objs) + "".join(plates) +
        '  <assemble>\n' + "".join(asm) + '  </assemble>\n</config>\n')
    files["Metadata/project_settings.config"] = cfg_text
    files["Metadata/slice_info.config"] = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<config>\n  <header>\n'
        '    <header_item key="X-BBL-Client-Type" value="slicer"/>\n'
        f'    <header_item key="X-BBL-Client-Version" value="{version}"/>\n'
        '  </header>\n</config>\n')

    rel = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n{}'
           '</Relationships>\n')
    rel_line = (' <Relationship Target="{}" Id="rel-{}" '
                'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n')
    obj_files = sorted(f for f in files if f.startswith("3D/Objects/"))
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8"?>\n'
                   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
                   ' <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
                   ' <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>\n'
                   ' <Default Extension="png" ContentType="image/png"/>\n'
                   ' <Default Extension="gcode" ContentType="text/x.gcode"/>\n'
                   '</Types>\n')
        z.writestr("_rels/.rels", rel.format(rel_line.format("/3D/3dmodel.model", 1)))
        z.writestr("3D/3dmodel.model", files["3D/3dmodel.model"])
        z.writestr("3D/_rels/3dmodel.model.rels",
                   rel.format("".join(rel_line.format("/" + f, i) for i, f in enumerate(obj_files, start=1))))
        for f in obj_files:
            z.writestr(f, files[f])
        for f in ("Metadata/project_settings.config", "Metadata/model_settings.config", "Metadata/slice_info.config"):
            z.writestr(f, files[f])


# --------------------------------------------------------------------------
# Preview
# --------------------------------------------------------------------------
def preview(path, orange, white, route_xy):
    """Top view PNG of the tile front."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon as MPoly, Circle

    fig, ax = plt.subplots(figsize=(8, 7.2), dpi=150)
    fig.patch.set_facecolor("#f4f2ee")

    def draw(geom, color, z=1):
        for p in as_polys(geom):
            ax.add_patch(MPoly(np.array(p.exterior.coords), closed=True, fc=color, ec="none", zorder=z))
            for h in p.interiors:
                ax.add_patch(MPoly(np.array(h.coords), closed=True, fc=COL_BASE, ec="none", zorder=z + 0.1))

    draw(hexagon(P["R"]), COL_BASE, 0)
    draw(stadium(0, P["slot_y"], P["slot_w"], P["slot_h"]), "#f4f2ee", 2)
    mc = (0, P["slot_y"] - 4 - P["medal_max"] / 2)
    ax.add_patch(Circle(mc, P["medal_max"] / 2, fc="none", ec="#9a978f", ls="--", lw=1, zorder=1.5))
    ax.text(mc[0], mc[1], f"medal\nup to Ø {P['medal_max']:.0f} mm", color="#9a978f",
            ha="center", va="center", fontsize=8, zorder=1.6)
    draw(white, COL_TEXT, 3)
    draw(orange, COL_ORANGE, 4)
    ax.set_xlim(-128, 128)
    ax.set_ylim(-112, 112)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.tight_layout()
    import io, time
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor())
    plt.close(fig)
    # write the finished PNG; retry because Windows (viewer, antivirus, OneDrive,
    # controlled folder access) may briefly lock the file and raise Errno 22/13
    for attempt in range(5):
        try:
            with open(path, "wb") as f:
                f.write(buf.getvalue())
            return
        except OSError as e:
            err = e
            time.sleep(0.5)
    print(f"Warning: preview could not be saved ({err}). All other files are done.")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def ask(prompt, default=""):
    """Prompt on the console; empty input returns the default."""
    try:
        v = input(f"{prompt}" + (f" [{default}]" if default else "") + ": ").strip()
    except EOFError:
        v = ""
    return v or default


def slug(s):
    """File-name-safe version of a string."""
    keep = "".join(c if c.isalnum() else "_" for c in s)
    return "_".join(filter(None, keep.split("_")))[:40] or "tile"


def find_template(name="bambu_project_settings.config"):
    """Bambu project settings: a copy next to the .exe / script wins over the bundled one."""
    dirs = []
    if getattr(sys, "frozen", False):                      # PyInstaller build
        dirs.append(os.path.dirname(sys.executable))
        dirs.append(getattr(sys, "_MEIPASS", ""))
    dirs.append(os.path.dirname(os.path.abspath(__file__)))
    for d in dirs:
        p = os.path.join(d, name)
        if d and os.path.isfile(p):
            return p
    return os.path.join(dirs[-1], name)


def main():
    global COL_BASE, COL_TEXT, COL_ORANGE
    # Windows consoles may not support every character of a race name: never crash on output
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="GPX -> 3D-printable medal display tile (Bambu Lab P1S)")
    ap.add_argument("gpx", nargs="?", help="GPX file")
    ap.add_argument("--race", help="race name, e.g. 'Vienna City Marathon'")
    ap.add_argument("--name", help="athlete name")
    ap.add_argument("--time", help="finish time h:mm:ss (default: from the GPX)")
    ap.add_argument("--date", help="date as printed, e.g. '12 Apr 2026' (default: from the GPX)")
    ap.add_argument("--distance", type=float, help="official distance in km, e.g. 21.1 (default: from the GPX)")
    ap.add_argument("--extra", default="", help="extra line below the name, e.g. 'Rank 87'")
    ap.add_argument("--no-pace", action="store_true", help="do not show the pace")
    ap.add_argument("--rotate", type=float, default=0.0, help="rotate the route (degrees, counter-clockwise)")
    ap.add_argument("--smooth", type=float, default=P["smooth"],
                    help="GPS track smoothing in mm (default 0.9, 0 = off, 1.5 = very smooth)")
    ap.add_argument("--out", help="output folder (default: next to the GPX)")
    ap.add_argument("--no-frame", action="store_true",
                    help="do not generate wall frame and keys (only if you already printed a spare frame)")
    a = ap.parse_args()
    P["smooth"] = a.smooth

    interactive = sys.stdin.isatty()
    gpx = a.gpx or (ask("Path to the GPX file") if interactive else None)
    if not gpx or not os.path.isfile(gpx):
        sys.exit("GPX file not found.")

    pts, times = read_gpx(gpx)
    dist, gdate, gdur = gpx_stats(pts, times)

    # fill missing values from the GPX or by asking on the console
    race = a.race or (ask("Race name", os.path.splitext(os.path.basename(gpx))[0]) if interactive else
                      os.path.splitext(os.path.basename(gpx))[0])
    name = a.name if a.name is not None else (ask("Athlete name") if interactive else "")
    tdefault = fmt_time(gdur) if gdur else ""
    time_s = a.time or (ask("Finish time (h:mm:ss)", tdefault) if interactive else tdefault)
    secs = parse_time(time_s) if time_s else None
    dist_m = a.distance * 1000 if a.distance else dist
    date_s = a.date or (fmt_date(gdate) if gdate else "")

    fields = dict(
        race=race,
        sub=" · ".join(x for x in (date_s, fmt_km(dist_m)) if x),
        name=name,
        time=fmt_time(secs) if secs else "",
        pace="" if a.no_pace else fmt_pace(secs, dist_m),
        extra=a.extra,
    )

    out = a.out or os.path.join(os.path.dirname(os.path.abspath(gpx)), "output_" + slug(race))
    os.makedirs(out, exist_ok=True)
    stem = slug(race)

    print(f"Route: {len(pts)} points, {dist/1000:.2f} km  ->  {fields}")
    xy = fit_route(project(pts, a.rotate), P["route_box"])

    base, text_m, orange_m, (og, wg) = build_tile(xy, fields)
    files = {
        f"{stem}_1_tile_base.stl": base,
        f"{stem}_2_text_white.stl": text_m,
        f"{stem}_3_route_time_orange.stl": orange_m,
    }
    full = trimesh.boolean.union([m for m in (base, text_m, orange_m) if m is not None], engine="manifold")
    files[f"{stem}_tile_single_color.stl"] = full

    parts = [("Tile base", base, 1, COL_BASE),
             ("Text white", text_m, 2, COL_TEXT),
             ("Route, title + time orange", orange_m, 3, COL_ORANGE)]
    # every medal needs its own clamp, winder and clips; frame + keys can be skipped
    clamp, winder, clips = build_clamp(), build_winder(), build_winder_clips()
    files["ribbon_clamp.stl"] = clamp
    files["ribbon_winder.stl"] = winder
    files["winder_clips_2x.stl"] = clips
    frame = keys = None
    if not a.no_frame:
        frame, keys = build_frame(), build_keys()
        files["wall_frame.stl"] = frame
        files["connector_keys_6x.stl"] = keys

    path_3mf = os.path.join(out, f"{stem}_tile_multicolor.3mf")
    template = find_template()
    if os.path.isfile(template):
        # native Bambu project: plate 1 = tile (3 colours), plate 2 = accessories (filament 1)
        objects = [dict(name=race, plate=0, pos=(128.0, 128.0),
                        parts=[(n, m, e) for n, m, e, _ in parts])]
        # plate 2: small parts inside the frame opening
        objects += [dict(name="Ribbon clamp", plate=1, pos=(128.0, 150.0), parts=[("Ribbon clamp", clamp, 1)]),
                    dict(name="Ribbon winder", plate=1, pos=(128.0, 183.0), parts=[("Ribbon winder", winder, 1)]),
                    dict(name="Winder clips", plate=1, pos=(128.0, 72.0), parts=[("Winder clips", clips, 1)])]
        if frame is not None:
            objects += [dict(name="Wall frame", plate=1, pos=(128.0, 128.0), parts=[("Wall frame", frame, 1)]),
                        dict(name="Connector keys", plate=1, pos=(128.0, 103.0), parts=[("Connector keys", keys, 1)])]
        write_bambu_project(path_3mf, objects, template, race)
    else:
        # fallback: standard 3MF (Bambu Studio loads geometry + colours only)
        write_multicolor_3mf(path_3mf, race, parts)

    for fn, m in files.items():
        if m is not None:
            m.export(os.path.join(out, fn))
            print(f"  {fn:45s} watertight={m.is_watertight}  {m.extents.round(1)}")
    if os.path.isfile(template):
        # show the filament colours of the Bambu template in the preview
        import json
        with open(template, "r", encoding="utf-8") as f:
            cols = json.load(f).get("filament_colour", [])
        if len(cols) >= 3:
            COL_BASE, COL_TEXT, COL_ORANGE = (c[:7] for c in cols[:3])
    preview(os.path.join(out, f"{stem}_preview.png"), og, wg, xy)
    print("Done ->", out)


if __name__ == "__main__":
    # keep the console window open when the .exe was started by drag & drop
    keep_open = getattr(sys, "frozen", False) and sys.stdin is not None and sys.stdin.isatty()
    rc = 0
    try:
        main()
    except SystemExit as e:
        if e.code not in (None, 0):
            print(e.code if isinstance(e.code, str) else f"Exit code {e.code}")
            rc = e.code if isinstance(e.code, int) else 1
    except Exception:
        import traceback
        traceback.print_exc()
        rc = 1
    if keep_open:
        try:
            input("\nPress Enter to close ...")
        except EOFError:
            pass
    sys.exit(rc)
