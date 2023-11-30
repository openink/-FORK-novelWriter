"""
novelWriter – Project Storage Class
===================================

File History:
Created: 2022-11-01 [2.0rc2] NWStorage

This file is a part of novelWriter
Copyright 2018–2023, Veronica Berglyd Olsen

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful, but
WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.
"""
from __future__ import annotations

import json
import logging

from enum import Enum
from time import time
from typing import TYPE_CHECKING
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from novelwriter import CONFIG
from novelwriter.error import logException
from novelwriter.common import isHandle, minmax
from novelwriter.constants import nwFiles
from novelwriter.core.document import NWDocument
from novelwriter.core.projectxml import ProjectXMLReader, ProjectXMLWriter
from novelwriter.core.spellcheck import UserDictionary

if TYPE_CHECKING:  # pragma: no cover
    from novelwriter.core.project import NWProject

logger = logging.getLogger(__name__)


class NWStorageOpen(Enum):

    UNKOWN    = 0
    NOT_FOUND = 1
    LOCKED    = 2
    FAILED    = 3
    READY     = 4

# END Enum NWStorageOpen


class NWStorage:
    """Core: Project Storage Class

    The class that handles all paths related to the project storage.
    """

    MODE_INACTIVE = 0
    MODE_INPLACE  = 1
    MODE_ARCHIVE  = 2

    def __init__(self, project: NWProject) -> None:
        self._project = project
        self._storagePath = None
        self._runtimePath = None
        self._lockFilePath = None
        self._lockedBy = None
        self._openMode = self.MODE_INACTIVE
        self._ready = False
        self._exception = None
        return

    def clear(self) -> None:
        """Reset internal variables."""
        self._storagePath = None
        self._runtimePath = None
        self._lockFilePath = None
        self._openMode = self.MODE_INACTIVE
        self._ready = False
        self._exception = None
        return

    ##
    #  Properties
    ##

    @property
    def storagePath(self) -> Path | None:
        """Return the path where the project is stored."""
        return self._storagePath

    @property
    def runtimePath(self) -> Path | None:
        """Return the path where the project is stored at runtime."""
        return self._runtimePath

    @property
    def contentPath(self) -> Path | None:
        """Return the path used for project content. The folder must
        already exist, otherwise this property is None.
        """
        if isinstance(self._runtimePath, Path):
            contentPath = self._runtimePath / "content"
            if contentPath.is_dir():
                return contentPath
        logger.error("Content path cannot be resolved")
        return None

    @property
    def lockStatus(self) -> list | None:
        """Return the project lock information."""
        if isinstance(self._lockedBy, list) and len(self._lockedBy) == 4:
            return self._lockedBy
        return None

    @property
    def exc(self) -> Exception | None:
        """Return the latest exception of the storage instance."""
        return self._exception

    ##
    #  Core Methods
    ##

    def isOpen(self) -> bool:
        """Check if the storage location is open."""
        return self._runtimePath is not None

    def createNewProject(self, path: str | Path) -> bool:
        """Create a new project at the given location."""
        inPath = Path(path).resolve()
        if inPath.is_dir() and len(list(inPath.iterdir())) > 0:
            logger.error("Folder is not empty: %s", inPath)
            return False

        self._storagePath = inPath
        self._runtimePath = inPath
        self._lockFilePath = inPath / nwFiles.PROJ_LOCK
        self._openMode = self.MODE_INPLACE

        basePath = self._runtimePath
        metaPath = basePath / "meta"
        contPath = basePath / "content"
        try:
            basePath.mkdir(exist_ok=True)
            metaPath.mkdir(exist_ok=True)
            contPath.mkdir(exist_ok=True)
        except Exception as exc:
            logger.error("Failed to create project folders", exc_info=exc)
            self.clear()
            return False

        self._ready = True

        return True

    def initProjectStorage(self, path: str | Path, clearLock: bool = False) -> NWStorageOpen:
        """Initialise the a novelWriter project."""
        inPath = Path(path).resolve()

        # Initialise Storage Instance
        # ===========================

        # Check what we're opening. Only three options are allowed:
        # 1. A folder with a nwProject.nwx file in it (not home)
        # 2. A full path to an nwProject.nwx file
        if inPath.is_dir() and inPath != Path.home().resolve():
            nwxFile = inPath / nwFiles.PROJ_FILE
        elif inPath.is_file() and inPath.name == nwFiles.PROJ_FILE:
            nwxFile = inPath
        else:
            logger.error("Not a novelWriter project")
            return NWStorageOpen.UNKOWN

        if not nwxFile.exists():
            # The .nwx file must exist to continue
            logger.error("Not found: %s", nwxFile)
            return NWStorageOpen.NOT_FOUND

        nwxPath = nwxFile.parent

        self._storagePath = nwxPath
        self._runtimePath = nwxPath
        self._lockFilePath = nwxPath / nwFiles.PROJ_LOCK
        self._openMode = self.MODE_INPLACE

        # Check Project Lock
        # ==================

        if clearLock:
            self._clearLockFile()

        self._readLockFile()
        if self._lockedBy and len(self._lockedBy) == 4:
            if self._lockedBy[0] == "ERROR":
                logger.warning("Failed to check lock file")
            else:
                logger.error("Project is locked, so not opening")
            return NWStorageOpen.LOCKED
        else:
            logger.debug("Project is not locked")

        # Prepare Folder
        # ==============

        basePath = self._runtimePath
        metaPath = basePath / "meta"
        contPath = basePath / "content"
        try:
            metaPath.mkdir(exist_ok=True)
            contPath.mkdir(exist_ok=True)
        except Exception as exc:
            logger.error("Failed to create project folders", exc_info=exc)
            self.clear()
            return NWStorageOpen.FAILED

        # Check for legacy data folders
        legacy = _LegacyStorage(self._project)
        legacy.deprecatedFiles(basePath)
        for child in basePath.iterdir():
            if child.is_dir() and child.name.startswith("data_"):
                legacy.legacyDataFolder(basePath, child)

        self._writeLockFile()
        self._ready = True

        return NWStorageOpen.READY

    def runPostSaveTasks(self, autoSave: bool = False) -> bool:  # pragma: no cover
        """Run tasks after the project has been saved.
        Placeholder for later implementation. See #977.
        """
        if self._openMode == self.MODE_INPLACE:
            # Nothing to do, so we just return
            return True
        return True

    def closeSession(self) -> None:
        """Run tasks related to closing the session."""
        self._clearLockFile()
        self.clear()
        return

    ##
    #  Content Access Methods
    ##

    def getXmlReader(self) -> ProjectXMLReader | None:
        """Return a properly configured ProjectXMLReader instance."""
        if isinstance(self._runtimePath, Path) and self._ready:
            return ProjectXMLReader(self._runtimePath / nwFiles.PROJ_FILE)
        return None

    def getXmlWriter(self) -> ProjectXMLWriter | None:
        """Return a properly configured ProjectXMLWriter instance."""
        if isinstance(self._runtimePath, Path) and self._ready:
            return ProjectXMLWriter(self._runtimePath / nwFiles.PROJ_FILE)
        return None

    def getDocument(self, tHandle: str | None) -> NWDocument:
        """Return a document wrapper object."""
        if isinstance(self._runtimePath, Path) and self._ready:
            return NWDocument(self._project, tHandle)
        return NWDocument(self._project, None)

    def getMetaFile(self, fileName: str) -> Path | None:
        """Return the path to a file in the project meta folder."""
        if isinstance(self._runtimePath, Path) and self._ready:
            return self._runtimePath / "meta" / fileName
        return None

    def scanContent(self) -> list[str]:
        """Scan the content folder and return the handle of all files
        found in it. Files that do not match the pattern are ignored.
        """
        contentPath = self.contentPath
        return [
            item.stem for item in contentPath.iterdir()
            if item.suffix == ".nwd" and isHandle(item.stem)
        ] if contentPath else []

    def zipIt(self, target: str | Path, compression: int | None = None) -> bool:
        """Zip the content of the project at its runtime location into a
        zip file. This process will only grab files that are supposed to
        be in the project. All non-project files will be left out.
        """
        basePath = self._runtimePath
        if not isinstance(basePath, Path):
            logger.error("No path set")
            return False

        baseMeta = basePath / "meta"
        baseCont = basePath / "content"
        files = [
            (basePath / nwFiles.PROJ_FILE,   nwFiles.PROJ_FILE),
            (basePath / nwFiles.PROJ_BACKUP, nwFiles.PROJ_BACKUP),
            (baseMeta / nwFiles.BUILDS_FILE, f"meta/{nwFiles.BUILDS_FILE}"),
            (baseMeta / nwFiles.INDEX_FILE,  f"meta/{nwFiles.INDEX_FILE}"),
            (baseMeta / nwFiles.OPTS_FILE,   f"meta/{nwFiles.OPTS_FILE}"),
            (baseMeta / nwFiles.DICT_FILE,   f"meta/{nwFiles.DICT_FILE}"),
            (baseMeta / nwFiles.SESS_FILE,   f"meta/{nwFiles.SESS_FILE}"),
        ]
        for contItem in baseCont.iterdir():
            name = contItem.name
            if contItem.is_file() and len(name) == 17 and name.endswith(".nwd"):
                files.append((contItem, f"content/{name}"))

        comp = ZIP_STORED if compression is None else ZIP_DEFLATED
        level = minmax(compression, 0, 9) if isinstance(compression, int) else None
        try:
            with ZipFile(target, mode="w", compression=comp, compresslevel=level) as zipObj:
                logger.info("Creating archive: %s", target)
                for srcPath, zipPath in files:
                    if srcPath.is_file():
                        zipObj.write(srcPath, zipPath)
                        logger.debug("Added: %s", zipPath)
        except Exception:
            logger.error("Failed to create archive")
            logException()
            return False

        return True

    ##
    #  Internal Functions
    ##

    def _readLockFile(self) -> None:
        """Read the project lock file."""
        self._lockedBy = None
        path = self._lockFilePath
        if isinstance(path, Path) and path.exists():
            try:
                self._lockedBy = path.read_text(encoding="utf-8").strip().split(";")
            except Exception:
                logger.error("Failed to read project lockfile")
                logException()
                self._lockedBy = ["ERROR", "ERROR", "ERROR", "ERROR"]
                return
        return

    def _writeLockFile(self) -> bool:
        """Write the project lock file."""
        if self._lockFilePath is None:
            return False
        try:
            self._lockFilePath.write_text(
                f"{CONFIG.hostName};{CONFIG.osType};{CONFIG.kernelVer};{int(time())}",
                encoding="utf-8"
            )
        except Exception:
            logger.error("Failed to write project lockfile")
            logException()
            return False
        return True

    def _clearLockFile(self) -> bool:
        """Remove the lock file, if it exists."""
        if self._lockFilePath is None:
            return False
        if self._lockFilePath.exists():
            try:
                self._lockFilePath.unlink()
            except Exception:
                logger.error("Failed to remove project lockfile")
                logException()
                return False
        self._lockedBy = None
        return True

