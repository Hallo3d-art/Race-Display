@rem //ai
@echo off
rem Drag a GPX file onto this file (drag & drop) or double-click it.
chcp 65001 >nul
cd /d "%~dp0"
rem install the required Python packages on first run
python -c "import trimesh, shapely, manifold3d, mapbox_earcut, matplotlib, lxml, networkx" 2>/dev/null || (
    echo Installing required Python packages ...
    python -m pip install -r requirements.txt
)
python gpx_medal_tile.py %*
echo.
pause
