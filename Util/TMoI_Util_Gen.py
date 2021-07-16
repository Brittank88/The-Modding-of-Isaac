### IMPORTS ###

from __future__ import annotations

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Union
from datetime import datetime

from lxml.etree import parse, ParseError, _ElementTree, _Element
from lxml.html import HtmlElement, fromstring
from lxml.cssselect import CSSSelector

from requests import get
from requests.models import HTTPError, Response

from urllib.parse import urlparse, parse_qs

from pathlib2 import Path

from textwrap import shorten

### GLOBALS ###

MOD_LIST                          : List[Mod] = []
ABP_RELEASE_DATE                  : datetime  = datetime(year = 2017 , month = 1 , day = 3  , hour = 23 , minute = 14 , second = 0 )
REP_RELEASE_DATE                  : datetime  = datetime(year = 2021 , month = 3 , day = 31 , hour = 6  , minute = 48 , second = 58)
WORKSHOP_ADDON_LINK_PREFIX        : str       = 'https://steamcommunity.com/sharedfiles/filedetails/?id='
DEFAULT_UNKNOWN_MOD_ID            : int       = -1
STEAM_DATETIME_FORMAT_STR         : str       = '%d %b, %Y @ %I:%M%p'
STEAM_DATETIME_FORMAT_STR_NO_YEAR : str       = '%d %b @ %I:%M%p'
REPR_TAB_WIDTH                    : int       = 2

### CLASSES ###

#=# EXCEPTIONS #=#

@dataclass(frozen = True)
class ModError(Exception):
    """Base class for all mod-related exceptions."""

    id  : int              = field(init = True, default = DEFAULT_UNKNOWN_MOD_ID)
    msg : Union[str, None] = field(init = True, default = None)
    
    # Change the error message appropriately.
    def __post_init__(self):
        if self.msg is None: object.__setattr__(self, 'msg', f'An unspecified error occurred when handling mod with ID == {self.id}!')

@dataclass(frozen = True)
class ModNotInstalledError(ModError):
    """Raised when a mod that was expected to be installed is not found."""

    # Change the error message appropriately.
    def __post_init__(self): object.__setattr__(self, 'msg', f'Mod with ID == {super().id} is not installed!')

@dataclass(frozen = True)
class ModAddonNotFoundError(ModError):
    """Raised when the mod's addon in the Steam Workshop is not found."""

    # Change the error message appropriately.
    def __post_init__(self): object.__setattr__(self, 'msg', f'Mod with ID == {super().id} could not be found on the Steam Workshop!')

@dataclass(frozen = True)
class ModInstanceInvalidError(ModError):
    """Raised when a retrieved reference to a mod instance is not actually a valid Mod class instance."""

    # Change the error message appropriately.
    def __post_init__(self): object.__setattr__(self, 'msg', f'Mod with ID == {super().id} is not a valid Mod class instance!')

@dataclass(frozen = True)
class ModCircularDependencyError(ModError):
    """Raised when mods form a circular dependency chain."""

    other_ids : List[int] = field(init = True, default = list)

    # Change the error message appropriately.
    def __post_init__(self): object.__setattr__(self, 'msg', f'Mods with IDs == {[super().id] + self.other_ids} form a circular dependency chain!')

#=# ENUMS #=#

class IsaacVer(Enum):
    REP = 0
    ABP = 1

class DataPathType(Enum):
    SAVE = 0
    MODS = 1

#=# DATACLASSES #=#

@dataclass
class ModAuthor:
    """Represents basic information about a BoI mod author."""

    name     : str = '' # The author's name.
    url      : str = '' # The author's page URL.
    icon_url : str = '' # The URL of the author's profile image.

    def __str__(self):

        ljust_val : int = 9

        # Calculate all the property strings to display.
        qual_name      : str = self.__class__.__qualname__
        info_title_str : str = _t(1 , '' ) + 'Info:'
        name_str       : str = _t(2 , '│') + 'name'     . ljust(ljust_val) + f'= {self.name}'
        url_str        : str = _t(2 , '│') + 'url'      . ljust(ljust_val) + f'= {self.url}'
        icon_url_str   : str = _t(2 , '╰') + 'icon_url' . ljust(ljust_val) + f'= {self.icon_url}'

        return f'{qual_name} (' + '\n' + \
               info_title_str   + '\n' + \
               name_str         + '\n' + \
               url_str          + '\n' + \
               icon_url_str     + '\n' + \
               ')'

