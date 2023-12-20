"""
novelWriter – Project Document Tools
====================================

File History:
Created: 2022-10-02 [2.0rc1] DocMerger
Created: 2022-10-11 [2.0rc1] DocSplitter
Created: 2022-11-03 [2.0rc2] ProjectBuilder
Created: 2023-07-20 [2.1b1]  DocDuplicator

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

import shutil
import logging

from typing import Iterable
from pathlib import Path
from functools import partial

from PyQt5.QtCore import QCoreApplication

from novelwriter import CONFIG, SHARED
from novelwriter.common import minmax, simplified
from novelwriter.constants import nwItemClass
from novelwriter.core.item import NWItem
from novelwriter.core.project import NWProject
from novelwriter.core.storage import NWStorageCreate

logger = logging.getLogger(__name__)


class DocMerger:
    """Document tool for merging a set of documents into a single new
    document. The parameters are defined by the user using the
    GuiDocMerge dialog.
    """

    def __init__(self, project: NWProject) -> None:
        self._project = project
        self._error = ""
        self._targetDoc = None
        self._targetText = []
        return

    ##
    #  Methods
    ##

    def getError(self) -> str:
        """Return any collected errors."""
        return self._error

    def setTargetDoc(self, tHandle: str) -> None:
        """Set the target document for the merging. Calling this
        function resets the class.
        """
        self._targetDoc = tHandle
        self._targetText = []
        return

    def newTargetDoc(self, srcHandle: str, docLabel: str) -> str | None:
        """Create a brand new target document based on a source handle
        and a new doc label. Calling this function resets the class.
        """
        srcItem = self._project.tree[srcHandle]
        if srcItem is None or srcItem.itemParent is None:
            return None

        newHandle = self._project.newFile(docLabel, srcItem.itemParent)
        newItem = self._project.tree[newHandle]
        if isinstance(newItem, NWItem):
            newItem.setLayout(srcItem.itemLayout)
            newItem.setStatus(srcItem.itemStatus)
            newItem.setImport(srcItem.itemImport)

        self._targetDoc = newHandle
        self._targetText = []

        return newHandle

    def appendText(self, srcHandle: str, addComment: bool, cmtPrefix: str) -> bool:
        """Append text from an existing document to the text buffer."""
        srcItem = self._project.tree[srcHandle]
        if srcItem is None:
            return False

        inDoc = self._project.storage.getDocument(srcHandle)
        docText = (inDoc.readDocument() or "").rstrip("\n")

        if addComment:
            docInfo = srcItem.describeMe()
            docSt, _ = srcItem.getImportStatus(incIcon=False)
            cmtLine = f"% {cmtPrefix} {docInfo}: {srcItem.itemName} [{docSt}]\n\n"
            docText = cmtLine + docText

        self._targetText.append(docText)

        return True

    def writeTargetDoc(self) -> bool:
        """Write the accumulated text into the designated target
        document, appending any existing text.
        """
        if self._targetDoc is None:
            return False

        outDoc = self._project.storage.getDocument(self._targetDoc)
        docText = (outDoc.readDocument() or "").rstrip("\n")
        if docText:
            self._targetText.insert(0, docText)

        status = outDoc.writeDocument("\n\n".join(self._targetText) + "\n\n")
        if not status:
            self._error = outDoc.getError()

        return status

# END Class DocMerger


class DocSplitter:
    """Document tool for splitting a document into a set of new
    documents. The parameters are defined by the user using the
    GuiDocSplit dialog.
    """

    def __init__(self, project: NWProject, sHandle: str) -> None:

        self._project = project

        self._error = ""
        self._parHandle = None
        self._srcHandle = None
        self._srcItem = None

        self._inFolder = False
        self._rawData = []

        srcItem = self._project.tree[sHandle]
        if srcItem is not None and srcItem.isFileType():
            self._srcHandle = sHandle
            self._srcItem = srcItem

        return

    ##
    #  Methods
    ##

    def getError(self) -> str:
        """Return any collected errors."""
        return self._error

    def setParentItem(self, pHandle: str) -> None:
        """Set the item that will be the top level parent item for the
        new documents.
        """
        self._parHandle = pHandle
        self._inFolder = False
        return

    def newParentFolder(self, pHandle: str, folderLabel: str) -> str | None:
        """Create a new folder that will be the top level parent item
        for the new documents.
        """
        if self._srcItem is None:
            return None

        newHandle = self._project.newFolder(folderLabel, pHandle)
        newItem = self._project.tree[newHandle]
        if isinstance(newItem, NWItem):
            newItem.setStatus(self._srcItem.itemStatus)
            newItem.setImport(self._srcItem.itemImport)

        self._parHandle = newHandle
        self._inFolder = True

        return newHandle

    def splitDocument(self, splitData: list, splitText: list[str]) -> None:
        """Loop through the split data record and perform the split job
        on a list of text lines.
        """
        self._rawData = []
        buffer = splitText.copy()
        for lineNo, hLevel, hLabel in reversed(splitData):
            chunk = buffer[lineNo:]
            buffer = buffer[:lineNo]
            self._rawData.insert(0, (chunk, hLevel, hLabel))
        return

    def writeDocuments(self, docHierarchy: bool) -> Iterable[tuple[bool, str | None, str | None]]:
        """An iterator that will write each document in the buffer, and
        return its new handle, parent handle, and sibling handle.
        """
        if self._srcHandle is None or self._srcItem is None or self._parHandle is None:
            return

        pHandle = self._parHandle
        nHandle = self._parHandle if self._inFolder else self._srcHandle
        hHandle = [self._parHandle, None, None, None, None]

        pLevel = 0
        for docText, hLevel, docLabel in self._rawData:

            hLevel = minmax(hLevel, 1, 4)
            if pLevel == 0:
                pLevel = hLevel

            if docHierarchy:
                if hLevel == 1:
                    pHandle = self._parHandle
                elif hLevel == 2:
                    pHandle = hHandle[1] or hHandle[0]
                elif hLevel == 3:
                    pHandle = hHandle[2] or hHandle[1] or hHandle[0]
                elif hLevel == 4:
                    pHandle = hHandle[3] or hHandle[2] or hHandle[1] or hHandle[0]

                if hLevel < pLevel:
                    nHandle = hHandle[hLevel] or hHandle[0]
                elif hLevel > pLevel:
                    nHandle = pHandle

            dHandle = self._project.newFile(docLabel, pHandle)
            hHandle[hLevel] = dHandle

            newItem = self._project.tree[dHandle]
            if isinstance(newItem, NWItem):
                newItem.setStatus(self._srcItem.itemStatus)
                newItem.setImport(self._srcItem.itemImport)

            outDoc = self._project.storage.getDocument(dHandle)
            status = outDoc.writeDocument("\n".join(docText))
            if not status:
                self._error = outDoc.getError()

            yield status, dHandle, nHandle

            hHandle[hLevel] = dHandle
            nHandle = dHandle
            pLevel = hLevel

        return

# END Class DocSplitter


class DocDuplicator:
    """A class that will duplicate all documents and folders starting
    from a given handle.
    """

    def __init__(self, project: NWProject) -> None:
        self._project = project
        return

    ##
    #  Methods
    ##

    def duplicate(self, items: list[str]) -> Iterable[tuple[str, str | None]]:
        """Run through a list of items, duplicate them, and copy the
        text content if they are documents.
        """
        if not items:
            return

        nHandle = items[0]
        hMap: dict[str, str | None] = {t: None for t in items}
        for tHandle in items:
            newItem = self._project.tree.duplicate(tHandle)
            if newItem is None:
                return
            hMap[tHandle] = newItem.itemHandle
            if newItem.itemParent in hMap:
                newItem.setParent(hMap[newItem.itemParent])
                self._project.tree.updateItemData(newItem.itemHandle)
            if newItem.isFileType():
                oldDoc = self._project.storage.getDocument(tHandle)
                newDoc = self._project.storage.getDocument(newItem.itemHandle)
                if newDoc.fileExists():
                    return
                newDoc.writeDocument(oldDoc.readDocument() or "")
            yield newItem.itemHandle, nHandle
            nHandle = None

        return

# END Class DocDuplicator


class ProjectBuilder:
    """A class to build a new project from a set of user-defined
    parameter provided by the New Project Wizard.
    """

    def __init__(self) -> None:
        self._path = None
        self.tr = partial(QCoreApplication.translate, "NWProject")
        return

    @property
    def projPath(self) -> Path | None:
        """The path of the newly created project."""
        return self._path

    ##
    #  Methods
    ##

    def buildProject(self, data: dict) -> bool:
        """Build or copy a project from a data dictionary."""
        if not isinstance(data, dict):
            logger.error("Invalid call to buildProject function")
            return False

        path = data.get("path", None) or None
        if isinstance(path, (str, Path)):
            self._path = Path(path).resolve()
            if data.get("sample", False):
                return self._extractSampleProject(self._path)
            elif data.get("template"):
                return True
            else:
                return self._buildAndPopulate(self._path, data)

        SHARED.error("A project path is required.")

        return False

    ##
    #  Internal Functions
    ##

    def _buildAndPopulate(self, path: Path, data: dict) -> bool:
        """Build a blank project from a data dictionary."""
        project = NWProject()
        status = project.storage.createNewProject(path)
        if status == NWStorageCreate.NOT_EMPTY:
            SHARED.error(self.tr(
                "A project already exists in that location. "
                "Please choose another folder."
            ))
            return False
        elif status == NWStorageCreate.OS_ERROR:
            SHARED.error(self.tr(
                "An error occured while trying to create the project."
            ), exc=project.storage.exc)
            return False

        self._path = project.storage.storagePath

        lblNewProject = self.tr("New Project")
        lblTitlePage  = self.tr("Title Page")
        lblByAuthors  = self.tr("By")

        # Settings
        projName = data.get("name", lblNewProject)
        projAuthor = data.get("author", "")
        projLang = data.get("language", "en_GB")

        project.data.setUuid(None)
        project.data.setName(projName)
        project.data.setAuthor(projAuthor)
        project.data.setLanguage(projLang)
        project.setDefaultStatusImport()
        project.session.startSession()

        # Add Root Folders
        hNovelRoot = project.newRoot(nwItemClass.NOVEL)
        hTitlePage = project.newFile(lblTitlePage, hNovelRoot)
        novelTitle = project.data.title if project.data.title else project.data.name

        titlePage = f"#! {novelTitle}\n\n"
        if project.data.author:
            titlePage += f">> {lblByAuthors} {project.data.author} <<\n\n"

        aDoc = project.storage.getDocument(hTitlePage)
        aDoc.writeDocument(titlePage)

        # Create a project structure based on selected root folders
        # and a number of chapters and scenes selected in the
        # wizard's custom page.

        # Create chapters and scenes
        numChapters = data.get("chapters", 0)
        numScenes = data.get("scenes", 0)

        chSynop = self.tr("Summary of the chapter.")
        scSynop = self.tr("Summary of the scene.")
        bfNote = self.tr("A short description.")

        # Create chapters
        if numChapters > 0:
            for ch in range(numChapters):
                chTitle = self.tr("Chapter {0}").format(f"{ch+1:d}")
                cHandle = project.newFile(chTitle, hNovelRoot)
                aDoc = project.storage.getDocument(cHandle)
                aDoc.writeDocument(f"## {chTitle}\n\n%Synopsis: {chSynop}\n\n")

                # Create chapter scenes
                if numScenes > 0 and cHandle:
                    for sc in range(numScenes):
                        scTitle = self.tr("Scene {0}").format(f"{ch+1:d}.{sc+1:d}")
                        sHandle = project.newFile(scTitle, cHandle)
                        aDoc = project.storage.getDocument(sHandle)
                        aDoc.writeDocument(f"### {scTitle}\n\n%Synopsis: {scSynop}\n\n")

        # Create scenes (no chapters)
        elif numScenes > 0:
            for sc in range(numScenes):
                scTitle = self.tr("Scene {0}").format(f"{sc+1:d}")
                sHandle = project.newFile(scTitle, hNovelRoot)
                aDoc = project.storage.getDocument(sHandle)
                aDoc.writeDocument(f"### {scTitle}\n\n%Synopsis: {scSynop}\n\n")

        # Create notes folders
        noteTitles = {
            nwItemClass.PLOT: self.tr("Main Plot"),
            nwItemClass.CHARACTER: self.tr("Protagonist"),
            nwItemClass.WORLD: self.tr("Main Location"),
        }

        addNotes = data.get("notes", False)
        for newRoot in data.get("roots", []):
            if newRoot in nwItemClass:
                rHandle = project.newRoot(newRoot)
                if addNotes:
                    aHandle = project.newFile(noteTitles[newRoot], rHandle)
                    ntTag = simplified(noteTitles[newRoot]).replace(" ", "")
                    aDoc = project.storage.getDocument(aHandle)
                    aDoc.writeDocument(
                        f"# {noteTitles[newRoot]}\n\n"
                        f"@tag: {ntTag}\n\n"
                        f"%Short: {bfNote}\n\n"
                    )

        # Also add the archive and trash folders
        project.newRoot(nwItemClass.ARCHIVE)
        project.trashFolder()

        project.saveProject()
        project.closeProject()

        return True

    def _extractSampleProject(self, path: Path) -> bool:
        """Make a copy of the sample project by extracting the
        sample.zip file to the new path.
        """
        pkgSample = CONFIG.assetPath("sample.zip")
        if pkgSample.is_file():
            try:
                shutil.unpack_archive(pkgSample, path)
            except Exception as exc:
                SHARED.error(self.tr(
                    "Failed to create a new example project."
                ), exc=exc)
                return False
        else:
            SHARED.error(self.tr(
                "Failed to create a new example project. "
                "Could not find the necessary files. "
                "They seem to be missing from this installation."
            ))
            return False

        return True

# END Class ProjectBuilder
