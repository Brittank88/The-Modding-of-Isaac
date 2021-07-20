### IMPORTS ###
# region IMPORTS

#=# Allow Self-Annotations #=#
from __future__ import annotations

#=# Logger #=#
from loguru import logger

#=# Platform-Specific #=#
from platform import system
HOST_OS : str = system()
if   HOST_OS == 'Windows' : import TMoI_Util_Win as TMoI_Util
elif HOST_OS == 'Linux'   : import TMoI_Util_Nix as TMoI_Util
elif HOST_OS == 'Darwin'  : import TMoI_Util_Mac as TMoI_Util
else                      : logger.critical('Could not determine correct utils import for the given OS!')

#=# Data Types #=#
from enum import Enum
from dataclasses import dataclass, field
from typing import Generator, List, Tuple, Union

#=# HTTP Requesting / Parsing #=#
from requests import get
from requests.models import HTTPError, Response
from urllib.parse import urlparse, parse_qs
from time import sleep

#=# HTML / XML Parsing #=#
from lxml.etree import parse, ParseError, _ElementTree, XMLParser
from lxml.html import HtmlElement, fromstring
from lxml.cssselect import CSSSelector

#=# File System #=#
from pathlib2 import Path

#=# String Helpers #=#
from textwrap import shorten

#=# Parameters #=#
from datetime import datetime

# endregion

### GLOBALS ###
# region GLOBALS

XML_PARSER                        : XMLParser = XMLParser(recover = True)
ABP_RELEASE_DATE                  : datetime  = datetime(year = 2017 , month = 1 , day = 3  , hour = 23 , minute = 14 , second = 0 )
REP_RELEASE_DATE                  : datetime  = datetime(year = 2021 , month = 3 , day = 31 , hour = 6  , minute = 48 , second = 58)
WORKSHOP_ADDON_LINK_PREFIX        : str       = 'https://steamcommunity.com/sharedfiles/filedetails/?id='
STEAM_DATETIME_FORMAT_STR         : str       = '%d %b, %Y @ %I:%M%p'
STEAM_DATETIME_FORMAT_STR_NO_YEAR : str       = '%d %b @ %I:%M%p'
REPR_TAB_WIDTH                    : int       = 2
DEFAULT_RETRY_TIME                : int       = 5
MAX_REQUEST_RETRIES               : int       = 5

# endregion

### CLASSES ###
# region CLASSES

#=# EXCEPTIONS #=#
# region EXCEPTIONS

class ModError(Exception):
    """Base class for all mod-related exceptions."""

    def __init__(self, *args, **kwargs):

        # Store the ref, if it was provided.
        self.ref : Union[int, Path, None] = kwargs.get('ref')

        # Initialise parent class with all parameters.
        super().__init__(*args if args else f'An unspecified error occurred whilst handling a mod!')

class ModInstanceCreationError(ModError):
    """Raised when a Mod instance cannot be created at all due to lack of data."""

    def __init__(self, *args, **kwargs):

        # Initialise super class with all parameters.
        super().__init__(*args if args else f'Creation of Mod instance failed!', **kwargs)

# endregion

#=# ENUMS #=#
# region ENUMS

class IsaacVer(Enum):
    """Enum representing the game version."""

    REP     = 2
    ABP     = 1
    UNKNOWN = 0

# endregion

#=# DATACLASSES #=#
# region DATACLASSES

@dataclass
class ModAuthor:
    """Represents basic information about a BoI mod author."""

    name     : Union[str, None] = None  # The author's name.
    url      : Union[str, None] = None  # The author's page URL.
    icon_url : Union[str, None] = None  # The URL of the author's profile image.

    def __str__(self):

        # Internal property for justification value used to align '=' chars.
        ljust_val : int = 9

        # Calculate all the property strings to display.
        qual_name      : str = self.__class__.__qualname__
        info_title_str : str = _t(1 , '' ) + 'Info:'
        name_str       : str = _t(2 , '│') + 'name'     . ljust(ljust_val) + f'= {self.name}'
        url_str        : str = _t(2 , '│') + 'url'      . ljust(ljust_val) + f'= {self.url}'
        icon_url_str   : str = _t(2 , '╰') + 'icon_url' . ljust(ljust_val) + f'= {self.icon_url}'

        # Return the string, surrounded by brackets (to represent scoping).
        return f'{qual_name} (' + '\n' + \
               info_title_str   + '\n' + \
               name_str         + '\n' + \
               url_str          + '\n' + \
               icon_url_str     + '\n' + \
               ')'

