"""
novelWriter – Project Details Dialog Class Tester
=================================================

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

import pytest

from tools import getGuiItem

from PyQt5.QtWidgets import QAction

from novelwriter import SHARED
from novelwriter.dialogs.projdetails import GuiProjectDetails


@pytest.mark.gui
def testDlgProjDetails_Dialog(qtbot, nwGUI, prjLipsum):
    """Test the project details dialog.
    """
    # Create a project to work on
    assert nwGUI.openProject(prjLipsum)
    assert nwGUI.rebuildIndex(beQuiet=True)
    qtbot.wait(100)

    # Open the Writing Stats dialog
    nwGUI.mainMenu.aProjectDetails.activate(QAction.Trigger)
    qtbot.waitUntil(lambda: getGuiItem("GuiProjectDetails") is not None, timeout=1000)

    projDet = getGuiItem("GuiProjectDetails")
    assert isinstance(projDet, GuiProjectDetails)

    # Overview Page
    # =============

    assert projDet.tabMain.bookTitle.text() == "Lorem Ipsum"
    assert projDet.tabMain.projName.text()[-11:] == "Lorem Ipsum"
    assert projDet.tabMain.bookAuthors.text()[-10:] == "lipsum.com"

    assert projDet.tabMain.wordCountVal.text() == f"{3000:n}"
    assert projDet.tabMain.chapCountVal.text() == f"{3:n}"
    assert projDet.tabMain.sceneCountVal.text() == f"{5:n}"
    assert projDet.tabMain.revCountVal.text() == f"{SHARED.project.data.saveCount:n}"

    assert projDet.tabMain.projPathVal.text() == str(prjLipsum)

    # Contents Page
    # =============

    tocTab = projDet.tabContents
    tocTree = tocTab.tocTree
    assert tocTree.topLevelItemCount() == 7
    assert tocTree.topLevelItem(0).text(tocTab.C_TITLE) == "Lorem Ipsum"  # type: ignore
    assert tocTree.topLevelItem(2).text(tocTab.C_TITLE) == "Prologue"  # type: ignore
    assert tocTree.topLevelItem(3).text(tocTab.C_TITLE) == "Act One"  # type: ignore
    assert tocTree.topLevelItem(4).text(tocTab.C_TITLE) == "Chapter One"  # type: ignore
    assert tocTree.topLevelItem(5).text(tocTab.C_TITLE) == "Chapter Two"  # type: ignore
    assert tocTree.topLevelItem(6).text(tocTab.C_TITLE) == "END"  # type: ignore

    # Count Pages
    tocTab.wpValue.setValue(100)
    tocTab.poValue.setValue(4)
    tocTab.dblValue.setChecked(False)
    tocTab._populateTree()

    thePages = ["1", "2", "1", "1", "11", "17", "0"]
    thePage = ["i", "ii", "1", "2", "3", "14", "31"]
    for i in range(7):
        assert tocTree.topLevelItem(i).text(tocTab.C_PAGES) == thePages[i]  # type: ignore
        assert tocTree.topLevelItem(i).text(tocTab.C_PAGE) == thePage[i]  # type: ignore

    tocTab.poValue.setValue(5)
    tocTab.dblValue.setChecked(True)
    tocTab._populateTree()

    thePages = ["2", "2", "2", "2", "12", "18", "0"]
    thePage = ["i", "iii", "1", "3", "5", "17", "35"]
    for i in range(7):
        assert tocTree.topLevelItem(i).text(tocTab.C_PAGES) == thePages[i]  # type: ignore
        assert tocTree.topLevelItem(i).text(tocTab.C_PAGE) == thePage[i]  # type: ignore

    # Re-populate
    assert tocTab._currentRoot is None
    tocTab._novelValueChanged("7a992350f3eb6")     # Not a root
    assert tocTab._currentRoot == "b3643d0f92e32"  # The actual novel root

    # qtbot.stop()

    # Clean Up
    projDet.close()
    nwGUI.closeMain()

# END Test testDlgProjDetails_Dialog
