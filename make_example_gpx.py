# //ai
"""Create a generic, simplified Boston-style point-to-point example track
(Hopkinton -> Boston) with GPS-like noise. Not the official course."""
import math
import random
import datetime as dt

random.seed(7)
# rough waypoints of towns along the way (lat, lon)
WP = [(42.2290, -71.5226), (42.2610, -71.4630), (42.2793, -71.4162), (42.2834, -71.3495),
      (42.2965, -71.2924), (42.3195, -71.2570), (42.3370, -71.2092), (42.3390, -71.1700),
      (42.3480, -71.1250), (42.3487, -71.0952), (42.3499, -71.0782)]

pts = []
for (la1, lo1), (la2, lo2) in zip(WP, WP[1:]):
    n = 500
    for i in range(n):
        t = i / n
        wig = 0.0012 * math.sin(t * math.pi * 3)          # gentle curves between towns
        lat = la1 + (la2 - la1) * t + wig + random.gauss(0, 0.00003)
        lon = lo1 + (lo2 - lo1) * t + random.gauss(0, 0.00004)
        pts.append((lat, lon))
pts.append(WP[-1])

t0 = dt.datetime(2026, 4, 20, 10, 0, 0)
step = 3.5 * 3600 / len(pts)                              # 3:30:00 in total
with open("example.gpx", "w") as f:
    f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<gpx creator="gpx_medal_tile example" version="1.1" xmlns="http://www.topografix.com/GPX/1/1">\n'
            '<trk><name>Boston Marathon (generic example)</name><type>running</type><trkseg>\n')
    for i, (lat, lon) in enumerate(pts):
        ts = (t0 + dt.timedelta(seconds=i * step)).isoformat()
        f.write(f'<trkpt lat="{lat:.6f}" lon="{lon:.6f}"><ele>{60 + 40 * math.sin(i / 900):.1f}</ele>'
                f'<time>{ts}Z</time></trkpt>\n')
    f.write('</trkseg></trk>\n</gpx>\n')
print("example.gpx", len(pts), "points")