@logger.catch(exception = ModInstanceCreationError, level = 40, reraise = True)
@dataclass
class Mod:

    # Init Vars #
    ref         : Union[int, Path]  = field(init = True)                        # Path object to the directory of a single installed mod, or the mod's workshop addon ID.
    mods_path   : Union[Path, None] = field(init = True, default = None)        # Path object to the directory of all installed mods. Required when we only have a workshop addon ID.
    register_to : Union[List[Mod], None] = field(init = True, default = True)   # Whether the mod should register itself in the global list of mods.

    # Metadata XML File #
    name         : Union[str             , None] = None # Mod's display name in-game.
    id           : Union[str             , None] = None # The ID of the mod's addon in the Steam Workshop.
    size         : Union[str             , None] = None # The file size of the mod.
    version      : Union[str             , None] = None # The version of the mod as defined by the mod author.
    uploaded     : Union[datetime        , None] = None # The date the addon was first uploaded to the workshop.
    last_updated : Union[datetime        , None] = None # The date the addon was last updated.
    authors      : Union[List[ModAuthor] , None] = None # The author/s of the mod.
    description  : Union[str             , None] = None # The full description of the mod.
    visibility   : Union[str             , None] = None # The visibility of the mod's addon in the Steam Workshop.
    preview      : Union[str             , None] = None # The preview image of the mod.

    # Internal #
    position           : int            = -1                            # The position of the mod, which determines its load order.
    dependencies       : List[Mod]      = field(default_factory = list) # All mods that this mod requires to be loaded first.
    dependents         : List[Mod]      = field(default_factory = list) # All mods that require that this mod is loaded first.

    metadata_ok        : bool           = True  # Tracks our ability to successfully retrieve information from the metadata.xml file.
    workshop_ok        : bool           = True  # Tracks our ability to successfully retrieve information from the Steam Workshop page.

    def __post_init__(self):

        # This holds a reference to the mod's 'metadata.xml' if we were able to find it (else, is None).
        meta_tree : Union[_ElementTree, None] = None

        # If we're working with a path we can immediately get a reference to 'metadata.xml'.
        if isinstance(self.ref, Path):

            logger.debug(f'Constructor was supplied Path "{self.ref}".')

            # Check that the path is a directory and not targeting a file.
            if not self.ref.is_dir():
                with logger.contextualize(original_error = NotADirectoryError()):
                    raise ModInstanceCreationError(f'Path "{self.ref}" is not a directory. Cannot proceed.')

            # Get path to 'metadata.xml' and check for existence.
            meta_path: Path = self.ref / 'metadata.xml'
            if not meta_path.exists(): raise ModInstanceCreationError(f'Cannot find metadata.xml for ref "{self.ref}". Cannot proceed.', ref = self.ref)

            logger.info(f'Parsing metadata.xml @ "{meta_path}"...')

            # Parse the XML file.
            try                    : meta_tree = parse(str(meta_path), XML_PARSER)
            except ParseError as e :
                with logger.contextualize(original_error = ParseError):
                    raise ModInstanceCreationError(f'Failed to parse metadata.xml @ "{meta_path}". Cannot proceed.')

        # If we're working with an addon ID, we'll have to search for the appropriate mod folder.
        elif isinstance(self.ref, int):

            logger.debug(f'Constructor was supplied integer ID "{self.ref}".')

            # We will need the mods directory - if it isn't supplied, raise an error.
            # TODO: We may actually be able to recover from this and just scrape the info from the web.
            if self.mods_path is None or not self.mods_path.is_dir():
                raise ModInstanceCreationError(f'"{self.mods_path}" is invalid and is required when building from a Steam Workshop ID. Cannot proceed.', ref = self.ref)

            logger.info(f'Searching for local (Mod @ "{self.mods_path}")...')

            # Loop through each mod folder in the mods directory and try to find the mod with the correct workshop addon ID in 'metadata.xml'.
            for mod_folder in self.mods_path.iterdir():

                # Iteration also iterates files, which we don't want.
                if not mod_folder.is_dir(): 
                    logger.trace(f'Skipping "{mod_folder}" as it is not a directory.')
                    continue

                logger.debug(f'Examining (Mod @ "{mod_folder}").')

                # Try to target 'metadata.xml', skip the subfolder if we fail.
                meta_path                 : Path = mod_folder / 'metadata.xml'
                if not meta_path.exists() : continue

                # Attempt to parse the XML file - skip this interation if we fail.
                try               : meta_tree = parse(str(meta_path), XML_PARSER)
                except ParseError : 
                    logger.warning(f'Failed to parse existing metadata.xml @ "{mod_folder}" (during search for ID "{self.ref}").')
                    continue

                # Try to match the mod addon ID to the ID we have been provided.
                # There are some mod folder entries whereby the metadata.xml doesn't have an ID element and will cause an AttributeError - we will ignore these.
                try:
                    if str(self.ref) == meta_tree.find('id').text: break
                except AttributeError:
                    logger.trace(f'Metadata file @ "{meta_path}" is missing required ID element.')
                    continue

                # If the mod folder wasn't found, we need to nullify meta_tree so we can pick that up later.
                meta_tree = None

        # If the supplied value wasn't a Path object or integer, it is invalid.
        else: raise ModInstanceCreationError(f'Initialisation argument is of incorrect type "{type(self.ref)}". Cannot proceed.')

        # If we didn't find the mod, meta_tree will be None and we should raise an appropriate error.
        if meta_tree is None: raise ModInstanceCreationError(f'Unable to find (Mod @ "{self.ref}") locally @ "{self.mods_path}". Cannot proceed.', ref = self.ref)

        # Attempt to extract each target attribute from the metadata.
        attrs = ('name', 'id', 'description', 'version', 'visibility')
        logger.info(f'Extracting {", ".join(attrs)} from metadata...')
        for attr in attrs:

            logger.debug(f'Extracting "{attr}" from metadata...')

            # For each attribute, attempt to extract it, and respond appropriately to failure.
            try: self.__setattr__(attr, meta_tree.find(attr).text)
            except AttributeError:
                # If the ID is missing, warn about it and note that we will be unable to scrape Steam Workshop information.
                if attr == 'id' :
                    logger.error('Could not determine mod addon ID - aborting Steam Workshop scrape.')
                    self.workshop_ok = False
                # If any other value is missing, just warn about it.
                else            : logger.warning(f'Could not find mod attribute "{attr}" in metadata.xml file.')
                continue
            else: logger.success(f'Extracted {attr}!')

        logger.debug('Checking if HTML retrieval can begin...')

        # We can only scrape from the Steam Workshop if we have the ability and permission to.
        if self.workshop_ok and self.id:

            # Construct URL.
            addon_url : str = WORKSHOP_ADDON_LINK_PREFIX + self.id

            logger.success(f'OK to attempt retrieval of HTML @ "{addon_url}"!')

            # Count our retries so we know when to abort.
            retry_attempts : int = 0
            # We will have a limited amount of attempts to scrape the rest of the data we want from the addon page.
            while (retry_attempts <= MAX_REQUEST_RETRIES):

                logger.bind(attempt = retry_attempts).debug(f'Requesting HTML from "{addon_url}".')

                # We will begin by requesting the page data.
                addon_page            : Response = get(addon_url)
                try                   :
                    if addon_page.raise_for_status() is None: break
                except HTTPError as e :

                    # 429 means we were rate-limited and should try again after an appropriate delay.
                    if e.response.status_code == 429:

                        logger.bind(attempt = retry_attempts).warning(
                            f'Status code "{e.response.status_code}" indicates that we encountered a rate limit. Checking for a Retry-After header...'
                        )

                        retry_delay : int = DEFAULT_RETRY_TIME
                        if (retry_after_header := e.response.headers.get('Retry-After')) is not None:

                            logger.bind(attempt = retry_attempts).success('Retry-After header found! Extracting retry delay time...')

                            try               : retry_delay = int(retry_after_header)
                            except ValueError : retry_delay = (datetime.strptime(retry_after_header, '%a, %d %b %Y %H:%M:%S %Z') - datetime.now()).second

                            logger.bind(attempt = retry_attempts).success(f'Retry delay time of {retry_delay} seconds extracted!')

                        else: logger.bind(attempt = retry_attempts).warning(f'No Retry-After header found - waiting {DEFAULT_RETRY_TIME} seconds to retry...')

                        # Sleep until next attempt.
                        sleep(retry_delay)

                        # Increment retry count.
                        retry_attempts += 1

                    # 404 means the addon page doesn't even exist.
                    elif e.response.status_code == 404:
                        logger.bind(attempt = retry_attempts).warning(
                            f'Status code "{e.response.status_code}" indicates addon page @ "{addon_url}" is nonexistent. Maybe it was removed?'
                        )
                        break

                    # Something other than 404 means the page exists, but we still failed to retrieve the HTML.
                    else:
                        logger.bind(attempt = retry_attempts).warning(
                            f'Status code "{e.response.status_code}" indicates failure to retrieve HTML of "{addon_url}". Retrying after {DEFAULT_RETRY_TIME} seconds...'
                        )
                        
                        # Sleep until next attempt.
                        sleep(DEFAULT_RETRY_TIME)

                        # Increment retry count.
                        retry_attempts += 1

            # Error if we were unable to retrieve the addon page HTML.
            if retry_attempts > MAX_REQUEST_RETRIES:
                logger.error(f'Failed to retrieve HTML @ "{addon_url}" after {MAX_REQUEST_RETRIES} retries. Aborting Steam Workshop scrape.')
                self.workshop_ok = False

            # We will parse the requested page content with LXML and handle failure to do so appropriately.
            try               : addon_html: HtmlElement = fromstring(addon_page.content)
            except ParseError :
                logger.error(f'Failed to parse HTML retrieved from "{addon_url}". Aborting Steam Workshop scrape.')
                self.workshop_ok = False

            # If the addon doesn't exist, we'll reach the Steam error page, and should handle this appropriately.
            if len(CSSSelector('div.error_ctn')(addon_html)) > 0:
                logger.error(f'Steam error page indicates addon page @ "{addon_url}" is nonexistent. Maybe it was removed? Aborting Steam Workshop scrape.')
                self.workshop_ok = False

            logger.debug(f'Checking if scraping from "{addon_url}" HTML can begin...')

            # We have to re-check self.workshop_ok now that we can determine if HTML retrieval was successful.
            if self.workshop_ok:

                logger.success(f'OK to scrape from "{addon_url}" HTML!')

                logger.info('Attempting extraction of last update datetime, first upload datetime and file size...')

                # Get all of the elements corresponding to uploaded, last updated and file size attributes (and their labels).
                for file_meta_elem_tup in zip(
                    CSSSelector('div.rightDetailsBlock>div>div.detailsStatLeft')(addon_html)  ,
                    CSSSelector('div.rightDetailsBlock>div>div.detailsStatRight')(addon_html)
                ):
                    logger.trace(f'Attempting extraction from {file_meta_elem_tup}...')

                    # Use each label to assign the appropriate class attribute to the its associated value.
                    if   file_meta_elem_tup[0].text == 'Updated '   :
                        self.last_updated = parse_steam_datetime(file_meta_elem_tup[1].text)
                        logger.success('Extracted time of last update!')
                    elif file_meta_elem_tup[0].text == 'Posted '    :
                        self.uploaded     = parse_steam_datetime(file_meta_elem_tup[1].text)
                        logger.success('Extracted time of first upload!')
                    elif file_meta_elem_tup[0].text == 'File Size ' :
                        self.size         = file_meta_elem_tup[1].text
                        logger.success('Extracted addon size!')
                    else                                            : continue

                logger.info('Attempting extraction of preview image...')

                # Grab the addon's main preview image URL.
                try               : self.preview = CSSSelector('img#previewImageMain')(addon_html)[0].get('src')
                except IndexError :
                    try               : self.preview = CSSSelector('img#previewImage')(addon_html)[0].get('src')
                    except IndexError : logger.warning('Failed to retrieve preview image.')
                    else              : logger.success('Extracted preview image (img#previewImage)!')
                else              : logger.success('Extracted preview image (img#previewImageMain)!')

                logger.info('Attempting extraction of required items...')

                # Process dependency mods for this mod.
                for req_item_elem in CSSSelector('div#RequiredItems>a')(addon_html):

                    logger.trace(f'Parsing required item "{req_item_elem}".')

                    # Extract the addon ID of the mod from its Steam Workshop URL.
                    try                        : item_ref : int = int(parse_qs(urlparse(req_item_elem.get('href')).query)['id'][0])
                    except AttributeError as e : logger.warning(f'Parsing dependency mod URL query string failed!'     )
                    except KeyError       as e : logger.warning(f'Dependency mod URL query string has no ID parameter!')
                    except ValueError     as e : logger.warning(f'Parsing dependency mod ID to integer failed!'        )

                    # Get or create the mod instance for this dependency, using its Steam Workshop URL.
                    # If the creation of the dependency mod object raises any errors, they will be caught and either noted as a warning or raised.
                    logger.debug(f'Attempting to build mod instance via ref "{item_ref}"...')
                    new_dep                         : Union[Mod, None] = None
                    try                             : new_dep = ModFactory.build(item_ref, self.mods_path)
                    except ModInstanceCreationError : logger.warning(f'Failed to build dependency (Mod @ "{item_ref}") for (Mod @ "{self.ref}").')

                    logger.debug(f'Checking if OK to create link (Mod @ {self.ref} <=> Mod @ {item_ref})...')

                    # If the new dependency instance is valid, we can create a linkage between that mod and this one.
                    if isinstance(new_dep, self.__class__):

                        logger.info(f'Mod @ {self.ref} has Mod @ {item_ref} as a dependency. Linking...')

                        # Add this mod to the mod's dependents list.
                        new_dep.dependents.append(self)

                        # Add the dependency mod to this mod's dependencies list.
                        self.dependencies.append(new_dep)

                        # TODO: Detect 2-mod circular dependencies AND be able to react to it.
                        if (new_dep.dependencies.count(self) > 0): logger.warning(f'Link (Mod @ {self.ref} <=> Mod @ {item_ref}) creates a circular dependency chain!')

                    else: logger.warning(f'Cannot create link (Mod @ {self.ref} <=> Mod @ {item_ref}).')

                if (dep_count := len(self.dependencies)) > 0: logger.success(f'Successfully extracted {dep_count} dependencies!')
                else                                        : logger.info   ('Mod has no dependencies.')

                logger.info('Attempting extraction of authors...')

                # Process authors for this mod.
                try:
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
                except IndexError: logger.warning(f'Failed to extract authors for (Mod @ "{self.ref}").')
                else             : logger.success(f'Successfully extracted {len(self.authors)} authors!')

            else: logger.warning(f'Scraping from "{addon_url}" HTML must be aborted.')

        else: logger.warning('HTML retrieval must be aborted.')

        # Register this mod in the unified mod list.
        self.__register_self()

    def __register_self(self):
        """Method by which a mod instance registers itself in the list supplied to it."""

        # Register this mod in the unified mod list.
        if self.register_to and isinstance(self.register_to, list):
            logger.info(f'Self-registering as mod #{len(self.register_to) + 1}...')
            self.register_to.append(self)

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
                                       '\n' + \
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

    # This is the unified list that holds references to all parsed mods.
    MOD_LIST: List[Mod] = []

    def __new__(cls, *args, **kwargs):
        if cls is ModFactory: raise TypeError('ModFactory cannot be instantiated!')
        return object.__new__(cls, *args, **kwargs)

    @staticmethod
    def build(
        ref       : Union[
            Union    [      int , Path ] ,
            List     [Union[int , Path]] ,
            Generator[Union[int , Path]]
        ],
        mods_path : Union[Path , None] = None
    ) -> Union[Tuple[List[Mod], List[Union[int, Path]]], Mod]:
        """Dispatches to either the single or multiple ref build function depending on whether the ref parameter is singular or iterable."""

        if isinstance(ref, (int, Path))         : return ModFactory.__build_singular(ref, mods_path)
        elif isinstance(ref, (List, Generator)) : return ModFactory.__build_multiple(ref, mods_path)
        else                                    : raise TypeError(f'ModFactory could not understand ref input of type {type(ref)}!')

    @staticmethod
    def __build_multiple(
        refs      : Union[
            List     [Union[int, Path]] ,
            Generator[Union[int, Path]]
        ],
        mods_path : Union[Path, None] = None
    ) -> List[Mod]:
        """Attempts to build a list of mods given a list of refs that are either local folders or addon IDs."""

        # Attempt to build each ref and append it to this list.
        ret : List[Union[Mod, Union[int, Path]]] = []
        for ref in refs:

            # Attempt to build - if we failed, skip the ref.
            try                                    : ret.append(ModFactory.__build_singular(ref = ref, mods_path = mods_path))
            except ModInstanceCreationError        : continue

        # Return the list.
        return ret

    @staticmethod
    def __build_singular(
        ref       : Union[int  , Path] ,
        mods_path : Union[Path , None] = None
    ) -> Mod:
        """Attempts to build a single mod given a ref that is either a local folder or an addon ID."""

        # Sanity check ref type.
        if not isinstance(ref, (int, Path)):
            with logger.contextualize(original_error = TypeError()):
                raise ModInstanceCreationError(f'ModFactory was supplied a ref of type "{type(ref)}". Cannot proceed.')

        # Sanity check path target if ref is a path.
        elif isinstance(ref, Path) and not ref.is_dir():
            with logger.contextualize(original_error = NotADirectoryError()):
                raise ModInstanceCreationError(f'ModFactory was supplied a path "{ref}" that is not a directory. Cannot proceed.')

        try:

            # If we couldn't retrieve a reference, create a new mod instance (which will self-register to ModFactory.MOD_LIST) and return it.
            if (
                exist_mod := next((m for m in ModFactory.MOD_LIST if m.ref == ref or m.id == ref), None)
            ) is None: return Mod(ref = ref, mods_path = mods_path, register_to = ModFactory.MOD_LIST)

            # If we were able to retrieve an existing reference, we'll simply return it.
            elif isinstance(exist_mod, Mod.__class__): return exist_mod

            # If what we retrieved somehow isn't a Mod instance reference, we should definitely raise an exception.
            else: raise TypeError(f'Object "{repr(exist_mod)}" is of wrong type ({type(exist_mod)} != {type(Mod)})!')

        # If the creation of the mod object raises ModInstanceCreationError, it will be caught and reraised with further detail here.
        except ModInstanceCreationError as e:
            with logger.contextualize(original_error = e):
                raise ModInstanceCreationError(f'Failed to create (Mod @ "{ref}").')

