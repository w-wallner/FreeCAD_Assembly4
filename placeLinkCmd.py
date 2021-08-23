#!/usr/bin/env python3
# coding: utf-8
#
# placeLinkCmd.py


import os, time

from PySide import QtGui, QtCore
import FreeCADGui as Gui
import FreeCAD as App
from FreeCAD import Console as FCC

import Asm4_libs as Asm4
import selectionFilter




"""
    +-----------------------------------------------+
    |                Global variables               |
    +-----------------------------------------------+
"""
#global taskUI

# link being placed view properties overrides
DrawStyle = 'Solid'
LineWidth = 3.0
DiffuseColor = (1.0, 1.0, 1.0, 0.0)
Transparency = 0.50

LineHighlight = (1.0, 1.0, 0.0, 0.0)



"""
    +-----------------------------------------------+
    |                  The command                  |
    +-----------------------------------------------+
"""
class placeLinkCmd():
    def __init__(self):
        super(placeLinkCmd,self).__init__()

    def GetResources(self):
        return {"MenuText": "Edit Placement of a Part",
                "ToolTip": "Move/Attach a Part in the assembly",
                "Pixmap" : os.path.join( Asm4.iconPath , 'Place_Link.svg')
                }

    def IsActive(self):
        # We only insert a link into an Asm4  Model
        if App.ActiveDocument:
            ( obj, tree ) = Asm4.getSelectionTree()
            # something at 2nd level is selected
            if tree and len(tree)==2:
                # the root container must be an App::Part
                root = App.ActiveDocument.getObject(tree[0])
                if root and root.TypeId=='App::Part':
                    return True
        return False

    def Activated(self):
        #Handle single selected App::Link
        selectedLink = None
        #parentAssembly = None
        selection = Asm4.getSelectedLink()
        if not selection :
            # This shouldn't happen
            FCC.PrintWarning("This is not an error message you are supposed to see, something went wrong\n")
            return
        else:
            parent = selection.getParentGeoFeatureGroup()
            if parent and parent == Asm4.getAssembly():
                # if it's a valid assembly and part
                if Asm4.isAsm4EE(selection):
                    # launch the UI in the task panel
                    ui = placeLinkUI()
                    Gui.Control.showDialog(ui)
                # else try to convert it
                else:
                    convert = Asm4.confirmBox("This Part wasn't assembled with this Assembly4 WorkBench, but I can convert it.")
                    if convert:
                        Asm4.makeAsmProperties( selection, reset=True )
                        # launch the UI in the task panel
                        ui = placeLinkUI()
                        Gui.Control.showDialog(ui)
            else:
                Asm4.warningBox('Please select a link in the assembly Model.')
        return
        '''
            # only handle if the parent is at the root of the document:
            if parent and parent.TypeId == 'App::Part' and parent.getParentGeoFeatureGroup() is None:
                # only accept Asm4 Models as assemblies
                # this is self-imposed, works also without an Asm4 Model
                # the following check can be omitted
                if parent.Name=='Model':
                    # check that the selected Part is from this workbench
                    if Asm4.isAsm4EE(selection):
                        # launch the UI in the task panel
                        ui = placeLinkUI()
                        Gui.Control.showDialog(ui)
                    else:
                        # Asm4.warningBox("This Part wasn't assembled with this Assembly4 WorkBench")
                        convert = Asm4.confirmBox("This Part wasn't assembled with this Assembly4 WorkBench, but I can convert it.")
                        if convert:
                            Asm4.makeAsmProperties( selection, reset=True )
                            # launch the UI in the task panel
                            ui = placeLinkUI()
                            Gui.Control.showDialog(ui)
                else:
                    Asm4.warningBox('Please select a link in the assembly Model')
            else:
                Asm4.warningBox('Please select a link in the assembly Model.')
        return
        '''