@dataclass
class Mod:  # TODO: Allow this class to handle missing dependencies / dependents.

    # Init Vars
    ref       : Union[int, Path]  = field(init = True)                  # Path object targeting the directory the mod resides in, or the mod's workshop addon ID.
    mods_path : Union[Path, None] = field(init = True, default = None)  # Path object targeting the directory that all mods reside in. Required when we only have a workshop addon ID.
    register  : Union[bool, None] = field(init = True, default = True)  # Whether the mod should register itself in the global list of mods.

    # Metadata XML File
    name         : Union[str             , None] = None # Mod's display name in-game.
    id           : Union[str             , None] = None # The ID of the mod's addon in the Steam Workshop.
    description  : Union[str             , None] = None # The full description of the mod.
    version      : Union[str             , None] = None # The version of the mod as defined by the mod author.
    visibility   : Union[str             , None] = None # The visibility of the mod's addon in the Steam Workshop.
    last_updated : Union[datetime        , None] = None # The date the addon was last updated.
    uploaded     : Union[datetime        , None] = None # The date the addon was first uploaded to the workshop.
    authors      : Union[List[ModAuthor] , None] = None # The author/s of the mod.
    size         : Union[str             , None] = None # The file size of the mod.
    preview      : Union[str             , None] = None # The preview image of the mod.

    # Internal
    position           : int            = -1                            # The position of the mod, which determines its load order.
    dependencies       : List[Mod]      = field(default_factory = list) # All mods that this mod requires to be loaded first.
    dependents         : List[Mod]      = field(default_factory = list) # All mods that require that this mod is loaded first.
    warning_exceptions : List[ModError] = field(default_factory = list) # Any warnings this mod has about itself.

    def __post_init__(self):

        # If we have a path reference to the mod, we can calculate the mods folder path quite easily.
        # This means that self.mods_path is a reliable source to reference in code.
        if isinstance(self.ref, Path): self.mods_path = self.ref.parent

        # This holds a reference to the mod's 'metadata.xml' if we were able to find it (else, is None).
        meta_tree : Union[_ElementTree, None] = None

        # If we're working with a path we can immediately get a reference to 'metadata.xml'.
        if isinstance(self.ref, Path):

            # Get path to 'metadata.xml' and check for existence.
            meta_path: Path = self.ref / 'metadata.xml'
            if not meta_path.exists(): raise FileNotFoundError('Cannot find metadata.xml!')

            # Parse the XML file.
            try                    : meta_tree = parse(meta_path.as_posix())
            except ParseError as e : raise type(e)(f'Could not parse metadata XML!\n\n### ORIGINAL ERROR ###\n\n{e}')

        # If we're working with an addon ID, we'll have to search for the appropriate mod folder.
        elif isinstance(self.ref, int):

            # We will need the mods directory - if it isn't supplied, raise an error.
            if self.mods_path is None or not self.mods_path.is_dir():
                raise NotADirectoryError(f'Mods path ({self.mods_path}) is invalid or was not supplied and is required when building mods from a Steam Workshop ID!')

            # Loop through each mod folder in the mods directory and try to find the mod with the correct workshop addon ID in 'metadata.xml'.
            for mod_folder in self.mods_path.iterdir():

                # Iteration also iterates files, which we don't want.
                if not mod_folder.is_dir(): continue

                # Try to target 'metadata.xml', skip the subfolder if we fail.
                meta_path: Path = mod_folder / 'metadata.xml'
                if not meta_path.exists(): continue

                # Parse the XML file.
                try               : meta_tree = parse(meta_path.as_posix())
                except ParseError : continue

                # Try to match the mod addon ID to the ID we have been provided.
                # There are some mod folder entries whereby the metadata.xml doesn't have an ID element and will cause an AttributeError - we will ignore these.
                try:
                    if str(self.ref) == meta_tree.find('id').text: break
                except AttributeError: continue

                # If the mod folder wasn't found, we need to nullify meta_tree so we can pick that up later.
                meta_tree = None

        # If the supplied value wasn't a Path object or integer, it is invalid.
        else: raise TypeError(f'Initialisation argument is of incorrect type ({type(self.ref)})!')

        # If we didn't find the mod, meta_tree will be None and we should raise an appropriate error.
        if meta_tree is None: raise ModNotInstalledError(id = self.ref if isinstance(self.ref, int) else DEFAULT_UNKNOWN_MOD_ID)

        # These will hold all the values we wish to extract from the XML.
        name_root        : _Element
        id_root          : _Element
        description_root : _Element
        version_root     : _Element
        visibility_root  : _Element

        # Sanity check all fields before we begin extraction.
        if None in (
            name_root        := meta_tree.find('name')        ,
            id_root          := meta_tree.find('id')          ,
            description_root := meta_tree.find('description') ,
            version_root     := meta_tree.find('version')     ,
            visibility_root  := meta_tree.find('visibility')
        ): raise ParseError('Metadata XML file is missing expected mod info!')

        # Extract all the fields we can from 'metadata.xml'.
        self.name        = name_root        .text
        self.id          = id_root          .text
        self.description = description_root .text
        self.version     = version_root     .text
        self.visibility  = visibility_root  .text

        # We will have to scrape the rest of the data we need from the addon page, so we will begin by requesting the page data.
        addon_page: Response = get(addon_url := WORKSHOP_ADDON_LINK_PREFIX + self.id)
        try: addon_page.raise_for_status()
        except HTTPError as e:
            # 404 means the addon page doesn't even exist.
            if e.response.status_code == 404:
                raise ModAddonNotFoundError(
                    id = self.id,
                    msg = f'Addon page at {addon_url} is nonexistent!\nStatus code: {e.response}\n\n### ORIGINAL ERROR ###\n\n{e}'
                )
            # Something other than 404 means the page exists, but we still failed to retrieve the HTML.
            else: raise type(e)(f'Could not access addon page at {addon_url}!\nStatus code: {e.response}\n\n### ORIGINAL ERROR ###\n\n{e}')

        # We will parse the requested page content with LXML.
        try                    : addon_html: HtmlElement = fromstring(addon_page.content)
        except ParseError as e : raise type(e)(f'Could not parse addon page HTML!\n\n### ORIGINAL ERROR ###\n\n{e}')

        # Get all of the elements corresponding to uploaded, last updated and file size attributes (and their labels).
        for file_meta_elem_tup in zip(
            CSSSelector('div.rightDetailsBlock>div>div.detailsStatLeft')(addon_html)  ,
            CSSSelector('div.rightDetailsBlock>div>div.detailsStatRight')(addon_html)
        ):
            # Use each label to assign the appropriate class attribute to the its associated value.
            if   file_meta_elem_tup[0].text == 'Updated '   : self.last_updated = parse_steam_datetime(file_meta_elem_tup[1].text)
            elif file_meta_elem_tup[0].text == 'Posted '    : self.uploaded     = parse_steam_datetime(file_meta_elem_tup[1].text)
            elif file_meta_elem_tup[0].text == 'File Size ' : self.size         = file_meta_elem_tup[1].text
            else                                            : continue

        # Grab the addon's main preview image URL.
        try: self.preview = CSSSelector('img#previewImageMain')(addon_html)[0].get('src')
        except IndexError: self.preview = CSSSelector('img#previewImage')(addon_html)[0].get('src')

        # Process dependency mods for this mod.
        for req_item_elem in CSSSelector('div#RequiredItems>a')(addon_html):

            # Extract the addon ID of the mod from its Steam Workshop URL.
            try                        : item_ref : int = int(parse_qs(urlparse(req_item_elem.get('href')).query)['id'][0])
            except AttributeError as e : raise type(e)(f'Parsing dependency mod URL query string failed!\n\n### ORIGINAL ERROR ###\n\n{e}'     )
            except KeyError       as e : raise type(e)(f'Dependency mod URL query string has no ID parameter!\n\n### ORIGINAL ERROR ###\n\n{e}')
            except ValueError     as e : raise type(e)(f'Parsing dependency mod ID to integer failed!\n\n### ORIGINAL ERROR ###\n\n{e}'        )

            # Get or create the mod instance for this dependency, using its Steam Workshop URL.
            # If the creation of the dependency mod object raises any errors, they will be caught and either noted as a warning or raised.
            new_dep : Union[Mod, None] = None
            try                                                       : new_dep = ModFactory.build(item_ref, self.mods_path)
            except (ModNotInstalledError, ModAddonNotFoundError) as e : self.warning_exceptions.append(e)
            except ModInstanceInvalidError                       as e : raise type(e)(
                id = item_ref,
                msg = f'ModFactory failed to fetch existing dependency mod instance reference!\n\n### ORIGINAL ERROR ###\n\n{e}'
            )

            # If new_dep is None we encountered ModNotInstalledError or ModAddonNotFoundError and should just record the ref and add to this mod's dependencies list.
            if new_dep is None:
                new_dep = item_ref
                # Add the mod instance to this mod's dependency list.
                self.dependencies.append(new_dep)

            # If new_dep is a Mod, we can also add this mod to that mod's dependents list (and check for basic circular dependency chains).
            else:
                # Add this mod to the mod's dependents list.
                new_dep.dependents.append(self)
                # Basic check to see if this pair causes a circular dependency chain.
                if self in new_dep.dependencies: self.warning_exceptions.append(ModCircularDependencyError(id = self.id, other_ids = [new_dep.id]))

        # Process authors for this mod.
        self.authors = [
            ModAuthor(
                author_elem_tup[0].text.lstrip() ,
                author_elem_tup[1].get('href')   ,
                author_elem_tup[2].get('src')
            ) for author_elem_tup in zip(
                CSSSelector('div.creatorsBlock>div.friendBlock>div.friendBlockContent'  )(addon_html) ,
                CSSSelector('div.creatorsBlock>div.friendBlock>a.friendBlockLinkOverlay')(addon_html) ,
                CSSSelector('div.creatorsBlock>div.friendBlock>div.playerAvatar>img'    )(addon_html)
            )
        ]

        # Finally, register this mod in the global mod list.
        MOD_LIST.append(self)

    def __str__(self):

        ljust_val  : int = 17   # Adjustable justification for main equals sign alignment.

        # Calculate all the property strings to display.
        qual_name        : str = self.__class__.__qualname__
        meta_title       : str = _t(1 , '' ) + 'Metadata:'
        name_str         : str = _t(2 , '│') + 'name'         . ljust(ljust_val) + f'= {self.name}'
        id_str           : str = _t(2 , '│') + 'id'           . ljust(ljust_val) + f'= {self.id}'
        size_str         : str = _t(2 , '│') + 'size'         . ljust(ljust_val) + f'= {self.size}'
        version_str      : str = _t(2 , '│') + 'version'      . ljust(ljust_val) + f'= {self.version}'
        uploaded_str     : str = _t(2 , '│') + 'uploaded'     . ljust(ljust_val) + f'= {self.uploaded}'
        last_updated_str : str = _t(2 , '│') + 'last_updated' . ljust(ljust_val) + f'= {self.last_updated}'
        authors_str      : str = _process_authors_str(pipe = '│' , authors = self.authors , ljust_val = ljust_val)
        description_str  : str = _t(2 , '│') + 'description'  . ljust(ljust_val) + f'= {shorten(self.description, 128)}'
        visibility_str   : str = _t(2 , '│') + 'visibility'   . ljust(ljust_val) + f'= {self.visibility}'
        preview_str      : str = _t(2 , '╰') + 'preview'      . ljust(ljust_val) + f'= {self.preview}'
        internal_title   : str = _t(1 , '' ) + 'Internal:'
        ref_str          : str = _t(2 , '│') + 'ref'          . ljust(ljust_val) + f'= {self.ref.__class__.__qualname__} ({self.ref})'
        mods_path_str    : str = _t(2 , '│') + 'mods_path'    . ljust(ljust_val) + f'= {self.mods_path.__class__.__qualname__} ({self.mods_path})'
        register_str     : str = _t(2 , '│') + 'register'     . ljust(ljust_val) + f'= {self.register}'
        position_str     : str = _t(2 , '│') + 'position'     . ljust(ljust_val) + f'= {self.position}'
        dependencies_str : str = _process_deps_str(pipe = '│' , deps = self.dependencies , ljust_val = ljust_val)
        dependents_str   : str = _process_deps_str(pipe = '╰' , deps = self.dependents   , ljust_val = ljust_val)

        # Assemble all property strings and return.
        return  f'{qual_name} ('     + '\n' + \
                    meta_title       + '\n' + \
                    name_str         + '\n' + \
                    id_str           + '\n' + \
                    size_str         + '\n' + \
                    version_str      + '\n' + \
                    uploaded_str     + '\n' + \
                    last_updated_str + '\n' + \
                    authors_str      + '\n' + \
                    description_str  + '\n' + \
                    visibility_str   + '\n' + \
                    preview_str      + '\n' + \
                    '\n'                    + \
                    internal_title   + '\n' + \
                    ref_str          + '\n' + \
                    mods_path_str    + '\n' + \
                    register_str     + '\n' + \
                    position_str     + '\n' + \
                    dependencies_str + '\n' + \
                    dependents_str   + '\n' + \
                ')'

