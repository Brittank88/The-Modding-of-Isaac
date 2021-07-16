from platform import system as get_sys
from typing import List, Union
from pathlib2 import Path

from ctypes import create_unicode_buffer, windll
from ctypes.wintypes import MAX_PATH

if get_sys() == 'Windows': from winreg import ConnectRegistry, OpenKey, QueryValue, HKEY_CLASSES_ROOT, KEY_READ

from enum import Enum

class IsaacVer(Enum):
    REP = 0
    ABP = 1

def find_steam_location(os: str = get_sys()) -> Path:
    """Determines the location of Steam on the target system."""

    if os == 'Windows':
        reg = ConnectRegistry(None, HKEY_CLASSES_ROOT)
        with OpenKey(reg, 'steam\\Shell\\Open\\Command', 0, KEY_READ) as steam_key:
            return Path(QueryValue(steam_key, '').split(' -- ')[0].replace('"', ''))

    elif os == 'Linux':
        pass

    elif os == 'Darwin':
        pass


def find_steam_library_folders(os: str = get_sys()) -> Union[List[Path], Path]:
    """Determines the location of any Steam library folders, via libraryfolders.vdf.
    
    See: https://stackoverflow.com/a/34091380/7913061
    """

    pass

def find_boi_version(doc_path: Path, os: str = get_sys()) -> IsaacVer:

    pass

def find_mods_folder(os: str = get_sys()) -> Path:
    """Determines the location of the Binding of Isaac mod folder."""
    
    if os == 'Windows':
        
        # Check current and default documents folder.
        # Credits: https://stackoverflow.com/a/30924555/7913061
        path_buffer = create_unicode_buffer(MAX_PATH)
        windll.shell32.SHGetFolderPathW(
            None ,
            5    ,  # CSIDL_PERSONAL = 5 for My Documents.
            None ,
            0    ,  # Get current, not default value.
            path_buffer
        )
        


    elif os == 'Linux':
        pass

    elif os == 'Darwin':
        pass
