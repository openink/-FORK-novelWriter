"""
novelWriter – Project XML Read/Write
====================================
Classes for reading and writing the project XML file

File History:
Created: 2022-09-28 [2.0rc1] ProjectXMLReader
Created: 2022-09-28 [2.0rc1] XMLReadState

This file is a part of novelWriter
Copyright 2018–2022, Veronica Berglyd Olsen

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

import os
import logging
import novelwriter

from enum import Enum
from lxml import etree

from novelwriter.common import (
    checkBool, checkInt, checkStringNone, formatTimeStamp, simplified, checkString
)
from novelwriter.constants import nwFiles

logger = logging.getLogger(__name__)

FILE_VERSION = "1.4"  # The current project file format version

NUM_VERSION = {
    "1.0": 0x0100,
    "1.1": 0x0101,
    "1.2": 0x0102,
    "1.3": 0x0103,
    "1.4": 0x0104,
}


class XMLReadState(Enum):

    NO_ACTION       = 0
    NO_ERROR        = 1
    PARSED_BACKUP   = 2
    CANNOT_PARSE    = 3
    NOT_NWX_FILE    = 4
    UNKNOWN_VERSION = 5
    PARSING_ERROR   = 6
    PARSED_OK       = 7
    WAS_LEGACY      = 8

# END Class XMLReadState


class ProjectXMLReader:
    """The main project XML file reader class. All data is read into a
    NWProjectData instance, which must be provided.

    Version Change History
    ======================
    1.0 Original file format.

    1.1 Changes the way documents are structured in the project folder
        from data_X, where X is the first hex value of the handle, to a
        single content folder. Introduced in version 0.7.

    1.2 Changes the way autoReplace entries are stored. The 1.1 parser
        will lose the autoReplace settings if allowed to read the file.
        Introduced in version 0.10.

    1.3 Reduces the number of layouts to only two. One for novel
        documents and one for project notes. Introduced in version 1.5.

    1.4 Introduces a more compact format for storing items. All settings
        aside from name are now attributes. This format also changes the
        way satus and importance labels are stored and handled.
        Introduced in version 2.0.
    """

    def __init__(self, path):

        self._path = path
        self._state = XMLReadState.NO_ACTION

        self._content = []
        self._statusData = {}
        self._statusMap = {}

        self._root = ""
        self._version = 0x0000
        self._appVersion = ""
        self._hexVersion = ""
        self._timeStamp = ""

        return

    ##
    #  Properties
    ##

    @property
    def content(self):
        """The project content section, a dictionary of project items.
        """
        return self._content

    @property
    def state(self):
        """The state of the parsing as an XMLReadState enum value.
        """
        return self._state

    @property
    def xmlRoot(self):
        """The root tag name of the XNL file,
        """
        return self._root

    @property
    def xmlVersion(self):
        """The project XML version number.
        """
        return self._version

    @property
    def appVersion(self):
        """The novelWriter version number who wrote the file.
        """
        return self._appVersion

    @property
    def hexVersion(self):
        """The novelWriter version number who wrote the file as hex.
        """
        return self._hexVersion

    @property
    def timeStamp(self):
        """The date and time when the file was written.
        """
        return self._timeStamp

    ##
    #  Methods
    ##

    def read(self, projData):
        """Read and parse the project XML file.
        """
        self._content = []

        try:
            xml = etree.parse(self._path)
            self._state = XMLReadState.NO_ERROR

        except Exception as exc:
            # Trying to open backup file instead
            logger.error("Failed to parse project xml", exc_info=exc)
            self._state = XMLReadState.CANNOT_PARSE

            backFile = self._path[:-3]+"bak"
            if os.path.isfile(backFile):
                try:
                    xml = etree.parse(backFile)
                    self._state = XMLReadState.PARSED_BACKUP
                    logger.info("Backup project file parsed")
                except Exception as exc:
                    logger.error("Failed to parse backup project xml", exc_info=exc)
                    self._state = XMLReadState.CANNOT_PARSE
                    return False
            else:
                return False

        xRoot = xml.getroot()
        self._root = str(xRoot.tag)
        if self._root != "novelWriterXML":
            self._state = XMLReadState.NOT_NWX_FILE
            return False

        fileVersion = str(xRoot.attrib.get("fileVersion", ""))
        if fileVersion in NUM_VERSION:
            self._version = NUM_VERSION[fileVersion]
        else:
            self._state = XMLReadState.UNKNOWN_VERSION
            return False

        self._appVersion = str(xRoot.attrib.get("appVersion", ""))
        self._hexVersion = str(xRoot.attrib.get("appVersion", ""))
        self._timeStamp = str(xRoot.attrib.get("timeStamp", ""))

        status = True
        for xSection in xRoot:
            if xSection.tag == "project":
                status &= self._parseProjectMeta(xSection, projData)
            elif xSection.tag == "settings":
                status &= self._parseProjectSettings(xSection, projData)
            elif xSection.tag == "content":
                if self._version >= 0x0104:
                    status &= self._parseProjectContent(xSection)
                else:
                    self._genLegacyImportStatysMap(projData)
                    status &= self._parseProjectContentLegacy(xSection)
            else:
                logger.warning("Ignored <root/%s> in xml", xSection.tag)

        if not status:
            self._state = XMLReadState.PARSING_ERROR
            return False

        if self._version == 0x0104:
            self._state = XMLReadState.PARSED_OK
        else:
            self._state = XMLReadState.WAS_LEGACY

        return True

    ##
    #  Internal Functions
    ##

    def _parseProjectMeta(self, xSection, projData):
        """Parse the project section of the XML file.
        """
        logger.debug("Parsing xml <root/project>")
        for xItem in xSection:
            if xItem.tag == "name":
                projData.setName(xItem.text)
            elif xItem.tag == "title":
                projData.setTitle(xItem.text)
            elif xItem.tag == "author":
                projData.addAuthor(xItem.text)
            elif xItem.tag == "saveCount":
                projData.setSaveCount(xItem.text)
            elif xItem.tag == "autoCount":
                projData.setAutoCount(xItem.text)
            elif xItem.tag == "editTime":
                projData.setEditTime(xItem.text)
            else:
                logger.warning("Ignored <root/project/%s> in xml", xItem.tag)

        return True

    def _parseProjectSettings(self, xSection, projData):
        """Parse the settings section of the XML file.
        """
        logger.debug("Parsing xml <root/settings>")

        for xItem in xSection:
            if xItem.tag == "doBackup":
                projData.setDoBackup(xItem.text)
            elif xItem.tag == "language":
                projData.setLanguage(xItem.text)
            elif xItem.tag == "spellCheck":
                projData.setSpellCheck(xItem.text)
            elif xItem.tag == "spellLang":
                projData.setSpellLang(xItem.text)
            elif xItem.tag == "lastEdited":
                projData.setLastHandle(xItem.text, "editor")
            elif xItem.tag == "lastViewed":
                projData.setLastHandle(xItem.text, "viewer")
            elif xItem.tag == "lastNovel":
                projData.setLastHandle(xItem.text, "noveltree")
            elif xItem.tag == "lastOutline":
                projData.setLastHandle(xItem.text, "outline")
            elif xItem.tag == "lastWordCount":
                projData.setLastCount(xItem.text, "total")
            elif xItem.tag == "novelWordCount":
                projData.setLastCount(xItem.text, "novel")
            elif xItem.tag == "notesWordCount":
                projData.setLastCount(xItem.text, "notes")
            elif xItem.tag == "status":
                self._parseStatusImport(xItem, projData.itemStatus)
            elif xItem.tag in ("import", "importance"):
                self._parseStatusImport(xItem, projData.itemImport)
            elif xItem.tag == "autoReplace":
                if self._version >= 0x0102:
                    projData.setAutoReplace(self._parseDictKeyText(xItem))
                else:  # Pre 1.2 format
                    projData.setAutoReplace(self._parseDictTagText(xItem))
            elif xItem.tag == "titleFormat":
                projData.setTitleFormat(self._parseDictTagText(xItem))
            else:
                logger.warning("Ignored <root/settings/%s> in xml", xItem.tag)

        return True

    def _parseProjectContent(self, xSection):
        """Parse the content section of the XML file.
        """
        logger.debug("Parsing xml <root/content>")

        for xItem in xSection:
            if xItem.tag == "item":
                item = {}
                item["handle"] = xItem.attrib.get("handle", None)
                item["parent"] = xItem.attrib.get("parent", None)
                item["root"]   = xItem.attrib.get("root", None)
                item["order"]  = checkInt(xItem.attrib.get("order", 0), 0)
                item["type"]   = checkString(xItem.attrib.get("type", ""), "")
                item["class"]  = checkString(xItem.attrib.get("class", ""), "")
                item["layout"] = checkString(xItem.attrib.get("layout", ""), "")
                for xVal in xItem:
                    if xVal.tag == "meta":
                        item["expanded"]  = checkBool(xVal.attrib.get("expanded", False), False)
                        item["heading"]   = checkString(xVal.attrib.get("heading", "H0"), "H0")
                        item["charCount"] = checkInt(xVal.attrib.get("charCount", 0), 0)
                        item["wordCount"] = checkInt(xVal.attrib.get("wordCount", 0), 0)
                        item["paraCount"] = checkInt(xVal.attrib.get("paraCount", 0), 0)
                        item["cursorPos"] = checkInt(xVal.attrib.get("cursorPos", 0), 0)
                    elif xVal.tag == "name":
                        item["label"]  = simplified(checkString(xVal.text, ""))
                        item["status"] = checkStringNone(xVal.attrib.get("status", None), None)
                        item["import"] = checkStringNone(xVal.attrib.get("import", None), None)
                        item["active"] = checkBool(xVal.attrib.get("active", False), False)

                        # ToDo: Remove before 2.0 release. Only needed for 2.0 pre-releases.
                        if "exported" in xVal.attrib:
                            item["active"] = checkBool(xVal.attrib.get("exported", False), False)
                    else:
                        logger.warning("Ignored <root/content/item/%s> in xml", xVal.tag)

                self._content.append(item)

            else:
                logger.warning("Ignored item <root/content/%s> in xml", xItem.tag)

        return True

    def _parseProjectContentLegacy(self, xSection):
        """Parse the content section of the XML file for older version.
        """
        logger.debug("Parsing xml <root/content> (legacy format)")
        depLayout = ("TITLE", "PAGE", "BOOK", "PARTITION", "UNNUMBERED", "CHAPTER", "SCENE")

        for xItem in xSection:
            item = {}
            if xItem.tag == "item":
                item["handle"]  = xItem.attrib.get("handle", None)
                item["parent"]  = xItem.attrib.get("parent", None)
                item["root"]    = None  # Value was added in 1.4
                item["order"]   = checkInt(xItem.attrib.get("order", 0), 0)
                item["heading"] = "H0"  # Value was added in 1.4

                tmpStatus = ""
                for xVal in xItem:
                    if xVal.tag == "name":
                        item["label"] = simplified(checkString(xVal.text, ""))
                    elif xVal.tag == "status":
                        tmpStatus = checkStringNone(xVal.text, None)
                    elif xVal.tag == "type":
                        item["type"] = checkString(xVal.text, "")
                    elif xVal.tag == "class":
                        item["class"] = checkString(xVal.text, "")
                    elif xVal.tag == "layout":
                        item["layout"] = checkString(xVal.text, "")
                    elif xVal.tag == "expanded":
                        item["expanded"] = checkBool(xVal.text, False)
                    elif xVal.tag == "exported":  # Renamed to active in 1.4
                        item["active"] = checkBool(xVal.text, False)
                    elif xVal.tag == "charCount":
                        item["charCount"] = checkInt(xVal.text, 0)
                    elif xVal.tag == "wordCount":
                        item["wordCount"] = checkInt(xVal.text, 0)
                    elif xVal.tag == "paraCount":
                        item["paraCount"] = checkInt(xVal.text, 0)
                    elif xVal.tag == "cursorPos":
                        item["cursorPos"] = checkInt(xVal.text, 0)
                    else:
                        logger.warning("Ignored <root/content/item/%s> in xml", xVal.tag)

                # Status was split into separate status/import with a key in 1.4
                if item.get("class", "") in ("NOVEL", "ARCHIVE"):
                    item["status"] = self._statusMap.get(tmpStatus, None)
                else:
                    item["import"] = self._importMap.get(tmpStatus, None)

                # A number of layouts were removed in 1.3
                if item.get("layout", "") in depLayout:
                    item["layout"] = "DOCUMENT"

                # The trast type was removed in 1.4
                if item.get("type", "") == "TRASH":
                    item["type"] = "ROOT"

                self._content.append(item)

            else:
                logger.warning("Ignored <root/content/%s> in xml", xItem.tag)

        return True

    def _parseStatusImport(self, xItem, sObject):
        """Parse a status or importance entry.
        """
        for xEntry in xItem:
            if xEntry.tag == "entry":
                key   = xEntry.attrib.get("key", None)
                red   = checkInt(xEntry.attrib.get("red", 0), 0)
                green = checkInt(xEntry.attrib.get("green", 0), 0)
                blue  = checkInt(xEntry.attrib.get("blue", 0), 0)
                count = checkInt(xEntry.attrib.get("count", 0), 0)
                sObject.write(key, xEntry.text, (red, green, blue), count)
        return

    def _genLegacyImportStatysMap(self, projData):
        """Generate a map of legacy import/status values.
        """
        self._statusMap = {entry["name"]: key for key, entry in projData.itemStatus.items()}
        self._importMap = {entry["name"]: key for key, entry in projData.itemImport.items()}
        return

    def _parseDictKeyText(self, xItem):
        """Parse a dictionary stored with key as an attribute and the
        value as the text porperty.
        """
        result = {}
        for xEntry in xItem:
            if xEntry.tag == "entry" and "key" in xEntry.attrib:
                result[xEntry.attrib["key"]] = checkString(xEntry.text, "")
        return result

    def _parseDictTagText(self, xItem):
        """Parse a dictionary stored with key as the tag and the value
        as the text porperty.
        """
        return {n.tag: checkString(n.text, "") for n in xItem}

# END Class ProjectXMLReader


class ProjectXMLWriter:

    def __init__(self, path):

        self._path = path
        self._error = None

        return

    def write(self, projData, projContent, saveTime, editTime):

        nwXML = etree.Element("novelWriterXML", attrib={
            "appVersion":  str(novelwriter.__version__),
            "hexVersion":  str(novelwriter.__hexversion__),
            "fileVersion": FILE_VERSION,
            "timeStamp":   formatTimeStamp(saveTime),
        })

        # Save Project Meta
        xProject = etree.SubElement(nwXML, "project")
        self._packSingleValue(xProject, "name", projData.name)
        self._packSingleValue(xProject, "title", projData.title)
        self._packListValue(xProject, "author", projData.authors)
        self._packSingleValue(xProject, "saveCount", projData.saveCount)
        self._packSingleValue(xProject, "autoCount", projData.autoCount)
        self._packSingleValue(xProject, "editTime", editTime)

        # Save Project Settings
        xSettings = etree.SubElement(nwXML, "settings")
        self._packSingleValue(xSettings, "doBackup", projData.doBackup)
        self._packSingleValue(xSettings, "language", projData.language)
        self._packSingleValue(xSettings, "spellCheck", projData.spellCheck)
        self._packSingleValue(xSettings, "spellLang", projData.spellLang)
        self._packSingleValue(xSettings, "lastEdited", projData.getLastHandle("editor"))
        self._packSingleValue(xSettings, "lastViewed", projData.getLastHandle("viewer"))
        self._packSingleValue(xSettings, "lastNovel", projData.getLastHandle("noveltree"))
        self._packSingleValue(xSettings, "lastOutline", projData.getLastHandle("outline"))
        self._packSingleValue(xSettings, "lastWordCount", projData.getCurrCount("total"))
        self._packSingleValue(xSettings, "novelWordCount", projData.getCurrCount("novel"))
        self._packSingleValue(xSettings, "notesWordCount", projData.getCurrCount("notes"))
        self._packDictKeyValue(xSettings, "autoReplace", projData.autoReplace)
        self._packDictTagValue(xSettings, "titleFormat", projData.titleFormat)

        # Save Status/Importance
        xStatus = etree.SubElement(xSettings, "status")
        for (label, attr) in projData.itemStatus.pack():
            xEntry = etree.SubElement(xStatus, "entry", attrib=attr)
            xEntry.text = label

        xImport = etree.SubElement(xSettings, "importance")
        for (label, attr) in projData.itemImport.pack():
            xEntry = etree.SubElement(xImport, "entry", attrib=attr)
            xEntry.text = label

        # Save Tree Content
        cAttr = {"count": str(len(projContent))}
        xContent = etree.SubElement(nwXML, "content", attrib=cAttr)
        for item in projContent:
            xItem = etree.SubElement(xContent, "item", attrib=item.get("itemAttr", {}))
            etree.SubElement(xItem, "meta", attrib=item.get("metaAttr", {}))
            xName = etree.SubElement(xItem, "name", attrib=item.get("nameAttr", {}))
            xName.text = item["name"]

        # Write the xml tree to file
        tempFile = os.path.join(self._path, nwFiles.PROJ_FILE+"~")
        saveFile = os.path.join(self._path, nwFiles.PROJ_FILE)
        backFile = os.path.join(self._path, nwFiles.PROJ_FILE[:-3]+"bak")
        try:
            with open(tempFile, mode="wb") as outFile:
                outFile.write(etree.tostring(
                    nwXML,
                    pretty_print=True,
                    encoding="utf-8",
                    xml_declaration=True
                ))
        except Exception:
            return False

        # If we're here, the file was successfully saved,
        # so let's sort out the temps and backups
        try:
            if os.path.isfile(saveFile):
                os.replace(saveFile, backFile)
            os.replace(tempFile, saveFile)
        except OSError:
            return False

        return True

    ##
    #  Internal Functions
    ##

    def _packSingleValue(self, xParent, name, value, allowNone=True):
        """Pack a list of values into an xml element.
        """
        if (value == "" or value is None) and not allowNone:
            return
        xItem = etree.SubElement(xParent, name)
        xItem.text = str(value)
        return

    def _packListValue(self, xParent, name, data, allowNone=True):
        """Pack a list of values into an xml element.
        """
        for value in data:
            self._packSingleValue(xParent, name, value, allowNone=allowNone)
        return

    def _packDictKeyValue(self, xParent, name, data):
        """Pack the entries of a dictionary into an xml element.
        """
        xItem = etree.SubElement(xParent, name)
        for key, value in data.items():
            if len(key) > 0:
                xEntry = etree.SubElement(xItem, "entry", attrib={"key": key})
                xEntry.text = value
        return

    def _packDictTagValue(self, xParent, name, data):
        """Pack the entries of a dictionary into an xml element.
        """
        xItem = etree.SubElement(xParent, name)
        for aKey, value in data.items():
            if len(aKey) > 0:
                self._packSingleValue(xItem, aKey, value)
        return

# END Class ProjectXMLWriter