class ModFactory:
    """A non-instantiable class used to create Mod instances only if they do not already exist."""

    def __new__(cls, *args, **kwargs):
        if cls is ModFactory: raise TypeError('ModFactory cannot be instantiated!')
        return object.__new__(cls, *args, **kwargs)

    @staticmethod
    def build(
        ref       : Union[int  , Path] ,
        mods_path : Union[Path , None] = None
    ) -> Mod:
        try:
            # If we couldn't retrieve a reference, create a new mod instance (which will self-register) and return it.
            if (exist_mod := next((m for m in MOD_LIST if m.ref == ref), None)) is None: return Mod(ref = ref, mods_path = mods_path, register = True)
            # If we were able to retrieve an existing reference, we'll simply return it.
            elif isinstance(exist_mod, Mod): return exist_mod
            # If what we retrieved somehow isn't a Mod instance reference, we should definitely raise an exception.
            else: raise ModInstanceInvalidError(
                id = ref if isinstance(ref, int) else -1,
                msg = f'Somehow, the object retrieved from the global mod list is not of type Mod, but instead of type {type(exist_mod)}!'
            )
        # If the creation of the mod object raises any errors, they will be caught and re-raised here.
        except (ModNotInstalledError, ModAddonNotFoundError) as e: raise type(e)(id = ref, msg = f'Mod instance could not be created!\n\n### ORIGINAL ERROR ###\n\n{e}')

