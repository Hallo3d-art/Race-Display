# GPX Medal Tile

Turn a GPX track into a wall-mounted hex tile for 3D printing that shows your route **and** holds your finisher medal. Designed for the Bambu Lab P1S.

![Preview](example_output/Boston_Marathon_preview.png)

- Raised route in orange, GPS noise is smoothed out automatically
- Start as a ring. On loops the ring is also the finish; on point-to-point courses the finish is a filled dot
- Race name (orange), date and distance at the top, athlete name on the left, finish time (orange) and pace on the right
- Ribbon slot (45 × 4 mm) for medals of any shape, Ø up to approx. 95 mm, ribbons 20–40 mm wide
- Dovetail pockets on all 6 edges, so several tiles can be joined into a honeycomb wall
- 6 magnet pockets (6 × 3 mm) for the wall frame

Also generated: a wall frame with 2 keyholes, a ribbon clamp and 6 connector keys.

## Download (Windows, no Python needed)

Get `gpx_medal_tile_windows.zip` from the [Releases](../../releases) page, unzip it and drag your GPX file onto `gpx_medal_tile.exe`. The console asks for race name, athlete name and finish time; the files are created next to your GPX.

To use your own Bambu Studio settings, put your `bambu_project_settings.config` next to the `.exe` (see "Printing on the P1S").

## Installation with Python (once)

1. Install Python 3.10 or newer (python.org; on Windows tick "Add to PATH" during setup).
2. On first run, `make_tile.bat` installs the packages automatically. Manually:
   `python -m pip install -r requirements.txt`

## Usage

**Easy (Windows):** drag your GPX file onto `make_tile.bat`. You will be asked for race name, athlete name and finish time (press Enter to accept the value read from the GPX).

**Command line:**
```
python gpx_medal_tile.py run.gpx --race "Vienna City Marathon" --name "Alex" --time 3:28:45
```

| Option | Meaning |
|---|---|
| `--race` | race name (shrunk automatically if it is too long) |
| `--name` | athlete name |
| `--time` | finish time `h:mm:ss`, default is the duration from the GPX |
| `--date` | date as printed, e.g. `"12 Apr 2026"`, default from the GPX |
| `--distance` | official distance in km, e.g. `21.1`, default from the GPX |
| `--extra` | extra line below the name, e.g. `"Rank 87"` |
| `--no-pace` | hide the pace |
| `--smooth` | GPS track smoothing in mm (default `0.9`, `0` = off, `1.5` = very smooth) |
| `--rotate` | rotate the route (degrees) if it looks better another way |
| `--no-frame` | only generate the tile (you already have frame, clamp and keys) |
| `--out` | output folder, default is `output_<race name>` next to the GPX |

GPX exports from Strava, Garmin, Komoot etc. work.

## Output

| File | Purpose |
|---|---|
| `*_tile_multicolor.3mf` | ready Bambu Studio project: plate 1 = tile (3 colours), plate 2 = wall frame, ribbon clamp, keys |
| `*_1_tile_base.stl` | base plate |
| `*_2_text_white.stl` | white text |
| `*_3_route_time_orange.stl` | race name, route, start/finish, finish time |
| `*_tile_single_color.stl` | everything merged, for printing with filament-change pauses |
| `wall_frame.stl`, `ribbon_clamp.stl`, `connector_keys_6x.stl` | accessories |
| `*_preview.png` | preview of the front |

## Printing on the P1S

The tile is printed face up and needs no supports. Recommended: 0.4 mm nozzle, PLA, textured PEI plate.

**With AMS:** open `*_tile_multicolor.3mf`. It is a complete Bambu Studio project with two plates:

- **Plate 1:** the tile as one object with 3 parts; filament 1 (grey), 2 (white) and 3 (orange) are already assigned. The prime tower is placed at the back left (x 4, y 213), clear of the tile.
- **Plate 2:** wall frame, ribbon clamp and connector keys, all in filament 1.

Printer, process and filament settings come from `bambu_project_settings.config` next to the script. It was taken from a project saved in Bambu Studio (P1S 0.4 nozzle, Bambu PLA Basic, 0.08 mm Extra Fine). To use your own settings: set up a project in Bambu Studio, save it, open the `.3mf` as a ZIP and copy `Metadata/project_settings.config` next to the script under that name. Without this file the script writes a standard 3MF (Bambu Studio then loads geometry and colours only).

Alternative: drag the three colour-part STLs into Bambu Studio at the same time and answer "load as a single object with multiple parts?" with Yes.

**Without AMS:** load `*_tile_single_color.stl` and add two pauses / filament changes in the layer preview:

| Height | Filament |
|---|---|
| up to 5.0 mm | grey (base) |
| from 5.0 mm | white (text, lower layers of the orange parts) |
| from 5.8 mm | orange (race name, route and time are taller, so only orange is visible on top) |

## Assembly

1. Glue in 12 magnets 6 × 3 mm, 6 in the tile and 6 in the frame. Check the polarity first so they attract.
2. Hang the frame on the wall with 2 screws (head up to 9 mm). The keyholes are at the top.
3. Push the ribbon loop through the slot from the front and pull it at the back until the medal hangs centred below the slot.
4. Press the ribbon clamp into the two holes below the slot at the back. It holds the ribbon; the rest disappears inside the frame.
5. Put the tile onto the frame.

For more races, generate new tiles (`--no-frame`) and join them at an edge with the keys.

All dimensions can be changed in the `P` dictionary at the top of the script (tile size, slot, heights, magnets).

## Privacy

GPX files contain your start location (often near home), date and time. Do not commit your own GPX files to a public repository. `example.gpx` is a synthetic, simplified Boston-style route (not the official course), created by `make_example_gpx.py`.

## License

[PolyForm Noncommercial License 1.0.0](LICENSE.md): free for personal use and for noncommercial organizations (e.g. running clubs, schools, charities). **Commercial use is not permitted**, including selling tiles made with this tool. For commercial licensing, open an issue.

## Building the exe yourself

The GitHub Action in `.github/workflows/build-exe.yml` builds and tests the Windows exe on every push. Pushing a tag such as `v1.0.0` attaches the ZIP to a release automatically.
