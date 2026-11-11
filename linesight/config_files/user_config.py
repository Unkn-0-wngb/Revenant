"""
Machine settings. The paths are worked out for whatever PC this runs on, the rest can be changed from the dashboard.
"""

import sys
from pathlib import Path
from sys import platform

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import paths

is_linux = platform in ["linux", "linux2"]

username = "Revenant"

target_python_link_path = Path(paths.TMI_PLUGIN)

trackmania_base_path = Path(paths.TRACKMANIA)

base_tmi_port = 8478

linux_launch_game_path = "path_to_be_filled_only_if_on_linux"

windows_TMLoader_path = Path(paths.TMLOADER_EXE)

windows_TMLoader_profile_name = "default"