### FUNCTIONS ###

def parse_steam_datetime(steam_datetime: str) -> datetime:
    """Attempts to parse a datetime string as seen on the Steam Workshop."""

    try:
        return datetime.strptime(steam_datetime, STEAM_DATETIME_FORMAT_STR)
    except ValueError:
        try:
            ret = datetime.strptime(steam_datetime, STEAM_DATETIME_FORMAT_STR_NO_YEAR)
            return ret.replace(year = datetime.now().year)
        except ValueError as e: raise type(e)(f'Failed to parse Steam datetime string!\n\n### ORIGINAL ERROR ###\n\n{e}')

### PRIVATE FUNCTIONS ###

# Helper function to produce a string of <n> tabs of <tab_width> width,
# with <c> inserted such that there is a single whitespace between it and the end of the string.
def _t(n: int, c: str) -> str:
    """Helper function to produce a string of <n> tabs of <tab_width> width.

    The parameter <c> inserted such that there is a single whitespace between it and the end of the string.
    """

    return (n * REPR_TAB_WIDTH * ' ')[:-REPR_TAB_WIDTH] + c + ' ' * (REPR_TAB_WIDTH - len(c))

def _pad_str_line(line: str, ljust_val: int):
    """Takes a completed str line and pads the equal sign to the target position."""

    # if there are no equals signs we have nothing to align.
    if '=' not in line: return line

    # Split the line up into what comes before and after the equal sign (accounting for the possibility of multiple equal signs).
    before, *after = line.split('=')

    # We only want from the label forward.
    #if   (pipe := '│') in before : tab , *before = before.split('│')
    #elif (pipe := '╰') in before : tab , *before = before.split('╰')

    # Reconstruct the line, with what comes before the equal sign being padded to the appropriate length.
    return f'{before.ljust(ljust_val)}={"".join(after)}'

