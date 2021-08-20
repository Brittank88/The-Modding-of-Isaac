### IMPORTS ###
# region IMPORTS

from json.decoder import JSONDecoder
from typing import Iterator, List, Tuple, Union
from pathlib2 import Path
from winreg import OpenKeyEx, QueryValueEx, HKEY_CURRENT_USER, KEY_READ
from json import loads
from re import search

# endregion

### CODE ###
# region CODE

def find_steam_location() -> Union[Path, None]:
    """Determines the location of Steam on the target system by extracting it from the registry.
    
    Will return:
        - A Path object targeting the Steam executable.
        - None if the registry key was not found.
    """

    try:
        with OpenKeyEx(HKEY_CURRENT_USER, 'SOFTWARE\\Valve\\Steam', 0, KEY_READ) as steam_key:
            return Path(QueryValueEx(steam_key, 'SteamPath')[0])
    except FileNotFoundError: return None

def find_steam_library_folders() -> Union[Iterator[Path], None]:
    """Determines the location of any Steam library folders, via 'libraryfolders.vdf'.

    Will return:
        - A generator of path objects targeting steam library folder roots if there were multiple.
        - None if we couldn't find the Steam directory.
    
    See: https://stackoverflow.com/a/34091380/7913061
    """

    # Get the steam path and check if it is valid.
    try: steam_path: Path = find_steam_location().parent
    except AttributeError: return None

    # Create the default Steam library path.
    default_lib_path: List[Path] = [steam_path / 'steamapps']

    # Get the path to libraryfolders.vdf and check that it exists. If not, we'll return the default Steam library path.
    vdf_path: Path = steam_path / 'steamapps/libraryfolders.vdf'
    if not vdf_path.exists(): return default_lib_path

    # Read the libraryfolders.vdf content and convert it to a valid JSON object.
    vdf_json = loads(vdf_path.read_text().replace('"LibraryFolders"', '').strip(' \n').replace('\t\t', ':').replace('"\n', '",\n').replace(',\n}', '\n}'))

    # Filter the libraries out of the JSON  and return them (alongside the default path).
    # Note: There are a maximum of 7 Steam library paths, hence '1234567'.
    libraries_list = [Path(vdf_json[key]) / 'steamapps' for key in vdf_json.keys() if str(key) in '1234567'] + default_lib_path

    # Return a generator for the list of library path objects.
    return (l for l in libraries_list)

def find_boi_data_folders() -> Union[Tuple[Path, Path], None]:
    """Determines the location of BoI's save data and mod folders, via 'savedatapath.txt'.
    
    Will return:
        - A tuple of two path objects, pointing to the save data and mod folders respectively.
        - None if we couldn't find, open or extract the paths from 'savedatapath.txt'.
    """

    # This is the path we will use to locate 'savedatapath.txt'.
    lib_folder: Union[Path, None] = None

    # We need to test all library folders for the game.
    for lib_folder in find_steam_library_folders():

        # Navigate to where BoI should be.
        lib_folder /= 'common/The Binding of Isaac Rebirth'

        # If this path exists, we know we have the correct library folder and can move on.
        if lib_folder.exists(): break

        # This will cause lib_folder to be None if we naturally exit the loop.
        lib_folder = None

    # If we didn't find the game, we can't continue.
    if lib_folder is None: return None

    # Point to the file and test for existence.
    lib_folder /= 'savedatapath.txt'
    if not lib_folder.exists(): return None

    # Attempt to extract the two paths from the file.
    text = lib_folder.read_text()
    try:
        save_path : str = Path(search('Save Data Path: (.+?)\n'   , text).group(1))
        mods_path : str = Path(search('Modding Data Path: (.+?)\n', text).group(1))
    # Return None if extraction failed.
    except AttributeError: return None
    # If we succeeded we'll package the path objects into a dictionary and return it.
    else: return save_path, mods_path

# endregion

### TESTING ###
# region TESTING

if __name__ == '__main__':

    print(f'Steam.exe location  : {find_steam_location()}'             )
    print(f'Steam library paths : {list(find_steam_library_folders())}')
    print(f'BoI data paths      : {find_boi_data_folders()}'           )

# endregion