"""
    +-----------------------------------------------+
    |    The UI and functions in the Task panel     |
    +-----------------------------------------------+
"""
class placeLinkUI():

    def __init__(self):
        # remove selectionFilter
        self.selectionFilterStatus = selectionFilter.observerStatus()
        selectionFilter.observerDisable()

        # get the current active document to avoid errors if user changes tab
        self.activeDoc = App.ActiveDocument

        # we have checked before that all this is correct 
        self.selectedLink = Asm4.getSelectedLink()
        #self.rootAssembly = self.selectedLink.getParentGeoFeatureGroup()
        self.rootAssembly = Asm4.getAssembly()

        # has been checked before, this is for security only
        if Asm4.isAsm4EE(self.selectedLink):
            # get the old values
            self.old_AO = self.selectedLink.AttachmentOffset
            self.old_linkLCS = self.selectedLink.AttachedBy[1:]
        else:
            # this shouldn't happen
            FCC.PrintWarning("WARNING : unsupported Assembly/Solver/Part combination, you shouldn't be seeing this\n")
            Asm4.makeAsmProperties(self.selectedLink)
            self.old_AO = []
            self.old_linkLCS = ''

        # define the GUI
        #global taskUI
        #taskUI = self
        # draw the GUI, objects are defined later down
        self.UI = QtGui.QWidget()
        self.form = self.UI        
        iconFile = os.path.join( Asm4.iconPath , 'Place_Link.svg')
        self.form.setWindowIcon(QtGui.QIcon( iconFile ))
        self.form.setWindowTitle('Place linked Part')
        self.drawUI(self.form)

        #save original AttachmentOffset of linked part
        self.old_LinkAttachmentOffset = self.selectedLink.AttachmentOffset
        self.old_LinkRotation = self.selectedLink.AttachmentOffset.Rotation
        self.old_LinkPosition = self.selectedLink.AttachmentOffset.Base
        # default values correspond to original AttachmentOffset of linked part
        self.Xtranslation = self.old_LinkPosition[0]
        self.Ytranslation = self.old_LinkPosition[1]
        self.Ztranslation = self.old_LinkPosition[2]
        self.XrotationAngle = self.old_LinkRotation.toEuler()[0]
        self.YrotationAngle = self.old_LinkRotation.toEuler()[1]
        self.ZrotationAngle = self.old_LinkRotation.toEuler()[2]
        
        # save previous view properties
        self.old_OverrideMaterial = self.selectedLink.ViewObject.OverrideMaterial
        self.old_DrawStyle = self.selectedLink.ViewObject.DrawStyle
        self.old_LineWidth = self.selectedLink.ViewObject.LineWidth
        self.old_DiffuseColor = self.selectedLink.ViewObject.ShapeMaterial.DiffuseColor
        self.old_Transparency = self.selectedLink.ViewObject.ShapeMaterial.Transparency
        # set new view properties
        self.selectedLink.ViewObject.OverrideMaterial = True
        self.selectedLink.ViewObject.DrawStyle = DrawStyle
        self.selectedLink.ViewObject.LineWidth = LineWidth
        self.selectedLink.ViewObject.ShapeMaterial.DiffuseColor = DiffuseColor
        self.selectedLink.ViewObject.ShapeMaterial.Transparency = Transparency
        

        # get the old values
        self.old_EE     = ''
        old_Parent      = ''
        old_ParentPart  = ''
        old_attLCS      = ''
        constrName      = ''
        linkedDoc       = ''
        old_linkLCS     = ''
        # get and store the current expression engine:
        self.old_EE = Asm4.placementEE(self.selectedLink.ExpressionEngine)

        # decode the old ExpressionEngine
        # if the decode is unsuccessful, old_Expression is set to False and the other things are set to 'None'
        (self.old_Parent, separator, self.old_parentLCS) = self.selectedLink.AttachedTo.partition('#')
        ( old_Parent, old_attLCS, old_linkLCS ) = self.splitExpressionLink( self.old_EE, self.old_Parent )
        # sometimes, the object is in << >> which is an error by FreeCAD,
        # because that's reserved for labels, but we still look for it
        if len(old_attLCS)>4 and old_attLCS[:2]=='<<' and old_attLCS[-2:]=='>>':
            old_attLCS = old_attLCS[2:-2]
        if len(old_linkLCS)>4 and old_linkLCS[:2]=='<<' and old_linkLCS[-2:]=='>>':
            old_linkLCS = old_linkLCS[2:-2]

        # initialize the UI with the current data
        self.attLCStable = []
        self.initUI()
        # now self.parentList and self.parentTable are available

        # find all the linked parts in the assembly
        for objName in self.rootAssembly.getSubObjects():
            # remove the trailing .
            obj = self.activeDoc.getObject(objName[0:-1])
            if obj.TypeId=='App::Link' and hasattr(obj.LinkedObject,'isDerivedFrom'):
                if obj.LinkedObject.isDerivedFrom('App::Part') or obj.LinkedObject.isDerivedFrom('PartDesign::Body'):
                # ... except if it's the selected link itself
                    if obj != self.selectedLink:
                        self.parentTable.append( obj )
                        # add to the drop-down combo box with the assembly tree's parts
                        objIcon = obj.LinkedObject.ViewObject.Icon
                        objText = Asm4.labelName(obj)
                        self.parentList.addItem( objIcon, objText, obj)

        # find all the LCS in the selected link
        self.partLCStable = Asm4.getPartLCS( self.selectedLink.LinkedObject )
        # build the list
        self.partLCSlist.clear()
        for lcs in self.partLCStable:
            newItem = QtGui.QListWidgetItem()
            newItem.setText(Asm4.labelName(lcs))
            newItem.setIcon( lcs.ViewObject.Icon )
            self.partLCSlist.addItem(newItem)

        # find the old LCS in the list of LCS of the linked part...
        # MatchExactly, MatchContains, MatchEndsWith ...
        # find with Name ...
        lcs_found = self.partLCSlist.findItems( old_linkLCS, QtCore.Qt.MatchExactly )
        # ... or with (Name)
        if not lcs_found:
            lcs_found = self.partLCSlist.findItems( '('+old_linkLCS+')', QtCore.Qt.MatchEndsWith )
        if lcs_found:
            # ... and select it
            self.partLCSlist.setCurrentItem( lcs_found[0] )

        # find the oldPart in the part list...
        if old_Parent == 'Parent Assembly':
            parent_found = True
            parent_index = 1
        else:
            parent_found = False
            parent_index = 1
            for item in self.parentTable[1:]:
                if item.Name == old_Parent:
                    parent_found = True
                    break
                else:
                    parent_index = parent_index +1
        if not parent_found:
            parent_index = 0
        self.parentList.setCurrentIndex( parent_index )
        # this should have triggered self.getPartLCS() to fill the LCS list

        # find the old attachment Datum in the list of the Datums in the linked part...
        lcs_found = self.attLCSlist.findItems( old_attLCS, QtCore.Qt.MatchExactly )
        if not lcs_found:
            lcs_found = self.attLCSlist.findItems( '('+old_attLCS+')', QtCore.Qt.MatchEndsWith )
        if lcs_found:
            # ... and select it
            self.attLCSlist.setCurrentItem( lcs_found[0] )
        
        Gui.Selection.addObserver(self, 0)


    # Close
    def finish(self):
        # remove the  observer
        Gui.Selection.removeObserver(self)
        self.restoreView()
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection( self.activeDoc.Name, self.rootAssembly.Name, self.selectedLink.Name+'.' )
        # restore previous selection filter (if any)
        if self.selectionFilterStatus:
            selectionFilter.observerEnable()
        Gui.Control.closeDialog()


    # restore initial view properties
    def restoreView(self, normal=True):
        self.selectedLink.ViewObject.OverrideMaterial = False
        self.selectedLink.ViewObject.DrawStyle    = self.old_DrawStyle
        self.selectedLink.ViewObject.LineWidth    = self.old_LineWidth
        self.selectedLink.ViewObject.ShapeMaterial.DiffuseColor = self.old_DiffuseColor
        self.selectedLink.ViewObject.ShapeMaterial.Transparency = self.old_Transparency


    # standard FreeCAD Task panel buttons
    def getStandardButtons(self):
        return int(QtGui.QDialogButtonBox.Cancel
                   | QtGui.QDialogButtonBox.Ok
                   | QtGui.QDialogButtonBox.Apply)


    # OK
    def accept(self):
        if self.Apply():
            # highlight in the 3D window the object we placed
            self.finish()
        else:
            FCC.PrintWarning("Problem in selections\n")
            return


    # Cancel, restore previous values if available
    def reject(self):
        if self.old_AO:
            self.selectedLink.AttachmentOffset = self.old_AO
        if self.old_EE:
            self.selectedLink.setExpression( 'Placement', self.old_EE )
        self.selectedLink.recompute()
        # highlight in the 3D window the object we placed
        self.finish()


    # Free insert
    def clicked(self, button):
        if button == QtGui.QDialogButtonBox.Apply:
            self.Apply()
        elif button == QtGui.QDialogButtonBox.Ignore:
            # ask for confirmation before resetting everything
            msgName = Asm4.labelName(self.selectedLink)
            # see whether the ExpressionEngine field is filled
            if self.selectedLink.ExpressionEngine :
                # if yes, then ask for confirmation
                confirmed = Asm4.confirmBox('This command will release all attachments on '+msgName+' and set it to manual positioning in its current location.')
                # if not, then it's useless to bother the user
            else:
                confirmed = True
            if confirmed:
                # unset the ExpressionEngine for the Placement
                self.selectedLink.setExpression('Placement', None)
                # reset the assembly properties
                Asm4.makeAsmProperties( self.selectedLink, reset=True )
                # finish
                FCC.PrintMessage("Part is now manually placed\n")
                self.finish()
            else:
                FCC.PrintMessage("Part untouched\n")
                self.finish()


    """
    +-----------------------------------------------+
    | check that all necessary things are selected, |
    |   populate the expression with the selected   |
    |    elements, put them into the constraint     |
    |   and trigger the recomputation of the part   |
    +-----------------------------------------------+
    """
    def Apply( self ):
        # get the instance to attach to:
        # it's either the top level assembly or a sister App::Link
        if self.parentList.currentText() == 'Parent Assembly':
            a_Link = 'Parent Assembly'
            a_Part = None
        elif self.parentList.currentIndex() > 1:
            parent = self.parentTable[ self.parentList.currentIndex() ]
            a_Link = parent.Name
            a_Part = parent.LinkedObject.Document.Name
        else:
            a_Link = None
            a_Part = None

        # the attachment LCS's name in the parent
        # check that something is selected in the QlistWidget
        if self.attLCSlist.selectedItems():
            a_LCS = self.attLCStable[ self.attLCSlist.currentRow() ].Name
        else:
            a_LCS = None

        # the linked App::Part's name
        l_Part = self.selectedLink.LinkedObject.Document.Name

        # the LCS's name in the linked part to be used for its attachment
        # check that something is selected in the QlistWidget
        if self.partLCSlist.selectedItems():
            #l_LCS = self.partLCSlist.selectedItems()[0].text()
            l_LCS = self.partLCStable[ self.partLCSlist.currentRow() ].Name
        else:
            l_LCS = None
            
        # check that all of them have something in
        # constrName has been checked at the beginning
        if a_Link and a_LCS and l_Part and l_LCS :
            # add the Asm4 properties if it's a pure App::Link
            Asm4.makeAsmProperties(self.selectedLink)
            # self.selectedLink.AssemblyType = 'Part::Link'
            self.selectedLink.AttachedBy = '#'+l_LCS
            self.selectedLink.AttachedTo = a_Link+'#'+a_LCS
            self.selectedLink.SolverId = 'Placement::ExpressionEngine'
            # build the expression for the ExpressionEngine
            # this is where all the magic is, see:
            # 
            # https://forum.freecadweb.org/viewtopic.php?p=278124#p278124
            #
            # as of FreeCAD v0.19 the syntax is different:
            # https://forum.freecadweb.org/viewtopic.php?f=17&t=38974&p=337784#p337784
            #
            # expr = ParentLink.Placement * ParentPart#LCS.Placement * constr_LinkName.AttachmentOffset * LinkedPart#LCS.Placement ^ -1'			
            # expr = LCS_in_the_assembly.Placement * constr_LinkName.AttachmentOffset * LinkedPart#LCS.Placement ^ -1'			
            expr = Asm4.makeExpressionPart( a_Link, a_Part, a_LCS, l_Part, l_LCS )
            # load the expression into the link's Expression Engine
            self.selectedLink.setExpression('Placement', expr )
            # recompute the object to apply the placement:
            self.selectedLink.recompute()
            self.rootAssembly.recompute(True)
            return True
        else:
            #FCC.PrintWarning("Problem in selections\n")
            return False


    # fill the LCS list when changing the parent
    def onParentSelected(self):
        # clear the selection in the GUI window
        Gui.Selection.clearSelection()
        # build the LCS table
        self.attLCStable = []
        # the current text in the combo-box is the link's name...
        # ... or it's 'Parent Assembly' then the parent is the 'Model' root App::Part
        if self.parentList.currentText() == 'Parent Assembly':
            parentName = 'Parent Assembly'
            parentPart = self.rootAssembly
            # we get the LCS directly in the root App::Part 'Model'
            self.attLCStable = Asm4.getPartLCS( parentPart )
            self.parentDoc.setText( Asm4.labelName(parentPart) )
        # if something is selected
        elif self.parentList.currentIndex() > 1:
            parentName = self.parentTable[ self.parentList.currentIndex() ].Name
            parentPart = self.activeDoc.getObject( parentName )
            if parentPart:
                # we get the LCS from the linked part
                self.attLCStable = Asm4.getPartLCS( parentPart.LinkedObject )
                # linked part & doc
                dText = ''
                if parentPart.LinkedObject.Document != self.activeDoc:
                    dText = parentPart.LinkedObject.Document.Name +'#'
                # if the linked part has been renamed by the user
                pText = Asm4.labelName( parentPart.LinkedObject )
                self.parentDoc.setText( dText + pText )
                '''
                # show all LCS in selected parent
                for lcsName in parentPart.LinkedObject.getSubObjects(1):
                    lcs = parentPart.LinkedObject.Document.getObject(lcsName[0:-1])
                    if lcs.TypeId in [ 'PartDesign::CoordinateSystem', 'PartDesign::Line' ]:
                        lcs.ViewObject.show()
                '''
                # highlight the selected part for a short time:
                Gui.Selection.addSelection( \
                        parentPart.Document.Name, self.rootAssembly.Name, parentPart.Name+'.' )
                QtCore.QTimer.singleShot(1500, lambda:Gui.Selection.removeSelection( \
                        parentPart.Document.Name, self.rootAssembly.Name, parentPart.Name+'.' ) )
        # something wrong
        else:
            return

        # build the list
        self.attLCSlist.clear()
        for lcs in self.attLCStable:
            newItem = QtGui.QListWidgetItem()
            newItem.setText(Asm4.labelName(lcs))
            newItem.setIcon( lcs.ViewObject.Icon )
            self.attLCSlist.addItem( newItem )
            #self.attLCStable.append(lcs)
        return


    # highlight selected LCSs
    def onLCSclicked( self ):
        p_LCS_selected = False
        a_LCS_selected = False
        # LCS of the linked part
        if len(self.partLCSlist.selectedItems())>0:
            p_LCS = self.partLCStable[ self.partLCSlist.currentRow() ]
            p_LCS.Visibility = True
            p_LCStext = self.selectedLink.Name+'.'+p_LCS.Name+'.'
            p_LCS_selected = True
        # LCS in the parent
        if len(self.attLCSlist.selectedItems())>0:
            a_LCS = self.attLCStable[ self.attLCSlist.currentRow() ]
            # get the part where the selected LCS is
            # parent assembly and sister part need a different treatment
            if self.parentList.currentText() == 'Parent Assembly':
                a_LCStext = a_LCS.Name+'.'
            else:
                a_Part = self.parentTable[ self.parentList.currentIndex() ].Name
                a_LCStext = a_Part+'.'+a_LCS.Name+'.'
            a_LCS.Visibility = True
            a_LCS_selected = True
        # clear the selection in the GUI window
        Gui.Selection.clearSelection()
        # apply selections
        if p_LCS_selected:
            Gui.Selection.addSelection( self.activeDoc.Name, self.rootAssembly.Name, p_LCStext)
        if a_LCS_selected:
            Gui.Selection.addSelection( self.activeDoc.Name, self.rootAssembly.Name, a_LCStext)
        return


    # selection observer
    def addSelection(self, doc, obj, sub, pnt):
        selLinkOK = False
        # Since both 3D view clicks and manual tree selection gets into the same callback
        # we will determine by clicked coordinates
        # for manual tree selections the coordinates are (0,0,0)
        # 3D view click
        if pnt != (0,0,0):
            selObj = Gui.Selection.getSelection()[0]
            selPath = Asm4.getSelectionPath(doc, obj, sub)
            if selObj and len(selPath) > 2:
                selLinkName = selPath[2]
                selLink = self.activeDoc.getObject(selLinkName)
                if selLink:
                    selLinkOK = True
            else:
                self.parentList.setCurrentIndex( 1 )
        # tree selection
        elif len(Gui.Selection.getSelection())==1:
            selObj = Gui.Selection.getSelection()[0]
            ( obj, tree ) = Asm4.getSelectionTree()
            if selObj == obj:
                # obj is selected in a root part
                if len(tree)==2:
                    root = App.ActiveDocument.getObject(tree[0])
                    if root==self.rootAssembly:
                        selLinkOK = True
                # obj is in a child part
                elif len(tree)==3:
                    selLinkName = tree[1]
                    selLink = self.activeDoc.getObject(selLinkName)
                    if selLink:
                        selLinkOK = True
        # if selection has been found
        if selLinkOK:
            # if the selected datum belongs to the part to be placed
            if self.selectedLink.Name == selLink.Name:
                found = self.partLCSlist.findItems(Asm4.labelName(selObj), QtCore.Qt.MatchExactly)
                if len(found) > 0:
                    self.partLCSlist.clearSelection()
                    found[0].setSelected(True)
                    self.partLCSlist.scrollToItem(found[0])
                    self.partLCSlist.setCurrentItem(found[0])
                    # show and highlight LCS
                    selObj.Visibility=True
                    self.onLCSclicked()
                    #self.Apply()
            # if the selected datum belongs to another part
            else:
                idx = self.parentList.findText(Asm4.labelName(selLink), QtCore.Qt.MatchExactly)
                # the selected LCS is in a child part
                if idx >= 0:
                    self.parentList.setCurrentIndex(idx)
                # the parent was not found in the child part list
                # may-be the selected LCS is in the Parent Assembly
                else:
                    self.parentList.setCurrentIndex(1)
                # this has triggered to fill in the attachment LCS list
                # now lets try to find the selected LCS in this list
                found = self.attLCSlist.findItems(Asm4.labelName(selObj), QtCore.Qt.MatchExactly)
                if len(found) > 0:
                    self.attLCSlist.clearSelection()
                    found[0].setSelected(True)
                    self.attLCSlist.scrollToItem(found[0])
                    self.attLCSlist.setCurrentItem(found[0])
                    # show and highlight LCS
                    selObj.Visibility=True
                    self.onLCSclicked()
                    #self.Apply()


    # Reorientation
    def reorientLink( self ):
        moveXYZ = App.Placement( App.Vector(self.Xtranslation,self.Ytranslation,self.Ztranslation), self.old_LinkRotation )
        # New AttachmentOffset rotation of the link is difference between set rotation angles and original AttachmentOffset rotation of the link
        rotationX = App.Placement( App.Vector(0.00, 0.00, 0.00), App.Rotation( App.Vector(1,0,0), self.XrotationAngle - self.old_LinkRotation.toEuler()[0] ))
        rotationY = App.Placement( App.Vector(0.00, 0.00, 0.00), App.Rotation( App.Vector(0,1,0), self.YrotationAngle - self.old_LinkRotation.toEuler()[1] ))
        rotationZ = App.Placement( App.Vector(0.00, 0.00, 0.00), App.Rotation( App.Vector(0,0,1), self.ZrotationAngle - self.old_LinkRotation.toEuler()[2] ))

        self.selectedLink.AttachmentOffset = moveXYZ * rotationX * rotationY * rotationZ
        self.selectedLink.recompute()

        
    def onXTranslValChanged(self):
        self.Xtranslation = self.XtranslSpinBox.value()
        self.reorientLink()
        
    def onYTranslValChanged(self):
        self.Ytranslation = self.YtranslSpinBox.value()
        self.reorientLink()
        
    def onZTranslValChanged(self):
        self.Ztranslation = self.ZtranslSpinBox.value()
        self.reorientLink()
        
    # Rotations
    def onRotX(self):
        if self.XrotationAngle > 270.0: 
            self.XrotationAngle = self.XrotationAngle - 270.0
        else:
            self.XrotationAngle = self.XrotationAngle + 90.0
        self.reorientLink()

    def onRotY(self):
        if self.YrotationAngle > 270.0: 
            self.YrotationAngle = self.YrotationAngle - 270.0
        else:
            self.YrotationAngle = self.YrotationAngle + 90.0
        self.reorientLink()

    def onRotZ(self):
        if self.ZrotationAngle > 270.0: 
            self.ZrotationAngle = self.ZrotationAngle - 270.0
        else:
            self.ZrotationAngle = self.ZrotationAngle + 90.0
        self.reorientLink()


    """
        +-----------------------------------------------+
        |  split the ExpressionEngine of a linked part  |
        |          to find the old attachments          |
        |   (in the parent assembly or a sister part)   |
        |   and the old target LCS in the linked Part   |
        +-----------------------------------------------+
    """
    def splitExpressionLink( self, expr, parent ):
        # same document:
        # expr = LCS_target.Placement * AttachmentOffset * LCS_attachment.Placement ^ -1
        # external document:
        # expr = LCS_target.Placement * AttachmentOffset * linkedPart#LCS_attachment.Placement ^ -1
        # expr = sisterLink.Placement * sisterPart#LCS_target.Placement * AttachmentOffset * linkedPart#LCS_attachment.Placement ^ -1
        retval = ( expr, 'None', 'None' )
        restFinal = ''
        attLink = ''
        # expr is empty
        if not expr:
            return retval
        nbHash = expr.count('#')
        if nbHash==0:
            # linked part, sister part and assembly in the same document
            if parent == 'Parent Assembly':
                # we're attached to an LCS in the parent assembly
                # expr = LCS_in_the_assembly.Placement * AttachmentOffset * LCS_linkedPart.Placement ^ -1
                ( attLCS,     separator, rest1 ) = expr.partition('.Placement * AttachmentOffset * ')
                ( linkLCS,    separator, rest2 ) = rest1.partition('.Placement ^ ')
                restFinal = rest2[0:2]
                attLink = parent
                attPart = 'None'
            else:
                # we're attached to an LCS in a sister part
                # expr = ParentLink.Placement * LCS_parent.Placement * AttachmentOffset * LCS_linkedPart.Placement ^ -1
                ( attLink,    separator, rest1 ) = expr.partition('.Placement * ')
                ( attLCS,     separator, rest2 ) = rest1.partition('.Placement * AttachmentOffset * ')
                ( linkLCS,    separator, rest3 ) = rest2.partition('.Placement ^ ')
                restFinal = rest3[0:2]
        elif nbHash==1:
            # an external part is linked to the assembly or a part in the same document as the assembly
            if parent == 'Parent Assembly':
                # we're attached to an LCS in the parent assembly
                # expr = LCS_assembly.Placement * AttachmentOffset * LinkedPart#LCS.Placement ^ -1'			
                ( attLCS,     separator, rest1 ) = expr.partition('.Placement * AttachmentOffset * ')
                ( linkedDoc,  separator, rest2 ) = rest1.partition('#')
                ( linkLCS,    separator, rest3 ) = rest2.partition('.Placement ^ ')
                restFinal = rest3[0:2]
                attLink = parent
                attPart = 'None'
            # a part from the document is attached to an external part
            else:
                # expr = Rail_40x40_Y.Placement * Rails_V_Slot#LCS_AR.Placement * AttachmentOffset * LCS_Plaque_Laterale_sym.Placement ^ -1
                # expr = parentLink.Placement * externalDoc#LCS_parentPart * AttachmentOffset * LCS_linkedPart.Placement ^ -1
                ( attLink,    separator, rest1 ) = expr.partition('.Placement * ')
                ( linkedDoc,  separator, rest2 ) = rest1.partition('#')
                ( attLCS,     separator, rest3 ) = rest2.partition('.Placement * AttachmentOffset * ')
                ( linkLCS,    separator, rest4 ) = rest3.partition('.Placement ^ ')
                restFinal = rest4[0:2]
        elif nbHash==2:
            # linked part and sister part in external documents to the parent assembly:
            # expr = ParentLink.Placement * ParentPart#LCS.Placement * AttachmentOffset * LinkedPart#LCS.Placement ^ -1'			
            ( attLink,    separator, rest1 ) = expr.partition('.Placement * ')
            ( attPart,    separator, rest2 ) = rest1.partition('#')
            ( attLCS,     separator, rest3 ) = rest2.partition('.Placement * AttachmentOffset * ')
            ( linkedDoc,  separator, rest4 ) = rest3.partition('#')
            ( linkLCS,    separator, rest5 ) = rest4.partition('.Placement ^ ')
            restFinal = rest5[0:2]
        else:
            # complicated stuff, we'll do it later
            pass
        # final check, all options should give the correct data
        if restFinal=='-1' and attLink==parent :
            # wow, everything went according to plan
            # retval = ( expr, attPart, attLCS, constrLink, partLCS )
            retval = ( attLink, attLCS, linkLCS )
        return retval


    """
        +-----------------------------------------------+
        |                    the UI                     |
        +-----------------------------------------------+
    """
    # initialize the UI for the selected link
    def initUI(self):
        # clear the parent name (if any)
        self.parentDoc.clear()
        self.partLCSlist.clear()
        self.attLCSlist.clear()
        # the selected link's name 
        self.linkName.setText( Asm4.labelName(self.selectedLink) )
        # linked part & doc
        dText = ''
        if self.selectedLink.LinkedObject.Document != self.activeDoc :
            dText = self.selectedLink.LinkedObject.Document.Name +'#'
        # if the linked part has been renamed by the user, keep the label and add (.Name)
        pText = Asm4.labelName(self.selectedLink.LinkedObject)
        self.linkedDoc.setText( dText + pText )
        # Initialize the assembly tree with the Parent Assembly as first element
        # clear the available parents combo box
        self.parentTable = []
        self.parentList.clear()
        self.parentTable.append( [] )
        self.parentList.addItem('Please select')
        self.parentTable.append( self.rootAssembly )
        parentIcon = self.rootAssembly.ViewObject.Icon
        self.parentList.addItem( parentIcon, 'Parent Assembly', self.rootAssembly )
        # set the old position values
        self.XtranslSpinBox.setValue(self.old_LinkPosition[0])
        self.YtranslSpinBox.setValue(self.old_LinkPosition[1])
        self.ZtranslSpinBox.setValue(self.old_LinkPosition[2])



    # defines the UI, only static elements
    def drawUI(self,Form):
        # the layout for the main window is vertical (top to down)
        self.mainLayout = QtGui.QVBoxLayout(Form)
        
        # Define the fields for the form ( label + widget )
        self.formLayout = QtGui.QFormLayout(Form)
        # Selected Link (the name as seen in the tree of the selected link)
        self.linkName = QtGui.QLineEdit(Form)
        self.linkName.setReadOnly(True)
        self.formLayout.addRow(QtGui.QLabel('Selected Link :'),self.linkName)

        # combobox showing all available App::Link
        self.parentList = QtGui.QComboBox(Form)
        self.parentList.setMaximumWidth(300)
        self.parentList.setToolTip('Choose the part in which the attachment\ncoordinate system is to be found')
        # the parent assembly is hardcoded, and made the first real element
        self.formLayout.addRow(QtGui.QLabel('Attach to :'),self.parentList)
        self.mainLayout.addLayout(self.formLayout)

        # with 2 columns
        self.columnsLayout = QtGui.QHBoxLayout(Form)
        self.leftLayout = QtGui.QVBoxLayout(Form)
        self.rightLayout = QtGui.QVBoxLayout(Form)
        # Part, left side
        #
        # the document containing the linked part
        self.leftLayout.addWidget(QtGui.QLabel("Linked Part :"))
        self.linkedDoc = QtGui.QLineEdit(Form)
        self.linkedDoc.setReadOnly(True)
        self.leftLayout.addWidget(self.linkedDoc)

        # The list of all LCS in the part is a QListWidget
        self.leftLayout.addWidget(QtGui.QLabel("Select LCS in Part :"))
        self.partLCSlist = QtGui.QListWidget(self.form)
        self.partLCSlist.setMinimumHeight(200)
        self.partLCSlist.setToolTip('Select a coordinate system from the list')
        self.leftLayout.addWidget(self.partLCSlist)

        # Assembly, Right side
        #
        # the document containing the linked object
        self.rightLayout.addWidget(QtGui.QLabel("Parent Part :"))
        self.parentDoc = QtGui.QLineEdit(Form)
        self.parentDoc.setReadOnly(True)
        self.rightLayout.addWidget(self.parentDoc)
        # The list of all attachment LCS in the assembly is a QListWidget
        # it is populated only when the parent combo-box is activated
        self.rightLayout.addWidget(QtGui.QLabel("Select LCS in Parent :"))
        self.attLCSlist = QtGui.QListWidget(self.form)
        self.attLCSlist.setMinimumHeight(200)
        self.attLCSlist.setToolTip('Select a coordinate system from the list')
        self.rightLayout.addWidget(self.attLCSlist)

        # add the 2 columns
        self.columnsLayout.addLayout(self.leftLayout)
        self.columnsLayout.addLayout(self.rightLayout)
        self.mainLayout.addLayout(self.columnsLayout)

        # X Translation Value
        self.XoffsetLayout = QtGui.QHBoxLayout(Form)
        self.XtranslSpinBoxLabel = self.XoffsetLayout.addWidget(QtGui.QLabel("X Translation :"))
        self.XtranslSpinBox = QtGui.QDoubleSpinBox(Form)
        self.XtranslSpinBox.setRange(-999999.00, 999999.00)
        #self.XtranslSpinBox.setValue(self.Xtranslation)
        self.XtranslSpinBox.setToolTip("Translation along X axis")
        self.RotXButton = QtGui.QPushButton('Rotate X +90°')
        self.RotXButton.setToolTip("Rotate 90 deg around X axis")
        # add the QLDoubleSpinBox
        self.XoffsetLayout.addWidget(self.XtranslSpinBox)
        self.XoffsetLayout.addStretch()
        self.XoffsetLayout.addWidget(self.RotXButton)
        self.mainLayout.addLayout(self.XoffsetLayout)

        # Y Translation Value
        self.YoffsetLayout = QtGui.QHBoxLayout(Form)
        self.YtranslSpinBoxLabel = self.YoffsetLayout.addWidget(QtGui.QLabel("Y Translation :"))
        self.YtranslSpinBox = QtGui.QDoubleSpinBox(Form)
        self.YtranslSpinBox.setRange(-999999.00, 999999.00)
        #self.YtranslSpinBox.setValue(self.Ytranslation)
        self.YtranslSpinBox.setToolTip("Translation along Y")
        self.RotYButton = QtGui.QPushButton('Rotate Y +90°')
        self.RotYButton.setToolTip("Rotate 90 deg around Y axis")
        # add the QLDoubleSpinBox
        self.YoffsetLayout.addWidget(self.YtranslSpinBox)
        self.YoffsetLayout.addStretch()
        self.YoffsetLayout.addWidget(self.RotYButton)
        self.mainLayout.addLayout(self.YoffsetLayout)

        # Z Translation Value
        self.ZoffsetLayout = QtGui.QHBoxLayout(Form)
        self.ZtranslSpinBoxLabel = self.ZoffsetLayout.addWidget(QtGui.QLabel("Z Translation :"))
        self.ZtranslSpinBox = QtGui.QDoubleSpinBox(Form)
        self.ZtranslSpinBox.setRange(-999999.00, 999999.00)
        #self.ZtranslSpinBox.setValue(self.Ztranslation)
        self.ZtranslSpinBox.setToolTip("Translation along Z:")
        self.RotZButton = QtGui.QPushButton('Rotate Z +90°')
        self.RotZButton.setToolTip("Rotate 90 deg around Z axis")
        # add to the layout
        self.ZoffsetLayout.addWidget(self.ZtranslSpinBox)
        self.ZoffsetLayout.addStretch()
        self.ZoffsetLayout.addWidget(self.RotZButton)
        self.mainLayout.addLayout(self.ZoffsetLayout)

        # apply the layout to the main window
        self.form.setLayout(self.mainLayout)

        # Actions
        self.parentList.currentIndexChanged.connect( self.onParentSelected )
        self.parentList.activated.connect( self.onParentSelected )
        self.partLCSlist.itemClicked.connect( self.onLCSclicked )
        self.attLCSlist.itemClicked.connect(  self.onLCSclicked )
        self.RotXButton.clicked.connect( self.onRotX )
        self.RotYButton.clicked.connect( self.onRotY )
        self.RotZButton.clicked.connect( self.onRotZ )
        self.XtranslSpinBox.valueChanged.connect(self.onXTranslValChanged)
        self.YtranslSpinBox.valueChanged.connect(self.onYTranslValChanged)
        self.ZtranslSpinBox.valueChanged.connect(self.onZTranslValChanged)


    
"""
    +-----------------------------------------------+
    |       add the command to the workbench        |
    +-----------------------------------------------+
"""
Gui.addCommand( 'Asm4_placeLink', placeLinkCmd() )