def _process_authors_str(pipe: str, authors: List[ModAuthor], ljust_val: int) -> str:
    """Helper function to process a list of ModAuthors into a human-readable string."""

    return _t(2 , pipe) + 'authors'.ljust(ljust_val) + '= [' + (
        # If there are no authors we shouldn't place anything between the square brackets.
        '' if len(authors) == 0 else (
            # Move to next line.
            '\n'
            # We'll need to indent each line of each author repr appropriately.
            + ''.join([
                _t(2 , '│') + _pad_str_line(line = _t(1 , '') + l + '\n', ljust_val = ljust_val)
                for a in authors
                for l in str(a).split('\n')
            ])
            # Indent the final bracket, which will be on a new line.
            + _t(2 , '│')
        )
    ) + ']'

def _process_deps_str(deps: List[Union[Mod, int]], ljust_val: int, pipe: str) -> str:
    """Helper function to process a list of Mod and int addon references into a human-readable string."""

    return _t(2 , pipe) + 'dependencies'.ljust(ljust_val) + '= [' + (
        '' if len(deps) == 0 else (
            # Move to next line.
            '\n'
            # List each mod in simplest form.
            + ''.join([
                # Correct indentation.
                _t(2 , '│') + _t(1 , '')
                # Mod's simplest form.
                + (
                    f'{d.__class__.__qualname__} (name = {d.name}, ref = {d.ref}, id = {d.id}, size = {d.size})'
                    if isinstance(d, Mod) else
                    f'{d.__class__.__qualname__} ({d})'
                )
                # Newline for next mod (and for closing square bracket).
                + '\n'
                for d in deps
            ])
            # Indent the final bracket, which will be on a new line.
            + _t(2 , '│')
        )
    ) + ']'

### TESTING ###

if __name__ == '__main__':

    example_mod = Mod(Path('D:\Steam Library\steamapps\common\The Binding of Isaac Rebirth\mods\seinfeld death music_1229025788'))
    print(example_mod)