# endregion

# endregion

### FUNCTIONS ###
# region FUNCTIONS

#=# PUBLIC FUNCTIONS #=#
# region PUBLIC FUNCTIONS

def parse_steam_datetime(steam_datetime: str) -> datetime:
    """Attempts to parse a datetime string as seen on the Steam Workshop."""

    try:
        return datetime.strptime(steam_datetime, STEAM_DATETIME_FORMAT_STR)
    except ValueError:
        try:
            ret = datetime.strptime(steam_datetime, STEAM_DATETIME_FORMAT_STR_NO_YEAR)
            return ret.replace(year = datetime.now().year)
        except ValueError as e: raise type(e)(f'Failed to parse Steam datetime string!\n\n### ORIGINAL ERROR ###\n\n{e}')

def get_game_version(save_path: Union[str, Path, None] = None) -> IsaacVer:
    """Determines the game edition via the save data path the game uses."""

    # Ensure save_path is correct.
    save_path = str(save_path) if save_path else str(TMoI_Util.find_boi_data_folders()[0])

    # Extract version.
    if   'Repentance'  in save_path : return IsaacVer.REP
    elif 'Afterbirth+' in save_path : return IsaacVer.ABP
    else                            : return IsaacVer.UNKNOWN

# endregion

#=# PRIVATE FUNCTIONS #=#
# region PRIVATE FUNCTIONS

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
                    if isinstance(d, Mod.__class__) else
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

# endregion

# endregion


### TESTING ###
# region TESTING

if __name__ == '__main__':

    print(f'BoI game version : {get_game_version()}')

    mods_path : Path = TMoI_Util.find_boi_data_folders()[1]

    parsed_mods = list(filter(None, ModFactory.build(mods_path.iterdir(), mods_path)))
    print(f'Parsed mods: {len(parsed_mods)}')
    for i, m in enumerate(parsed_mods): print(f'#{i} | Name: {m.name}; ID: {m.id}')

# endregion