# END Class NWStorage


class _LegacyStorage:
    """Core: Legacy Storage Converter Utils

    A class with various functions to convert old file formats and
    file/folder layouts to the current project format.
    """

    def __init__(self, project: NWProject) -> None:
        self._project = project
        return

    def legacyDataFolder(self, path: Path, child: Path) -> None:
        """Handle the content of a legacy data folder from a version 1.0
        project. This format had 16 data folders where there now is only
        one content folder.
        """
        logger.info("Processing legacy data folder: %s", path)

        # Move Documents to Content
        first = child.name[-1]
        if first not in "0123456789abcdef":
            return

        for item in child.iterdir():
            if not item.is_file():
                continue

            name = item.name
            if len(name) == 21 and name.endswith("_main.nwd"):
                newPath = path / "content" / f"{first}{name[:12]}.nwd"
                try:
                    item.rename(newPath)
                    logger.info("Moved file: %s", newPath)
                except Exception as exc:
                    logger.warning("Failed to move: %s", item, exc_info=exc)
            elif len(name) == 21 and name.endswith("_main.bak"):
                try:
                    item.unlink()
                    logger.info("Deleted file: %s", item)
                except Exception as exc:
                    logger.warning("Failed to delete: %s", item, exc_info=exc)

        # Remove Data Folder
        try:
            child.rmdir()
            logger.info("Deleted folder: %s", child)
        except Exception as exc:
            logger.warning("Failed to delete: %s", child, exc_info=exc)

        return

    def deprecatedFiles(self, path: Path) -> None:
        """Handle files that are no longer used by novelWriter."""
        self._convertOldWordList(  # Changed in 2.1 Beta 1
            path / "meta" / "wordlist.txt",
            path / "meta" / nwFiles.DICT_FILE
        )
        self._convertOldLogFile(  # Changed in 2.1 Beta 1
            path / "meta" / "sessionStats.log",
            path / "meta" / nwFiles.SESS_FILE
        )
        self._convertOldOptionsFile(  # Changed in 2.1 Beta 1
            path / "meta" / "guiOptions.json",
            path / "meta" / nwFiles.OPTS_FILE
        )

        # Delete removed files
        remove = [
            path / "meta" / "tagsIndex.json",          # Renamed in 2.1 Beta 1
            path / "meta" / "mainOptions.json",        # Replaced in 0.5
            path / "meta" / "exportOptions.json",      # Replaced in 0.5
            path / "meta" / "outlineOptions.json",     # Replaced in 0.5
            path / "meta" / "timelineOptions.json",    # Replaced in 0.5
            path / "meta" / "docMergeOptions.json",    # Replaced in 0.5
            path / "meta" / "sessionLogOptions.json",  # Replaced in 0.5
            path / "cache" / "prevBuild.json",         # Dropped in 2.1 Beta 1
            path / "cache",                            # Dropped in 2.1 Beta 1
            path / "ToC.json",                         # Dropped in 1.0 RC 1
        ]
        for item in remove:
            if item.exists():
                try:
                    if item.is_dir():
                        item.rmdir()
                    else:
                        item.unlink()
                    logger.info("Deleted: %s", item)
                except Exception as exc:
                    logger.warning("Failed to delete: %s", item, exc_info=exc)

        return

    ##
    #  Internal Functions
    ##

    def _convertOldWordList(self, wordList: Path, wordJson: Path) -> None:
        """Convert the old word list plain text file to new format."""
        if wordJson.exists() or not wordList.exists():
            # If the new file already exists, we won't overwrite it
            return

        userDict = UserDictionary(self._project)
        try:
            logger.info("Converting: %s", wordList)
            with open(wordList, mode="r", encoding="utf-8") as fObj:
                for line in fObj:
                    word = line.strip()
                    if word:
                        userDict.add(word)

            # Save dictionary and clean up old file
            userDict.save()
            wordList.unlink()

        except Exception:
            logger.error("Failed to convert old word list file")
            logException()

        return

    def _convertOldLogFile(self, sessLog: Path, sessJson: Path) -> None:
        """Convert the old text log file format to JSON Lines."""
        if sessJson.exists() or not sessLog.exists():
            # If the new file already exists, we won't overwrite it
            return

        try:
            data = []
            offset = 0
            session = self._project.session
            logger.info("Converting: %s", sessLog)
            with open(sessLog, mode="r", encoding="utf-8") as fObj:
                for record in fObj:
                    bits = record.split()
                    nBits = len(bits)
                    if record.startswith("# Offset") and nBits == 3:
                        offset = int(bits[2])
                    elif not record.startswith("#") and nBits > 5:
                        data.append(session.createRecord(
                            start=f"{bits[0]} {bits[1]}",
                            end=f"{bits[2]} {bits[3]}",
                            novel=int(bits[4]),
                            notes=int(bits[5]),
                            idle=int(bits[6]) if nBits > 6 else 0,
                        ))

            with open(sessJson, mode="a+", encoding="utf-8") as fObj:
                fObj.write(session.createInitial(offset))
                fObj.write("".join(data))

            # If we're here, we remove the old file
            sessLog.unlink()

        except Exception:
            logger.error("Failed to convert old stats file")
            logException()

        return

    def _convertOldOptionsFile(self, optsOld: Path, optsNew: Path) -> None:
        """Convert the old options state file format to new format."""
        if optsNew.exists() or not optsOld.exists():
            # If the new file already exists, we won't overwrite it
            return

        try:
            data = {}
            logger.info("Converting: %s", optsOld)
            with open(optsOld, mode="r", encoding="utf-8") as fObj:
                data = json.load(fObj)
                if "GuiOutline" in data:
                    # Convert Outline Values
                    state = {}
                    outline = data.get("GuiOutline", {})
                    hidden = outline.get("columnHidden", {})
                    width = outline.get("columnWidth", {})
                    for key in outline.get("headerOrder", []):
                        state[key] = [hidden.get(key, False), width.get(key, 100)]
                    data["GuiOutline"]["columnState"] = state

            with open(optsNew, mode="w", encoding="utf-8") as fObj:
                json.dump({"novelWriter.guiOptions": data}, fObj, indent=2)

            # If we're here, we remove the old file, and then we reload
            # the converted file and save it again
            optsOld.unlink()
            self._project.options.loadSettings()
            self._project.options.saveSettings()

        except Exception:
            logger.error("Failed to convert old options file")
            logException()

        return

# END Class _LegacyStorage
