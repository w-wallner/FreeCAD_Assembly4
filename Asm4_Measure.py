#!/usr/bin/python
# -*- coding: utf-8 -*-
#****************************************************************************
#*                                                                          *
#* by Zoltan Hubert                                                         *
#*                                                                          *
#*   code partially based on:                                               *
#*                                                                          *
#* Caliper tool, icons by easyw-fc                                          *
#* evolution of Macro_CenterFace                                            *
#* some part of Macro WorkFeature                                           *
#* and Macro Rotate To Point, Macro_Delta_xyz                               *
#* and assembly2                                                            *
#*                                                                          *
#* Measure tool                                                             *
#*                                                                          *
#*    This is a stand-alone tool that doesn't need anything outside Part    *                                                                     *
#*                                                                          *
#*    This program is free software; you can redistribute it and/or modify  *
#*    it under the terms of the GNU Library General Public License (LGPL)   *
#*    as published by the Free Software Foundation; either version 2 of     *
#*    the License, or (at your option) any later version.                   *
#*    for detail see the LICENCE text file.                                 *
#****************************************************************************




import threading, sys, math, os
import numpy as np
import base64

from PySide import QtGui, QtCore
#from pivy import coin

import FreeCADGui as Gui
import FreeCAD as App
from FreeCAD import Base
from FreeCAD import Console as FCC
import Part

# only needed for icons
import libAsm4 as Asm4




"""
    +-----------------------------------------------+
    |                Global variables               |
    +-----------------------------------------------+
"""
global taskUI, addedDims, PtS
addedDims = []
PtS = None


annoFontSize = 12.0
annoPrecision = 0.001
iconDir = Asm4.iconPath


# remove previous snap point
def removePtS():
    global PtS
    if PtS and hasattr(PtS,'Name') and App.ActiveDocument.getObject(PtS.Name):
        App.ActiveDocument.removeObject(PtS.Name)
        PtS = None


# usage:
# object = App.ActiveDocument.addObject('App::FeaturePython','objName')
# object.ViewObject.Proxy = setCustomIcon(object,'Icon.svg')
# import base64
# encoded = base64.b64encode(open("filename.png", "rb").read())
class setCustomIcon():
    def __init__( self, obj, iconFile ):
        icon = os.path.join( iconDir , iconFile )
        self.customIcon = icon
        
    def getIcon(self):
        return self.customIcon


"""
    +-----------------------------------------------+
    |         The menu and toolbar command          |
    +-----------------------------------------------+
"""
class MeasureCmd():
    def __init__(self):
        super(MeasureCmd,self).__init__()

    def GetResources(self):
        return {"MenuText": "Measure",
                "ToolTip": "Measure Tool",
                "Pixmap" : os.path.join( iconDir , 'Part_Measure.svg')
                }

    def IsActive(self):
        if App.ActiveDocument:
            return True
        return False

    def Activated(self):
        Gui.Control.showDialog( MeasureUI() )




"""
    +-----------------------------------------------+
    |    The UI and functions in the Task panel     |
    +-----------------------------------------------+
"""
class MeasureUI():

    def __init__(self):
        self.base = QtGui.QWidget()
        self.form = self.base
        iconFile = os.path.join( iconDir , 'Part_Measure.svg')
        self.form.setWindowIcon(QtGui.QIcon( iconFile ))
        self.form.setWindowTitle('Measure')

        # draw the GUI, objects are defined later down
        self.drawUI()
        global taskUI
        taskUI = self
        global PtS
        global addedDims

        # start the observer
        Gui.Selection.clearSelection()
        #self.so=SelObserverCaliper()
        self.so = selectionObserver()
        Gui.Selection.addObserver( self.so, 1 ) # 1 = resolve
        FCC.PrintMessage('Observer started\n')

        # enable the measurement points
        self.Selection1.setEnabled(True)
        self.Selection1.setChecked(False)
        self.Selection2.setEnabled(False)
        self.sel1Icon.setIcon(QtGui.QIcon(self.selectIcon))
        # init finished


    # standard FreeCAD Task panel buttons
    def getStandardButtons(self):
        return int(   QtGui.QDialogButtonBox.Cancel
                    | QtGui.QDialogButtonBox.Reset
                    | QtGui.QDialogButtonBox.Ok )

    # OK button
    def accept(self):
        # update the Measure group to get rid if the smal overlay icon
        App.ActiveDocument.recompute()
        self.Finish()

    # Cancel button
    def reject(self):
        self.Reset()
        self.Finish()

    # Reset button
    def clicked(self, button):
        if button == QtGui.QDialogButtonBox.Reset:
            self.Reset()

    # Close
    def Finish(self):
        FCC.PrintMessage("closing ... ")
        try:
            Gui.Selection.removeObserver(self.so)   # desinstalle la fonction residente SelObserver
            FCC.PrintMessage("done\n")
        except:
            FCC.PrintWarning("was not able to remove observer\n")
        # remove PtS because it can have strange results
        removePtS()
        # close Task widget
        Gui.Control.closeDialog()

    # Reset (clear measures)
    def Reset(self):
        global PtS, addedDims
        Gui.Selection.clearSelection()
        self.clearConsole()
        FCC.PrintMessage('Removing all measurements ...')
        removePtS()
        for d in addedDims:
            FCC.PrintMessage('.')
            try:
                App.ActiveDocument.removeObject(d.Name)
            except:
                pass
        addedDims=[]
        # remove also the "Measures" group if any
        if App.ActiveDocument.getObject('Measures') and \
                    App.ActiveDocument.getObject('Measures').TypeId=='App::DocumentObjectGroup':
            App.ActiveDocument.removeObject('Measures')
        # clear UI
        self.sel1Name.clear()
        self.sel2Name.clear()
        self.sel1Icon.setIcon(QtGui.QIcon(self.selectIcon))
        self.sel2Icon.setIcon(QtGui.QIcon(self.noneIcon))
        self.Selection1.setEnabled(True)
        self.Selection1.setChecked(False)
        self.Selection2.setEnabled(False)
        self.resultText.clear()
        FCC.PrintMessage(' done\n')


    # clear report view and Python panel
    def clearConsole(self):
        #clearing previous messages
        mw = Gui.getMainWindow()
        #c=mw.findChild(QtGui.QPlainTextEdit, "Python console")
        #c.clear()
        rv = mw.findChild(QtGui.QTextEdit, "Report view")
        rv.clear()

    # Actions
    #
    # when changing the measurement type, reset pre-existing selection
    def onMeasure_toggled(self):
        global PtS
        self.Selection1.setChecked(False)
        self.Selection2.setEnabled(False)
        Gui.Selection.clearSelection()
        removePtS()
        self.sel1Icon.setIcon(QtGui.QIcon(self.selectIcon))
        self.sel2Icon.setIcon(QtGui.QIcon(self.noneIcon))
        # Angle dimensions only work with Snap selection
        if self.rbAngle.isChecked():
            self.rbShape.setChecked(True)

    # re-initialize Selection 1
    def onSel1_toggled(self):
        if not self.Selection1.isChecked() and self.Selection2.isEnabled():
            self.Selection1.setChecked(False)
            self.sel1Name.clear()
            self.Selection2.setEnabled(False)
            Gui.Selection.clearSelection()
            removePtS()
            self.sel1Icon.setIcon(QtGui.QIcon(self.selectIcon))
            self.sel2Icon.setIcon(QtGui.QIcon(self.noneIcon))
        else:
            if not self.Selection2.isEnabled():
                self.Selection1.setChecked(False)
                self.sel1Icon.setIcon(QtGui.QIcon(self.selectIcon))
                #self.sel2Icon.setIcon(QtGui.QIcon(self.noneIcon))

    # Angle can be measured only between shapes
    def onSnap_toggled(self):
        if self.rbAngle.isChecked() and self.rbSnap.isChecked():
            self.rbDistance.setChecked(True)


    # defines the UI, only static elements
    def drawUI(self):
        iconSize = 32
        btSize = 48
        btn_sizeX=32;btn_sizeY=32;
        btn_sizeX=32;btn_sizeY=32;
        chkb_sizeX=20;chkb_sizeY=20;
        btn_sm_sizeX=20;btn_sm_sizeY=20;
        btn_md_sizeX=26;btn_md_sizeY=26;
        
        # icons of UI
        pm = QtGui.QPixmap()
        self.noneIcon      = None
        pm.loadFromData(base64.b64decode(    valid_b64         ))
        self.validIcon     = QtGui.QIcon(pm)
        pm.loadFromData(base64.b64decode(    select_b64        ))
        self.selectIcon    = QtGui.QIcon(pm)
        # icons for the tree
        self.pointIcon     = 'Draft_Point.svg'
        self.lineIcon      = 'Draft_Line.svg'
        self.circleIcon    = 'Draft_Circle.svg'
        self.dimensionIcon = 'Draft_Dimension.svg'

        # the layout for the main window is vertical (top to down)
        self.mainLayout = QtGui.QVBoxLayout(self.form)

        # measurement type
        self.mainLayout.addWidget(QtGui.QLabel('Controls'))
        self.measureGroup = QtGui.QFrame(self.form)
        self.measureGroup.setFrameStyle(QtGui.QFrame.StyledPanel | QtGui.QFrame.Plain)
        self.mainLayout.addWidget(self.measureGroup)
        self.measureGrid = QtGui.QGridLayout(self.measureGroup)
        self.mainLayout.addLayout(self.measureGrid)

        # 0,0
        pm.loadFromData(base64.b64decode(Dim_Radius_b64))
        self.rbRadius = QtGui.QRadioButton(self.measureGroup)
        self.rbRadius.setObjectName("rbRadius")
        self.rbRadius.setToolTip("Measure Radius of Arc or Circle\nMeasure Length of Edge")
        self.rbRadius.setIconSize(QtCore.QSize(btn_md_sizeX,btn_md_sizeY))
        self.rbRadius.setIcon(QtGui.QIcon(pm))
        self.rbRadius.setChecked(True)
        self.measureGrid.addWidget(self.rbRadius, 0, 0 )
        # 0,1
        pm.loadFromData(base64.b64decode(Dim_Length_b64))
        self.rbDistance = QtGui.QRadioButton(self.measureGroup)
        self.rbDistance.setObjectName("rbDistance")
        self.rbDistance.setToolTip("Measure Distance")
        self.rbDistance.setIconSize(QtCore.QSize(btn_md_sizeX,btn_md_sizeY))
        self.rbDistance.setIcon(QtGui.QIcon(pm))
        self.measureGrid.addWidget(self.rbDistance, 0, 1 )
        # 0,2
        pm.loadFromData(base64.b64decode(Dim_Angle_b64))
        self.rbAngle = QtGui.QRadioButton(self.measureGroup)
        self.rbAngle.setObjectName("rbAngle")
        self.rbAngle.setToolTip("Measure Angle")
        self.rbAngle.setIconSize(QtCore.QSize(btn_md_sizeX,btn_md_sizeY))
        self.rbAngle.setIcon(QtGui.QIcon(pm))
        self.measureGrid.addWidget(self.rbAngle, 0, 2 )

        # actual measurement tools
        self.snapGroup = QtGui.QFrame(self.form)
        self.snapGroup.setFrameStyle(QtGui.QFrame.StyledPanel | QtGui.QFrame.Plain)
        # self.snapGroup.setTitle("Selection method")
        self.mainLayout.addWidget(self.snapGroup)
        self.snapGrid = QtGui.QGridLayout(self.snapGroup)
        self.mainLayout.addLayout(self.snapGrid)
        self.selectGrid = QtGui.QGridLayout(self.snapGroup)

        # 0,0
        pm.loadFromData(base64.b64decode(Snap_Options_b64))
        self.rbSnap = QtGui.QRadioButton(self.snapGroup)
        self.rbSnap.setObjectName("rbSnap")
        self.rbSnap.setToolTip("Snap to EndPoint, MiddlePoint, Center")
        self.rbSnap.setIconSize(QtCore.QSize(3*btn_md_sizeX,btn_md_sizeY))
        self.rbSnap.setIcon(QtGui.QIcon(pm))
        self.rbSnap.setChecked(False)
        self.snapGrid.addWidget(self.rbSnap, 0, 0, 1, 2 )

        # 0,2
        pm.loadFromData(base64.b64decode(Center_Mass_b64))
        self.rbShape = QtGui.QRadioButton(self.snapGroup)
        self.rbShape.setObjectName("rbShape")
        self.rbShape.setToolTip("Select Shape")
        self.rbShape.setIconSize(QtCore.QSize(btn_md_sizeX,btn_md_sizeY))
        self.rbShape.setIcon(QtGui.QIcon(pm))
        self.rbShape.setChecked(True)
        self.snapGrid.addWidget(self.rbShape, 0, 2 )

        # first element
        self.Selection1 = QtGui.QPushButton('Selection 1')
        self.Selection1.setToolTip("Select First Element")
        self.Selection1.setMaximumWidth(150)
        self.Selection1.setCheckable(True)
        self.Selection1.setChecked(False)
        self.sel1Name  = QtGui.QLineEdit()
        self.sel1Name.setMinimumWidth (50)
        self.sel1Name.setReadOnly(True)
        self.sel1Icon = QtGui.QPushButton()
        self.sel1Icon.setFlat(True)
        self.sel1Icon.setMinimumSize(QtCore.QSize(iconSize, iconSize))
        self.sel1Icon.setMaximumSize(QtCore.QSize(iconSize, iconSize))
        self.sel1Icon.setIconSize(QtCore.QSize(iconSize,iconSize))
        self.sel1Icon.setIcon(QtGui.QIcon(self.noneIcon))
        self.selectGrid.addWidget(self.Selection1, 0,0)
        self.selectGrid.addWidget(self.sel1Name,   0,1)
        self.selectGrid.addWidget(self.sel1Icon,   0,2)

        # second element
        self.Selection2 = QtGui.QPushButton('Selection 2')
        self.Selection2.setToolTip("Select Second Element")
        self.Selection2.setMaximumWidth(150)
        self.Selection2.setEnabled(False)
        self.Selection2.setChecked(False)
        self.sel2Name  = QtGui.QLineEdit()
        self.sel2Name.setMinimumWidth (50)
        self.sel2Name.setReadOnly(True)
        self.sel2Icon = QtGui.QPushButton()
        self.sel2Icon.setFlat(True)
        self.sel2Icon.setMinimumSize(QtCore.QSize(iconSize, iconSize))
        self.sel2Icon.setMaximumSize(QtCore.QSize(iconSize, iconSize))
        self.sel2Icon.setIconSize(QtCore.QSize(iconSize,iconSize))
        self.sel2Icon.setIcon(QtGui.QIcon(self.noneIcon))
        self.selectGrid.addWidget(self.Selection2, 1,0)
        self.selectGrid.addWidget(self.sel2Name,   1,1)
        self.selectGrid.addWidget(self.sel2Icon,   1,2)

        self.mainLayout.addLayout(self.selectGrid)
        
        # Results
        self.Results_Group = QtGui.QGroupBox(self.form)
        self.Results_Group.setToolTip("Results")
        self.Results_Group.setTitle("Results")
        self.Results_Group.setObjectName("Results_Group")
        self.mainLayout.addWidget(self.Results_Group)
        self.resultLayout = QtGui.QVBoxLayout(self.Results_Group)

        # draw annotation in the GUI window
        self.bLabel = QtGui.QCheckBox(self.Results_Group)
        self.bLabel.setObjectName("bLabel")
        self.bLabel.setToolTip("Enable extra Label")
        self.bLabel.setText("Show Label in 3D view")
        self.bLabel.setChecked(True)
        self.resultLayout.addWidget(self.bLabel)

        # draw X-Y-Z components
        self.Components = QtGui.QCheckBox(self.Results_Group)
        self.Components.setObjectName("Components")
        self.Components.setToolTip("Show all dimension components")
        self.Components.setText("Show Components")
        self.Components.setChecked(False)
        self.resultLayout.addWidget(self.Components)

        # Results
        self.resultText = QtGui.QTextEdit()
        self.resultText.setMinimumSize(200, 200)
        self.resultText.setReadOnly(True)
        self.resultLayout.addWidget(self.resultText)
        
        # apply the layout to the main window
        self.mainLayout.addLayout(self.resultLayout)
        
        self.form.setLayout(self.mainLayout)

        # Actions
        self.rbRadius.toggled.connect(self.onMeasure_toggled)
        self.rbDistance.toggled.connect(self.onMeasure_toggled)
        self.rbAngle.toggled.connect(self.onMeasure_toggled)
        #self.rbAngle.toggled.connect(self.onAngle_toggled)
        self.rbSnap.toggled.connect(self.onSnap_toggled)
        self.Selection1.toggled.connect(self.onSel1_toggled)



"""
    +-----------------------------------------------+
    |    a selection observer resident function     |
    +-----------------------------------------------+
"""
class selectionObserver():
    def __init__(self):
        global PtS
        self.Sel1 = None
        self.Shp1 = None
        self.Pt1  = None
        self.Sel2 = None
        self.Shp2 = None
        self.Pt2  = None
        PtS       = None

    def render_distance(self, distance: int) -> str:
        return App.Units.schemaTranslate(
            App.Units.Quantity(str(distance) + " mm"),
            App.Units.getSchema(),
        )[0]

    # add the dim to the global addedDims table to be able to remove it
    # add it also the the "Measures" group
    def addToDims( self, dim ):
        global addedDims
        # check whether there is a "Measures" group
        if not App.ActiveDocument.getObject('Measures'):
            # if no, create one
            measuresGroup = App.ActiveDocument.addObject( 'App::DocumentObjectGroup', 'Measures' )
        # if there is already one, use it
        elif App.ActiveDocument.getObject('Measures').TypeId=='App::DocumentObjectGroup':
            measuresGroup = App.ActiveDocument.getObject('Measures')
        # there is already a "Measures" object but it's not a Group, don't use it
        else:
            measuresGroup = None
        if measuresGroup:
            measuresGroup.addObject(dim)
        # finally, add the dim to the global addedDims table/list
        addedDims.append(dim)

    # the real function
    def addSelection(self, document, obj, element, position):
        global taskUI
        global PtS

        fntsize='0.25mm'
        ticksize='0.1mm'

        # Select a subObject w/ the full hierarchy information
        # empty string means current document, '*' means all document. 
        # The second argument 1 means resolve sub-object, which is the default value. 0 means full hierarchy.
        # sel = Gui.Selection.getSelectionEx('', 0)[0].SubObjects[0]
        sel = Gui.Selection.getSelectionEx('', 0) 
        selobject = Gui.Selection.getSelection()
        if len(selobject) == 1 or len(sel) == 1:# or (len(selobject) == 1 and len(sel) == 1):
            #Faces or Edges
            if len(sel[0].SubObjects)>0: 
                subShape = sel[0].SubObjects[0]
                # if valid selection
                if subShape.isValid() and ('Face' in str(subShape) or 'Edge' in str(subShape) or 'Vertex' in str(subShape)):
                    # clear the result area
                    taskUI.resultText.clear()
                    removePtS()

                    # first element selection
                    if not taskUI.Selection1.isChecked():
                        # figure out the first selected element
                        self.Sel1 = None
                        self.Shp1 = None
                        self.Pt1  = None
                        self.Sel2 = None
                        self.Shp2 = None
                        self.Pt2  = None
                        #taskUI.sel1Name.setText(str(subShape))
                        taskUI.sel1Name.setText(str(subShape).split(' ')[0][1:])
                        taskUI.sel2Name.clear()                        # shape selected
                        if taskUI.rbShape.isChecked():
                            # the shape is actually a vertex, thus a point
                            if 'Vertex' in str(subShape):
                                self.Pt1 = subShape.Vertexes[0].Point
                                PtS  = self.drawPoint(self.Pt1)
                                self.Sel1 = 'point'
                            # all other (real) shapes
                            else:
                                self.Shp1 = subShape
                                self.Sel1 = 'shape'
                        # Snap to select a point
                        elif taskUI.rbSnap.isChecked():
                            self.Pt1 = self.getSnap(subShape)
                            if self.Pt1:
                                PtS  = self.drawPoint(self.Pt1)
                                self.Sel1 = 'point'
                        # this measures single objects
                        if taskUI.rbRadius.isChecked():
                            # if we have snapped a point before, we show its coordinates
                            if self.Sel1 == 'point':
                                self.measureCoords(self.Pt1)
                            # if we have selected a shape before, we show its charcteristics
                            elif self.Sel1 == 'shape':
                                # a surface
                                if 'Face' in str(self.Shp1):
                                    self.measureArea(self.Shp1)
                                # a point (should have been caught before)
                                elif 'Vertex' in str(self.Shp1):
                                    self.measureCoords( self.Shp1 )
                                # a circle or arc of circle
                                # elif hasattr(self.Shp1,'Curve') and hasattr(self.Shp1.Curve,'Radius'):
                                elif self.isCircle(self.Shp1):
                                    taskUI.sel1Name.setText('Circle')
                                    self.measureCircle( self.Shp1 )
                                # a straight line segment
                                #elif hasattr(self.Shp1,'Curve') and self.Shp1.Curve.TypeId=='Part::GeomLine':
                                elif self.isSegment(self.Shp1):
                                    taskUI.sel1Name.setText('Segment')
                                    self.measureLine( self.Shp1 )
                                # dunno what that stuff is
                                else:
                                    self.printResult("Can't measure\n"+str(self.Shp1))
                            # dunno what that stuff is
                            else:
                                self.printResult("Can't measure\n"+str(subShape))
                            # unset first selection
                            self.Sel1 == None
                        # if not rbRadius, launch the selection of the second element
                        elif self.Sel1 is not None:
                            #taskUI.Selection1.setEnabled(False)
                            taskUI.Selection2.setEnabled(True)
                            taskUI.Selection1.setChecked(True)
                            taskUI.sel1Icon.setIcon(QtGui.QIcon(taskUI.validIcon))
                            taskUI.sel2Icon.setIcon(QtGui.QIcon(taskUI.selectIcon))

                    # second element selected
                    elif taskUI.Selection2.isEnabled(): #step #2
                        #if PtS and ha#sattr(PtS,'Name') and App.ActiveDocument.getObject(PtS.Name):
                        #    App.ActiveDocument.removeObject(PtS.Name)
                        #    PtS = None
                        # figure out the second selected element
                        taskUI.sel2Name.setText(str(subShape).split(' ')[0][1:])
                        if taskUI.rbShape.isChecked():
                            self.Sel2 = 'shape'
                            self.Shp2 = subShape
                        # Snap to select a point
                        elif taskUI.rbSnap.isChecked():
                            self.Pt2 = self.getSnap(subShape)
                            if self.Pt2:
                                self.Sel2 = 'point'
                        # if we have a valid selection:
                        if self.Sel2 is not None:
                            taskUI.Selection2.setEnabled(False)
                            taskUI.Selection1.setChecked(False)
                            taskUI.sel1Icon.setIcon(QtGui.QIcon(taskUI.selectIcon))
                            taskUI.sel2Icon.setIcon(QtGui.QIcon(taskUI.validIcon))
                            removePtS()
                            # Measure distance
                            if taskUI.rbDistance.isChecked():
                                # make a vertex shape out of a point
                                if self.Pt1 and self.Sel1=='point':
                                    self.Shp1 = Part.Vertex(Part.Point( self.Pt1 ))
                                    self.Sel1 = 'shape'
                                if self.Pt2 and self.Sel2=='point':
                                    self.Shp2 = Part.Vertex(Part.Point( self.Pt2 ))
                                    self.Sel2 = 'shape'
                                if self.Sel1=='shape' and self.Sel2=='shape':
                                    self.distShapes(self.Shp1,self.Shp2)
                                # unexpected behaviour
                                else:
                                    self.printResult( 'ERROR 42\n'+str(self.Shp1)+'\n'+str(self.Shp2) )
                            # Measure angle
                            elif taskUI.rbAngle.isChecked():
                                if self.Sel1=='shape' and self.Sel2=='shape':
                                    self.angleShapes( self.Shp1, self.Shp2 )
                                else:
                                    self.printResult( 'Select only faces or lines' )
                        # some problem
                        else:
                            self.printResult( 'ERROR 44\n'+str(self.Shp2) )
                # not valid selection
                else:
                    self.printResult('ERROR 40\n'+str(subShape))


    # uses BRepExtrema_DistShapeShape to calculate the distance between 2 shapes
    def angleShapes( self, shape1, shape2 ):
        global taskUI
        if shape1.isValid() and shape2.isValid():
            Gui.Selection.clearSelection()
            self.printResult( 'Measuring angles' )
            # Datum object
            if shape1.BoundBox.DiagonalLength > 1e+10:
                pt1 = shape1.Placement.Base
            else:
                pt1 = shape1.BoundBox.Center
            # Datum object
            if shape2.BoundBox.DiagonalLength > 1e+10:
                pt2 = shape2.Placement.Base
            else:
                pt2 = shape2.BoundBox.Center
            # get the direction of the shape
            dir1 = self.getDir(shape1)
            dir2 = self.getDir(shape2)
            if dir1 and dir2:
                distance = -1
                angle = dir1.getAngle(dir2)*180./math.pi
                # 2 flat faces
                if self.isFlatFace(shape1) and self.isFlatFace(shape2):
                    angle = 180 - angle
                else:
                    # 1 flat face and 1 direction
                    if self.isFlatFace(shape1) or self.isFlatFace(shape2):
                        angle = 90 - angle
                    if angle > 90:
                        angle = 180. - angle
                # parallel directions
                if abs(angle) < 1.0e-6 or abs(180-angle)<1.0e-6:
                    v1 = Part.Vertex(Part.Point( pt1 ))
                    v2 = Part.Vertex(Part.Point( pt2 ))
                    distance = v1.distToShape(v2)[0]
                self.printAngle( angle, distance )
                try:
                    self.drawLine(pt1,pt2,'Angle')
                    self.annoAngle( self.midPoint(pt1,pt2), angle, distance )
                except:
                    pass
            else:
                self.printResult('Ivalid directions')
        else:
            self.printResult('Ivalid shapes')

    # uses BRepExtrema_DistShapeShape to calculate the distance between 2 shapes
    def distShapes( self, shape1, shape2 ):
        global taskUI
        if shape1.isValid() and shape2.isValid():
            Gui.Selection.clearSelection()
            measure = shape1.distToShape(shape2)
            if measure and self.isVector(measure[1][0][0]) and self.isVector(measure[1][0][1]):
                dist = measure[0]
                self.printResult('Minimum Distance :\n  '+str(dist))
                if dist > 1.0e-9:
                    pt1   = measure[1][0][0]
                    pt2   = measure[1][0][1]
                    self.measurePoints(pt1,pt2)
        else:
            self.printResult('Ivalid shapes')

    # measure a straight line
    def measureLine(self, line ):
        global taskUI
        if self.isSegment(line):
            pt1 = line.Vertexes[0].Point
            pt2 = line.Vertexes[1].Point
            Gui.Selection.clearSelection()
            self.drawLine(pt1,pt2,'Length')
            dx = pt1[0]-pt2[0]
            dy = pt1[1]-pt2[1]
            dz = pt1[2]-pt2[2]
            length = line.Length
            text = 'Length = '+self.render_distance(length)+'\n'
            text += "ΔX = "+self.render_distance(dx)+"\n"
            text += 'ΔY = '+self.render_distance(dy)+'\n'
            text += 'ΔZ = '+self.render_distance(dz)
            # self.printResult( 'Measuring length of\n'+str(line) )
            self.printResult( text )
            if taskUI.bLabel.isChecked():
                mid = line.BoundBox.Center
                if taskUI.Components.isChecked():
                    anno = ['L  = '+self.arrondi(length),'ΔX = '+self.arrondi(dx), \
                            'ΔY = '+self.arrondi(dy),    'ΔZ = '+self.arrondi(dz) ]
                else:
                    anno = ['L = '+self.render_distance(length)]
                self.drawAnnotation( mid, anno )
        else:
            self.printResult( 'Not a valid Line\n'+str(line) )

    # mesure distance between 2 points
    def measurePoints(self, pt1, pt2 ):
        global taskUI
        mid = self.midPoint(pt1,pt2)
        if mid:
            Gui.Selection.clearSelection()
            self.drawLine(pt1,pt2,'DistPoints')
            dx = pt1[0]-pt2[0]
            dy = pt1[1]-pt2[1]
            dz = pt1[2]-pt2[2]
            dist = math.sqrt(dx*dx + dy*dy + dz*dz)
            text = 'Distance = '+self.render_distance(dist)+'\n'
            text += "ΔX : "+self.render_distance(dx)+"\n"
            text += 'ΔY : '+self.render_distance(dy)+'\n'
            text += 'ΔZ : '+self.render_distance(dz)
            # self.printResult( 'Measuring length of\n'+str(line) )
            self.printResult( text )
            if taskUI.bLabel.isChecked():
                if taskUI.Components.isChecked():
                    anno = ['D  = '+self.render_distance(dist), 'ΔX = '+self.arrondi(dx),
                            'ΔY = '+self.arrondi(dy),  'ΔZ = '+self.arrondi(dz) ]
                else:
                    anno = ['D = '+self.render_distance(dist)]
                self.drawAnnotation( mid, anno )
        else:
            self.printResult( 'Not valid Points' )

    # measure radius of a circle
    def measureCircle(self, circle):
        global taskUI, PtS
        if self.isCircle(circle):
            radius = circle.Curve.Radius
            center = circle.Curve.Center
            axis   = circle.Curve.Axis
            Gui.Selection.clearSelection()
            self.drawCircle( radius, center, axis )
            text = 'Radius : '+self.render_distance(radius)+"\n"
            # if annotation is checked, show label with R = radius
            text += "Diameter : "+self.render_distance(radius*2)+"\n"
            text += 'Center : \n'
            text += '  ( '+self.arrondi(center.x)+", "+self.arrondi(center.y)+", "+self.arrondi(center.z)+" )\n"
            text += 'Axis : \n'
            text += "  ( "+self.arrondi(axis.x)+", "+self.arrondi(axis.y)+", "+self.arrondi(axis.z)+" )"
            self.printResult(text)
            if taskUI.bLabel.isChecked():
                pt = circle.Vertexes[0].Point
                self.drawLine(center,pt,'Radius')
                self.drawAnnotation(pt, ['R = '+self.render_distance(radius)])
            else:
                PtS = self.drawPoint(center)
        else:
            self.printResult('Not a valid circle\n'+str(circle))


    # figure out the direction of a shape, be it a line, a surface or a circle
    def getDir( self, shape ):
        direction = None
        # for a segment, it's the normalized vector along the segment
        if self.isSegment(shape):
            line = shape
            pt1 = line.Vertexes[0].Point
            pt2 = line.Vertexes[1].Point
            vect = (pt2.sub(pt1))
            if vect.Length != 0:
                direction = vect / vect.Length
        # for another line (like Datum::Line) it's the Z vector 
        # multiplied by the Line's Placement
        elif self.isLine(shape):
            direction = shape.Placement.Rotation.multVec(App.Vector(0,0,1))
        # for a Circle it's the circle's axis
        elif self.isCircle(shape):
            direction = shape.Curve.Axis
            # TODO: drawAxis(circle)
        # for a flt face it's the normal
        elif self.isFlatFace(shape):
            direction = shape.normalAt(0,0)
            # TODO: drawNormal(face)
        return direction

    # figure out snap point of shape
    def getSnap( self, shape ):
        point = None
        if shape.isValid():
            if 'Vertex' in str(shape):
                point  = shape.Vertexes[0].Point
            # for a circle, snap to the center
            elif 'Edge' in str(shape) and hasattr(shape,'Curve') \
                                      and hasattr(shape.Curve,'Radius'):
                point = shape.Curve.Center
            # as fall-back, snap to center of bounding box
            elif hasattr(shape,'BoundBox'):
                point = shape.BoundBox.Center
        else:
            self.printResult('Invalid shape\n'+str(shape))
        return point

    # measure the coordinates of a single point
    def measureCoords(self, vertex ):
        global taskUI
        point = None
        if self.isVector(vertex):
            point = vertex
        elif hasattr(vertex,'isValid')  and vertex.isValid() \
                                        and hasattr(vertex,'Vertexes') \
                                        and len(vertex.Vertexes) > 0:
            point = vertex.Vertexes[0].Point
        else:
            self.printResult('Not a valid point\n'+str(vertex))
        if point:
            #self.printResult( 'Measuring coordinates of\n'+str(vertex) )
            anno = ['Coordinates :', 'X : '+self.arrondi(point.x), 'Y : '+self.arrondi(point.y), 'Z : '+self.arrondi(point.z)]
            text =  'Coordinates :\n'
            text += "X : "+str(point.x)+"\n"
            text += 'Y : '+str(point.y)+'\n'
            text += 'Z : '+str(point.z)
            self.printResult(text)
            if taskUI.bLabel.isChecked():
                self.drawAnnotation( point, anno )


    def measureArea(self, face ):
        if face.isValid() and hasattr(face,'Area'):
            if self.isFlatFace(face):
                self.printResult('Flat face\nArea : '+str(face.Area)+'\n')
            else:
                self.printResult('Area : '+str(face.Area)+"\n")
        else:
            self.printResult('Not a valid surface\n'+str(face) )


    def printDims(self, ds, dx, dy, dz, dimType='Distance'):
        text = dimType+' : '+str(ds)
        text += "\nΔX = "+str(dx)+"\nΔY = "+str(dy)+"\nΔZ = "+str(dz)
        self.printResult(text)

    def printAngle(self, angle, distance=-1 ):
        global taskUI
        taskUI.resultText.clear()
        text = 'Angle : '+str(angle)+'°\n'
        if distance != -1:
            text += 'Distance // '+str(distance)
        taskUI.resultText.setPlainText(text)

    # print the result in the text field of the UI
    def printResult(self,text):
        global taskUI
        taskUI.resultText.clear()
        taskUI.resultText.setPlainText(text)

    def drawAnnotation(self, pos, textTable ):
        anno = App.ActiveDocument.addObject("App::AnnotationLabel","MeasureLbl")
        anno.BasePosition = pos
        # textTable is a table if strings: [ 'toto', 'titi', 'tata' ]
        anno.LabelText = textTable
        annoG = Gui.ActiveDocument.getObject(anno.Name)
        annoG.FontSize = annoFontSize
        self.addToDims(anno)

    def drawCircle( self, radius, center, axis ):
        global taskUI
        cc = Part.makeCircle( radius, center, axis )
        circle = App.ActiveDocument.addObject('Part::FeaturePython', 'aCircle')
        #circle.ViewObject.Proxy = setCustomIcon(circle,'Draft_Circle.svg')
        circle.ViewObject.Proxy = setCustomIcon( circle, taskUI.circleIcon )
        circle.Shape = Part.Wire( cc )
        circle.ViewObject.LineWidth = 5
        circle.ViewObject.LineColor = ( 1.0, 1.0, 1.0 )
        circle.ViewObject.PointSize = 10
        circle.ViewObject.PointColor= ( 0.0, 0.0, 1.0 )
        self.addToDims(circle)

    def drawLine( self, pt1, pt2, name='aLine', width=3 ):
        global taskUI
        if pt1!=pt2:
            line = Part.makeLine( pt1, pt2 )
            wire = App.ActiveDocument.addObject('Part::FeaturePython', name)
            wire.ViewObject.Proxy = setCustomIcon(wire, taskUI.lineIcon )
            wire.Shape = Part.Wire(line)
            wire.ViewObject.LineWidth = width
            wire.ViewObject.LineColor = ( 1.0, 1.0, 1.0 )
            wire.ViewObject.PointSize = 10
            wire.ViewObject.PointColor= ( 0.0, 0.0, 1.0 )
            self.addToDims(wire)
        else:
            point = App.ActiveDocument.addObject('Part::FeaturePython', 'aPoint')
            point.ViewObject.Proxy = setCustomIcon(point, taskUI.pointIcon )
            point.Shape = Part.Vertex(Part.Point( pt1 ))
            point.ViewObject.PointSize = 10
            point.ViewObject.PointColor= ( 0.0, 0.0, 1.0 )
            self.addToDims(point)

    def drawPoint( self, pt ):
        global taskUI
        point = App.ActiveDocument.addObject('Part::FeaturePython', 'PtS')
        point.ViewObject.Proxy = setCustomIcon(point, taskUI.pointIcon )
        point.Shape = Part.Vertex(Part.Point( pt ))
        point.ViewObject.PointSize = 10
        point.ViewObject.PointColor= ( 1.000, 0.667, 0.000 )
        self.addToDims(point)
        return point

    def annoAngle(self, pos, angle, distance=-1 ):
        global taskUI
        anno = App.ActiveDocument.addObject("App::AnnotationLabel","AngleLbl")
        anno.BasePosition = pos
        if distance == -1 or taskUI.Components.isChecked()==False :
            anno.LabelText = [self.arrondi(angle)+'°']
        else:
            anno.LabelText = ['Angle: '+self.arrondi(angle)+'°', 'Distance // '+self.arrondi(distance)]
        annoG = Gui.ActiveDocument.getObject(anno.Name)
        annoG.FontSize = annoFontSize
        self.addToDims(anno)

    # round to precision anno_precision
    def arrondi( self, val ):
        approxval = int(val/annoPrecision + annoPrecision*0.1)*annoPrecision
        string = '{0:.3f}'.format(approxval)
        return string
    
    def midPoint(self, pt1, pt2):
        if self.isVector(pt1) and self.isVector(pt2):
            return App.Vector.add(pt1,(pt2.sub(pt1)).multiply(.5))
        return None

    def isVector( self, vect ):
        if isinstance(vect,App.Vector):
            return True
        return False

    def isCircle(self, shape):
        if shape.isValid()  and hasattr(shape,'Curve') \
                            and shape.Curve.TypeId=='Part::GeomCircle' \
                            and hasattr(shape.Curve,'Center') \
                            and hasattr(shape.Curve,'Radius'):
            return True
        return False

    def isLine(self, shape):
        if shape.isValid()  and hasattr(shape,'Curve') \
                            and shape.Curve.TypeId=='Part::GeomLine' \
                            and hasattr(shape,'Placement'):
            return True
        return False
    
    def isSegment(self, shape):
        if shape.isValid()  and hasattr(shape,'Curve') \
                            and shape.Curve.TypeId=='Part::GeomLine' \
                            and hasattr(shape,'Length') \
                            and hasattr(shape,'Vertexes') \
                            and len(shape.Vertexes)==2:
            return True
        return False

    def isFlatFace(self, shape):
        if shape.isValid()  and hasattr(shape,'Area')   \
                            and shape.Area > 1.0e-6     \
                            and hasattr(shape,'Volume') \
                            and shape.Volume < 1.0e-9:
            return True
        return False




"""
    +-----------------------------------------------+
    |            embedded button images             |
    +-----------------------------------------------+
"""
import base64
# "b64_data" is a variable containing your base64 encoded icon
draftPoint_b64=\
"""
iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAYAAACqaXHeAAAABHNCSVQICAgIfAhkiAAAAAlwSFlzAAAOxAAADsQBlSsOGwAAABl0RVh0U29mdHdhcmUAd3d3Lmlua3NjYXBlLm9yZ5vuPBoAAAAWdEVYdEF1dGhvcgBbeW9yaWt2YW5oYXZyZV3R/pfWAAAAG3RFWHREZXNjcmlwdGlvbgBBIGRvdCBvciBjaXJjbGUOOmfJAAAALHRFWHRDcmVhdGlvbiBUaW1lAFNhdCBEZWMgMTcgMTU6MzY6MDIgMjAxMSArMDAwMNC6QOkAAAP5SURBVHic7dhbb1RVGMbx/9pzFMSWKQMtNCBYHCo9aAqxYlRuuIF6uhD9DCghAWr8BhrKwYRWv4EJ8UIlgBfcEBNBTECm02O0KpJSQKZMa2n33mtmvV7M9ABGuVqTGNYvmcxMZrL2s57svfYBHMdxHMdxHMdxHMdxHMdxnMeHqubGdu4kmr9Nl4K9Au0KGioh8gZ+QHG6bjVfXbhAsVqZqlZAazO7FXwGbHjEX68r4YPsCGeqkasaBaj2Zj4R+BAg01Qzdmh/y42WzMr6RNJbgygVhKU7gyOFiaMn+xtHf5l+BhBRnMgNcRgQq+FsDg7QtoUeFIdjUS/o7Xnp0vYXVr0CRP7l73Ilm/9uf/fFF/3QJFEc6y+XYI3VAiq7/ZlEzAtOf7Erl04ntyOCEYMpGcQUkZIgniLiRYjEYygUk5P+ld3vnm8JtUl40HVtmLO2Mnq2Bn4HIgr6AHXi485L6XRyu4gQhiGh76MDHx1qtA4J/TlmZ6aZKRQwpkQqlezoO7bjRwADfR0dxGzltFbA6FbeBp7evOmpsc5t6ddEhGBuFh34FHVIUevKe0gx1BS1JpybZSp/F0HoaKt7uTlTOwZsCGfZYyuntQLE8CZA94HWG4BXDEN04FPSenHy4UNFaE0we5/ZqWkA7+D7LTcBFOy1lTNqa2APOgVoy6ysB/Dn7lPUGjEGYwwighiDiEFMeV0QU37NFCZZXlNDS6a2oTLc87ZyWitAIA0QS0TWAYT+HKZYQsRgjFQmvljE0lKKOgQgkYg0VoZbbyuntQKWjK0AilovFCDGYOb3gMpesLSU+ZOTyMI1gLYV0t4aANcBgqA0DqCUeuBYLx//82uAprTkt0i03J0fliYqw92xldNaAQqyAIOjhVsAyWVPLkz2gSIeKKX8fUWqDoCR0cJ8AZdt5bRZwJcAx3tza4HSipUpvGh0YeUv/eM0WP4cjSVIrWkAkKN9A2sBEL6xldNaAdFlnAGuD/88tflq9u73SinWbmwiEos/tAcsTj4WT7KppR3P87iazV8cHi1sBH7LjPC1rZzVuBQ+G495wblTuwZSqWSHMYb8xDj3bt/i/l9TiDE8sXwFqfoG0o3r8TyPyUKQff2985k5v5QQ6MoNc85WRvs3Q80cAbqTcc8/2bPjckd73av/sV3zU3/+0r7DF7cFoUmI4nhuiEM281Xldrj1OY4q4SBApqnm1+4DreNbn61tiMcj9UqRCALzx8DovZuffj64bnD43qZKsCPZYT7i/347PK99C12i6OXRD0R+F8W+3BDfViNX1R+JTf7JWxjeADqBVZQX4pvANVGcqlvN2Wo+EnMcx3Ecx3Ecx3Ecx3Ecx3EeJ38DdD0uzREulD4AAAAASUVORK5CYII=
"""
draftLine_b64=\
"""
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
"""
draftCircle_b64=\
"""
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
"""
draftDimension_b64=\
"""
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
"""
select_b64=\
"""
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
"""
valid_b64=\
"""
iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAYAAACqaXHeAAAABHNCSVQICAgIfAhkiAAAAAlwSFlzAAAOxAAADsQBlSsOGwAAABl0RVh0U29mdHdhcmUAd3d3Lmlua3NjYXBlLm9yZ5vuPBoAABURSURBVHic7ZtpkBzHld9/WV3V1d3Vx/QxBwb3EMTBASFIJEMSKVIEyfXKsg5bBymtNriSImRF+MvGKrQRq4MEIHtth8WQJW+EHbH27lIicQxAAqTMBQGQNC3SorjkkguAAAY3MDjnPvqYPqoy0x+qp7tnpgfn8NMqJya6o/p19fv9873MV5lV8Pv2z7uJD/sH2tfhCGXeoxX3CiFWK62XCcQy0FEgCDjAOOhREINCiJOgj6D1IW3KNwYOUfgw/ftQBGjtpiOA9WWN/iqa+wDzJk9VAX6rBS8hvC2DhxmYRzeBeRagtdv8lAHfA76AJgAQMAMsuGM5i9d30NYVIprRRFNlgmEXw1AEgh5uMUh5MkgpbzF6yWCkr8zlIwNcPHAaKeXU6V1gjxD8ov+I9/p8+TwvArStNe8VmqfQfBLADNms/PQdrHogzeK1WSy7clPnrRRtLh2P0vvaKCde/wDpeQBoeMMw2Nh/2Pu/t+r7LQmQXslC07KeQuvHAOGkW7jnsfV0P1QmFC3OstcaQKO1ABRo0FMfCFF7FYBhGNO8K+XD9P4mzNvPvsfk2ET1hGKbDrh/diupcdMCtHUHviy0+GsgZYVDfOrbn2DdHxYwg+40O631NNCqBvhCNNhUjzfaCQRGQGCYBobwXXXLFodfjfHm//odbrEIMIbW/26gV26/GY4bF+AurPZi4K9AfBdgzcPrefC7ESLxSd95NEILdA22Dq1rhHVoXf+wiUh1O2EIgkETI2AAUBh3eP1/5jn+2sGqY/qvMkJ+/8gRbijfbkiAZBeJYMh8DnjECoX4g+/dx+r7RxHCd1orPSdMLdQboKc6/vpE8t+IgIEdtggYvhC9b2bY99RvkGUXDW94Fe/zo6fIzrsAnSvJyID5GoJ18fY0X/qPd5JeOA4ItFIoXaOcI7QbhZkBOkO0a4okwA6a2KEgCBi5kGT3xiNMXB4EwXsB1/vM5RMMXw9X4HqMUiuIC9Pcj+Cj7SuX8OhPbyPRmgMNUmmUVjcd2lpXP6sGT+P7qfGj8f2UvedK3IqHFQzgtJRZ9WAH596XTI7lOrUwPhOMq22lMcq3LsBdWHFl7kFwb6ark0f/82I/37VGSlV17NZDe6bd9USDkppyqYJlmYQiHqs/naHvgKAwmm0PmMbdhSVqO1dQtyRAe9L8rwgeS3S28dhPb/PhlcbzpD+TTeuZGb12o6F9Fbu50kkrTaVUwbRM7LBixSdbOfHGJOVCsSvqibbCkH7ppgVo7w58HcR/CdgWj/30bhJtWbTWuJ43NY3Pe2jPErMJ9MzpVCkolVyCQZOQI1l291KOvNKP8uTdTps4XBjSvTcsQGs3HUIH9gDhz/5gA0vuHPXhKxKtPtzQnnbeBnFqwkjNiV9HGDxokVxZqdZQmnKxQihs4yTLxDtWc/L/nUEgHg4l1ZbiCLkbEiCWsf4awT1r/uAjfPJrRbQGt+ShlJ5V3FwbZm67q/VyU3sJh7c4XPhNiIk+k9ylAG3rylAVoVL2CDshMsuKjF5pZ+TsQMQIBDoLQ+r56xagY635IPBUMBLmS5uXYoVcvIpXHfQaHLqV0J5jnGgM7Zki+fBRrrxj09qaoTWT4fLJAvlLAVrXlUHUB+ZQ2GJRd5SDLw2hPK/baTdeKQyqCzNZjWYCKMVmgAf+7SeItBRQSuG69d7XDa9qxqvWumanmtqp6Xaq/tr4P/Mz5ekafCaT4cWdO3hu2xa6upYzdNjm0N8kkK5vmxufpFL2iLQUuO9bHwcQQvLTZqyzBOjoNjcIeMBJJeh+KI8GKiW3AUY1hb4++Jl26qp2tVepObK1Af65HTiOQzAYZPuvfsnSpUsZ6Q3ywd8m8Sr+d8aGs2jgI/9yEifdAoJ727rN+64pgNb8KcAnH/8YZtBFeRLXlXP0jGreW7cUITMiTGqObotx5Z0QmUyaF3f2EHUcP0XQ2LbNji3PsGTpEkaPBTnytC9CabJCqVDCDLrc89X1Pqzie1cVoH0dbcBnA5bJmgcmAX96udHQniuMr35MzTo2G34H0WgUjcbzPDzX8/Pdtnluy7MsX76c0eM2R3+VQlY046P+alr3I2WMoIU2+GLbWtrnjgBpfQOwVj+8jmCkjJIKryJvObRvPBoUytP0bo/T/+4MeK1xXRepJEpJKm4FrRW2bdPzzC9Zvnw5Y8dtep9JUxgvUym5hKJFVj1wJ2gCSOtLcwug9ecA1jyYBKBc7f2mvXYDMDc6XihP09tThW+dDl9xyygpUUr5QklJqVxCVUXY9qunWbJ4MWMnQpzalSI74Ufyqk+nABDoR5sK0L4OB7gvYAboXOPXDJWyNzu05xi9b+pYkwhRnuZYT4KBfwyTaU3zwo46fKlcRErpgytVF0EplPRL/pBts2b1KgCKwyb5cV+AJeuyBAIBENzXeReRWQIoad4P2IvW34ZlV5BS4Xly7tCWmtxlAy1vIRpmCKKk5viOBAPvhUklW9jd00OsCl8sFevQyp/rp+CDQRvTNFFa8eNNm9n3yquE0i63PzZIuexSKbtYdoWOO5YBWKpg3jNLgIBiHcCiO9sAcCvenDDK0xz4W4e3/rKFD56NorybmQrVNDulNMd76vAvPreTeCyG1orJYgEpvek9rhRaKUJ2CMu0UErxxKaf8NKelwmlXFY9PoAZ9RlKBX+RaNH6BX6mG9w7xV1frzdEN1qTWhwC8nUBZlZqCg49HWPwgA3AlXds0JrVX8v6Nbn/E02rO107OP26QWvNyZ1JBt+P1OHjcZTy4ZWS0yvEqsuRsINlBX34zZt5ac9eQimXlY/3+/DVKrRQKBFPObQtD/njgBCrZ0WA1noVQHKhvw7vubJpQTIFv2DBAnZu3UI6k+LKuyF6t8WQ8ur5P1fYT8FnMml+/fxzNfj8ZA6v2vO6ofe1UkTCDsEm8Lc/fgUz6k6LvErRX6iNt/nSKa2XzRIAdAYgHPONG/PfdxyOPOvDd3R08Pz2ray8fQUv7txBJp2m/x/D9G6Jo+QNTJlSc+p5Hz6dTrOrZzuxWAylFLn8BNKbHfZKK5xItAH+JzX4FX98BdNxZ405pbKfAtGUv0Dkb83NFECIDIDt+MbSVfXiRMLhZ6L0vxeio6ODXT3bcCL+QBqLxnhhZw+ZdJrBA2F6tyZQktqgORe8lJpTu+rwu3dsIxGPo5RkIjfh97ye8kHV3kedGMGg3QD/MnbKZcU3LmNF3aZR5lX8qA6Gp5bsdXS2ABoHwLR8o5rDEo5siTHwfoj2tjae374VJxJBKUVhMo9Silgsxu6dPbRmMgwdDHNsewLlMcMRNQ3+9K4UQ+87JFta2LV9K4l4wofPjiM9d/Y0pxTRaAw7GJoN/0eXMKNu08jTWiM9f4o0ArXVMbtJCvjr6VoZU3niw2+N1+B37dhG1HF8+EIO13PJT+ZQShGPxdi1YxutmQzDByOc2NGC9JjlkJSaM7tSDP2TD79753ZaWlpQSjI2MYrruX5vaz1tyovFEoTscEPOv4yddLnt63PD1yJP6ZkCWHMKIKW/ROCHfYLB96thv2M7USeKUpJcIYsnPbRSeJ5HNj9RFSHO8z1bSadTDB+KcHpX0h8Yp+BVFf6AQzqd5MXnd5BsSSKlZHR8BM/zmhY58VgL4Sr8jzdu4qU9e7GTFbq+fhHTqVyz4DKM+q5StWWbCCCyAJWibzR82Gb4kD9tbPvl3xF1HLTWZHPZuqPVvPQ8l4nsGEpJEvEEu3u2k077oGd2p1CyCr87zfDBKOl0kt09PSTiCaSUjIwP4bpu09G+JZEkHPLhf7RxE3+/dx92ssLyr13EdNwZ44uiWR0SqO4mVSZrs/7YLAE0ug8gN+KnR2qlIpz2d2Of+vkvUEohhCAcjtQHpgZnXc9lbGIUqSSJRIJdPdtJp5MMH4hy5oU0Z1/IMNIIn/Dhh0eH8Fy3JmijCC2JFOFQpAq/kT1V+GWPXZgG37wIU7XjpuVHdTEXrPZ1fdOkJoAhxDmA3LAfLpEkdH9niHDa4+9f3ssPnngCpRR20CYWjc/KUaUVrusyOjaMlJKWRILdPT1kMilGDkYZORglmUzw/PZtVXiP4ZEBXK9Sh24QNJlIEwk7KCX50ZMb2bN3P3aywtJHq/A3cH0Rivjgo5eqG2FaH5sdAdWDQ6f9uTJoW1hRjzu+PUgo7bF3/6tVESS2HSIeS8wqS6dEGB4dQEqPRMIHTmdSJJN+avg57zE43E/FrdShG6a8VDKDE3GQSvLDJzexZ58Pv+Sr5+vwc9UXTYqwSMRP5ZG+ks8qxOEp7lpSCIO3tIKLH1wBYoQilh8+MY813+yn9+l29u5/FUMY/OVPNhOyw7TEk4yOj0wpWE0lUK5kaHiATKadlkQLv35uJwBRJ4onPQaHruB67lTuNRS3gtZ0G04kilSSHz25iZf37SfYUmHxV+rw9e9xzYVUNMSSfs1y6XC//yuaqS3lhggwvHcB9/LhPryyhWVbBEyjJsLqb/YTbnXZs28/P3jiSZRShEMRUol002qt4lUYHLqCJz2iTtSH9zz6By/Xe36qwKn2XibVWoP/8cbNNfglX+nDjFSaLK4ornUFaoUsQpGgf7fJobMAJSvrvTVLgIFDFBC8JV2P80fiCCAaD9d+wHQ8bv/jK4QzFfbuf4W/eOJJpJKEwxHSyYxf1zdWbkpRcStcGbjkL195HlcGL1GplGddzmqlac20E3ViSCn50cbN7Nm7D6ulwuKv9BGIVJquQ1zP2kOqNeb3fm/UXzMQvHnxIrXbV6btC8TaAg7wWTOYZMUnNIFAgLHhXG3t37AUiTV5sqciHP+gj3N9fTy04UHsoI1lWhQK+Vo4az3VG5JCMU8un8V1K/5SZvUztAYBbZkOYtG4D79pEy/v3e/Df/kcZsSdM7RnXanWUqFud/vaRVhBk989W2T4bD8g/lthSP1DUwHCbeqCEMafjV4YNdZ/bgkhR5PPFqlUvNoPGaYisTpP7rTD8cN9nD5zhkce2oBthzAti0I+7wM2gErp4SlZg679aU17WyfxaKLa837OW4kyi2rw0y+d57rUnrYrVW3xpMOirjaKuQj7n3ofrXUl4Hnfyo0w2VSAySHy0TZjvfLkmljrChasKhEwA0yM5Kc5IExFfFWe/GmHE0cvVEV4kJAdxrKC5As5/0KoARQ9472GBe2dxGMtVfiNvLzvFaxEmYX/5qwPP2uHieY7UXO0FWsXE44E+WCfw5l3zqJhd/8x9ctGm1lbY5E245KAbw+dG+ejn88QcgLkqzstjb1hmIr4yhy5Mw4nqyI8/NCGmgi5fLYWAY3RoKtJ0tm+kES8Cfy/PkvAqVwztK/VYi0Oy1Z24JaDvPjvD+GVKmjBdyeH1PmrCjA5pM5H24w/rBRKiyOplSxYVSIUthkdmEDN2OczLElsRZ78OYeTRy/WRAiHwljBILn8RH3knvqShoUdi0jEk7PgO794hoDjXjO0r9WEIVjz0aUEbYuDe2OceuMEwGuDR73/MNO26eao02YcE/CtS0f7xbrPLiES82+IKGT9wbNxQDIsRWxFjsLZaF2EDRsIhyIELZtsfrw26gMs7FxCSzP4L5zGmBH2N9sWLs3QvjBFfizKi5veQXmeVoI/mdn7cwpQGFIXom2BNbLirc2NpFh5nyCWiDA+kvcHRKaPxsJSRFdkmTwXmy5COIIdtMnmJxCIpvBmvEznF09hhN1mrtxwi8bDrPrIEoQQ7P9FkcFTlxFCPDt4xPtFM/s57w8IJdXvDMP45vDZgXBqWTetS4vEWiKMDmSRUs3Y8tYIS+HclmWyL8ap3oucPXeuFgl+6dxSg//hxo3srcIv+MIpApH5gTetAGvv6cIKmvS+kebtZ94GGBEV7wv50frIf10CFEfIxdrEGRCPnnv3Crd/agWxtEs0HmG4P+uP8o0Dk/YHxkjXOMW+GCePXuDM2bM1EUJ26EOFDwQMuu9ejhMLM3Ihya4fv4mWCoH+Zv9x/e6c37vaSfND+mi0VXQqT9515h9yrNnQidOiicbDjAxm0WpqTq7PzYYpiXRNUDwfnyaC1vpDgzcCBnd8bBmJVJTCuMNzP+ylOJ4Dwc8HjsqfXe2717xLrLBE74t6xr3lQrHrwiHByvtTRBOCeIvD6OAEUupZo7YwFeFlExTPJzjZe4Fzfed47fXX2bf/VazE/MJbQZO1d/vwxVyYHX9xlrHzAwCvD4S9P7nWbXLXdadosotEMGy+iebOTFcnX/lPy3ESBcrFCsf+6Ty5bNP0Qk5a9P/vFbgT/iKLlSjT8fn5g3diIdZ8dBmhSJDCuMOuJ/oYPHkR4B0pvUeGjze/MaqxXdedoqUxyomk2qkDxsOTY7nOk2+VWfqxxcTSLm2dLUipyGdn3x5vWAqnmg6BkEfH50/PD7yAhctbWfWRpVhBk5ELSXb8+WFGLwwAHLCE9y/6e5m4zlNdf0t2kbBC5q8FPBCwLT7z/QdYfb+/HpDPFjl99BK58ebRMF8tnnToWr2AaCKC1oLjbybZ/7O3cEslBOzzpPfV6+n5qXZdETDVSmOUl7WprZMYCS3Vx0++eZaxy+0s7I4STWg6FqWIJiKUii6V0vyE+VRLpB1uW7OQZasWEAxZTE5E2PfzMm8/8zbK89BC//eBNvn45HuUbuS8N/3ARPuawGMI8T+ApBUOc/93Ps6dDxcwbR98Mldi4NIoI/0TlG5SjFAkSKY9QVtnkkjMX9byKhYHXw7z26ffwS2WAIa11t8Z7JUv3Mxv3NIjM21raRfK+hnoPwKIpOJ84ht3cceDRWyn3hHFQpmJsTyFbIlivkSp5OJ5Cs/1MAwDwxCYVoBQOEjYsYklIsRaIoQdu36OXISj/8fk3R0HKYxMgF+DbpXa/fPhXq7cLMO8PDS1YI35gILNCB4EME2TlRvu5I5HUixYlScYuuZd602bWw5y/lCME2+Mcuw3h1GVWiT9Fi2+P9Drvn2rvs/rY3Mdq81P6wB/iuZf4T8USSAQoHNdF4vubCe91CbZqQknKthhFytUQbomShpUShb5EZvsoGDwbImLBy7T39uH9OSUp1JrdqP42eAx73fz5fOH8uBkxwpatWV9A6E/B3yKhs3IG2wu8KZG7BSmu2vgEIPz56XfPvRHZzvvIuJNmvcZsF4huoXQq/x7EUQKSAI5QILIa/RZQ4hzGt1rKN4K5Lx3Gxcwf99+3+a//X+6fTqhYhK7qQAAAABJRU5ErkJggg==
"""
Center_Mass_b64=\
"""
PD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0iVVRGLTgiIHN0YW5kYWxvbmU9Im5vIj8+CjwhLS0gQ3JlYXRlZCB3aXRoIElua3NjYXBlIChodHRwOi8vd3d3Lmlua3NjYXBlLm9yZy8pIC0tPgoKPHN2ZwogICB4bWxuczpkYz0iaHR0cDovL3B1cmwub3JnL2RjL2VsZW1lbnRzLzEuMS8iCiAgIHhtbG5zOmNjPSJodHRwOi8vY3JlYXRpdmVjb21tb25zLm9yZy9ucyMiCiAgIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyIKICAgeG1sbnM6c3ZnPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyIKICAgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIgogICB4bWxuczp4bGluaz0iaHR0cDovL3d3dy53My5vcmcvMTk5OS94bGluayIKICAgeG1sbnM6c29kaXBvZGk9Imh0dHA6Ly9zb2RpcG9kaS5zb3VyY2Vmb3JnZS5uZXQvRFREL3NvZGlwb2RpLTAuZHRkIgogICB4bWxuczppbmtzY2FwZT0iaHR0cDovL3d3dy5pbmtzY2FwZS5vcmcvbmFtZXNwYWNlcy9pbmtzY2FwZSIKICAgd2lkdGg9IjY0cHgiCiAgIGhlaWdodD0iNjRweCIKICAgaWQ9InN2ZzI5ODUiCiAgIHZlcnNpb249IjEuMSIKICAgaW5rc2NhcGU6dmVyc2lvbj0iMC45Mi4xIHIxNTM3MSIKICAgc29kaXBvZGk6ZG9jbmFtZT0iQ2VudGVyT2ZNYXNzLnN2ZyI+CiAgPGRlZnMKICAgICBpZD0iZGVmczI5ODciPgogICAgPGxpbmVhckdyYWRpZW50CiAgICAgICBpbmtzY2FwZTpjb2xsZWN0PSJhbHdheXMiCiAgICAgICBpZD0ibGluZWFyR3JhZGllbnQzNzczIj4KICAgICAgPHN0b3AKICAgICAgICAgc3R5bGU9InN0b3AtY29sb3I6Izg4OGE4NTtzdG9wLW9wYWNpdHk6MSIKICAgICAgICAgb2Zmc2V0PSIwIgogICAgICAgICBpZD0ic3RvcDM3NzUiIC8+CiAgICAgIDxzdG9wCiAgICAgICAgIHN0eWxlPSJzdG9wLWNvbG9yOiNkM2Q3Y2Y7c3RvcC1vcGFjaXR5OjEiCiAgICAgICAgIG9mZnNldD0iMSIKICAgICAgICAgaWQ9InN0b3AzNzc3IiAvPgogICAgPC9saW5lYXJHcmFkaWVudD4KICAgIDxsaW5lYXJHcmFkaWVudAogICAgICAgaWQ9ImxpbmVhckdyYWRpZW50Mzc5NCI+CiAgICAgIDxzdG9wCiAgICAgICAgIHN0eWxlPSJzdG9wLWNvbG9yOiNkM2Q3Y2Y7c3RvcC1vcGFjaXR5OjEiCiAgICAgICAgIG9mZnNldD0iMCIKICAgICAgICAgaWQ9InN0b3AzNzk2IiAvPgogICAgICA8c3RvcAogICAgICAgICBzdHlsZT0ic3RvcC1jb2xvcjojZmZmZmZmO3N0b3Atb3BhY2l0eToxIgogICAgICAgICBvZmZzZXQ9IjEiCiAgICAgICAgIGlkPSJzdG9wMzc5OCIgLz4KICAgIDwvbGluZWFyR3JhZGllbnQ+CiAgICA8bGluZWFyR3JhZGllbnQKICAgICAgIGlua3NjYXBlOmNvbGxlY3Q9ImFsd2F5cyIKICAgICAgIHhsaW5rOmhyZWY9IiNsaW5lYXJHcmFkaWVudDM3OTQiCiAgICAgICBpZD0ibGluZWFyR3JhZGllbnQzODY3IgogICAgICAgZ3JhZGllbnRVbml0cz0idXNlclNwYWNlT25Vc2UiCiAgICAgICB4MT0iMzIuNzE0NzQ4IgogICAgICAgeTE9IjI3LjM5ODM1MiIKICAgICAgIHgyPSIzOC45OTc3MjYiCiAgICAgICB5Mj0iMy42NTIzMTI1IgogICAgICAgZ3JhZGllbnRUcmFuc2Zvcm09Im1hdHJpeCgwLjkyODk2OTMxLDAsMCwwLjgwMTQ1NzEzLDEuODQwNzE3Nyw0LjQ0MzIyNTIpIgogICAgICAgc3ByZWFkTWV0aG9kPSJyZWZsZWN0IiAvPgogICAgPGxpbmVhckdyYWRpZW50CiAgICAgICBpZD0ibGluZWFyR3JhZGllbnQzNzk0LTgiPgogICAgICA8c3RvcAogICAgICAgICBzdHlsZT0ic3RvcC1jb2xvcjojZmZiNDAwO3N0b3Atb3BhY2l0eToxOyIKICAgICAgICAgb2Zmc2V0PSIwIgogICAgICAgICBpZD0ic3RvcDM3OTYtNSIgLz4KICAgICAgPHN0b3AKICAgICAgICAgc3R5bGU9InN0b3AtY29sb3I6I2ZmZWEwMDtzdG9wLW9wYWNpdHk6MTsiCiAgICAgICAgIG9mZnNldD0iMSIKICAgICAgICAgaWQ9InN0b3AzNzk4LTgiIC8+CiAgICA8L2xpbmVhckdyYWRpZW50PgogICAgPGxpbmVhckdyYWRpZW50CiAgICAgICB5Mj0iMjMuODQ4Njg2IgogICAgICAgeDI9IjYyLjY1MjM3IgogICAgICAgeTE9IjIzLjg0ODY4NiIKICAgICAgIHgxPSIxNS4xODQ5NzEiCiAgICAgICBncmFkaWVudFRyYW5zZm9ybT0ibWF0cml4KDEuMDI2NTU2OCwwLDAsMC45MTQ5MDYyNiwtMy4yMzY3MDYsLTEuODAyNzAzMikiCiAgICAgICBncmFkaWVudFVuaXRzPSJ1c2VyU3BhY2VPblVzZSIKICAgICAgIGlkPSJsaW5lYXJHcmFkaWVudDM4ODYiCiAgICAgICB4bGluazpocmVmPSIjbGluZWFyR3JhZGllbnQzNzk0LTgiCiAgICAgICBpbmtzY2FwZTpjb2xsZWN0PSJhbHdheXMiIC8+CiAgICA8bGluZWFyR3JhZGllbnQKICAgICAgIGlkPSJsaW5lYXJHcmFkaWVudDM3OTQtMSI+CiAgICAgIDxzdG9wCiAgICAgICAgIHN0eWxlPSJzdG9wLWNvbG9yOiNmZmI0MDA7c3RvcC1vcGFjaXR5OjE7IgogICAgICAgICBvZmZzZXQ9IjAiCiAgICAgICAgIGlkPSJzdG9wMzc5Ni0yIiAvPgogICAgICA8c3RvcAogICAgICAgICBzdHlsZT0ic3RvcC1jb2xvcjojZmZlYTAwO3N0b3Atb3BhY2l0eToxOyIKICAgICAgICAgb2Zmc2V0PSIxIgogICAgICAgICBpZD0ic3RvcDM3OTgtMiIgLz4KICAgIDwvbGluZWFyR3JhZGllbnQ+CiAgICA8bGluZWFyR3JhZGllbnQKICAgICAgIHkyPSIyMy44NDg2ODYiCiAgICAgICB4Mj0iNjIuNjUyMzciCiAgICAgICB5MT0iMjMuODQ4Njg2IgogICAgICAgeDE9IjE1LjE4NDk3MSIKICAgICAgIGdyYWRpZW50VHJhbnNmb3JtPSJtYXRyaXgoMS4wMjY1NTY4LDAsMCwwLjkxNDkwNjI2LC0zLjIzNjcwNiwtMS44MDI3MDMyKSIKICAgICAgIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZU9uVXNlIgogICAgICAgaWQ9ImxpbmVhckdyYWRpZW50Mzg4Ni0wIgogICAgICAgeGxpbms6aHJlZj0iI2xpbmVhckdyYWRpZW50Mzc5NC0xIgogICAgICAgaW5rc2NhcGU6Y29sbGVjdD0iYWx3YXlzIiAvPgogICAgPGxpbmVhckdyYWRpZW50CiAgICAgICBpbmtzY2FwZTpjb2xsZWN0PSJhbHdheXMiCiAgICAgICB4bGluazpocmVmPSIjbGluZWFyR3JhZGllbnQzNzczIgogICAgICAgaWQ9ImxpbmVhckdyYWRpZW50Mzc3OSIKICAgICAgIHgxPSI1Ny43MjQzNSIKICAgICAgIHkxPSIzNC40MzA0MDEiCiAgICAgICB4Mj0iNTAuNjIwMzgiCiAgICAgICB5Mj0iMjMuOTMzNjgiCiAgICAgICBncmFkaWVudFVuaXRzPSJ1c2VyU3BhY2VPblVzZSIgLz4KICAgIDxsaW5lYXJHcmFkaWVudAogICAgICAgaWQ9ImxpbmVhckdyYWRpZW50MzgzNi0wIj4KICAgICAgPHN0b3AKICAgICAgICAgc3R5bGU9InN0b3AtY29sb3I6I2M0YTAwMDtzdG9wLW9wYWNpdHk6MTsiCiAgICAgICAgIG9mZnNldD0iMCIKICAgICAgICAgaWQ9InN0b3AzODM4LTIiIC8+CiAgICAgIDxzdG9wCiAgICAgICAgIHN0eWxlPSJzdG9wLWNvbG9yOiNmY2U5NGY7c3RvcC1vcGFjaXR5OjE7IgogICAgICAgICBvZmZzZXQ9IjEiCiAgICAgICAgIGlkPSJzdG9wMzg0MC01IiAvPgogICAgPC9saW5lYXJHcmFkaWVudD4KICAgIDxsaW5lYXJHcmFkaWVudAogICAgICAgaW5rc2NhcGU6Y29sbGVjdD0iYWx3YXlzIgogICAgICAgeGxpbms6aHJlZj0iI2xpbmVhckdyYWRpZW50MzgzNi0wLTYtOTItNC02IgogICAgICAgaWQ9ImxpbmVhckdyYWRpZW50MzgwMS0xLTMtMTQtMC0zIgogICAgICAgZ3JhZGllbnRVbml0cz0idXNlclNwYWNlT25Vc2UiCiAgICAgICB4MT0iLTE4IgogICAgICAgeTE9IjE4IgogICAgICAgeDI9Ii0yMiIKICAgICAgIHkyPSI1IgogICAgICAgZ3JhZGllbnRUcmFuc2Zvcm09Im1hdHJpeCgwLjQyODU3MDE5LDEuMTk0MTM0OWUtOCwwLDAuNDI4NTcyOTcsNDEuMTAzOTA0LDI0LjIxMTQxMSkiIC8+CiAgICA8bGluZWFyR3JhZGllbnQKICAgICAgIGlkPSJsaW5lYXJHcmFkaWVudDM4MzYtMC02LTkyLTQtNiI+CiAgICAgIDxzdG9wCiAgICAgICAgIHN0eWxlPSJzdG9wLWNvbG9yOiNhNDAwMDA7c3RvcC1vcGFjaXR5OjEiCiAgICAgICAgIG9mZnNldD0iMCIKICAgICAgICAgaWQ9InN0b3AzODM4LTItNy0wNi04LTciIC8+CiAgICAgIDxzdG9wCiAgICAgICAgIHN0eWxlPSJzdG9wLWNvbG9yOiNlZjI5Mjk7c3RvcC1vcGFjaXR5OjEiCiAgICAgICAgIG9mZnNldD0iMSIKICAgICAgICAgaWQ9InN0b3AzODQwLTUtNS04LTctNSIgLz4KICAgIDwvbGluZWFyR3JhZGllbnQ+CiAgPC9kZWZzPgogIDxzb2RpcG9kaTpuYW1lZHZpZXcKICAgICBpZD0iYmFzZSIKICAgICBwYWdlY29sb3I9IiNmZmZmZmYiCiAgICAgYm9yZGVyY29sb3I9IiM2NjY2NjYiCiAgICAgYm9yZGVyb3BhY2l0eT0iMS4wIgogICAgIGlua3NjYXBlOnBhZ2VvcGFjaXR5PSIwLjAiCiAgICAgaW5rc2NhcGU6cGFnZXNoYWRvdz0iMiIKICAgICBpbmtzY2FwZTp6b29tPSI5LjY4NzUiCiAgICAgaW5rc2NhcGU6Y3g9IjEzLjcyOTAzMiIKICAgICBpbmtzY2FwZTpjeT0iMzIiCiAgICAgaW5rc2NhcGU6Y3VycmVudC1sYXllcj0ibGF5ZXIxIgogICAgIHNob3dncmlkPSJ0cnVlIgogICAgIGlua3NjYXBlOmRvY3VtZW50LXVuaXRzPSJweCIKICAgICBpbmtzY2FwZTpncmlkLWJib3g9InRydWUiCiAgICAgaW5rc2NhcGU6d2luZG93LXdpZHRoPSIyNTYwIgogICAgIGlua3NjYXBlOndpbmRvdy1oZWlnaHQ9IjEzNjEiCiAgICAgaW5rc2NhcGU6d2luZG93LXg9Ii05IgogICAgIGlua3NjYXBlOndpbmRvdy15PSItOSIKICAgICBpbmtzY2FwZTp3aW5kb3ctbWF4aW1pemVkPSIxIgogICAgIGlua3NjYXBlOnNuYXAtZ2xvYmFsPSJmYWxzZSI+CiAgICA8aW5rc2NhcGU6Z3JpZAogICAgICAgdHlwZT0ieHlncmlkIgogICAgICAgaWQ9ImdyaWQyOTk3IgogICAgICAgZW1wc3BhY2luZz0iMiIKICAgICAgIHZpc2libGU9InRydWUiCiAgICAgICBlbmFibGVkPSJ0cnVlIgogICAgICAgc25hcHZpc2libGVncmlkbGluZXNvbmx5PSJ0cnVlIiAvPgogIDwvc29kaXBvZGk6bmFtZWR2aWV3PgogIDxtZXRhZGF0YQogICAgIGlkPSJtZXRhZGF0YTI5OTAiPgogICAgPHJkZjpSREY+CiAgICAgIDxjYzpXb3JrCiAgICAgICAgIHJkZjphYm91dD0iIj4KICAgICAgICA8ZGM6Zm9ybWF0PmltYWdlL3N2Zyt4bWw8L2RjOmZvcm1hdD4KICAgICAgICA8ZGM6dHlwZQogICAgICAgICAgIHJkZjpyZXNvdXJjZT0iaHR0cDovL3B1cmwub3JnL2RjL2RjbWl0eXBlL1N0aWxsSW1hZ2UiIC8+CiAgICAgICAgPGRjOnRpdGxlPjwvZGM6dGl0bGU+CiAgICAgICAgPGRjOmNyZWF0b3I+CiAgICAgICAgICA8Y2M6QWdlbnQ+CiAgICAgICAgICAgIDxkYzp0aXRsZT5beW9yaWt2YW5oYXZyZV08L2RjOnRpdGxlPgogICAgICAgICAgPC9jYzpBZ2VudD4KICAgICAgICA8L2RjOmNyZWF0b3I+CiAgICAgICAgPGRjOnRpdGxlPkFyY2hfU2l0ZV9UcmVlPC9kYzp0aXRsZT4KICAgICAgICA8ZGM6ZGF0ZT4yMDExLTEyLTA2PC9kYzpkYXRlPgogICAgICAgIDxkYzpyZWxhdGlvbj5odHRwOi8vd3d3LmZyZWVjYWR3ZWIub3JnL3dpa2kvaW5kZXgucGhwP3RpdGxlPUFydHdvcms8L2RjOnJlbGF0aW9uPgogICAgICAgIDxkYzpwdWJsaXNoZXI+CiAgICAgICAgICA8Y2M6QWdlbnQ+CiAgICAgICAgICAgIDxkYzp0aXRsZT5GcmVlQ0FEPC9kYzp0aXRsZT4KICAgICAgICAgIDwvY2M6QWdlbnQ+CiAgICAgICAgPC9kYzpwdWJsaXNoZXI+CiAgICAgICAgPGRjOmlkZW50aWZpZXI+RnJlZUNBRC9zcmMvTW9kL0FyY2gvUmVzb3VyY2VzL2ljb25zL0FyY2hfU2l0ZV9UcmVlLnN2ZzwvZGM6aWRlbnRpZmllcj4KICAgICAgICA8ZGM6cmlnaHRzPgogICAgICAgICAgPGNjOkFnZW50PgogICAgICAgICAgICA8ZGM6dGl0bGU+RnJlZUNBRCBMR1BMMis8L2RjOnRpdGxlPgogICAgICAgICAgPC9jYzpBZ2VudD4KICAgICAgICA8L2RjOnJpZ2h0cz4KICAgICAgICA8Y2M6bGljZW5zZT5odHRwczovL3d3dy5nbnUub3JnL2NvcHlsZWZ0L2xlc3Nlci5odG1sPC9jYzpsaWNlbnNlPgogICAgICAgIDxkYzpjb250cmlidXRvcj4KICAgICAgICAgIDxjYzpBZ2VudD4KICAgICAgICAgICAgPGRjOnRpdGxlPlthZ3J5c29uXSBBbGV4YW5kZXIgR3J5c29uPC9kYzp0aXRsZT4KICAgICAgICAgIDwvY2M6QWdlbnQ+CiAgICAgICAgPC9kYzpjb250cmlidXRvcj4KICAgICAgPC9jYzpXb3JrPgogICAgPC9yZGY6UkRGPgogIDwvbWV0YWRhdGE+CiAgPGcKICAgICBpZD0ibGF5ZXIxIgogICAgIGlua3NjYXBlOmxhYmVsPSJMYXllciAxIgogICAgIGlua3NjYXBlOmdyb3VwbW9kZT0ibGF5ZXIiPgogICAgPHBhdGgKICAgICAgIHN0eWxlPSJjb2xvcjojMDAwMDAwO2ZpbGw6I2QzZDdjZjtmaWxsLW9wYWNpdHk6MTtmaWxsLXJ1bGU6bm9uemVybztzdHJva2U6IzJlMzQzNjtzdHJva2Utd2lkdGg6MjtzdHJva2UtbGluZWNhcDpidXR0O3N0cm9rZS1saW5lam9pbjpyb3VuZDtzdHJva2UtbWl0ZXJsaW1pdDo0O3N0cm9rZS1vcGFjaXR5OjE7c3Ryb2tlLWRhc2hhcnJheTpub25lO3N0cm9rZS1kYXNob2Zmc2V0OjA7bWFya2VyOm5vbmU7dmlzaWJpbGl0eTp2aXNpYmxlO2Rpc3BsYXk6aW5saW5lO292ZXJmbG93OnZpc2libGU7ZW5hYmxlLWJhY2tncm91bmQ6YWNjdW11bGF0ZSIKICAgICAgIGQ9Ik0gMyw0MSAyOSw1MyAyOSw2MSAzLDQ5IHoiCiAgICAgICBpZD0icGF0aDM5MDQiCiAgICAgICBpbmtzY2FwZTpjb25uZWN0b3ItY3VydmF0dXJlPSIwIgogICAgICAgc29kaXBvZGk6bm9kZXR5cGVzPSJjY2NjYyIKICAgICAgIGlua3NjYXBlOmV4cG9ydC14ZHBpPSIxMTMuMTIzIgogICAgICAgaW5rc2NhcGU6ZXhwb3J0LXlkcGk9IjExMy4xMjMiIC8+CiAgICA8cGF0aAogICAgICAgc3R5bGU9ImNvbG9yOiMwMDAwMDA7ZmlsbDp1cmwoI2xpbmVhckdyYWRpZW50Mzc3OSk7ZmlsbC1vcGFjaXR5OjE7ZmlsbC1ydWxlOm5vbnplcm87c3Ryb2tlOiMyZTM0MzY7c3Ryb2tlLXdpZHRoOjI7c3Ryb2tlLWxpbmVjYXA6YnV0dDtzdHJva2UtbGluZWpvaW46cm91bmQ7c3Ryb2tlLW1pdGVybGltaXQ6NDtzdHJva2Utb3BhY2l0eToxO3N0cm9rZS1kYXNoYXJyYXk6bm9uZTtzdHJva2UtZGFzaG9mZnNldDowO21hcmtlcjpub25lO3Zpc2liaWxpdHk6dmlzaWJsZTtkaXNwbGF5OmlubGluZTtvdmVyZmxvdzp2aXNpYmxlO2VuYWJsZS1iYWNrZ3JvdW5kOmFjY3VtdWxhdGUiCiAgICAgICBkPSJNIDYxLDExIDYxLDM1IDI5LDYxIDI5LDUzIDQwLjc3NDc0MywxMy45Mzk1OCB6IgogICAgICAgaWQ9InBhdGgzODY5IgogICAgICAgaW5rc2NhcGU6Y29ubmVjdG9yLWN1cnZhdHVyZT0iMCIKICAgICAgIHNvZGlwb2RpOm5vZGV0eXBlcz0iY2NjY2NjIgogICAgICAgaW5rc2NhcGU6ZXhwb3J0LXhkcGk9IjExMy4xMjMiCiAgICAgICBpbmtzY2FwZTpleHBvcnQteWRwaT0iMTEzLjEyMyIgLz4KICAgIDxwYXRoCiAgICAgICBzdHlsZT0iZmlsbDp1cmwoI2xpbmVhckdyYWRpZW50Mzg2Nyk7ZmlsbC1vcGFjaXR5OjE7c3Ryb2tlOiMyZTM0MzY7c3Ryb2tlLXdpZHRoOjI7c3Ryb2tlLWxpbmVjYXA6YnV0dDtzdHJva2UtbGluZWpvaW46cm91bmQ7c3Ryb2tlLW1pdGVybGltaXQ6NDtzdHJva2Utb3BhY2l0eToxO3N0cm9rZS1kYXNoYXJyYXk6bm9uZSIKICAgICAgIGQ9Ik0gMzUsMyAyMywxMyAxNywyOSAzLDQxIDI5LDUzIDQwLjY4MzI1LDQwLjIwODI0OSA0OSwyMyA2MSwxMSB6IgogICAgICAgaWQ9InBhdGgzNzYzIgogICAgICAgaW5rc2NhcGU6Y29ubmVjdG9yLWN1cnZhdHVyZT0iMCIKICAgICAgIHNvZGlwb2RpOm5vZGV0eXBlcz0iY2NjY2NjY2NjIgogICAgICAgaW5rc2NhcGU6ZXhwb3J0LXhkcGk9IjExMy4xMjMiCiAgICAgICBpbmtzY2FwZTpleHBvcnQteWRwaT0iMTEzLjEyMyIgLz4KICAgIDxwYXRoCiAgICAgICBzdHlsZT0iZmlsbDpub25lO3N0cm9rZTojZDNkN2NmO3N0cm9rZS13aWR0aDoyO3N0cm9rZS1saW5lY2FwOmJ1dHQ7c3Ryb2tlLWxpbmVqb2luOm1pdGVyO3N0cm9rZS1vcGFjaXR5OjEiCiAgICAgICBkPSJNIDMwLjk4MjY1OCw1My43OTc3MjQgMzEsNTYuODA5MTA0IDU4Ljk4MjY1OCwzNC4wNTIwMjUgbCAwLC0xOC4xODQ5MzQgLTguMzEyMTUzLDguMzIzNjY5IC04LjM0NjgzNiwxNy4xMjEzOTMgeiIKICAgICAgIGlkPSJwYXRoMjk5OSIKICAgICAgIGlua3NjYXBlOmNvbm5lY3Rvci1jdXJ2YXR1cmU9IjAiCiAgICAgICBzb2RpcG9kaTpub2RldHlwZXM9ImNjY2NjY2MiCiAgICAgICBpbmtzY2FwZTpleHBvcnQteGRwaT0iMTEzLjEyMyIKICAgICAgIGlua3NjYXBlOmV4cG9ydC15ZHBpPSIxMTMuMTIzIiAvPgogICAgPHBhdGgKICAgICAgIHN0eWxlPSJmaWxsOm5vbmU7c3Ryb2tlOiNmZmZmZmY7c3Ryb2tlLXdpZHRoOjI7c3Ryb2tlLWxpbmVjYXA6YnV0dDtzdHJva2UtbGluZWpvaW46bWl0ZXI7c3Ryb2tlLW9wYWNpdHk6MSIKICAgICAgIGQ9Ik0gNS4wMTA1NTQ2LDQ0LjE2OTM2OSA0Ljk5MDk1OTMsNDcuNzA2MzggMjcuMDE2ODE4LDU3Ljg4MzA1NSAyNi45NzU0NjIsNTQuMjc5NDQxIHoiCiAgICAgICBpZD0icGF0aDMwMDEiCiAgICAgICBpbmtzY2FwZTpjb25uZWN0b3ItY3VydmF0dXJlPSIwIgogICAgICAgc29kaXBvZGk6bm9kZXR5cGVzPSJjY2NjYyIKICAgICAgIGlua3NjYXBlOmV4cG9ydC14ZHBpPSIxMTMuMTIzIgogICAgICAgaW5rc2NhcGU6ZXhwb3J0LXlkcGk9IjExMy4xMjMiIC8+CiAgICA8ZwogICAgICAgaWQ9Imc0NTMxIgogICAgICAgdHJhbnNmb3JtPSJtYXRyaXgoMS42MjkxNDQ2LDAsMCwxLjYyOTE0NDYsLTE1LjIyNzE2LC0yMy4yOTkzNDcpIgogICAgICAgaW5rc2NhcGU6ZXhwb3J0LXhkcGk9IjExMy4xMjMiCiAgICAgICBpbmtzY2FwZTpleHBvcnQteWRwaT0iMTEzLjEyMyI+CiAgICAgIDxwYXRoCiAgICAgICAgIGlua3NjYXBlOmV4cG9ydC15ZHBpPSI0OS41NDg3OTgiCiAgICAgICAgIGlua3NjYXBlOmV4cG9ydC14ZHBpPSI0OS41NDg3OTgiCiAgICAgICAgIGQ9Im0gMjkuMDIyMDA2LDI1Ljg1ODgwMyBhIDUuMDE3NTkxMiw1LjAxNzI4OTcgMC4wMTMyODMwNiAxIDEgNy42MjIxNjgsNi41MjcwNDIgNS4wMTc1OTEyLDUuMDE3Mjg5NyAwLjAxMzI4MzA2IDEgMSAtNy42MjIxNjgsLTYuNTI3MDQyIHoiCiAgICAgICAgIGlkPSJwYXRoNDI1MC03MS02LTQ5LTIiCiAgICAgICAgIHN0eWxlPSJmaWxsOiNlZjI5Mjk7c3Ryb2tlOiNhNDAwMDA7c3Ryb2tlLXdpZHRoOjEuOTk5OTk5ODg7c3Ryb2tlLW1pdGVybGltaXQ6NDtzdHJva2UtZGFzaGFycmF5Om5vbmU7c3Ryb2tlLW9wYWNpdHk6MSIKICAgICAgICAgaW5rc2NhcGU6Y29ubmVjdG9yLWN1cnZhdHVyZT0iMCIgLz4KICAgICAgPHBhdGgKICAgICAgICAgaW5rc2NhcGU6ZXhwb3J0LXlkcGk9IjQ5LjU0ODc5OCIKICAgICAgICAgaW5rc2NhcGU6ZXhwb3J0LXhkcGk9IjQ5LjU0ODc5OCIKICAgICAgICAgZD0ibSAzMC41NDY2ODMsMjcuMTY1ODE2IGEgMy4wMDAwMTA4LDIuOTk5OTkxMyA4OS44NzczOTkgMSAxIDQuNTU3MjM4LDMuOTAyNzYxIDMuMDAwMDEwOCwyLjk5OTk5MTMgODkuODc3Mzk5IDAgMSAtNC41NTcyMzgsLTMuOTAyNzYxIHoiCiAgICAgICAgIGlkPSJwYXRoNDI1MC03LTMtMi01LTciCiAgICAgICAgIHN0eWxlPSJmaWxsOnVybCgjbGluZWFyR3JhZGllbnQzODAxLTEtMy0xNC0wLTMpO2ZpbGwtb3BhY2l0eToxO3N0cm9rZTojZWYyOTI5O3N0cm9rZS13aWR0aDoxLjk5OTk5OTQ7c3Ryb2tlLW1pdGVybGltaXQ6NDtzdHJva2UtZGFzaGFycmF5Om5vbmU7c3Ryb2tlLW9wYWNpdHk6MSIKICAgICAgICAgaW5rc2NhcGU6Y29ubmVjdG9yLWN1cnZhdHVyZT0iMCIgLz4KICAgIDwvZz4KICAgIDxwYXRoCiAgICAgICBzdHlsZT0iZmlsbDpub25lO3N0cm9rZTojZmZmZmZmO3N0cm9rZS13aWR0aDoyO3N0cm9rZS1saW5lY2FwOmJ1dHQ7c3Ryb2tlLWxpbmVqb2luOm1pdGVyO3N0cm9rZS1vcGFjaXR5OjEiCiAgICAgICBkPSJNIDYuNjU5NDIwNCw0MC40Njc4NjEgMTguNjk1NDc2LDMwLjE2NjMyMyAyNC42OTc5NSwxNC4xOTI2NTEgMzUuNTcwMjM3LDUuMjc4MTIzIDU3LjE1MzI5NSwxMS45MDkzMjEgNDcuMzU2NzExLDIxLjc3MDM0MiAzOC45ODc0MjMsMzkuMDcxMTY2IDI4LjQ3MjM0Miw1MC41MzgwMDUgeiIKICAgICAgIGlkPSJwYXRoMzAwMyIKICAgICAgIGlua3NjYXBlOmNvbm5lY3Rvci1jdXJ2YXR1cmU9IjAiCiAgICAgICBzb2RpcG9kaTpub2RldHlwZXM9ImNjY2NjY2NjYyIKICAgICAgIGlua3NjYXBlOmV4cG9ydC14ZHBpPSIxMTMuMTIzIgogICAgICAgaW5rc2NhcGU6ZXhwb3J0LXlkcGk9IjExMy4xMjMiIC8+CiAgICA8cGF0aAogICAgICAgc3R5bGU9ImZpbGw6bm9uZTtmaWxsLW9wYWNpdHk6MTtzdHJva2U6IzJlMzQzNjtzdHJva2Utd2lkdGg6MjtzdHJva2UtbGluZWNhcDpidXR0O3N0cm9rZS1saW5lam9pbjpyb3VuZDtzdHJva2UtbWl0ZXJsaW1pdDo0O3N0cm9rZS1kYXNoYXJyYXk6bm9uZTtzdHJva2Utb3BhY2l0eToxIgogICAgICAgZD0iTSAzNSwzLjAwMDAwMDUgMjMsMTMgMTcsMjkgMyw0MSAyOSw1MyA0MC42ODMyNSw0MC4yMDgyNDkgNDksMjMgNjEsMTEgWiIKICAgICAgIGlkPSJwYXRoMzc2My0xIgogICAgICAgaW5rc2NhcGU6Y29ubmVjdG9yLWN1cnZhdHVyZT0iMCIKICAgICAgIHNvZGlwb2RpOm5vZGV0eXBlcz0iY2NjY2NjY2NjIgogICAgICAgaW5rc2NhcGU6ZXhwb3J0LXhkcGk9IjExMy4xMjMiCiAgICAgICBpbmtzY2FwZTpleHBvcnQteWRwaT0iMTEzLjEyMyIgLz4KICA8L2c+Cjwvc3ZnPgo=
"""
Snap_Options_b64=\
"""
PD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0iVVRGLTgiIHN0YW5kYWxvbmU9Im5vIj8+CjwhLS0gQ3JlYXRlZCB3aXRoIElua3NjYXBlIChodHRwOi8vd3d3Lmlua3NjYXBlLm9yZy8pIC0tPgoKPHN2ZwogICB4bWxuczpkYz0iaHR0cDovL3B1cmwub3JnL2RjL2VsZW1lbnRzLzEuMS8iCiAgIHhtbG5zOmNjPSJodHRwOi8vY3JlYXRpdmVjb21tb25zLm9yZy9ucyMiCiAgIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyIKICAgeG1sbnM6c3ZnPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyIKICAgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIgogICB4bWxuczp4bGluaz0iaHR0cDovL3d3dy53My5vcmcvMTk5OS94bGluayIKICAgeG1sbnM6c29kaXBvZGk9Imh0dHA6Ly9zb2RpcG9kaS5zb3VyY2Vmb3JnZS5uZXQvRFREL3NvZGlwb2RpLTAuZHRkIgogICB4bWxuczppbmtzY2FwZT0iaHR0cDovL3d3dy5pbmtzY2FwZS5vcmcvbmFtZXNwYWNlcy9pbmtzY2FwZSIKICAgd2lkdGg9IjE5MiIKICAgaGVpZ2h0PSI2NCIKICAgaWQ9InN2ZzI3MjYiCiAgIHNvZGlwb2RpOnZlcnNpb249IjAuMzIiCiAgIGlua3NjYXBlOnZlcnNpb249IjAuOTIuMSByMTUzNzEiCiAgIHNvZGlwb2RpOmRvY25hbWU9IlNuYXBfT3B0aW9ucy5zdmciCiAgIGlua3NjYXBlOm91dHB1dF9leHRlbnNpb249Im9yZy5pbmtzY2FwZS5vdXRwdXQuc3ZnLmlua3NjYXBlIgogICB2ZXJzaW9uPSIxLjEiPgogIDxkZWZzCiAgICAgaWQ9ImRlZnMyNzI4Ij4KICAgIDxsaW5lYXJHcmFkaWVudAogICAgICAgaW5rc2NhcGU6Y29sbGVjdD0iYWx3YXlzIgogICAgICAgaWQ9ImxpbmVhckdyYWRpZW50Mzc3OSI+CiAgICAgIDxzdG9wCiAgICAgICAgIHN0eWxlPSJzdG9wLWNvbG9yOiMwNjk4OWE7c3RvcC1vcGFjaXR5OjEiCiAgICAgICAgIG9mZnNldD0iMCIKICAgICAgICAgaWQ9InN0b3AzNzgxIiAvPgogICAgICA8c3RvcAogICAgICAgICBzdHlsZT0ic3RvcC1jb2xvcjojMzRlMGUyO3N0b3Atb3BhY2l0eToxIgogICAgICAgICBvZmZzZXQ9IjEiCiAgICAgICAgIGlkPSJzdG9wMzc4MyIgLz4KICAgIDwvbGluZWFyR3JhZGllbnQ+CiAgICA8cmFkaWFsR3JhZGllbnQKICAgICAgIGlua3NjYXBlOmNvbGxlY3Q9ImFsd2F5cyIKICAgICAgIHhsaW5rOmhyZWY9IiNsaW5lYXJHcmFkaWVudDMxNDQiCiAgICAgICBpZD0icmFkaWFsR3JhZGllbnQ0Mjc0IgogICAgICAgZ3JhZGllbnRVbml0cz0idXNlclNwYWNlT25Vc2UiCiAgICAgICBncmFkaWVudFRyYW5zZm9ybT0ibWF0cml4KDEsMCwwLDAuNjk4NTI5NCwwLDIwMi44Mjg2MykiCiAgICAgICBjeD0iMjI1LjI2NDAyIgogICAgICAgY3k9IjY3Mi43OTczNiIKICAgICAgIGZ4PSIyMjUuMjY0MDIiCiAgICAgICBmeT0iNjcyLjc5NzM2IgogICAgICAgcj0iMzQuMzQ1MTg4IiAvPgogICAgPGxpbmVhckdyYWRpZW50CiAgICAgICBpbmtzY2FwZTpjb2xsZWN0PSJhbHdheXMiCiAgICAgICBpZD0ibGluZWFyR3JhZGllbnQzMTQ0Ij4KICAgICAgPHN0b3AKICAgICAgICAgc3R5bGU9InN0b3AtY29sb3I6I2ZmZmZmZjtzdG9wLW9wYWNpdHk6MTsiCiAgICAgICAgIG9mZnNldD0iMCIKICAgICAgICAgaWQ9InN0b3AzMTQ2IiAvPgogICAgICA8c3RvcAogICAgICAgICBzdHlsZT0ic3RvcC1jb2xvcjojZmZmZmZmO3N0b3Atb3BhY2l0eTowOyIKICAgICAgICAgb2Zmc2V0PSIxIgogICAgICAgICBpZD0ic3RvcDMxNDgiIC8+CiAgICA8L2xpbmVhckdyYWRpZW50PgogICAgPHJhZGlhbEdyYWRpZW50CiAgICAgICBpbmtzY2FwZTpjb2xsZWN0PSJhbHdheXMiCiAgICAgICB4bGluazpocmVmPSIjbGluZWFyR3JhZGllbnQzMTQ0IgogICAgICAgaWQ9InJhZGlhbEdyYWRpZW50NDI3MiIKICAgICAgIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZU9uVXNlIgogICAgICAgZ3JhZGllbnRUcmFuc2Zvcm09Im1hdHJpeCgxLDAsMCwwLjY5ODUyOTQsMCwyMDIuODI4NjMpIgogICAgICAgY3g9IjIyNS4yNjQwMiIKICAgICAgIGN5PSI2NzIuNzk3MzYiCiAgICAgICBmeD0iMjI1LjI2NDAyIgogICAgICAgZnk9IjY3Mi43OTczNiIKICAgICAgIHI9IjM0LjM0NTE4OCIgLz4KICAgIDxpbmtzY2FwZTpwZXJzcGVjdGl2ZQogICAgICAgc29kaXBvZGk6dHlwZT0iaW5rc2NhcGU6cGVyc3AzZCIKICAgICAgIGlua3NjYXBlOnZwX3g9IjAgOiAzMiA6IDEiCiAgICAgICBpbmtzY2FwZTp2cF95PSIwIDogMTAwMCA6IDAiCiAgICAgICBpbmtzY2FwZTp2cF96PSI2NCA6IDMyIDogMSIKICAgICAgIGlua3NjYXBlOnBlcnNwM2Qtb3JpZ2luPSIzMiA6IDIxLjMzMzMzMyA6IDEiCiAgICAgICBpZD0icGVyc3BlY3RpdmUyNzM0IiAvPgogICAgPHJhZGlhbEdyYWRpZW50CiAgICAgICBpbmtzY2FwZTpjb2xsZWN0PSJhbHdheXMiCiAgICAgICB4bGluazpocmVmPSIjbGluZWFyR3JhZGllbnQzMTQ0IgogICAgICAgaWQ9InJhZGlhbEdyYWRpZW50MzAxMSIKICAgICAgIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZU9uVXNlIgogICAgICAgZ3JhZGllbnRUcmFuc2Zvcm09Im1hdHJpeCgxLDAsMCwwLjY5ODUyOTQsMCwyMDIuODI4NjMpIgogICAgICAgY3g9IjIyNS4yNjQwMiIKICAgICAgIGN5PSI2NzIuNzk3MzYiCiAgICAgICBmeD0iMjI1LjI2NDAyIgogICAgICAgZnk9IjY3Mi43OTczNiIKICAgICAgIHI9IjM0LjM0NTE4OCIgLz4KICAgIDxsaW5lYXJHcmFkaWVudAogICAgICAgaW5rc2NhcGU6Y29sbGVjdD0iYWx3YXlzIgogICAgICAgeGxpbms6aHJlZj0iI2xpbmVhckdyYWRpZW50Mzc3OSIKICAgICAgIGlkPSJsaW5lYXJHcmFkaWVudDM3ODUiCiAgICAgICB4MT0iMTcwLjIwNDkxIgogICAgICAgeTE9IjcyOC44MzYzNiIKICAgICAgIHgyPSIxNDYuMDgwNjMiCiAgICAgICB5Mj0iNTA4LjM4NzE1IgogICAgICAgZ3JhZGllbnRVbml0cz0idXNlclNwYWNlT25Vc2UiIC8+CiAgICA8bGluZWFyR3JhZGllbnQKICAgICAgIGdyYWRpZW50VHJhbnNmb3JtPSJ0cmFuc2xhdGUoMzk0Ljc0OTQxLDcuNzgyNTQ4NmUtNikiCiAgICAgICBpbmtzY2FwZTpjb2xsZWN0PSJhbHdheXMiCiAgICAgICB4bGluazpocmVmPSIjbGluZWFyR3JhZGllbnQzNzc5IgogICAgICAgaWQ9ImxpbmVhckdyYWRpZW50Mzc4OCIKICAgICAgIHgxPSIxNzAuNDc4NjgiCiAgICAgICB5MT0iNzQwLjgyNjExIgogICAgICAgeDI9IjE0NS44MDY4NCIKICAgICAgIHkyPSI0ODEuNzcxODgiCiAgICAgICBncmFkaWVudFVuaXRzPSJ1c2VyU3BhY2VPblVzZSIgLz4KICAgIDxsaW5lYXJHcmFkaWVudAogICAgICAgZ3JhZGllbnRUcmFuc2Zvcm09Im1hdHJpeCgxLjE0MjY2OCwwLDAsMS4xNDI2NjgxLC0xMDM3LjEyNDgsLTE1MjYuNTc5OSkiCiAgICAgICBpbmtzY2FwZTpjb2xsZWN0PSJhbHdheXMiCiAgICAgICB4bGluazpocmVmPSIjbGluZWFyR3JhZGllbnQzNzc5IgogICAgICAgaWQ9ImxpbmVhckdyYWRpZW50MzgyNSIKICAgICAgIHgxPSIxODguNjA3MTkiCiAgICAgICB5MT0iNjE1LjAwNjM1IgogICAgICAgeDI9IjIwNi43MjgzMyIKICAgICAgIHkyPSI2OTAuMTM3MzkiCiAgICAgICBncmFkaWVudFVuaXRzPSJ1c2VyU3BhY2VPblVzZSIgLz4KICAgIDxsaW5lYXJHcmFkaWVudAogICAgICAgZ3JhZGllbnRUcmFuc2Zvcm09InRyYW5zbGF0ZSg3ODkuNDk4ODUsMS4xMzkzMjk3ZS02KSIKICAgICAgIGlua3NjYXBlOmNvbGxlY3Q9ImFsd2F5cyIKICAgICAgIHhsaW5rOmhyZWY9IiNsaW5lYXJHcmFkaWVudDM3NzkiCiAgICAgICBpZD0ibGluZWFyR3JhZGllbnQzODMzIgogICAgICAgeDE9IjIxMy42NTQzOSIKICAgICAgIHkxPSI3NzEuNjY1ODkiCiAgICAgICB4Mj0iMTAyLjYzMTEzIgogICAgICAgeTI9IjQ1MC45MzIwNyIKICAgICAgIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZU9uVXNlIiAvPgogIDwvZGVmcz4KICA8c29kaXBvZGk6bmFtZWR2aWV3CiAgICAgaWQ9ImJhc2UiCiAgICAgcGFnZWNvbG9yPSIjZmZmZmZmIgogICAgIGJvcmRlcmNvbG9yPSIjNjY2NjY2IgogICAgIGJvcmRlcm9wYWNpdHk9IjEuMCIKICAgICBpbmtzY2FwZTpwYWdlb3BhY2l0eT0iMC4wIgogICAgIGlua3NjYXBlOnBhZ2VzaGFkb3c9IjIiCiAgICAgaW5rc2NhcGU6em9vbT0iMy42MDQwMDM4IgogICAgIGlua3NjYXBlOmN4PSItNC40NTAzNTE1IgogICAgIGlua3NjYXBlOmN5PSIyNy4yNTYyNjYiCiAgICAgaW5rc2NhcGU6Y3VycmVudC1sYXllcj0iZzQyODkiCiAgICAgc2hvd2dyaWQ9InRydWUiCiAgICAgaW5rc2NhcGU6ZG9jdW1lbnQtdW5pdHM9InB4IgogICAgIGlua3NjYXBlOmdyaWQtYmJveD0idHJ1ZSIKICAgICBpbmtzY2FwZTp3aW5kb3ctd2lkdGg9IjI1NjAiCiAgICAgaW5rc2NhcGU6d2luZG93LWhlaWdodD0iMTM2MSIKICAgICBpbmtzY2FwZTp3aW5kb3cteD0iLTkiCiAgICAgaW5rc2NhcGU6d2luZG93LXk9Ii05IgogICAgIGlua3NjYXBlOndpbmRvdy1tYXhpbWl6ZWQ9IjEiCiAgICAgaW5rc2NhcGU6c25hcC1ub2Rlcz0idHJ1ZSIKICAgICBpbmtzY2FwZTpzbmFwLWJib3g9ImZhbHNlIgogICAgIGlua3NjYXBlOnNuYXAtZ2xvYmFsPSJmYWxzZSI+CiAgICA8aW5rc2NhcGU6Z3JpZAogICAgICAgdHlwZT0ieHlncmlkIgogICAgICAgaWQ9ImdyaWQyOTkxIgogICAgICAgZW1wc3BhY2luZz0iMiIKICAgICAgIHZpc2libGU9InRydWUiCiAgICAgICBlbmFibGVkPSJ0cnVlIgogICAgICAgc25hcHZpc2libGVncmlkbGluZXNvbmx5PSJ0cnVlIiAvPgogIDwvc29kaXBvZGk6bmFtZWR2aWV3PgogIDxnCiAgICAgaWQ9ImxheWVyMSIKICAgICBpbmtzY2FwZTpsYWJlbD0iTGF5ZXIgMSIKICAgICBpbmtzY2FwZTpncm91cG1vZGU9ImxheWVyIj4KICAgIDxnCiAgICAgICBpZD0iZzQyODkiCiAgICAgICB0cmFuc2Zvcm09Im1hdHJpeCgwLjE2MjEyODIsMCwwLDAuMTYyMTI4Miw2LjM2MDU5ODYsLTY2LjEwODgwNikiPgogICAgICA8cGF0aAogICAgICAgICBzdHlsZT0iY29sb3I6IzAwMDAwMDtkaXNwbGF5OmlubGluZTtvdmVyZmxvdzp2aXNpYmxlO3Zpc2liaWxpdHk6dmlzaWJsZTtmaWxsOnVybCgjbGluZWFyR3JhZGllbnQzNzg1KTtmaWxsLW9wYWNpdHk6MTtmaWxsLXJ1bGU6bm9uemVybztzdHJva2U6IzA0MmEyYTtzdHJva2Utd2lkdGg6MTIuMzM1OTE2NTI7c3Ryb2tlLWxpbmVjYXA6YnV0dDtzdHJva2UtbGluZWpvaW46cm91bmQ7c3Ryb2tlLW1pdGVybGltaXQ6NDtzdHJva2UtZGFzaGFycmF5Om5vbmU7c3Ryb2tlLWRhc2hvZmZzZXQ6MDtzdHJva2Utb3BhY2l0eToxO21hcmtlcjpub25lO2VuYWJsZS1iYWNrZ3JvdW5kOmFjY3VtdWxhdGUiCiAgICAgICAgIGQ9Ik0gMjc3LjgzNDIsNDUwLjkzMjA4IDkxLjI1MTAxNSw2MTguNzU3MjcgYyAtOC45MTgzMzUsLTMuNTU2NDcgLTE4LjY1MDUzNCwtNS40MTI4MiAtMjguODU3MTQ1LC01LjEzOTUyIC00MC4yMDY4MTUsMS4wNzY2NSAtNzEuODM1ODI4NSwzNC41MDk0MyAtNzAuNzU5MzAxLDc0LjcyMDc3IDEuMDc2NTI3Miw0MC4yMTEzNSAzNC41MDU1MTksNzIuMDQxNiA3NC43MTIzMzQsNzAuOTY0OTYgNDAuMjA2ODE3LC0xLjA3NjY1IDcyLjAzMzQ4NywtMzQuNzA3MSA3MC45NTY5NTcsLTc0LjkxODQ1IC0wLjEwNTQ5LC0zLjkzOTk1IC0wLjY4MDMsLTcuNzEwOTQgLTEuMzgzNTYsLTExLjQ2NTA4IEwgMzI0LjY3NzY0LDUwMy4xMTgwMSBaIgogICAgICAgICBpZD0icmVjdDIyNjkiCiAgICAgICAgIGlua3NjYXBlOmNvbm5lY3Rvci1jdXJ2YXR1cmU9IjAiCiAgICAgICAgIGlua3NjYXBlOmV4cG9ydC14ZHBpPSI1NC44NTcxNDMiCiAgICAgICAgIGlua3NjYXBlOmV4cG9ydC15ZHBpPSI1NC44NTcxNDMiIC8+CiAgICAgIDxwYXRoCiAgICAgICAgIHN0eWxlPSJjb2xvcjojMDAwMDAwO2Rpc3BsYXk6aW5saW5lO292ZXJmbG93OnZpc2libGU7dmlzaWJpbGl0eTp2aXNpYmxlO2ZpbGw6bm9uZTtzdHJva2U6IzM0ZTBlMjtzdHJva2Utd2lkdGg6MTIuMzM1OTE2NTI7c3Ryb2tlLWxpbmVjYXA6YnV0dDtzdHJva2UtbGluZWpvaW46cm91bmQ7c3Ryb2tlLW1pdGVybGltaXQ6NDtzdHJva2UtZGFzaGFycmF5Om5vbmU7c3Ryb2tlLWRhc2hvZmZzZXQ6MDtzdHJva2Utb3BhY2l0eToxO21hcmtlcjpub25lO2VuYWJsZS1iYWNrZ3JvdW5kOmFjY3VtdWxhdGUiCiAgICAgICAgIGQ9Ik0gMjc2Ljc0Mzg1LDQ2OC42NDI5NyA5NC4wODQyMyw2MzIuNTc4MzEgYyAtOC45MTgzMywtMy41NTY0NyAtMjUuMjYzNTY5LC03LjE5NzcyIC0zNi4wMTY1MjMsLTUuNzcxNDcgLTM1LjkxMzgzNiw0Ljc2MzU3IC01My44NjIzOTcyLDMwLjQxOTA1IC01NC4xMjM5MDU3LDY0LjY3NTYyIC0wLjI0OTU4NjIsMzIuNjk0NzggMzYuMzkwNjcxNyw1NS4xMTUxMyA1NS41MTE2MjU3LDU1LjUxMTYyIDI2LjY0ODU2MiwwLjU1MjU5IDYyLjg2MDcyMywtMTMuNzI3OSA2NS4wNzIxMDMsLTYyLjI3NDMyIDAuMjQ5NTcsLTUuNDc4NzcgLTAuOTA1MDUsLTExLjM3OTU2IC0yLjk5NjAzLC0xNS41MzAxOSBsIDE4NS43MzI2MSwtMTY3LjAzMDUgeiIKICAgICAgICAgaWQ9InJlY3QyMjY5LTEiCiAgICAgICAgIGlua3NjYXBlOmNvbm5lY3Rvci1jdXJ2YXR1cmU9IjAiCiAgICAgICAgIHNvZGlwb2RpOm5vZGV0eXBlcz0iY2Nzc3NzY2NjIgogICAgICAgICBpbmtzY2FwZTpleHBvcnQteGRwaT0iNTQuODU3MTQzIgogICAgICAgICBpbmtzY2FwZTpleHBvcnQteWRwaT0iNTQuODU3MTQzIiAvPgogICAgICA8cGF0aAogICAgICAgICBzdHlsZT0iY29sb3I6IzAwMDAwMDtkaXNwbGF5OmlubGluZTtvdmVyZmxvdzp2aXNpYmxlO3Zpc2liaWxpdHk6dmlzaWJsZTtmaWxsOnVybCgjbGluZWFyR3JhZGllbnQzNzg4KTtmaWxsLW9wYWNpdHk6MTtmaWxsLXJ1bGU6bm9uemVybztzdHJva2U6IzA0MmEyYTtzdHJva2Utd2lkdGg6MTIuMzM1OTE2NTI7c3Ryb2tlLWxpbmVjYXA6YnV0dDtzdHJva2UtbGluZWpvaW46cm91bmQ7c3Ryb2tlLW1pdGVybGltaXQ6NDtzdHJva2UtZGFzaGFycmF5Om5vbmU7c3Ryb2tlLWRhc2hvZmZzZXQ6MDtzdHJva2Utb3BhY2l0eToxO21hcmtlcjpub25lO2VuYWJsZS1iYWNrZ3JvdW5kOmFjY3VtdWxhdGUiCiAgICAgICAgIGQ9Im0gNjgwLjgwNTAxLDQzOC41OTYxNiAtOTcuMjYzNyw4OS40OTU3MyBjIC05LjQ3NDA3LC00LjAyNjE1IC0xOS44NjAzMywtNi40NTQ3NSAtMzAuNzM0NTgsLTYuNzA3MzggLTQ2Ljk2NDIyLC0xLjA5MTExIC04NS44ODk0MSwzNy4wNjI4MyAtODYuOTU2NCw4NS4wODgwMSAtMC4yMDY2OSw5LjMwMzUzIDEuMTAyMDIsMTguMTcyMzUgMy41NjA3MSwyNi42Mzc5MiBsIC05NS4zODk2Niw4Ny43NzA5NyA0NC42MDI2Myw1MC43ODQ1MSA5My41MTU2MSwtODYuMDQ2MjEgYyAxMS4wODUyOCw1LjgyNDc4IDIzLjQzNDgzLDkuNDY0NzEgMzYuNzMxNTgsOS43NzM2MiA0Ni45NjQyMSwxLjA5MTExIDg2LjA3Njc4LC0zNy4wNjI4MyA4Ny4xNDM3NywtODUuMDg4MDEgMC4yNjA1MywtMTEuNzI3NTggLTEuOTIwNywtMjIuODQ5NDYgLTUuODA5NTgsLTMzLjE1MzY3IGwgOTUuMzg5NjUsLTg3Ljc3MDk3IHoiCiAgICAgICAgIGlkPSJyZWN0MjI2OS0yIgogICAgICAgICBpbmtzY2FwZTpjb25uZWN0b3ItY3VydmF0dXJlPSIwIgogICAgICAgICBpbmtzY2FwZTpleHBvcnQteGRwaT0iNTQuODU3MTQzIgogICAgICAgICBpbmtzY2FwZTpleHBvcnQteWRwaT0iNTQuODU3MTQzIiAvPgogICAgICA8cGF0aAogICAgICAgICBzdHlsZT0iY29sb3I6IzAwMDAwMDtkaXNwbGF5OmlubGluZTtvdmVyZmxvdzp2aXNpYmxlO3Zpc2liaWxpdHk6dmlzaWJsZTtmaWxsOm5vbmU7c3Ryb2tlOiMzNGUwZTI7c3Ryb2tlLXdpZHRoOjEyLjMzNTkxNjUyO3N0cm9rZS1saW5lY2FwOmJ1dHQ7c3Ryb2tlLWxpbmVqb2luOnJvdW5kO3N0cm9rZS1taXRlcmxpbWl0OjQ7c3Ryb2tlLWRhc2hhcnJheTpub25lO3N0cm9rZS1kYXNob2Zmc2V0OjA7c3Ryb2tlLW9wYWNpdHk6MTttYXJrZXI6bm9uZTtlbmFibGUtYmFja2dyb3VuZDphY2N1bXVsYXRlIgogICAgICAgICBkPSJtIDY4MC4wNjEwMSw0NTYuNDU3MTkgLTkzLjk5NTg0LDg1Ljg1MTUyIGMgLTcuOTc4MTYsLTMuNDI5NjggLTI0LjAxMzkxLC04LjMwMjExIC0zMy4xNzExNiwtOC41MTcyOSAtMzkuNTQ4ODEsLTAuOTI5NDggLTczLjY1MDA0LDMxLjM2MjEgLTc0LjU0ODU2LDcyLjI3MjQzIC0wLjE3NDA2LDcuOTI1MjMgMi42MzAxMiwyNC4yNTEwOSA0LjcwMDU5LDMxLjQ2MjUgbCAtOTEuMzgxOCw4NC4zNTE2NiAyNy43MTU4NSwzMi4yNzUyNiA5MC44NzcwMiwtODMuODUzNzYgYyA5LjMzNDk1LDQuOTYxODcgMjUuODgyNiwxMi4yOTk1NSAzNy4wNzk4NywxMi41NjI3MSAzOS41NDg4MSwwLjkyOTQ1IDc1LjAwODk3LC0yOS42MDk1MiA3Ni4xODc4NCwtNzMuODg0MTkgMC4yNjU5NiwtOS45ODkwMiAtNC43MDE0LC0yNi40NzM0MSAtNy45NzYyMywtMzUuMjUxMDUgbCA5Mi42NjQwMiwtODUuMTQxMjUgeiIKICAgICAgICAgaWQ9InJlY3QyMjY5LTEtMyIKICAgICAgICAgaW5rc2NhcGU6Y29ubmVjdG9yLWN1cnZhdHVyZT0iMCIKICAgICAgICAgc29kaXBvZGk6bm9kZXR5cGVzPSJjY3NzY2NjY3NzY2NjIgogICAgICAgICBpbmtzY2FwZTpleHBvcnQteGRwaT0iNTQuODU3MTQzIgogICAgICAgICBpbmtzY2FwZTpleHBvcnQteWRwaT0iNTQuODU3MTQzIiAvPgogICAgICA8cGF0aAogICAgICAgICBzdHlsZT0iY29sb3I6IzAwMDAwMDtkaXNwbGF5OmlubGluZTtvdmVyZmxvdzp2aXNpYmxlO3Zpc2liaWxpdHk6dmlzaWJsZTtmaWxsOnVybCgjbGluZWFyR3JhZGllbnQzODMzKTtmaWxsLW9wYWNpdHk6MTtmaWxsLXJ1bGU6bm9uemVybztzdHJva2U6IzA0MmEyYTtzdHJva2Utd2lkdGg6MTIuMzM1OTE2NTI7c3Ryb2tlLWxpbmVjYXA6YnV0dDtzdHJva2UtbGluZWpvaW46cm91bmQ7c3Ryb2tlLW1pdGVybGltaXQ6NDtzdHJva2UtZGFzaGFycmF5Om5vbmU7c3Ryb2tlLWRhc2hvZmZzZXQ6MDtzdHJva2Utb3BhY2l0eToxO21hcmtlcjpub25lO2VuYWJsZS1iYWNrZ3JvdW5kOmFjY3VtdWxhdGUiCiAgICAgICAgIGQ9Im0gOTQ3LjU0NDg2LDQzOC41OTYxNiBjIC05Mi4wMDQwNSwwIC0xNjYuNDM4MTIsNzQuNjI3NTkgLTE2Ni40MzgxMiwxNjYuNjMxNjQgMCw5Mi4wMDQwNSA3NC40MzQwNywxNjYuNDM4MTIgMTY2LjQzODEyLDE2Ni40MzgxMiA5Mi4wMDQwNCwwIDE2Ni42MzE0NCwtNzQuNDM0MDcgMTY2LjYzMTQ0LC0xNjYuNDM4MTIgMCwtOTIuMDA0MDUgLTc0LjYyNzQsLTE2Ni42MzE2NCAtMTY2LjYzMTQ0LC0xNjYuNjMxNjQgeiBtIDAuMDk2OCw2MS42Nzk1NyBjIDYwLjYyMzQ0LDAgMTA0Ljg1NTI0LDQ0LjIzMTkgMTA0Ljg1NTI0LDEwNC44NTUzIDAsNjAuNjIzNDUgLTQ0LjIzMTgsMTA0Ljg1NTMgLTEwNC44NTUyNCwxMDQuODU1MyAtNjAuNjIzNDIsMCAtMTA0Ljg1NTMsLTQ0LjIzMTg1IC0xMDQuODU1MywtMTA0Ljg1NTMgMCwtNjAuNjIzNCA0NC4yMzE4OCwtMTA0Ljg1NTMgMTA0Ljg1NTMsLTEwNC44NTUzIHoiCiAgICAgICAgIGlkPSJwYXRoNDM2NCIKICAgICAgICAgaW5rc2NhcGU6Y29ubmVjdG9yLWN1cnZhdHVyZT0iMCIKICAgICAgICAgc29kaXBvZGk6bm9kZXR5cGVzPSJzc3Nzc3Nzc3NzIgogICAgICAgICBpbmtzY2FwZTpleHBvcnQteGRwaT0iNTQuODU3MTQzIgogICAgICAgICBpbmtzY2FwZTpleHBvcnQteWRwaT0iNTQuODU3MTQzIiAvPgogICAgICA8ZWxsaXBzZQogICAgICAgICByeT0iNTUuNTAxMDI2IgogICAgICAgICByeD0iNTUuNTAxMDE5IgogICAgICAgICBjeT0iLTc3Ny44Nzk3IgogICAgICAgICBjeD0iLTgxMS44NTU2NSIKICAgICAgICAgaWQ9InBhdGgzMTYyIgogICAgICAgICBzdHlsZT0iY29sb3I6IzAwMDAwMDtkaXNwbGF5OmlubGluZTtvdmVyZmxvdzp2aXNpYmxlO3Zpc2liaWxpdHk6dmlzaWJsZTtmaWxsOnVybCgjbGluZWFyR3JhZGllbnQzODI1KTtmaWxsLW9wYWNpdHk6MTtmaWxsLXJ1bGU6bm9uemVybztzdHJva2U6IzA0MmEyYTtzdHJva2Utd2lkdGg6MTIuMzM1OTE2NTI7c3Ryb2tlLWxpbmVjYXA6YnV0dDtzdHJva2UtbGluZWpvaW46cm91bmQ7c3Ryb2tlLW1pdGVybGltaXQ6NDtzdHJva2UtZGFzaGFycmF5Om5vbmU7c3Ryb2tlLWRhc2hvZmZzZXQ6MDtzdHJva2Utb3BhY2l0eToxO21hcmtlcjpub25lO2VuYWJsZS1iYWNrZ3JvdW5kOmFjY3VtdWxhdGUiCiAgICAgICAgIHRyYW5zZm9ybT0icm90YXRlKDE2OC43ODUyMykiCiAgICAgICAgIGlua3NjYXBlOmV4cG9ydC14ZHBpPSI1NC44NTcxNDMiCiAgICAgICAgIGlua3NjYXBlOmV4cG9ydC15ZHBpPSI1NC44NTcxNDMiIC8+CiAgICAgIDxjaXJjbGUKICAgICAgICAgcj0iMTU0LjE2OTUxIgogICAgICAgICBjeT0iLTc3Ny44Nzk3NiIKICAgICAgICAgY3g9Ii04MTEuODU1NjUiCiAgICAgICAgIGlkPSJwYXRoMzE2Mi0xIgogICAgICAgICBzdHlsZT0iY29sb3I6IzAwMDAwMDtkaXNwbGF5OmlubGluZTtvdmVyZmxvdzp2aXNpYmxlO3Zpc2liaWxpdHk6dmlzaWJsZTtmaWxsOm5vbmU7c3Ryb2tlOiMzNGUwZTI7c3Ryb2tlLXdpZHRoOjEyLjMzNTkxNjUyO3N0cm9rZS1saW5lY2FwOmJ1dHQ7c3Ryb2tlLWxpbmVqb2luOnJvdW5kO3N0cm9rZS1taXRlcmxpbWl0OjQ7c3Ryb2tlLWRhc2hhcnJheTpub25lO3N0cm9rZS1kYXNob2Zmc2V0OjA7c3Ryb2tlLW9wYWNpdHk6MTttYXJrZXI6bm9uZTtlbmFibGUtYmFja2dyb3VuZDphY2N1bXVsYXRlIgogICAgICAgICB0cmFuc2Zvcm09InJvdGF0ZSgxNjguNzg1MjMpIgogICAgICAgICBpbmtzY2FwZTpleHBvcnQteGRwaT0iNTQuODU3MTQzIgogICAgICAgICBpbmtzY2FwZTpleHBvcnQteWRwaT0iNTQuODU3MTQzIiAvPgogICAgICA8ZWxsaXBzZQogICAgICAgICByeT0iMTE3LjE2ODgzIgogICAgICAgICByeD0iMTE3LjE2ODgyIgogICAgICAgICBjeT0iLTc3Ny44Nzk3NiIKICAgICAgICAgY3g9Ii04MTEuODU1NzEiCiAgICAgICAgIGlkPSJwYXRoMzE2Mi0xLTciCiAgICAgICAgIHN0eWxlPSJjb2xvcjojMDAwMDAwO2Rpc3BsYXk6aW5saW5lO292ZXJmbG93OnZpc2libGU7dmlzaWJpbGl0eTp2aXNpYmxlO2ZpbGw6bm9uZTtzdHJva2U6IzM0ZTBlMjtzdHJva2Utd2lkdGg6MTIuMzM1OTE2NTI7c3Ryb2tlLWxpbmVjYXA6YnV0dDtzdHJva2UtbGluZWpvaW46cm91bmQ7c3Ryb2tlLW1pdGVybGltaXQ6NDtzdHJva2UtZGFzaGFycmF5Om5vbmU7c3Ryb2tlLWRhc2hvZmZzZXQ6MDtzdHJva2Utb3BhY2l0eToxO21hcmtlcjpub25lO2VuYWJsZS1iYWNrZ3JvdW5kOmFjY3VtdWxhdGUiCiAgICAgICAgIHRyYW5zZm9ybT0icm90YXRlKDE2OC43ODUyMykiCiAgICAgICAgIGlua3NjYXBlOmV4cG9ydC14ZHBpPSI1NC44NTcxNDMiCiAgICAgICAgIGlua3NjYXBlOmV4cG9ydC15ZHBpPSI1NC44NTcxNDMiIC8+CiAgICAgIDxlbGxpcHNlCiAgICAgICAgIHJ5PSI0My4xNjc0NjkiCiAgICAgICAgIHJ4PSI0My4xNjc0NjEiCiAgICAgICAgIGN5PSItNzc3Ljg3OTciCiAgICAgICAgIGN4PSItODExLjg1NTY1IgogICAgICAgICBpZD0icGF0aDMxNjItMS03LTQiCiAgICAgICAgIHN0eWxlPSJjb2xvcjojMDAwMDAwO2Rpc3BsYXk6aW5saW5lO292ZXJmbG93OnZpc2libGU7dmlzaWJpbGl0eTp2aXNpYmxlO2ZpbGw6bm9uZTtzdHJva2U6IzM0ZTBlMjtzdHJva2Utd2lkdGg6MTIuMzM1OTE2NTI7c3Ryb2tlLWxpbmVjYXA6YnV0dDtzdHJva2UtbGluZWpvaW46cm91bmQ7c3Ryb2tlLW1pdGVybGltaXQ6NDtzdHJva2UtZGFzaGFycmF5Om5vbmU7c3Ryb2tlLWRhc2hvZmZzZXQ6MDtzdHJva2Utb3BhY2l0eToxO21hcmtlcjpub25lO2VuYWJsZS1iYWNrZ3JvdW5kOmFjY3VtdWxhdGUiCiAgICAgICAgIHRyYW5zZm9ybT0icm90YXRlKDE2OC43ODUyMykiCiAgICAgICAgIGlua3NjYXBlOmV4cG9ydC14ZHBpPSI1NC44NTcxNDMiCiAgICAgICAgIGlua3NjYXBlOmV4cG9ydC15ZHBpPSI1NC44NTcxNDMiIC8+CiAgICA8L2c+CiAgPC9nPgogIDxtZXRhZGF0YQogICAgIGlkPSJtZXRhZGF0YTYzMDUiPgogICAgPHJkZjpSREY+CiAgICAgIDxjYzpXb3JrCiAgICAgICAgIHJkZjphYm91dD0iIj4KICAgICAgICA8ZGM6Zm9ybWF0PmltYWdlL3N2Zyt4bWw8L2RjOmZvcm1hdD4KICAgICAgICA8ZGM6dHlwZQogICAgICAgICAgIHJkZjpyZXNvdXJjZT0iaHR0cDovL3B1cmwub3JnL2RjL2RjbWl0eXBlL1N0aWxsSW1hZ2UiIC8+CiAgICAgICAgPGRjOnRpdGxlPjwvZGM6dGl0bGU+CiAgICAgICAgPGNjOmxpY2Vuc2UKICAgICAgICAgICByZGY6cmVzb3VyY2U9IiIgLz4KICAgICAgICA8ZGM6ZGF0ZT5Nb24gTWFyIDEyIDE3OjIwOjAzIDIwMTIgLTAzMDA8L2RjOmRhdGU+CiAgICAgICAgPGRjOmNyZWF0b3I+CiAgICAgICAgICA8Y2M6QWdlbnQ+CiAgICAgICAgICAgIDxkYzp0aXRsZT5bWW9yaWsgdmFuIEhhdnJlXTwvZGM6dGl0bGU+CiAgICAgICAgICA8L2NjOkFnZW50PgogICAgICAgIDwvZGM6Y3JlYXRvcj4KICAgICAgICA8ZGM6cmlnaHRzPgogICAgICAgICAgPGNjOkFnZW50PgogICAgICAgICAgICA8ZGM6dGl0bGU+RnJlZUNBRCBMR1BMMis8L2RjOnRpdGxlPgogICAgICAgICAgPC9jYzpBZ2VudD4KICAgICAgICA8L2RjOnJpZ2h0cz4KICAgICAgICA8ZGM6cHVibGlzaGVyPgogICAgICAgICAgPGNjOkFnZW50PgogICAgICAgICAgICA8ZGM6dGl0bGU+RnJlZUNBRDwvZGM6dGl0bGU+CiAgICAgICAgICA8L2NjOkFnZW50PgogICAgICAgIDwvZGM6cHVibGlzaGVyPgogICAgICAgIDxkYzppZGVudGlmaWVyPkZyZWVDQUQvc3JjL01vZC9EcmFmdC9SZXNvdXJjZXMvaWNvbnMvU25hcF9FbmRwb2ludC5zdmc8L2RjOmlkZW50aWZpZXI+CiAgICAgICAgPGRjOnJlbGF0aW9uPmh0dHA6Ly93d3cuZnJlZWNhZHdlYi5vcmcvd2lraS9pbmRleC5waHA/dGl0bGU9QXJ0d29yazwvZGM6cmVsYXRpb24+CiAgICAgICAgPGRjOmNvbnRyaWJ1dG9yPgogICAgICAgICAgPGNjOkFnZW50PgogICAgICAgICAgICA8ZGM6dGl0bGU+W2Fncnlzb25dIEFsZXhhbmRlciBHcnlzb248L2RjOnRpdGxlPgogICAgICAgICAgPC9jYzpBZ2VudD4KICAgICAgICA8L2RjOmNvbnRyaWJ1dG9yPgogICAgICAgIDxkYzpzdWJqZWN0PgogICAgICAgICAgPHJkZjpCYWc+CiAgICAgICAgICAgIDxyZGY6bGk+bGluZTwvcmRmOmxpPgogICAgICAgICAgICA8cmRmOmxpPmVuZHBvaW50PC9yZGY6bGk+CiAgICAgICAgICAgIDxyZGY6bGkgLz4KICAgICAgICAgIDwvcmRmOkJhZz4KICAgICAgICA8L2RjOnN1YmplY3Q+CiAgICAgICAgPGRjOmRlc2NyaXB0aW9uPmxpbmUgd2l0aCBidWxnZSBhdCBvbmUgZW5kcG9pbnQ8L2RjOmRlc2NyaXB0aW9uPgogICAgICA8L2NjOldvcms+CiAgICA8L3JkZjpSREY+CiAgPC9tZXRhZGF0YT4KPC9zdmc+Cg==
"""
Dim_Radius_b64=\
"""
PD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0iVVRGLTgiIHN0YW5kYWxvbmU9Im5vIj8+CjwhLS0gQ3JlYXRlZCB3aXRoIElua3NjYXBlIChodHRwOi8vd3d3Lmlua3NjYXBlLm9yZy8pIC0tPgoKPHN2ZwogICB4bWxuczpkYz0iaHR0cDovL3B1cmwub3JnL2RjL2VsZW1lbnRzLzEuMS8iCiAgIHhtbG5zOmNjPSJodHRwOi8vY3JlYXRpdmVjb21tb25zLm9yZy9ucyMiCiAgIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyIKICAgeG1sbnM6c3ZnPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyIKICAgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIgogICB4bWxuczp4bGluaz0iaHR0cDovL3d3dy53My5vcmcvMTk5OS94bGluayIKICAgeG1sbnM6c29kaXBvZGk9Imh0dHA6Ly9zb2RpcG9kaS5zb3VyY2Vmb3JnZS5uZXQvRFREL3NvZGlwb2RpLTAuZHRkIgogICB4bWxuczppbmtzY2FwZT0iaHR0cDovL3d3dy5pbmtzY2FwZS5vcmcvbmFtZXNwYWNlcy9pbmtzY2FwZSIKICAgd2lkdGg9IjY0cHgiCiAgIGhlaWdodD0iNjRweCIKICAgaWQ9InN2ZzU4MjEiCiAgIHNvZGlwb2RpOnZlcnNpb249IjAuMzIiCiAgIGlua3NjYXBlOnZlcnNpb249IjAuOTIuMCByMTUyOTkiCiAgIHNvZGlwb2RpOmRvY25hbWU9IkRpbWVuc2lvbl9SYWRpdXMuc3ZnIgogICBpbmtzY2FwZTpvdXRwdXRfZXh0ZW5zaW9uPSJvcmcuaW5rc2NhcGUub3V0cHV0LnN2Zy5pbmtzY2FwZSIKICAgdmVyc2lvbj0iMS4xIgogICBpbmtzY2FwZTpleHBvcnQtZmlsZW5hbWU9Ii9ob21lL3VzZXIvRG93bmxvYWRzL2NhZC9teXN0dWZmL2ljb25zL0RyYXdpbmcvVGVjaERyYXdfZGltZW5zaW9ucy9kcmF3aW5nX0RpbWVuc2lvbl9SYWRpdXNfNV8zMnB4LnBuZyIKICAgaW5rc2NhcGU6ZXhwb3J0LXhkcGk9IjQ1IgogICBpbmtzY2FwZTpleHBvcnQteWRwaT0iNDUiPgogIDxkZWZzCiAgICAgaWQ9ImRlZnM1ODIzIj4KICAgIDxsaW5lYXJHcmFkaWVudAogICAgICAgaWQ9ImxpbmVhckdyYWRpZW50MzAyOSIKICAgICAgIGlua3NjYXBlOmNvbGxlY3Q9ImFsd2F5cyI+CiAgICAgIDxzdG9wCiAgICAgICAgIGlkPSJzdG9wMzAzMSIKICAgICAgICAgb2Zmc2V0PSIwIgogICAgICAgICBzdHlsZT0ic3RvcC1jb2xvcjojYzRhMDAwO3N0b3Atb3BhY2l0eToxIiAvPgogICAgICA8c3RvcAogICAgICAgICBpZD0ic3RvcDMwMzMiCiAgICAgICAgIG9mZnNldD0iMSIKICAgICAgICAgc3R5bGU9InN0b3AtY29sb3I6I2ZjZTk0ZjtzdG9wLW9wYWNpdHk6MSIgLz4KICAgIDwvbGluZWFyR3JhZGllbnQ+CiAgICA8bGluZWFyR3JhZGllbnQKICAgICAgIGlkPSJsaW5lYXJHcmFkaWVudDMwMjMiCiAgICAgICBpbmtzY2FwZTpjb2xsZWN0PSJhbHdheXMiPgogICAgICA8c3RvcAogICAgICAgICBpZD0ic3RvcDMwMjUiCiAgICAgICAgIG9mZnNldD0iMCIKICAgICAgICAgc3R5bGU9InN0b3AtY29sb3I6I2M0YTAwMDtzdG9wLW9wYWNpdHk6MSIgLz4KICAgICAgPHN0b3AKICAgICAgICAgaWQ9InN0b3AzMDI3IgogICAgICAgICBvZmZzZXQ9IjEiCiAgICAgICAgIHN0eWxlPSJzdG9wLWNvbG9yOiNmY2U5NGY7c3RvcC1vcGFjaXR5OjEiIC8+CiAgICA8L2xpbmVhckdyYWRpZW50PgogICAgPGxpbmVhckdyYWRpZW50CiAgICAgICBpbmtzY2FwZTpjb2xsZWN0PSJhbHdheXMiCiAgICAgICBpZD0ibGluZWFyR3JhZGllbnQzODEwIj4KICAgICAgPHN0b3AKICAgICAgICAgc3R5bGU9InN0b3AtY29sb3I6I2M0YTAwMDtzdG9wLW9wYWNpdHk6MSIKICAgICAgICAgb2Zmc2V0PSIwIgogICAgICAgICBpZD0ic3RvcDM4MTIiIC8+CiAgICAgIDxzdG9wCiAgICAgICAgIHN0eWxlPSJzdG9wLWNvbG9yOiNmY2U5NGY7c3RvcC1vcGFjaXR5OjEiCiAgICAgICAgIG9mZnNldD0iMSIKICAgICAgICAgaWQ9InN0b3AzODE0IiAvPgogICAgPC9saW5lYXJHcmFkaWVudD4KICAgIDxsaW5lYXJHcmFkaWVudAogICAgICAgaW5rc2NhcGU6Y29sbGVjdD0iYWx3YXlzIgogICAgICAgaWQ9ImxpbmVhckdyYWRpZW50NjM0OSI+CiAgICAgIDxzdG9wCiAgICAgICAgIHN0eWxlPSJzdG9wLWNvbG9yOiMwMDAwMDA7c3RvcC1vcGFjaXR5OjE7IgogICAgICAgICBvZmZzZXQ9IjAiCiAgICAgICAgIGlkPSJzdG9wNjM1MSIgLz4KICAgICAgPHN0b3AKICAgICAgICAgc3R5bGU9InN0b3AtY29sb3I6IzAwMDAwMDtzdG9wLW9wYWNpdHk6MDsiCiAgICAgICAgIG9mZnNldD0iMSIKICAgICAgICAgaWQ9InN0b3A2MzUzIiAvPgogICAgPC9saW5lYXJHcmFkaWVudD4KICAgIDxsaW5lYXJHcmFkaWVudAogICAgICAgaWQ9ImxpbmVhckdyYWRpZW50MzM3NyI+CiAgICAgIDxzdG9wCiAgICAgICAgIHN0eWxlPSJzdG9wLWNvbG9yOiMwMDE5YTM7c3RvcC1vcGFjaXR5OjE7IgogICAgICAgICBvZmZzZXQ9IjAiCiAgICAgICAgIGlkPSJzdG9wMzM3OSIgLz4KICAgICAgPHN0b3AKICAgICAgICAgc3R5bGU9InN0b3AtY29sb3I6IzAwNjlmZjtzdG9wLW9wYWNpdHk6MTsiCiAgICAgICAgIG9mZnNldD0iMSIKICAgICAgICAgaWQ9InN0b3AzMzgxIiAvPgogICAgPC9saW5lYXJHcmFkaWVudD4KICAgIDxsaW5lYXJHcmFkaWVudAogICAgICAgaW5rc2NhcGU6Y29sbGVjdD0iYWx3YXlzIgogICAgICAgeGxpbms6aHJlZj0iI2xpbmVhckdyYWRpZW50MzM3NyIKICAgICAgIGlkPSJsaW5lYXJHcmFkaWVudDMzODMiCiAgICAgICB4MT0iOTAxLjE4NzUiCiAgICAgICB5MT0iMTE5MC44NzUiCiAgICAgICB4Mj0iMTI2Ny45MDYyIgogICAgICAgeTI9IjExOTAuODc1IgogICAgICAgZ3JhZGllbnRVbml0cz0idXNlclNwYWNlT25Vc2UiCiAgICAgICBncmFkaWVudFRyYW5zZm9ybT0ibWF0cml4KC0xLDAsMCwxLDIxOTkuMzU2LDApIiAvPgogICAgPGlua3NjYXBlOnBlcnNwZWN0aXZlCiAgICAgICBzb2RpcG9kaTp0eXBlPSJpbmtzY2FwZTpwZXJzcDNkIgogICAgICAgaW5rc2NhcGU6dnBfeD0iMCA6IDMyIDogMSIKICAgICAgIGlua3NjYXBlOnZwX3k9IjAgOiAxMDAwIDogMCIKICAgICAgIGlua3NjYXBlOnZwX3o9IjY0IDogMzIgOiAxIgogICAgICAgaW5rc2NhcGU6cGVyc3AzZC1vcmlnaW49IjMyIDogMjEuMzMzMzMzIDogMSIKICAgICAgIGlkPSJwZXJzcGVjdGl2ZTU4MjkiIC8+CiAgICA8cmFkaWFsR3JhZGllbnQKICAgICAgIGlua3NjYXBlOmNvbGxlY3Q9ImFsd2F5cyIKICAgICAgIHhsaW5rOmhyZWY9IiNsaW5lYXJHcmFkaWVudDYzNDkiCiAgICAgICBpZD0icmFkaWFsR3JhZGllbnQ2MzU1IgogICAgICAgY3g9IjExMDMuNjM5OSIKICAgICAgIGN5PSIxNDI0LjQ0NjUiCiAgICAgICBmeD0iMTEwMy42Mzk5IgogICAgICAgZnk9IjE0MjQuNDQ2NSIKICAgICAgIHI9IjE5NC40MDYxNCIKICAgICAgIGdyYWRpZW50VHJhbnNmb3JtPSJtYXRyaXgoLTEuNDMwNzQ5OSwtMS4zNjA1MTU2ZS03LC0xLjIwMjcxM2UtOCwwLjEyNjQ4MDEsMjY3NC43NDg4LDEyNDQuMjgyNikiCiAgICAgICBncmFkaWVudFVuaXRzPSJ1c2VyU3BhY2VPblVzZSIgLz4KICAgIDxsaW5lYXJHcmFkaWVudAogICAgICAgaW5rc2NhcGU6Y29sbGVjdD0iYWx3YXlzIgogICAgICAgeGxpbms6aHJlZj0iI2xpbmVhckdyYWRpZW50MzgxMCIKICAgICAgIGlkPSJsaW5lYXJHcmFkaWVudDM4MTYiCiAgICAgICB4MT0iMzYuNDY1MzciCiAgICAgICB5MT0iNDEuOTk4Njc2IgogICAgICAgeDI9IjI2LjIzMjk0NiIKICAgICAgIHkyPSItMC43OTE0NjM1NSIKICAgICAgIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZU9uVXNlIiAvPgogICAgPGxpbmVhckdyYWRpZW50CiAgICAgICBncmFkaWVudFRyYW5zZm9ybT0ibWF0cml4KDAuNjY0OTY2MDQsMC42NzQwMzYzMiwtMC42NjQ5NjYwNCwwLjY3NDAzNjMyLDMxLjk2NDI4NSwtMTEuMjkzMDg3KSIKICAgICAgIHkyPSIyOC4zOTkxODUiCiAgICAgICB4Mj0iMjUuNDQ1MjIzIgogICAgICAgeTE9IjQwLjIyNzUwOSIKICAgICAgIHgxPSI0My4yODg4OTEiCiAgICAgICBncmFkaWVudFVuaXRzPSJ1c2VyU3BhY2VPblVzZSIKICAgICAgIGlkPSJsaW5lYXJHcmFkaWVudDQwNzUiCiAgICAgICB4bGluazpocmVmPSIjbGluZWFyR3JhZGllbnQzODkzIgogICAgICAgaW5rc2NhcGU6Y29sbGVjdD0iYWx3YXlzIiAvPgogICAgPGxpbmVhckdyYWRpZW50CiAgICAgICBpbmtzY2FwZTpjb2xsZWN0PSJhbHdheXMiCiAgICAgICBpZD0ibGluZWFyR3JhZGllbnQzODkzIj4KICAgICAgPHN0b3AKICAgICAgICAgc3R5bGU9InN0b3AtY29sb3I6I2QzZDdjZjtzdG9wLW9wYWNpdHk6MSIKICAgICAgICAgb2Zmc2V0PSIwIgogICAgICAgICBpZD0ic3RvcDM4OTUiIC8+CiAgICAgIDxzdG9wCiAgICAgICAgIHN0eWxlPSJzdG9wLWNvbG9yOiNmZmZmZmY7c3RvcC1vcGFjaXR5OjEiCiAgICAgICAgIG9mZnNldD0iMSIKICAgICAgICAgaWQ9InN0b3AzODk3IiAvPgogICAgPC9saW5lYXJHcmFkaWVudD4KICAgIDxsaW5lYXJHcmFkaWVudAogICAgICAgeTI9IjI4LjM5OTE4NSIKICAgICAgIHgyPSIyNS40NDUyMjMiCiAgICAgICB5MT0iNDAuMjI3NTA5IgogICAgICAgeDE9IjQzLjI4ODg5MSIKICAgICAgIGdyYWRpZW50VHJhbnNmb3JtPSJtYXRyaXgoMC42NjQ5NjYwNCwwLjY3NDAzNjMyLC0wLjY2NDk2NjA0LDAuNjc0MDM2MzIsMjQuOTc0NDksLTUuOTAwNzk2KSIKICAgICAgIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZU9uVXNlIgogICAgICAgaWQ9ImxpbmVhckdyYWRpZW50MzEwNyIKICAgICAgIHhsaW5rOmhyZWY9IiNsaW5lYXJHcmFkaWVudDM4OTMiCiAgICAgICBpbmtzY2FwZTpjb2xsZWN0PSJhbHdheXMiIC8+CiAgICA8bGluZWFyR3JhZGllbnQKICAgICAgIGlua3NjYXBlOmNvbGxlY3Q9ImFsd2F5cyIKICAgICAgIHhsaW5rOmhyZWY9IiNsaW5lYXJHcmFkaWVudDM5MDUiCiAgICAgICBpZD0ibGluZWFyR3JhZGllbnQzOTE5IgogICAgICAgeDE9IjkiCiAgICAgICB5MT0iNTAiCiAgICAgICB4Mj0iNSIKICAgICAgIHkyPSIzOCIKICAgICAgIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZU9uVXNlIiAvPgogICAgPGxpbmVhckdyYWRpZW50CiAgICAgICBpbmtzY2FwZTpjb2xsZWN0PSJhbHdheXMiCiAgICAgICBpZD0ibGluZWFyR3JhZGllbnQzOTA1Ij4KICAgICAgPHN0b3AKICAgICAgICAgc3R5bGU9InN0b3AtY29sb3I6I2QzZDdjZjtzdG9wLW9wYWNpdHk6MSIKICAgICAgICAgb2Zmc2V0PSIwIgogICAgICAgICBpZD0ic3RvcDM5MDciIC8+CiAgICAgIDxzdG9wCiAgICAgICAgIHN0eWxlPSJzdG9wLWNvbG9yOiNmZmZmZmY7c3RvcC1vcGFjaXR5OjEiCiAgICAgICAgIG9mZnNldD0iMSIKICAgICAgICAgaWQ9InN0b3AzOTA5IiAvPgogICAgPC9saW5lYXJHcmFkaWVudD4KICAgIDxsaW5lYXJHcmFkaWVudAogICAgICAgaW5rc2NhcGU6Y29sbGVjdD0iYWx3YXlzIgogICAgICAgeGxpbms6aHJlZj0iI2xpbmVhckdyYWRpZW50MzkwNSIKICAgICAgIGlkPSJsaW5lYXJHcmFkaWVudDM5MTEiCiAgICAgICB4MT0iOC41IgogICAgICAgeTE9IjQ4LjUiCiAgICAgICB4Mj0iNS41IgogICAgICAgeTI9IjM5LjUiCiAgICAgICBncmFkaWVudFVuaXRzPSJ1c2VyU3BhY2VPblVzZSIgLz4KICAgIDxsaW5lYXJHcmFkaWVudAogICAgICAgeTI9IjM5LjUiCiAgICAgICB4Mj0iNS41IgogICAgICAgeTE9IjQ4LjUiCiAgICAgICB4MT0iOC41IgogICAgICAgZ3JhZGllbnRVbml0cz0idXNlclNwYWNlT25Vc2UiCiAgICAgICBpZD0ibGluZWFyR3JhZGllbnQzMDQ3IgogICAgICAgeGxpbms6aHJlZj0iI2xpbmVhckdyYWRpZW50MzkwNSIKICAgICAgIGlua3NjYXBlOmNvbGxlY3Q9ImFsd2F5cyIgLz4KICAgIDxsaW5lYXJHcmFkaWVudAogICAgICAgaW5rc2NhcGU6Y29sbGVjdD0iYWx3YXlzIgogICAgICAgeGxpbms6aHJlZj0iI2xpbmVhckdyYWRpZW50MzkwNSIKICAgICAgIGlkPSJsaW5lYXJHcmFkaWVudDM4ODUiCiAgICAgICBncmFkaWVudFVuaXRzPSJ1c2VyU3BhY2VPblVzZSIKICAgICAgIHgxPSI4LjUiCiAgICAgICB5MT0iNDguNSIKICAgICAgIHgyPSI1LjUiCiAgICAgICB5Mj0iMzkuNSIgLz4KICAgIDxsaW5lYXJHcmFkaWVudAogICAgICAgaW5rc2NhcGU6Y29sbGVjdD0iYWx3YXlzIgogICAgICAgeGxpbms6aHJlZj0iI2xpbmVhckdyYWRpZW50MzAyOSIKICAgICAgIGlkPSJsaW5lYXJHcmFkaWVudDM4ODciCiAgICAgICBncmFkaWVudFVuaXRzPSJ1c2VyU3BhY2VPblVzZSIKICAgICAgIGdyYWRpZW50VHJhbnNmb3JtPSJtYXRyaXgoMC42NjQ5NjYwNCwwLjY3NDAzNjMyLC0wLjY2NDk2NjA0LDAuNjc0MDM2MzIsMjQuOTc0NDksLTUuOTAwNzk2KSIKICAgICAgIHgxPSI0My4yODg4OTEiCiAgICAgICB5MT0iNDAuMjI3NTA5IgogICAgICAgeDI9IjI1LjQ0NTIyMyIKICAgICAgIHkyPSIyOC4zOTkxODUiIC8+CiAgICA8bGluZWFyR3JhZGllbnQKICAgICAgIGlua3NjYXBlOmNvbGxlY3Q9ImFsd2F5cyIKICAgICAgIHhsaW5rOmhyZWY9IiNsaW5lYXJHcmFkaWVudDMwMjMiCiAgICAgICBpZD0ibGluZWFyR3JhZGllbnQzODg5IgogICAgICAgZ3JhZGllbnRVbml0cz0idXNlclNwYWNlT25Vc2UiCiAgICAgICB4MT0iOSIKICAgICAgIHkxPSI1MCIKICAgICAgIHgyPSI1IgogICAgICAgeTI9IjM4IiAvPgogIDwvZGVmcz4KICA8c29kaXBvZGk6bmFtZWR2aWV3CiAgICAgaWQ9ImJhc2UiCiAgICAgcGFnZWNvbG9yPSIjZmZmZmZmIgogICAgIGJvcmRlcmNvbG9yPSIjNjY2NjY2IgogICAgIGJvcmRlcm9wYWNpdHk9IjEuMCIKICAgICBpbmtzY2FwZTpwYWdlb3BhY2l0eT0iMC4wIgogICAgIGlua3NjYXBlOnBhZ2VzaGFkb3c9IjIiCiAgICAgaW5rc2NhcGU6em9vbT0iOS42ODc1IgogICAgIGlua3NjYXBlOmN4PSIzMiIKICAgICBpbmtzY2FwZTpjeT0iMzIiCiAgICAgaW5rc2NhcGU6Y3VycmVudC1sYXllcj0ibGF5ZXIxIgogICAgIHNob3dncmlkPSJ0cnVlIgogICAgIGlua3NjYXBlOmRvY3VtZW50LXVuaXRzPSJweCIKICAgICBpbmtzY2FwZTpncmlkLWJib3g9InRydWUiCiAgICAgaW5rc2NhcGU6d2luZG93LXdpZHRoPSIxNTM2IgogICAgIGlua3NjYXBlOndpbmRvdy1oZWlnaHQ9IjgwMSIKICAgICBpbmtzY2FwZTp3aW5kb3cteD0iLTgiCiAgICAgaW5rc2NhcGU6d2luZG93LXk9Ii04IgogICAgIGlua3NjYXBlOndpbmRvdy1tYXhpbWl6ZWQ9IjEiCiAgICAgc2hvd2d1aWRlcz0idHJ1ZSIKICAgICBpbmtzY2FwZTpndWlkZS1iYm94PSJ0cnVlIgogICAgIGlua3NjYXBlOnNuYXAtZ2xvYmFsPSJ0cnVlIgogICAgIGlua3NjYXBlOnNuYXAtYmJveD0idHJ1ZSIKICAgICBpbmtzY2FwZTpvYmplY3QtcGF0aHM9ImZhbHNlIgogICAgIGlua3NjYXBlOnNuYXAtbm9kZXM9InRydWUiPgogICAgPGlua3NjYXBlOmdyaWQKICAgICAgIHR5cGU9Inh5Z3JpZCIKICAgICAgIGlkPSJncmlkMjk5MyIKICAgICAgIGVtcHNwYWNpbmc9IjIiCiAgICAgICB2aXNpYmxlPSJ0cnVlIgogICAgICAgZW5hYmxlZD0idHJ1ZSIKICAgICAgIHNuYXB2aXNpYmxlZ3JpZGxpbmVzb25seT0idHJ1ZSIgLz4KICA8L3NvZGlwb2RpOm5hbWVkdmlldz4KICA8bWV0YWRhdGEKICAgICBpZD0ibWV0YWRhdGE1ODI2Ij4KICAgIDxyZGY6UkRGPgogICAgICA8Y2M6V29yawogICAgICAgICByZGY6YWJvdXQ9IiI+CiAgICAgICAgPGRjOmZvcm1hdD5pbWFnZS9zdmcreG1sPC9kYzpmb3JtYXQ+CiAgICAgICAgPGRjOnR5cGUKICAgICAgICAgICByZGY6cmVzb3VyY2U9Imh0dHA6Ly9wdXJsLm9yZy9kYy9kY21pdHlwZS9TdGlsbEltYWdlIiAvPgogICAgICAgIDxkYzp0aXRsZSAvPgogICAgICAgIDxkYzpjcmVhdG9yPgogICAgICAgICAgPGNjOkFnZW50PgogICAgICAgICAgICA8ZGM6dGl0bGU+W1dhbmRlcmVyRmFuXTwvZGM6dGl0bGU+CiAgICAgICAgICA8L2NjOkFnZW50PgogICAgICAgIDwvZGM6Y3JlYXRvcj4KICAgICAgICA8ZGM6dGl0bGU+VGVjaERyYXdfRGltZW5zaW9uX1JhZGl1czwvZGM6dGl0bGU+CiAgICAgICAgPGRjOmRhdGU+MjAxNi0wNC0yNzwvZGM6ZGF0ZT4KICAgICAgICA8ZGM6cmVsYXRpb24+aHR0cDovL3d3dy5mcmVlY2Fkd2ViLm9yZy93aWtpL2luZGV4LnBocD90aXRsZT1BcnR3b3JrPC9kYzpyZWxhdGlvbj4KICAgICAgICA8ZGM6cHVibGlzaGVyPgogICAgICAgICAgPGNjOkFnZW50PgogICAgICAgICAgICA8ZGM6dGl0bGU+RnJlZUNBRDwvZGM6dGl0bGU+CiAgICAgICAgICA8L2NjOkFnZW50PgogICAgICAgIDwvZGM6cHVibGlzaGVyPgogICAgICAgIDxkYzppZGVudGlmaWVyPkZyZWVDQUQvc3JjL01vZC9UZWNoRHJhdy9HdWkvUmVzb3VyY2VzL2ljb25zL1RlY2hEcmF3X0RpbWVuc2lvbl9SYWRpdXMuc3ZnPC9kYzppZGVudGlmaWVyPgogICAgICAgIDxkYzpyaWdodHM+CiAgICAgICAgICA8Y2M6QWdlbnQ+CiAgICAgICAgICAgIDxkYzp0aXRsZT5GcmVlQ0FEIExHUEwyKzwvZGM6dGl0bGU+CiAgICAgICAgICA8L2NjOkFnZW50PgogICAgICAgIDwvZGM6cmlnaHRzPgogICAgICAgIDxjYzpsaWNlbnNlCiAgICAgICAgICAgcmRmOnJlc291cmNlPSJodHRwczovL3d3dy5nbnUub3JnL2xpY2Vuc2VzL2xncGwtMy4wLmVuLmh0bWwiPmh0dHBzOi8vd3d3LmdudS5vcmcvY29weWxlZnQvbGVzc2VyLmh0bWw8L2NjOmxpY2Vuc2U+CiAgICAgICAgPGRjOmNvbnRyaWJ1dG9yPgogICAgICAgICAgPGNjOkFnZW50PgogICAgICAgICAgICA8ZGM6dGl0bGU+W2Fncnlzb25dIEFsZXhhbmRlciBHcnlzb248L2RjOnRpdGxlPgogICAgICAgICAgPC9jYzpBZ2VudD4KICAgICAgICA8L2RjOmNvbnRyaWJ1dG9yPgogICAgICAgIDxkYzpzdWJqZWN0PgogICAgICAgICAgPHJkZjpCYWc+CiAgICAgICAgICAgIDxyZGY6bGk+YXJyb3c8L3JkZjpsaT4KICAgICAgICAgICAgPHJkZjpsaT5yYWRpdXM8L3JkZjpsaT4KICAgICAgICAgICAgPHJkZjpsaT5hcmM8L3JkZjpsaT4KICAgICAgICAgIDwvcmRmOkJhZz4KICAgICAgICA8L2RjOnN1YmplY3Q+CiAgICAgICAgPGRjOmRlc2NyaXB0aW9uPkFycm93IHBvaW50aW5nIGZyb20gY2VudHJlIHRvIGFyYzwvZGM6ZGVzY3JpcHRpb24+CiAgICAgIDwvY2M6V29yaz4KICAgIDwvcmRmOlJERj4KICA8L21ldGFkYXRhPgogIDxnCiAgICAgaWQ9ImxheWVyMSIKICAgICBpbmtzY2FwZTpsYWJlbD0iTGF5ZXIgMSIKICAgICBpbmtzY2FwZTpncm91cG1vZGU9ImxheWVyIj4KICAgIDxwYXRoCiAgICAgICBzb2RpcG9kaTp0eXBlPSJhcmMiCiAgICAgICBzdHlsZT0iZmlsbDpub25lO3N0cm9rZTojMzAyYjAwO3N0cm9rZS13aWR0aDo3LjQ0MTc2MzQwMDAwMDAwMDEwO3N0cm9rZS1saW5lY2FwOnJvdW5kO3N0cm9rZS1saW5lam9pbjptaXRlcjtzdHJva2UtbWl0ZXJsaW1pdDo0O3N0cm9rZS1vcGFjaXR5OjE7c3Ryb2tlLWRhc2hhcnJheTpub25lO3N0cm9rZS1kYXNob2Zmc2V0OjAiCiAgICAgICBpZD0icGF0aDM3NjUiCiAgICAgICBzb2RpcG9kaTpjeD0iMTYiCiAgICAgICBzb2RpcG9kaTpjeT0iNDIiCiAgICAgICBzb2RpcG9kaTpyeD0iNDAiCiAgICAgICBzb2RpcG9kaTpyeT0iNDAiCiAgICAgICBkPSJNIDEzLjI1OTY4MSwyLjA5Mzk3NzMgQSA0MCw0MCAwIDAgMSA1Niw0Mi4wMDI4NiIKICAgICAgIHNvZGlwb2RpOnN0YXJ0PSI0LjY0MzgyNzMiCiAgICAgICBzb2RpcG9kaTplbmQ9IjYuMjgzMjU2OCIKICAgICAgIHRyYW5zZm9ybT0ibWF0cml4KDEuMDc1MDE0LDAsMCwxLjA3NTAxNCwtNC4yMDA3ODM5LDYuODQ2MzM3OCkiCiAgICAgICBzb2RpcG9kaTpvcGVuPSJ0cnVlIgogICAgICAgaW5rc2NhcGU6ZXhwb3J0LXhkcGk9IjU2LjE0NzAzIgogICAgICAgaW5rc2NhcGU6ZXhwb3J0LXlkcGk9IjU2LjE0NzAzIiAvPgogICAgPHBhdGgKICAgICAgIHNvZGlwb2RpOnR5cGU9ImFyYyIKICAgICAgIHN0eWxlPSJmaWxsOm5vbmU7c3Ryb2tlOnVybCgjbGluZWFyR3JhZGllbnQzODE2KTtzdHJva2Utd2lkdGg6My43MjA4ODE3O3N0cm9rZS1saW5lY2FwOnJvdW5kO3N0cm9rZS1saW5lam9pbjptaXRlcjtzdHJva2UtbWl0ZXJsaW1pdDo0O3N0cm9rZS1vcGFjaXR5OjE7c3Ryb2tlLWRhc2hhcnJheTpub25lO3N0cm9rZS1kYXNob2Zmc2V0OjAiCiAgICAgICBpZD0icGF0aDM3NjUtMSIKICAgICAgIHNvZGlwb2RpOmN4PSIxNiIKICAgICAgIHNvZGlwb2RpOmN5PSI0MiIKICAgICAgIHNvZGlwb2RpOnJ4PSI0MCIKICAgICAgIHNvZGlwb2RpOnJ5PSI0MCIKICAgICAgIGQ9Ik0gMTMuMzAxMDQ1LDIuMDkxMTU4NCBBIDQwLDQwIDAgMCAxIDU2LDQyLjAwMjg2IgogICAgICAgc29kaXBvZGk6c3RhcnQ9IjQuNjQ0ODYzOCIKICAgICAgIHNvZGlwb2RpOmVuZD0iNi4yODMyNTY4IgogICAgICAgdHJhbnNmb3JtPSJtYXRyaXgoMS4wNzUwMTQsMCwwLDEuMDc1MDE0LC00LjIwMTk4NTUsNi44NDk0MzM3KSIKICAgICAgIHNvZGlwb2RpOm9wZW49InRydWUiCiAgICAgICBpbmtzY2FwZTpleHBvcnQteGRwaT0iNTYuMTQ3MDMiCiAgICAgICBpbmtzY2FwZTpleHBvcnQteWRwaT0iNTYuMTQ3MDMiIC8+CiAgICA8cGF0aAogICAgICAgc29kaXBvZGk6dHlwZT0iYXJjIgogICAgICAgc3R5bGU9ImZpbGw6bm9uZTtzdHJva2U6I2ZjZTk0ZjtzdHJva2Utd2lkdGg6MS44NjA0NDA4NTAwMDAwMDAwMDtzdHJva2UtbGluZWNhcDpyb3VuZDtzdHJva2UtbGluZWpvaW46bWl0ZXI7c3Ryb2tlLW1pdGVybGltaXQ6NDtzdHJva2Utb3BhY2l0eToxO3N0cm9rZS1kYXNoYXJyYXk6bm9uZTtzdHJva2UtZGFzaG9mZnNldDowIgogICAgICAgaWQ9InBhdGgzNzY1LTEtNyIKICAgICAgIHNvZGlwb2RpOmN4PSIxNiIKICAgICAgIHNvZGlwb2RpOmN5PSI0MiIKICAgICAgIHNvZGlwb2RpOnJ4PSI0MCIKICAgICAgIHNvZGlwb2RpOnJ5PSI0MCIKICAgICAgIGQ9Ik0gMTIuNjU4MjYsMi4xMzk4MzQ3IEEgNDAsNDAgMCAwIDEgNTUuOTgzNDg3LDQzLjE0OTIzOCIKICAgICAgIHNvZGlwb2RpOnN0YXJ0PSI0LjYyODc0OCIKICAgICAgIHNvZGlwb2RpOmVuZD0iNi4zMTE5MjAyIgogICAgICAgdHJhbnNmb3JtPSJtYXRyaXgoMS4wNzUwMTQsMCwwLDEuMDc1MDE0LC0zLjIwMTk4NTUsNS44NDk0MzM3KSIKICAgICAgIHNvZGlwb2RpOm9wZW49InRydWUiCiAgICAgICBpbmtzY2FwZTpleHBvcnQteGRwaT0iNTYuMTQ3MDMiCiAgICAgICBpbmtzY2FwZTpleHBvcnQteWRwaT0iNTYuMTQ3MDMiIC8+CiAgICA8ZwogICAgICAgaWQ9ImczODc0IgogICAgICAgdHJhbnNmb3JtPSJ0cmFuc2xhdGUoLTEuMDEwMjA1LDEuNjA3NzA5KSIKICAgICAgIGlua3NjYXBlOmV4cG9ydC14ZHBpPSI1Ni4xNDcwMyIKICAgICAgIGlua3NjYXBlOmV4cG9ydC15ZHBpPSI1Ni4xNDcwMyI+CiAgICAgIDxwYXRoCiAgICAgICAgIHRyYW5zZm9ybT0ibWF0cml4KDEuMzMzMzMzMywwLDAsMS4zMzMzMzMxLDUuNjc2ODcxOSwtMTEuMjc0MzY0KSIKICAgICAgICAgZD0ibSAxMyw0NCBhIDYsNiAwIDAgMSAtNiw2IDYsNiAwIDAgMSAtNiwtNiA2LDYgMCAwIDEgNiwtNiA2LDYgMCAwIDEgNiw2IHoiCiAgICAgICAgIHNvZGlwb2RpOnJ5PSI2IgogICAgICAgICBzb2RpcG9kaTpyeD0iNiIKICAgICAgICAgc29kaXBvZGk6Y3k9IjQ0IgogICAgICAgICBzb2RpcG9kaTpjeD0iNyIKICAgICAgICAgaWQ9InBhdGgzMDM3IgogICAgICAgICBzdHlsZT0iZmlsbDp1cmwoI2xpbmVhckdyYWRpZW50Mzg4NSk7ZmlsbC1vcGFjaXR5OjE7c3Ryb2tlOiMzMDJiMDA7c3Ryb2tlLXdpZHRoOjEuNTAwMDAwMDAwMDAwMDAwMDA7c3Ryb2tlLWxpbmVjYXA6cm91bmQ7c3Ryb2tlLWxpbmVqb2luOm1pdGVyO3N0cm9rZS1taXRlcmxpbWl0OjQ7c3Ryb2tlLW9wYWNpdHk6MTtzdHJva2UtZGFzaGFycmF5Om5vbmU7c3Ryb2tlLWRhc2hvZmZzZXQ6MCIKICAgICAgICAgc29kaXBvZGk6dHlwZT0iYXJjIiAvPgogICAgICA8cGF0aAogICAgICAgICBzb2RpcG9kaTpub2RldHlwZXM9ImNjIgogICAgICAgICBpbmtzY2FwZTpjb25uZWN0b3ItY3VydmF0dXJlPSIwIgogICAgICAgICBpZD0icGF0aDM4NjQtNCIKICAgICAgICAgZD0ibSAxMy4wMDUxMDIsNDguMDIyMTA5IDEuMzI5OTMyLC02Ljc0MDM2MiIKICAgICAgICAgc3R5bGU9ImZpbGw6bm9uZTtzdHJva2U6I2ZmZmZmZjtzdHJva2Utd2lkdGg6MjtzdHJva2UtbGluZWNhcDpidXR0O3N0cm9rZS1saW5lam9pbjptaXRlcjtzdHJva2Utb3BhY2l0eToxIiAvPgogICAgICA8cGF0aAogICAgICAgICBzb2RpcG9kaTpub2RldHlwZXM9ImNjY2NjY2NjY2NjY2NjYyIKICAgICAgICAgaWQ9InBhdGgzNzcwLTEiCiAgICAgICAgIGQ9Im0gMjcuNjM0MzU1LDI1LjEwNDg3NCAyLjY1OTg2NSwyLjY5NjE0NiAtMTQuNjI5MjU0LDE0LjgyODggLTIuNjU0NzYxLDAuNzYyNDcxIGMgMCw0LjA0NDIxOSAtMC42NzAwNjgsMy45NTU3ODIgLTEuMzM1MDM1LDUuOTc3ODkyIGwgLTAuNjY0OTY1LDIuMDIyMTA4IDEuOTk0ODk3LC0wLjY3NDAzNSBDIDE1LDUwLjA0NDIxOSAxNi4wMjA0MDgsNDguMzkyMjkxIDIwLjAxMDIwNSw0OC4zOTIyOTEgbCAtMC4zNTU0NDIsLTEuNzE4MjU0IDE0LjYyOTI1MiwtMTQuODI4Nzk5IDIuNjU5ODY1LDIuNjk2MTQ2IGMgMCwtNC4wNDQyMTkgMC42NjQ5NjUsLTcuNDE0NCAxLjMyOTkzMiwtOS40MzY1MSBsIDAuNjY0OTY1LC0yLjAyMjEwOCAtMS45OTQ4OTcsMC42NzQwMzUgYyAtMS45OTQ4OTksMC42NzQwMzcgLTUuMzE5NzI4LDEuMzQ4MDczIC05LjMwOTUyNSwxLjM0ODA3MyB6IgogICAgICAgICBzdHlsZT0iZm9udC1zaXplOm1lZGl1bTtmb250LXN0eWxlOm5vcm1hbDtmb250LXZhcmlhbnQ6bm9ybWFsO2ZvbnQtd2VpZ2h0Om5vcm1hbDtmb250LXN0cmV0Y2g6bm9ybWFsO3RleHQtaW5kZW50OjA7dGV4dC1hbGlnbjpzdGFydDt0ZXh0LWRlY29yYXRpb246bm9uZTtsaW5lLWhlaWdodDpub3JtYWw7bGV0dGVyLXNwYWNpbmc6bm9ybWFsO3dvcmQtc3BhY2luZzpub3JtYWw7dGV4dC10cmFuc2Zvcm06bm9uZTtkaXJlY3Rpb246bHRyO2Jsb2NrLXByb2dyZXNzaW9uOnRiO3dyaXRpbmctbW9kZTpsci10Yjt0ZXh0LWFuY2hvcjpzdGFydDtiYXNlbGluZS1zaGlmdDpiYXNlbGluZTtjb2xvcjojMDAwMDAwO2ZpbGw6dXJsKCNsaW5lYXJHcmFkaWVudDM4ODcpO2ZpbGwtb3BhY2l0eToxO2ZpbGwtcnVsZTpub256ZXJvO3N0cm9rZTpub25lO3Zpc2liaWxpdHk6dmlzaWJsZTtkaXNwbGF5OmlubGluZTtvdmVyZmxvdzp2aXNpYmxlO2VuYWJsZS1iYWNrZ3JvdW5kOmFjY3VtdWxhdGU7Zm9udC1mYW1pbHk6c2Fucy1zZXJpZiIKICAgICAgICAgaW5rc2NhcGU6Y29ubmVjdG9yLWN1cnZhdHVyZT0iMCIgLz4KICAgICAgPHBhdGgKICAgICAgICAgc29kaXBvZGk6bm9kZXR5cGVzPSJjYyIKICAgICAgICAgaW5rc2NhcGU6Y29ubmVjdG9yLWN1cnZhdHVyZT0iMCIKICAgICAgICAgaWQ9InBhdGgzODY0IgogICAgICAgICBkPSJtIDM1LjYxMzk0NywyNS4xMDQ4NzQgLTUuNjAzNzQyLDEuMjg3NDE3IgogICAgICAgICBzdHlsZT0iZmlsbDpub25lO3N0cm9rZTojZmNlOTRmO3N0cm9rZS13aWR0aDoyO3N0cm9rZS1saW5lY2FwOmJ1dHQ7c3Ryb2tlLWxpbmVqb2luOm1pdGVyO3N0cm9rZS1vcGFjaXR5OjEiIC8+CiAgICAgIDxwYXRoCiAgICAgICAgIHNvZGlwb2RpOm5vZGV0eXBlcz0iY2MiCiAgICAgICAgIGlua3NjYXBlOmNvbm5lY3Rvci1jdXJ2YXR1cmU9IjAiCiAgICAgICAgIGlkPSJwYXRoMzg2NiIKICAgICAgICAgZD0iTSAzNi45NDM4OCwyMy43NTY4MDEgMTEuMDI5OTAxLDQ5Ljk3MjQzNCIKICAgICAgICAgc3R5bGU9ImZpbGw6bm9uZTtzdHJva2U6I2ZjZTk0ZjtzdHJva2Utd2lkdGg6MjtzdHJva2UtbGluZWNhcDpyb3VuZDtzdHJva2UtbGluZWpvaW46bWl0ZXI7c3Ryb2tlLW9wYWNpdHk6MSIgLz4KICAgICAgPHBhdGgKICAgICAgICAgaW5rc2NhcGU6Y29ubmVjdG9yLWN1cnZhdHVyZT0iMCIKICAgICAgICAgaWQ9InBhdGgzODY4IgogICAgICAgICBkPSJtIDMxLjAxMDIwNSwyNy4zOTIyOTEgMi42MDg4NDQsLTAuMjY1MzA3IgogICAgICAgICBzdHlsZT0iZmlsbDpub25lO3N0cm9rZTojZmNlOTRmO3N0cm9rZS13aWR0aDoyO3N0cm9rZS1saW5lY2FwOmJ1dHQ7c3Ryb2tlLWxpbmVqb2luOm1pdGVyO3N0cm9rZS1vcGFjaXR5OjEiCiAgICAgICAgIHNvZGlwb2RpOm5vZGV0eXBlcz0iY2MiIC8+CiAgICAgIDxwYXRoCiAgICAgICAgIGlua3NjYXBlOmNvbm5lY3Rvci1jdXJ2YXR1cmU9IjAiCiAgICAgICAgIGlkPSJwYXRoMzg2OC04IgogICAgICAgICBkPSJNIDE1LjY2NDk2Niw0Mi42Mjk4MiAxNSw0NiIKICAgICAgICAgc3R5bGU9ImZpbGw6bm9uZTtzdHJva2U6I2ZmZmZmZjtzdHJva2Utd2lkdGg6MjtzdHJva2UtbGluZWNhcDpidXR0O3N0cm9rZS1saW5lam9pbjptaXRlcjtzdHJva2Utb3BhY2l0eToxIiAvPgogICAgICA8cGF0aAogICAgICAgICBzb2RpcG9kaTpub2RldHlwZXM9ImNjY2NjY2NjY2NjY2NjYyIKICAgICAgICAgaWQ9InBhdGgzNzcwLTkiCiAgICAgICAgIGQ9Im0gMjcuODY3MzQ5LDI0LjUzNTE0NyAyLjg1NzE0NCwyLjg1NzE0NCAtMTUuNzE0Mjg5LDE1LjcxNDI4NyAxMGUtNywwLjI4NTcxMyBjIDAsNC4yODU3MTYgLTMuNTcxNDI4LDQuNzE0Mjg2IC00LjI4NTcxNSw2Ljg1NzE0NCBsIDIuMjg1NzE1LDAuMTQyODU2IC0wLjg1NzE0MywxLjI4NTcxNiBjIDIuMTQyODU3LC0wLjcxNDI4NyAxLjU3MTQyNywtNC4yODU3MTYgNS44NTcxNDMsLTQuMjg1NzE2IGwgMS4yODU3MTUsMCAxNS43MTQyODYsLTE1LjcxNDI4NiAyLjg1NzE0NCwyLjg1NzE0NCBjIDAsLTQuMjg1NzE2IDAuNzE0Mjg1LC03Ljg1NzE0NCAxLjQyODU3MSwtMTAuMDAwMDAyIGwgMC43MTQyODUsLTIuMTQyODU2IC0yLjE0Mjg1NiwwLjcxNDI4NCBjIC0yLjE0Mjg1OCwwLjcxNDI4NyAtNS43MTQyODYsMS40Mjg1NzIgLTEwLjAwMDAwMSwxLjQyODU3MiB6IgogICAgICAgICBzdHlsZT0iZm9udC1zaXplOm1lZGl1bTtmb250LXN0eWxlOm5vcm1hbDtmb250LXZhcmlhbnQ6bm9ybWFsO2ZvbnQtd2VpZ2h0Om5vcm1hbDtmb250LXN0cmV0Y2g6bm9ybWFsO3RleHQtaW5kZW50OjA7dGV4dC1hbGlnbjpzdGFydDt0ZXh0LWRlY29yYXRpb246bm9uZTtsaW5lLWhlaWdodDpub3JtYWw7bGV0dGVyLXNwYWNpbmc6bm9ybWFsO3dvcmQtc3BhY2luZzpub3JtYWw7dGV4dC10cmFuc2Zvcm06bm9uZTtkaXJlY3Rpb246bHRyO2Jsb2NrLXByb2dyZXNzaW9uOnRiO3dyaXRpbmctbW9kZTpsci10Yjt0ZXh0LWFuY2hvcjpzdGFydDtiYXNlbGluZS1zaGlmdDpiYXNlbGluZTtjb2xvcjojMDAwMDAwO2ZpbGw6bm9uZTtzdHJva2U6IzMwMmIwMDtzdHJva2Utd2lkdGg6MjtzdHJva2UtbGluZWNhcDpidXR0O3N0cm9rZS1saW5lam9pbjpyb3VuZDtzdHJva2UtbWl0ZXJsaW1pdDo0O3N0cm9rZS1vcGFjaXR5OjE7c3Ryb2tlLWRhc2hhcnJheTpub25lO3N0cm9rZS1kYXNob2Zmc2V0OjA7dmlzaWJpbGl0eTp2aXNpYmxlO2Rpc3BsYXk6aW5saW5lO292ZXJmbG93OnZpc2libGU7ZW5hYmxlLWJhY2tncm91bmQ6YWNjdW11bGF0ZTtmb250LWZhbWlseTpzYW5zLXNlcmlmIgogICAgICAgICBpbmtzY2FwZTpjb25uZWN0b3ItY3VydmF0dXJlPSIwIiAvPgogICAgICA8cGF0aAogICAgICAgICB0cmFuc2Zvcm09InRyYW5zbGF0ZSg4LjAxMDIwNSwzLjM5MjI5MSkiCiAgICAgICAgIGQ9Im0gMTMsNDQgYSA2LDYgMCAwIDEgLTYsNiA2LDYgMCAwIDEgLTYsLTYgNiw2IDAgMCAxIDYsLTYgNiw2IDAgMCAxIDYsNiB6IgogICAgICAgICBzb2RpcG9kaTpyeT0iNiIKICAgICAgICAgc29kaXBvZGk6cng9IjYiCiAgICAgICAgIHNvZGlwb2RpOmN5PSI0NCIKICAgICAgICAgc29kaXBvZGk6Y3g9IjciCiAgICAgICAgIGlkPSJwYXRoMzAzNy04IgogICAgICAgICBzdHlsZT0iZmlsbDp1cmwoI2xpbmVhckdyYWRpZW50Mzg4OSk7ZmlsbC1vcGFjaXR5OjE7c3Ryb2tlOiNmY2U5NGY7c3Ryb2tlLXdpZHRoOjEuOTk5OTk5NjQwMDAwMDAwMDA7c3Ryb2tlLWxpbmVjYXA6cm91bmQ7c3Ryb2tlLWxpbmVqb2luOm1pdGVyO3N0cm9rZS1taXRlcmxpbWl0OjQ7c3Ryb2tlLW9wYWNpdHk6MTtzdHJva2UtZGFzaGFycmF5Om5vbmU7c3Ryb2tlLWRhc2hvZmZzZXQ6MCIKICAgICAgICAgc29kaXBvZGk6dHlwZT0iYXJjIiAvPgogICAgPC9nPgogIDwvZz4KPC9zdmc+Cg==
"""
Dim_Length_b64=\
"""
PD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0iVVRGLTgiIHN0YW5kYWxvbmU9Im5vIj8+CjwhLS0gQ3JlYXRlZCB3aXRoIElua3NjYXBlIChodHRwOi8vd3d3Lmlua3NjYXBlLm9yZy8pIC0tPgoKPHN2ZwogICB4bWxuczpkYz0iaHR0cDovL3B1cmwub3JnL2RjL2VsZW1lbnRzLzEuMS8iCiAgIHhtbG5zOmNjPSJodHRwOi8vY3JlYXRpdmVjb21tb25zLm9yZy9ucyMiCiAgIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyIKICAgeG1sbnM6c3ZnPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyIKICAgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIgogICB4bWxuczp4bGluaz0iaHR0cDovL3d3dy53My5vcmcvMTk5OS94bGluayIKICAgeG1sbnM6c29kaXBvZGk9Imh0dHA6Ly9zb2RpcG9kaS5zb3VyY2Vmb3JnZS5uZXQvRFREL3NvZGlwb2RpLTAuZHRkIgogICB4bWxuczppbmtzY2FwZT0iaHR0cDovL3d3dy5pbmtzY2FwZS5vcmcvbmFtZXNwYWNlcy9pbmtzY2FwZSIKICAgd2lkdGg9IjY0cHgiCiAgIGhlaWdodD0iNjRweCIKICAgaWQ9InN2ZzU4MjEiCiAgIHNvZGlwb2RpOnZlcnNpb249IjAuMzIiCiAgIGlua3NjYXBlOnZlcnNpb249IjAuOTIuMCByMTUyOTkiCiAgIHNvZGlwb2RpOmRvY25hbWU9IkRpbWVuc2lvbl9MZW5ndGguc3ZnIgogICBpbmtzY2FwZTpvdXRwdXRfZXh0ZW5zaW9uPSJvcmcuaW5rc2NhcGUub3V0cHV0LnN2Zy5pbmtzY2FwZSIKICAgdmVyc2lvbj0iMS4xIgogICBpbmtzY2FwZTpleHBvcnQtZmlsZW5hbWU9Ii9ob21lL3VzZXIvRG93bmxvYWRzL2NhZC9teXN0dWZmL2ljb25zL0RyYXdpbmcvVGVjaERyYXdfRGltZW5zaW9uX0xlbmd0aF8yXzMycHgucG5nIgogICBpbmtzY2FwZTpleHBvcnQteGRwaT0iNDUiCiAgIGlua3NjYXBlOmV4cG9ydC15ZHBpPSI0NSI+CiAgPGRlZnMKICAgICBpZD0iZGVmczU4MjMiPgogICAgPGxpbmVhckdyYWRpZW50CiAgICAgICBpZD0ibGluZWFyR3JhZGllbnQzMDI2IgogICAgICAgaW5rc2NhcGU6Y29sbGVjdD0iYWx3YXlzIj4KICAgICAgPHN0b3AKICAgICAgICAgaWQ9InN0b3AzMDI4IgogICAgICAgICBvZmZzZXQ9IjAiCiAgICAgICAgIHN0eWxlPSJzdG9wLWNvbG9yOiNjNGEwMDA7c3RvcC1vcGFjaXR5OjEiIC8+CiAgICAgIDxzdG9wCiAgICAgICAgIGlkPSJzdG9wMzAzMCIKICAgICAgICAgb2Zmc2V0PSIxIgogICAgICAgICBzdHlsZT0ic3RvcC1jb2xvcjojZmNlOTRmO3N0b3Atb3BhY2l0eToxIiAvPgogICAgPC9saW5lYXJHcmFkaWVudD4KICAgIDxsaW5lYXJHcmFkaWVudAogICAgICAgaWQ9ImxpbmVhckdyYWRpZW50MzAyMCIKICAgICAgIGlua3NjYXBlOmNvbGxlY3Q9ImFsd2F5cyI+CiAgICAgIDxzdG9wCiAgICAgICAgIGlkPSJzdG9wMzAyMiIKICAgICAgICAgb2Zmc2V0PSIwIgogICAgICAgICBzdHlsZT0ic3RvcC1jb2xvcjojYzRhMDAwO3N0b3Atb3BhY2l0eToxIiAvPgogICAgICA8c3RvcAogICAgICAgICBpZD0ic3RvcDMwMjQiCiAgICAgICAgIG9mZnNldD0iMSIKICAgICAgICAgc3R5bGU9InN0b3AtY29sb3I6I2ZjZTk0ZjtzdG9wLW9wYWNpdHk6MSIgLz4KICAgIDwvbGluZWFyR3JhZGllbnQ+CiAgICA8bGluZWFyR3JhZGllbnQKICAgICAgIGlkPSJsaW5lYXJHcmFkaWVudDMwMTQiCiAgICAgICBpbmtzY2FwZTpjb2xsZWN0PSJhbHdheXMiPgogICAgICA8c3RvcAogICAgICAgICBpZD0ic3RvcDMwMTYiCiAgICAgICAgIG9mZnNldD0iMCIKICAgICAgICAgc3R5bGU9InN0b3AtY29sb3I6I2M0YTAwMDtzdG9wLW9wYWNpdHk6MSIgLz4KICAgICAgPHN0b3AKICAgICAgICAgaWQ9InN0b3AzMDE4IgogICAgICAgICBvZmZzZXQ9IjEiCiAgICAgICAgIHN0eWxlPSJzdG9wLWNvbG9yOiNmY2U5NGY7c3RvcC1vcGFjaXR5OjEiIC8+CiAgICA8L2xpbmVhckdyYWRpZW50PgogICAgPGxpbmVhckdyYWRpZW50CiAgICAgICBpbmtzY2FwZTpjb2xsZWN0PSJhbHdheXMiCiAgICAgICBpZD0ibGluZWFyR3JhZGllbnQ2MzQ5Ij4KICAgICAgPHN0b3AKICAgICAgICAgc3R5bGU9InN0b3AtY29sb3I6IzAwMDAwMDtzdG9wLW9wYWNpdHk6MTsiCiAgICAgICAgIG9mZnNldD0iMCIKICAgICAgICAgaWQ9InN0b3A2MzUxIiAvPgogICAgICA8c3RvcAogICAgICAgICBzdHlsZT0ic3RvcC1jb2xvcjojMDAwMDAwO3N0b3Atb3BhY2l0eTowOyIKICAgICAgICAgb2Zmc2V0PSIxIgogICAgICAgICBpZD0ic3RvcDYzNTMiIC8+CiAgICA8L2xpbmVhckdyYWRpZW50PgogICAgPGxpbmVhckdyYWRpZW50CiAgICAgICBpZD0ibGluZWFyR3JhZGllbnQzMzc3Ij4KICAgICAgPHN0b3AKICAgICAgICAgc3R5bGU9InN0b3AtY29sb3I6IzAwMTlhMztzdG9wLW9wYWNpdHk6MTsiCiAgICAgICAgIG9mZnNldD0iMCIKICAgICAgICAgaWQ9InN0b3AzMzc5IiAvPgogICAgICA8c3RvcAogICAgICAgICBzdHlsZT0ic3RvcC1jb2xvcjojMDA2OWZmO3N0b3Atb3BhY2l0eToxOyIKICAgICAgICAgb2Zmc2V0PSIxIgogICAgICAgICBpZD0ic3RvcDMzODEiIC8+CiAgICA8L2xpbmVhckdyYWRpZW50PgogICAgPGxpbmVhckdyYWRpZW50CiAgICAgICBpbmtzY2FwZTpjb2xsZWN0PSJhbHdheXMiCiAgICAgICB4bGluazpocmVmPSIjbGluZWFyR3JhZGllbnQzMzc3IgogICAgICAgaWQ9ImxpbmVhckdyYWRpZW50MzM4MyIKICAgICAgIHgxPSI5MDEuMTg3NSIKICAgICAgIHkxPSIxMTkwLjg3NSIKICAgICAgIHgyPSIxMjY3LjkwNjIiCiAgICAgICB5Mj0iMTE5MC44NzUiCiAgICAgICBncmFkaWVudFVuaXRzPSJ1c2VyU3BhY2VPblVzZSIKICAgICAgIGdyYWRpZW50VHJhbnNmb3JtPSJtYXRyaXgoLTEsMCwwLDEsMjE5OS4zNTYsMCkiIC8+CiAgICA8aW5rc2NhcGU6cGVyc3BlY3RpdmUKICAgICAgIHNvZGlwb2RpOnR5cGU9Imlua3NjYXBlOnBlcnNwM2QiCiAgICAgICBpbmtzY2FwZTp2cF94PSIwIDogMzIgOiAxIgogICAgICAgaW5rc2NhcGU6dnBfeT0iMCA6IDEwMDAgOiAwIgogICAgICAgaW5rc2NhcGU6dnBfej0iNjQgOiAzMiA6IDEiCiAgICAgICBpbmtzY2FwZTpwZXJzcDNkLW9yaWdpbj0iMzIgOiAyMS4zMzMzMzMgOiAxIgogICAgICAgaWQ9InBlcnNwZWN0aXZlNTgyOSIgLz4KICAgIDxyYWRpYWxHcmFkaWVudAogICAgICAgaW5rc2NhcGU6Y29sbGVjdD0iYWx3YXlzIgogICAgICAgeGxpbms6aHJlZj0iI2xpbmVhckdyYWRpZW50NjM0OSIKICAgICAgIGlkPSJyYWRpYWxHcmFkaWVudDYzNTUiCiAgICAgICBjeD0iMTEwMy42Mzk5IgogICAgICAgY3k9IjE0MjQuNDQ2NSIKICAgICAgIGZ4PSIxMTAzLjYzOTkiCiAgICAgICBmeT0iMTQyNC40NDY1IgogICAgICAgcj0iMTk0LjQwNjE0IgogICAgICAgZ3JhZGllbnRUcmFuc2Zvcm09Im1hdHJpeCgtMS40MzA3NDk5LC0xLjM2MDUxNTZlLTcsLTEuMjAyNzEzZS04LDAuMTI2NDgwMSwyNjc0Ljc0ODgsMTI0NC4yODI2KSIKICAgICAgIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZU9uVXNlIiAvPgogICAgPGxpbmVhckdyYWRpZW50CiAgICAgICBpbmtzY2FwZTpjb2xsZWN0PSJhbHdheXMiCiAgICAgICB4bGluazpocmVmPSIjbGluZWFyR3JhZGllbnQzODkzIgogICAgICAgaWQ9ImxpbmVhckdyYWRpZW50Mzg5OSIKICAgICAgIHgxPSIzNSIKICAgICAgIHkxPSI1MCIKICAgICAgIHgyPSIzMSIKICAgICAgIHkyPSIxNiIKICAgICAgIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZU9uVXNlIiAvPgogICAgPGxpbmVhckdyYWRpZW50CiAgICAgICBpbmtzY2FwZTpjb2xsZWN0PSJhbHdheXMiCiAgICAgICBpZD0ibGluZWFyR3JhZGllbnQzODkzIj4KICAgICAgPHN0b3AKICAgICAgICAgc3R5bGU9InN0b3AtY29sb3I6I2QzZDdjZjtzdG9wLW9wYWNpdHk6MSIKICAgICAgICAgb2Zmc2V0PSIwIgogICAgICAgICBpZD0ic3RvcDM4OTUiIC8+CiAgICAgIDxzdG9wCiAgICAgICAgIHN0eWxlPSJzdG9wLWNvbG9yOiNmZmZmZmY7c3RvcC1vcGFjaXR5OjEiCiAgICAgICAgIG9mZnNldD0iMSIKICAgICAgICAgaWQ9InN0b3AzODk3IiAvPgogICAgPC9saW5lYXJHcmFkaWVudD4KICAgIDxsaW5lYXJHcmFkaWVudAogICAgICAgZ3JhZGllbnRUcmFuc2Zvcm09Im1hdHJpeCgwLjcwNzEwNjc4LDAuNzA3MTA2NzgsLTAuNzA3MTA2NzgsMC43MDcxMDY3OCwzNC43NTczNTksLTkuOTcwNTYzKSIKICAgICAgIGlua3NjYXBlOmNvbGxlY3Q9ImFsd2F5cyIKICAgICAgIHhsaW5rOmhyZWY9IiNsaW5lYXJHcmFkaWVudDMwMTQiCiAgICAgICBpZD0ibGluZWFyR3JhZGllbnQzOTA3IgogICAgICAgeDE9IjM5Ljk0OTc0OSIKICAgICAgIHkxPSIxMC4zOTMzOTgiCiAgICAgICB4Mj0iMjEuNTY0OTcyIgogICAgICAgeTI9IjQuNzM2NTQ0MSIKICAgICAgIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZU9uVXNlIiAvPgogICAgPGxpbmVhckdyYWRpZW50CiAgICAgICBncmFkaWVudFRyYW5zZm9ybT0ibWF0cml4KDAuNjY0OTY2MDQsMC42NzQwMzYzMiwtMC42NjQ5NjYwNCwwLjY3NDAzNjMyLDMxLjk2NDI4NSwtMTEuMjkzMDg3KSIKICAgICAgIHkyPSIyOC4zOTkxODUiCiAgICAgICB4Mj0iMjUuNDQ1MjIzIgogICAgICAgeTE9IjQwLjIyNzUwOSIKICAgICAgIHgxPSI0My4yODg4OTEiCiAgICAgICBncmFkaWVudFVuaXRzPSJ1c2VyU3BhY2VPblVzZSIKICAgICAgIGlkPSJsaW5lYXJHcmFkaWVudDQwNzUiCiAgICAgICB4bGluazpocmVmPSIjbGluZWFyR3JhZGllbnQzMDIwIgogICAgICAgaW5rc2NhcGU6Y29sbGVjdD0iYWx3YXlzIiAvPgogICAgPGxpbmVhckdyYWRpZW50CiAgICAgICBncmFkaWVudFRyYW5zZm9ybT0ibWF0cml4KDAuNzA3MTA2NzgsMC43MDcxMDY3OCwtMC43MDcxMDY3OCwwLjcwNzEwNjc4LDM0LjcwNDEyNywtOS45NDI2Nzk2KSIKICAgICAgIGlua3NjYXBlOmNvbGxlY3Q9ImFsd2F5cyIKICAgICAgIHhsaW5rOmhyZWY9IiNsaW5lYXJHcmFkaWVudDM4OTMtNCIKICAgICAgIGlkPSJsaW5lYXJHcmFkaWVudDM5MDctNyIKICAgICAgIHgxPSIzOS45NDk3NDkiCiAgICAgICB5MT0iMTAuMzkzMzk4IgogICAgICAgeDI9IjIxLjU2NDk3MiIKICAgICAgIHkyPSI0LjczNjU0NDEiCiAgICAgICBncmFkaWVudFVuaXRzPSJ1c2VyU3BhY2VPblVzZSIgLz4KICAgIDxsaW5lYXJHcmFkaWVudAogICAgICAgaW5rc2NhcGU6Y29sbGVjdD0iYWx3YXlzIgogICAgICAgaWQ9ImxpbmVhckdyYWRpZW50Mzg5My00Ij4KICAgICAgPHN0b3AKICAgICAgICAgc3R5bGU9InN0b3AtY29sb3I6I2QzZDdjZjtzdG9wLW9wYWNpdHk6MSIKICAgICAgICAgb2Zmc2V0PSIwIgogICAgICAgICBpZD0ic3RvcDM4OTUtMCIgLz4KICAgICAgPHN0b3AKICAgICAgICAgc3R5bGU9InN0b3AtY29sb3I6I2ZmZmZmZjtzdG9wLW9wYWNpdHk6MSIKICAgICAgICAgb2Zmc2V0PSIxIgogICAgICAgICBpZD0ic3RvcDM4OTctOSIgLz4KICAgIDwvbGluZWFyR3JhZGllbnQ+CiAgICA8bGluZWFyR3JhZGllbnQKICAgICAgIHkyPSI0LjczNjU0NDEiCiAgICAgICB4Mj0iMjEuNTY0OTcyIgogICAgICAgeTE9IjEwLjM5MzM5OCIKICAgICAgIHgxPSIzOS45NDk3NDkiCiAgICAgICBncmFkaWVudFRyYW5zZm9ybT0ibWF0cml4KDAuNzA3MTA2NzgsMC43MDcxMDY3OCwtMC43MDcxMDY3OCwwLjcwNzEwNjc4LC0xLjI0MjY0MSwyNi4wMjk0MzcpIgogICAgICAgZ3JhZGllbnRVbml0cz0idXNlclNwYWNlT25Vc2UiCiAgICAgICBpZD0ibGluZWFyR3JhZGllbnQzMDY1IgogICAgICAgeGxpbms6aHJlZj0iI2xpbmVhckdyYWRpZW50MzAyNiIKICAgICAgIGlua3NjYXBlOmNvbGxlY3Q9ImFsd2F5cyIgLz4KICA8L2RlZnM+CiAgPHNvZGlwb2RpOm5hbWVkdmlldwogICAgIGlkPSJiYXNlIgogICAgIHBhZ2Vjb2xvcj0iI2ZmZmZmZiIKICAgICBib3JkZXJjb2xvcj0iIzY2NjY2NiIKICAgICBib3JkZXJvcGFjaXR5PSIxLjAiCiAgICAgaW5rc2NhcGU6cGFnZW9wYWNpdHk9IjAuMCIKICAgICBpbmtzY2FwZTpwYWdlc2hhZG93PSIyIgogICAgIGlua3NjYXBlOnpvb209IjkuNjg3NSIKICAgICBpbmtzY2FwZTpjeD0iMzIiCiAgICAgaW5rc2NhcGU6Y3k9IjMyIgogICAgIGlua3NjYXBlOmN1cnJlbnQtbGF5ZXI9ImxheWVyMSIKICAgICBzaG93Z3JpZD0idHJ1ZSIKICAgICBpbmtzY2FwZTpkb2N1bWVudC11bml0cz0icHgiCiAgICAgaW5rc2NhcGU6Z3JpZC1iYm94PSJ0cnVlIgogICAgIGlua3NjYXBlOndpbmRvdy13aWR0aD0iMTUzNiIKICAgICBpbmtzY2FwZTp3aW5kb3ctaGVpZ2h0PSI4MDEiCiAgICAgaW5rc2NhcGU6d2luZG93LXg9Ii04IgogICAgIGlua3NjYXBlOndpbmRvdy15PSItOCIKICAgICBpbmtzY2FwZTp3aW5kb3ctbWF4aW1pemVkPSIxIgogICAgIHNob3dndWlkZXM9InRydWUiCiAgICAgaW5rc2NhcGU6Z3VpZGUtYmJveD0idHJ1ZSIKICAgICBpbmtzY2FwZTpzbmFwLWdsb2JhbD0idHJ1ZSIKICAgICBpbmtzY2FwZTpzbmFwLWJib3g9InRydWUiCiAgICAgaW5rc2NhcGU6c25hcC1ub2Rlcz0iZmFsc2UiPgogICAgPGlua3NjYXBlOmdyaWQKICAgICAgIHR5cGU9Inh5Z3JpZCIKICAgICAgIGlkPSJncmlkMjk5NCIKICAgICAgIGVtcHNwYWNpbmc9IjIiCiAgICAgICB2aXNpYmxlPSJ0cnVlIgogICAgICAgZW5hYmxlZD0idHJ1ZSIKICAgICAgIHNuYXB2aXNpYmxlZ3JpZGxpbmVzb25seT0idHJ1ZSIgLz4KICA8L3NvZGlwb2RpOm5hbWVkdmlldz4KICA8bWV0YWRhdGEKICAgICBpZD0ibWV0YWRhdGE1ODI2Ij4KICAgIDxyZGY6UkRGPgogICAgICA8Y2M6V29yawogICAgICAgICByZGY6YWJvdXQ9IiI+CiAgICAgICAgPGRjOmZvcm1hdD5pbWFnZS9zdmcreG1sPC9kYzpmb3JtYXQ+CiAgICAgICAgPGRjOnR5cGUKICAgICAgICAgICByZGY6cmVzb3VyY2U9Imh0dHA6Ly9wdXJsLm9yZy9kYy9kY21pdHlwZS9TdGlsbEltYWdlIiAvPgogICAgICAgIDxkYzp0aXRsZSAvPgogICAgICAgIDxkYzpjcmVhdG9yPgogICAgICAgICAgPGNjOkFnZW50PgogICAgICAgICAgICA8ZGM6dGl0bGU+W1dhbmRlcmVyRmFuXTwvZGM6dGl0bGU+CiAgICAgICAgICA8L2NjOkFnZW50PgogICAgICAgIDwvZGM6Y3JlYXRvcj4KICAgICAgICA8ZGM6dGl0bGU+VGVjaERyYXdfRGltZW5zaW9uX0xlbmd0aDwvZGM6dGl0bGU+CiAgICAgICAgPGRjOmRhdGU+MjAxNi0wNC0yNzwvZGM6ZGF0ZT4KICAgICAgICA8ZGM6cmVsYXRpb24+aHR0cDovL3d3dy5mcmVlY2Fkd2ViLm9yZy93aWtpL2luZGV4LnBocD90aXRsZT1BcnR3b3JrPC9kYzpyZWxhdGlvbj4KICAgICAgICA8ZGM6cHVibGlzaGVyPgogICAgICAgICAgPGNjOkFnZW50PgogICAgICAgICAgICA8ZGM6dGl0bGU+RnJlZUNBRDwvZGM6dGl0bGU+CiAgICAgICAgICA8L2NjOkFnZW50PgogICAgICAgIDwvZGM6cHVibGlzaGVyPgogICAgICAgIDxkYzppZGVudGlmaWVyPkZyZWVDQUQvc3JjL01vZC9UZWNoRHJhdy9HdWkvUmVzb3VyY2VzL2ljb25zL1RlY2hEcmF3X0RpbWVuc2lvbl9MZW5ndGguc3ZnPC9kYzppZGVudGlmaWVyPgogICAgICAgIDxkYzpyaWdodHM+CiAgICAgICAgICA8Y2M6QWdlbnQ+CiAgICAgICAgICAgIDxkYzp0aXRsZT5GcmVlQ0FEIExHUEwyKzwvZGM6dGl0bGU+CiAgICAgICAgICA8L2NjOkFnZW50PgogICAgICAgIDwvZGM6cmlnaHRzPgogICAgICAgIDxjYzpsaWNlbnNlCiAgICAgICAgICAgcmRmOnJlc291cmNlPSJodHRwczovL3d3dy5nbnUub3JnL2xpY2Vuc2VzL2xncGwtMy4wLmVuLmh0bWwiPmh0dHBzOi8vd3d3LmdudS5vcmcvY29weWxlZnQvbGVzc2VyLmh0bWw8L2NjOmxpY2Vuc2U+CiAgICAgICAgPGRjOmNvbnRyaWJ1dG9yPgogICAgICAgICAgPGNjOkFnZW50PgogICAgICAgICAgICA8ZGM6dGl0bGU+W2Fncnlzb25dIEFsZXhhbmRlciBHcnlzb248L2RjOnRpdGxlPgogICAgICAgICAgPC9jYzpBZ2VudD4KICAgICAgICA8L2RjOmNvbnRyaWJ1dG9yPgogICAgICAgIDxkYzpzdWJqZWN0PgogICAgICAgICAgPHJkZjpCYWc+CiAgICAgICAgICAgIDxyZGY6bGk+ZG91YmxlIGFycm93PC9yZGY6bGk+CiAgICAgICAgICAgIDxyZGY6bGk+ZGlhZ29uYWw8L3JkZjpsaT4KICAgICAgICAgICAgPHJkZjpsaT5hcnJvdzwvcmRmOmxpPgogICAgICAgICAgPC9yZGY6QmFnPgogICAgICAgIDwvZGM6c3ViamVjdD4KICAgICAgICA8ZGM6ZGVzY3JpcHRpb24+RG91YmxlIGFycm93IGF0IGFuZ2xlIGJldHdlZW4gdHdvIGRpYWdvbmFsIGJhcnM8L2RjOmRlc2NyaXB0aW9uPgogICAgICA8L2NjOldvcms+CiAgICA8L3JkZjpSREY+CiAgPC9tZXRhZGF0YT4KICA8ZwogICAgIGlkPSJsYXllcjEiCiAgICAgaW5rc2NhcGU6bGFiZWw9IkxheWVyIDEiCiAgICAgaW5rc2NhcGU6Z3JvdXBtb2RlPSJsYXllciI+CiAgICA8cGF0aAogICAgICAgaW5rc2NhcGU6Y29ubmVjdG9yLWN1cnZhdHVyZT0iMCIKICAgICAgIHN0eWxlPSJmb250LXNpemU6bWVkaXVtO2ZvbnQtc3R5bGU6bm9ybWFsO2ZvbnQtdmFyaWFudDpub3JtYWw7Zm9udC13ZWlnaHQ6bm9ybWFsO2ZvbnQtc3RyZXRjaDpub3JtYWw7dGV4dC1pbmRlbnQ6MDt0ZXh0LWFsaWduOnN0YXJ0O3RleHQtZGVjb3JhdGlvbjpub25lO2xpbmUtaGVpZ2h0Om5vcm1hbDtsZXR0ZXItc3BhY2luZzpub3JtYWw7d29yZC1zcGFjaW5nOm5vcm1hbDt0ZXh0LXRyYW5zZm9ybTpub25lO2RpcmVjdGlvbjpsdHI7YmxvY2stcHJvZ3Jlc3Npb246dGI7d3JpdGluZy1tb2RlOmxyLXRiO3RleHQtYW5jaG9yOnN0YXJ0O2Jhc2VsaW5lLXNoaWZ0OmJhc2VsaW5lO2NvbG9yOiMwMDAwMDA7ZmlsbDp1cmwoI2xpbmVhckdyYWRpZW50NDA3NSk7ZmlsbC1vcGFjaXR5OjE7ZmlsbC1ydWxlOm5vbnplcm87c3Ryb2tlOm5vbmU7c3Ryb2tlLXdpZHRoOjI7c3Ryb2tlLWxpbmVjYXA6YnV0dDtzdHJva2UtbGluZWpvaW46cm91bmQ7c3Ryb2tlLW1pdGVybGltaXQ6NDtzdHJva2Utb3BhY2l0eToxO3N0cm9rZS1kYXNoYXJyYXk6bm9uZTtzdHJva2UtZGFzaG9mZnNldDowO3Zpc2liaWxpdHk6dmlzaWJsZTtkaXNwbGF5OmlubGluZTtvdmVyZmxvdzp2aXNpYmxlO2VuYWJsZS1iYWNrZ3JvdW5kOmFjY3VtdWxhdGU7Zm9udC1mYW1pbHk6c2Fucy1zZXJpZiIKICAgICAgIGQ9Im0gMzQuNjI0MTUsMTkuNzEyNTgzIDIuNjU5ODY1LDIuNjk2MTQ2IC0xNC42MjkyNTQsMTQuODI4OCAtMi42NTk4NjQsLTIuNjk2MTQ3IGMgMCw0LjA0NDIxOSAtMC42NjQ5NjUsNy40MTQ0IC0xLjMyOTkzMiw5LjQzNjUxIEwgMTgsNDYgMTkuOTk0ODk3LDQ1LjMyNTk2NSBjIDEuOTk0ODk4LC0wLjY3NDAzNyA1LjMxOTcyOCwtMS4zNDgwNzMgOS4zMDk1MjUsLTEuMzQ4MDczIGwgLTIuNjU5ODY0LC0yLjY5NjE0NiAxNC42MjkyNTIsLTE0LjgyODc5OSAyLjY1OTg2NSwyLjY5NjE0NiBjIDAsLTQuMDQ0MjE5IDAuNjY0OTY1LC03LjQxNDQgMS4zMjk5MzIsLTkuNDM2NTEgbCAwLjY2NDk2NSwtMi4wMjIxMDggLTEuOTk0ODk3LDAuNjc0MDM1IGMgLTEuOTk0ODk5LDAuNjc0MDM3IC01LjMxOTcyOCwxLjM0ODA3MyAtOS4zMDk1MjUsMS4zNDgwNzMgeiIKICAgICAgIGlkPSJwYXRoMzc3MC0xIgogICAgICAgc29kaXBvZGk6bm9kZXR5cGVzPSJjY2NjY2NjY2NjY2NjY2MiCiAgICAgICBpbmtzY2FwZTpleHBvcnQteGRwaT0iNTEuMjAwMDY5IgogICAgICAgaW5rc2NhcGU6ZXhwb3J0LXlkcGk9IjUxLjIwMDA2OSIgLz4KICAgIDxwYXRoCiAgICAgICBzdHlsZT0iZm9udC1zaXplOm1lZGl1bTtmb250LXN0eWxlOm5vcm1hbDtmb250LXZhcmlhbnQ6bm9ybWFsO2ZvbnQtd2VpZ2h0Om5vcm1hbDtmb250LXN0cmV0Y2g6bm9ybWFsO3RleHQtaW5kZW50OjA7dGV4dC1hbGlnbjpzdGFydDt0ZXh0LWRlY29yYXRpb246bm9uZTtsaW5lLWhlaWdodDpub3JtYWw7bGV0dGVyLXNwYWNpbmc6bm9ybWFsO3dvcmQtc3BhY2luZzpub3JtYWw7dGV4dC10cmFuc2Zvcm06bm9uZTtkaXJlY3Rpb246bHRyO2Jsb2NrLXByb2dyZXNzaW9uOnRiO3dyaXRpbmctbW9kZTpsci10Yjt0ZXh0LWFuY2hvcjpzdGFydDtiYXNlbGluZS1zaGlmdDpiYXNlbGluZTtjb2xvcjojMDAwMDAwO2ZpbGw6dXJsKCNsaW5lYXJHcmFkaWVudDM5MDcpO2ZpbGwtb3BhY2l0eToxO2ZpbGwtcnVsZTpub256ZXJvO3N0cm9rZTojMzAyYjAwO3N0cm9rZS13aWR0aDoyO3N0cm9rZS1saW5lY2FwOmJ1dHQ7c3Ryb2tlLWxpbmVqb2luOnJvdW5kO3N0cm9rZS1taXRlcmxpbWl0OjQ7c3Ryb2tlLW9wYWNpdHk6MTtzdHJva2UtZGFzaGFycmF5Om5vbmU7c3Ryb2tlLWRhc2hvZmZzZXQ6MDt2aXNpYmlsaXR5OnZpc2libGU7ZGlzcGxheTppbmxpbmU7b3ZlcmZsb3c6dmlzaWJsZTtlbmFibGUtYmFja2dyb3VuZDphY2N1bXVsYXRlO2ZvbnQtZmFtaWx5OnNhbnMtc2VyaWYiCiAgICAgICBkPSJtIDQzLDMgLTQsNCAxOCwxOCA0LC00IHoiCiAgICAgICBpZD0icGF0aDM3ODEtMSIKICAgICAgIGlua3NjYXBlOmNvbm5lY3Rvci1jdXJ2YXR1cmU9IjAiCiAgICAgICBzb2RpcG9kaTpub2RldHlwZXM9ImNjY2NjIgogICAgICAgaW5rc2NhcGU6ZXhwb3J0LXhkcGk9IjUxLjIwMDA2OSIKICAgICAgIGlua3NjYXBlOmV4cG9ydC15ZHBpPSI1MS4yMDAwNjkiIC8+CiAgICA8cGF0aAogICAgICAgc3R5bGU9ImZpbGw6bm9uZTtzdHJva2U6I2ZjZTk0ZjtzdHJva2Utd2lkdGg6MjtzdHJva2UtbGluZWNhcDpidXR0O3N0cm9rZS1saW5lam9pbjptaXRlcjtzdHJva2Utb3BhY2l0eToxIgogICAgICAgZD0iTSA0Mi4zNDQxNDMsNS4yMDA3NTAyIDU4Ljg1NjYwNywyMS42ODQ1MzUiCiAgICAgICBpZD0icGF0aDMwMTQiCiAgICAgICBpbmtzY2FwZTpjb25uZWN0b3ItY3VydmF0dXJlPSIwIgogICAgICAgc29kaXBvZGk6bm9kZXR5cGVzPSJjYyIKICAgICAgIGlua3NjYXBlOmV4cG9ydC14ZHBpPSI1MS4yMDAwNjkiCiAgICAgICBpbmtzY2FwZTpleHBvcnQteWRwaT0iNTEuMjAwMDY5IiAvPgogICAgPHBhdGgKICAgICAgIHN0eWxlPSJmaWxsOm5vbmU7c3Ryb2tlOiNmY2U5NGY7c3Ryb2tlLXdpZHRoOjI7c3Ryb2tlLWxpbmVjYXA6YnV0dDtzdHJva2UtbGluZWpvaW46bWl0ZXI7c3Ryb2tlLW9wYWNpdHk6MSIKICAgICAgIGQ9Im0gNDIuNjAzNzQyLDE5LjcxMjU4MyAtNi42NDk2NTksMS4zNDgwNzQiCiAgICAgICBpZD0icGF0aDM4NjQiCiAgICAgICBpbmtzY2FwZTpjb25uZWN0b3ItY3VydmF0dXJlPSIwIgogICAgICAgc29kaXBvZGk6bm9kZXR5cGVzPSJjYyIKICAgICAgIGlua3NjYXBlOmV4cG9ydC14ZHBpPSI1MS4yMDAwNjkiCiAgICAgICBpbmtzY2FwZTpleHBvcnQteWRwaT0iNTEuMjAwMDY5IiAvPgogICAgPHBhdGgKICAgICAgIHN0eWxlPSJmaWxsOm5vbmU7c3Ryb2tlOiNmY2U5NGY7c3Ryb2tlLXdpZHRoOjI7c3Ryb2tlLWxpbmVjYXA6YnV0dDtzdHJva2UtbGluZWpvaW46bWl0ZXI7c3Ryb2tlLW9wYWNpdHk6MSIKICAgICAgIGQ9Im0gMTkuOTk0ODk3LDQyLjYyOTgxOCAxLjMyOTkzMiwtNi43NDAzNjIiCiAgICAgICBpZD0icGF0aDM4NjQtNCIKICAgICAgIGlua3NjYXBlOmNvbm5lY3Rvci1jdXJ2YXR1cmU9IjAiCiAgICAgICBzb2RpcG9kaTpub2RldHlwZXM9ImNjIgogICAgICAgaW5rc2NhcGU6ZXhwb3J0LXhkcGk9IjUxLjIwMDA2OSIKICAgICAgIGlua3NjYXBlOmV4cG9ydC15ZHBpPSI1MS4yMDAwNjkiIC8+CiAgICA8cGF0aAogICAgICAgc3R5bGU9ImZpbGw6bm9uZTtzdHJva2U6I2ZjZTk0ZjtzdHJva2Utd2lkdGg6MjtzdHJva2UtbGluZWNhcDpyb3VuZDtzdHJva2UtbGluZWpvaW46bWl0ZXI7c3Ryb2tlLW9wYWNpdHk6MSIKICAgICAgIGQ9Ik0gNDMuOTMzNjc1LDE4LjM2NDUxIDE4LjAxOTY5Niw0NC41ODAxNDMiCiAgICAgICBpZD0icGF0aDM4NjYiCiAgICAgICBpbmtzY2FwZTpjb25uZWN0b3ItY3VydmF0dXJlPSIwIgogICAgICAgc29kaXBvZGk6bm9kZXR5cGVzPSJjYyIKICAgICAgIGlua3NjYXBlOmV4cG9ydC14ZHBpPSI1MS4yMDAwNjkiCiAgICAgICBpbmtzY2FwZTpleHBvcnQteWRwaT0iNTEuMjAwMDY5IiAvPgogICAgPHBhdGgKICAgICAgIHN0eWxlPSJmaWxsOm5vbmU7c3Ryb2tlOiNmY2U5NGY7c3Ryb2tlLXdpZHRoOjI7c3Ryb2tlLWxpbmVjYXA6YnV0dDtzdHJva2UtbGluZWpvaW46bWl0ZXI7c3Ryb2tlLW9wYWNpdHk6MSIKICAgICAgIGQ9Im0gMzcuMjg0MDE1LDIyLjQwODcyOSAzLjMyNDgyOSwtMC42NzQwMzYiCiAgICAgICBpZD0icGF0aDM4NjgiCiAgICAgICBpbmtzY2FwZTpjb25uZWN0b3ItY3VydmF0dXJlPSIwIgogICAgICAgaW5rc2NhcGU6ZXhwb3J0LXhkcGk9IjUxLjIwMDA2OSIKICAgICAgIGlua3NjYXBlOmV4cG9ydC15ZHBpPSI1MS4yMDAwNjkiIC8+CiAgICA8cGF0aAogICAgICAgc3R5bGU9ImZpbGw6bm9uZTtzdHJva2U6I2ZjZTk0ZjtzdHJva2Utd2lkdGg6MjtzdHJva2UtbGluZWNhcDpidXR0O3N0cm9rZS1saW5lam9pbjptaXRlcjtzdHJva2Utb3BhY2l0eToxIgogICAgICAgZD0ibSAyMi42NTQ3NjEsMzcuMjM3NTI5IC0wLjY2NDk2NiwzLjM3MDE4IgogICAgICAgaWQ9InBhdGgzODY4LTgiCiAgICAgICBpbmtzY2FwZTpjb25uZWN0b3ItY3VydmF0dXJlPSIwIgogICAgICAgaW5rc2NhcGU6ZXhwb3J0LXhkcGk9IjUxLjIwMDA2OSIKICAgICAgIGlua3NjYXBlOmV4cG9ydC15ZHBpPSI1MS4yMDAwNjkiIC8+CiAgICA8cGF0aAogICAgICAgaW5rc2NhcGU6Y29ubmVjdG9yLWN1cnZhdHVyZT0iMCIKICAgICAgIHN0eWxlPSJmb250LXNpemU6bWVkaXVtO2ZvbnQtc3R5bGU6bm9ybWFsO2ZvbnQtdmFyaWFudDpub3JtYWw7Zm9udC13ZWlnaHQ6bm9ybWFsO2ZvbnQtc3RyZXRjaDpub3JtYWw7dGV4dC1pbmRlbnQ6MDt0ZXh0LWFsaWduOnN0YXJ0O3RleHQtZGVjb3JhdGlvbjpub25lO2xpbmUtaGVpZ2h0Om5vcm1hbDtsZXR0ZXItc3BhY2luZzpub3JtYWw7d29yZC1zcGFjaW5nOm5vcm1hbDt0ZXh0LXRyYW5zZm9ybTpub25lO2RpcmVjdGlvbjpsdHI7YmxvY2stcHJvZ3Jlc3Npb246dGI7d3JpdGluZy1tb2RlOmxyLXRiO3RleHQtYW5jaG9yOnN0YXJ0O2Jhc2VsaW5lLXNoaWZ0OmJhc2VsaW5lO2NvbG9yOiMwMDAwMDA7ZmlsbDpub25lO3N0cm9rZTojMzAyYjAwO3N0cm9rZS13aWR0aDoyO3N0cm9rZS1saW5lY2FwOmJ1dHQ7c3Ryb2tlLWxpbmVqb2luOnJvdW5kO3N0cm9rZS1taXRlcmxpbWl0OjQ7c3Ryb2tlLW9wYWNpdHk6MTtzdHJva2UtZGFzaGFycmF5Om5vbmU7c3Ryb2tlLWRhc2hvZmZzZXQ6MDt2aXNpYmlsaXR5OnZpc2libGU7ZGlzcGxheTppbmxpbmU7b3ZlcmZsb3c6dmlzaWJsZTtlbmFibGUtYmFja2dyb3VuZDphY2N1bXVsYXRlO2ZvbnQtZmFtaWx5OnNhbnMtc2VyaWYiCiAgICAgICBkPSJNIDM0Ljg1NzE0NCwxOS4xNDI4NTYgMzcuNzE0Mjg4LDIyIDIxLjk5OTk5OSwzNy43MTQyODcgMTkuMTQyODU3LDM0Ljg1NzE0MiBjIDAsNC4yODU3MTYgLTAuNzE0Mjg1LDcuODU3MTQ0IC0xLjQyODU3MiwxMC4wMDAwMDIgTCAxNyw0NyAxOS4xNDI4NTcsNDYuMjg1NzE2IGMgMi4xNDI4NTcsLTAuNzE0Mjg3IDUuNzE0Mjg1LC0xLjQyODU3MiAxMC4wMDAwMDEsLTEuNDI4NTcyIEwgMjYuMjg1NzE1LDQyIDQyLjAwMDAwMSwyNi4yODU3MTQgbCAyLjg1NzE0NCwyLjg1NzE0NCBjIDAsLTQuMjg1NzE2IDAuNzE0Mjg1LC03Ljg1NzE0NCAxLjQyODU3MSwtMTAuMDAwMDAyIEwgNDcuMDAwMDAxLDE3IDQ0Ljg1NzE0NSwxNy43MTQyODQgYyAtMi4xNDI4NTgsMC43MTQyODcgLTUuNzE0Mjg2LDEuNDI4NTcyIC0xMC4wMDAwMDEsMS40Mjg1NzIgeiIKICAgICAgIGlkPSJwYXRoMzc3MC05IgogICAgICAgc29kaXBvZGk6bm9kZXR5cGVzPSJjY2NjY2NjY2NjY2NjY2MiCiAgICAgICBpbmtzY2FwZTpleHBvcnQteGRwaT0iNTEuMjAwMDY5IgogICAgICAgaW5rc2NhcGU6ZXhwb3J0LXlkcGk9IjUxLjIwMDA2OSIgLz4KICAgIDxwYXRoCiAgICAgICBzdHlsZT0iZm9udC1zaXplOm1lZGl1bTtmb250LXN0eWxlOm5vcm1hbDtmb250LXZhcmlhbnQ6bm9ybWFsO2ZvbnQtd2VpZ2h0Om5vcm1hbDtmb250LXN0cmV0Y2g6bm9ybWFsO3RleHQtaW5kZW50OjA7dGV4dC1hbGlnbjpzdGFydDt0ZXh0LWRlY29yYXRpb246bm9uZTtsaW5lLWhlaWdodDpub3JtYWw7bGV0dGVyLXNwYWNpbmc6bm9ybWFsO3dvcmQtc3BhY2luZzpub3JtYWw7dGV4dC10cmFuc2Zvcm06bm9uZTtkaXJlY3Rpb246bHRyO2Jsb2NrLXByb2dyZXNzaW9uOnRiO3dyaXRpbmctbW9kZTpsci10Yjt0ZXh0LWFuY2hvcjpzdGFydDtiYXNlbGluZS1zaGlmdDpiYXNlbGluZTtjb2xvcjojMDAwMDAwO2ZpbGw6dXJsKCNsaW5lYXJHcmFkaWVudDMwNjUpO2ZpbGwtb3BhY2l0eToxO2ZpbGwtcnVsZTpub256ZXJvO3N0cm9rZTojMzAyYjAwO3N0cm9rZS13aWR0aDoyO3N0cm9rZS1saW5lY2FwOmJ1dHQ7c3Ryb2tlLWxpbmVqb2luOnJvdW5kO3N0cm9rZS1taXRlcmxpbWl0OjQ7c3Ryb2tlLW9wYWNpdHk6MTtzdHJva2UtZGFzaGFycmF5Om5vbmU7c3Ryb2tlLWRhc2hvZmZzZXQ6MDt2aXNpYmlsaXR5OnZpc2libGU7ZGlzcGxheTppbmxpbmU7b3ZlcmZsb3c6dmlzaWJsZTtlbmFibGUtYmFja2dyb3VuZDphY2N1bXVsYXRlO2ZvbnQtZmFtaWx5OnNhbnMtc2VyaWYiCiAgICAgICBkPSJtIDcsMzkgLTQsNCAxOCwxOCA0LC00IHoiCiAgICAgICBpZD0icGF0aDM3ODEtMS00IgogICAgICAgaW5rc2NhcGU6Y29ubmVjdG9yLWN1cnZhdHVyZT0iMCIKICAgICAgIHNvZGlwb2RpOm5vZGV0eXBlcz0iY2NjY2MiCiAgICAgICBpbmtzY2FwZTpleHBvcnQteGRwaT0iNTEuMjAwMDY5IgogICAgICAgaW5rc2NhcGU6ZXhwb3J0LXlkcGk9IjUxLjIwMDA2OSIgLz4KICAgIDxwYXRoCiAgICAgICBzdHlsZT0iZmlsbDpub25lO3N0cm9rZTojZmNlOTRmO3N0cm9rZS13aWR0aDoyO3N0cm9rZS1saW5lY2FwOmJ1dHQ7c3Ryb2tlLWxpbmVqb2luOm1pdGVyO3N0cm9rZS1vcGFjaXR5OjEiCiAgICAgICBkPSJNIDYuMzQ0MTQzLDQxLjIwMDc1IDIyLjg1NjYwNyw1Ny42ODQ1MzUiCiAgICAgICBpZD0icGF0aDMwMTQtOCIKICAgICAgIGlua3NjYXBlOmNvbm5lY3Rvci1jdXJ2YXR1cmU9IjAiCiAgICAgICBzb2RpcG9kaTpub2RldHlwZXM9ImNjIgogICAgICAgaW5rc2NhcGU6ZXhwb3J0LXhkcGk9IjUxLjIwMDA2OSIKICAgICAgIGlua3NjYXBlOmV4cG9ydC15ZHBpPSI1MS4yMDAwNjkiIC8+CiAgPC9nPgo8L3N2Zz4K
"""
Dim_Angle_b64=\
"""
PD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0iVVRGLTgiIHN0YW5kYWxvbmU9Im5vIj8+CjwhLS0gQ3JlYXRlZCB3aXRoIElua3NjYXBlIChodHRwOi8vd3d3Lmlua3NjYXBlLm9yZy8pIC0tPgoKPHN2ZwogICB4bWxuczpkYz0iaHR0cDovL3B1cmwub3JnL2RjL2VsZW1lbnRzLzEuMS8iCiAgIHhtbG5zOmNjPSJodHRwOi8vY3JlYXRpdmVjb21tb25zLm9yZy9ucyMiCiAgIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyIKICAgeG1sbnM6c3ZnPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyIKICAgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIgogICB4bWxuczp4bGluaz0iaHR0cDovL3d3dy53My5vcmcvMTk5OS94bGluayIKICAgeG1sbnM6c29kaXBvZGk9Imh0dHA6Ly9zb2RpcG9kaS5zb3VyY2Vmb3JnZS5uZXQvRFREL3NvZGlwb2RpLTAuZHRkIgogICB4bWxuczppbmtzY2FwZT0iaHR0cDovL3d3dy5pbmtzY2FwZS5vcmcvbmFtZXNwYWNlcy9pbmtzY2FwZSIKICAgd2lkdGg9IjY0cHgiCiAgIGhlaWdodD0iNjRweCIKICAgaWQ9InN2ZzU4MjEiCiAgIHNvZGlwb2RpOnZlcnNpb249IjAuMzIiCiAgIGlua3NjYXBlOnZlcnNpb249IjAuOTIuMCByMTUyOTkiCiAgIHNvZGlwb2RpOmRvY25hbWU9IkRpbWVuc2lvbl9BbmdsZS5zdmciCiAgIGlua3NjYXBlOm91dHB1dF9leHRlbnNpb249Im9yZy5pbmtzY2FwZS5vdXRwdXQuc3ZnLmlua3NjYXBlIgogICB2ZXJzaW9uPSIxLjEiCiAgIGlua3NjYXBlOmV4cG9ydC1maWxlbmFtZT0iL21lZGlhL2RhdGEvWW9yaWsvRnJlZUNBRC9pY29ucy9Ta2V0Y2hlci5wbmciCiAgIGlua3NjYXBlOmV4cG9ydC14ZHBpPSI0NSIKICAgaW5rc2NhcGU6ZXhwb3J0LXlkcGk9IjQ1Ij4KICA8ZGVmcwogICAgIGlkPSJkZWZzNTgyMyI+CiAgICA8bGluZWFyR3JhZGllbnQKICAgICAgIGlkPSJsaW5lYXJHcmFkaWVudDMwNDIiCiAgICAgICBpbmtzY2FwZTpjb2xsZWN0PSJhbHdheXMiPgogICAgICA8c3RvcAogICAgICAgICBpZD0ic3RvcDMwNDQiCiAgICAgICAgIG9mZnNldD0iMCIKICAgICAgICAgc3R5bGU9InN0b3AtY29sb3I6I2M0YTAwMDtzdG9wLW9wYWNpdHk6MSIgLz4KICAgICAgPHN0b3AKICAgICAgICAgaWQ9InN0b3AzMDQ2IgogICAgICAgICBvZmZzZXQ9IjEiCiAgICAgICAgIHN0eWxlPSJzdG9wLWNvbG9yOiNmY2U5NGY7c3RvcC1vcGFjaXR5OjEiIC8+CiAgICA8L2xpbmVhckdyYWRpZW50PgogICAgPGxpbmVhckdyYWRpZW50CiAgICAgICBpZD0ibGluZWFyR3JhZGllbnQzMDM2IgogICAgICAgaW5rc2NhcGU6Y29sbGVjdD0iYWx3YXlzIj4KICAgICAgPHN0b3AKICAgICAgICAgaWQ9InN0b3AzMDM4IgogICAgICAgICBvZmZzZXQ9IjAiCiAgICAgICAgIHN0eWxlPSJzdG9wLWNvbG9yOiNjNGEwMDA7c3RvcC1vcGFjaXR5OjEiIC8+CiAgICAgIDxzdG9wCiAgICAgICAgIGlkPSJzdG9wMzA0MCIKICAgICAgICAgb2Zmc2V0PSIxIgogICAgICAgICBzdHlsZT0ic3RvcC1jb2xvcjojZmNlOTRmO3N0b3Atb3BhY2l0eToxIiAvPgogICAgPC9saW5lYXJHcmFkaWVudD4KICAgIDxsaW5lYXJHcmFkaWVudAogICAgICAgaWQ9ImxpbmVhckdyYWRpZW50MzAzMCIKICAgICAgIGlua3NjYXBlOmNvbGxlY3Q9ImFsd2F5cyI+CiAgICAgIDxzdG9wCiAgICAgICAgIGlkPSJzdG9wMzAzMiIKICAgICAgICAgb2Zmc2V0PSIwIgogICAgICAgICBzdHlsZT0ic3RvcC1jb2xvcjojYzRhMDAwO3N0b3Atb3BhY2l0eToxIiAvPgogICAgICA8c3RvcAogICAgICAgICBpZD0ic3RvcDMwMzQiCiAgICAgICAgIG9mZnNldD0iMSIKICAgICAgICAgc3R5bGU9InN0b3AtY29sb3I6I2ZjZTk0ZjtzdG9wLW9wYWNpdHk6MSIgLz4KICAgIDwvbGluZWFyR3JhZGllbnQ+CiAgICA8bGluZWFyR3JhZGllbnQKICAgICAgIGlkPSJsaW5lYXJHcmFkaWVudDMwMjQiCiAgICAgICBpbmtzY2FwZTpjb2xsZWN0PSJhbHdheXMiPgogICAgICA8c3RvcAogICAgICAgICBpZD0ic3RvcDMwMjYiCiAgICAgICAgIG9mZnNldD0iMCIKICAgICAgICAgc3R5bGU9InN0b3AtY29sb3I6I2M0YTAwMDtzdG9wLW9wYWNpdHk6MSIgLz4KICAgICAgPHN0b3AKICAgICAgICAgaWQ9InN0b3AzMDI4IgogICAgICAgICBvZmZzZXQ9IjEiCiAgICAgICAgIHN0eWxlPSJzdG9wLWNvbG9yOiNmY2U5NGY7c3RvcC1vcGFjaXR5OjEiIC8+CiAgICA8L2xpbmVhckdyYWRpZW50PgogICAgPGxpbmVhckdyYWRpZW50CiAgICAgICBpZD0ibGluZWFyR3JhZGllbnQzOTI5IgogICAgICAgaW5rc2NhcGU6Y29sbGVjdD0iYWx3YXlzIj4KICAgICAgPHN0b3AKICAgICAgICAgaWQ9InN0b3AzOTMxIgogICAgICAgICBvZmZzZXQ9IjAiCiAgICAgICAgIHN0eWxlPSJzdG9wLWNvbG9yOiNjNGEwMDA7c3RvcC1vcGFjaXR5OjEiIC8+CiAgICAgIDxzdG9wCiAgICAgICAgIGlkPSJzdG9wMzkzMyIKICAgICAgICAgb2Zmc2V0PSIxIgogICAgICAgICBzdHlsZT0ic3RvcC1jb2xvcjojZmNlOTRmO3N0b3Atb3BhY2l0eToxIiAvPgogICAgPC9saW5lYXJHcmFkaWVudD4KICAgIDxsaW5lYXJHcmFkaWVudAogICAgICAgaW5rc2NhcGU6Y29sbGVjdD0iYWx3YXlzIgogICAgICAgaWQ9ImxpbmVhckdyYWRpZW50MzkwNSI+CiAgICAgIDxzdG9wCiAgICAgICAgIHN0eWxlPSJzdG9wLWNvbG9yOiNkM2Q3Y2Y7c3RvcC1vcGFjaXR5OjEiCiAgICAgICAgIG9mZnNldD0iMCIKICAgICAgICAgaWQ9InN0b3AzOTA3IiAvPgogICAgICA8c3RvcAogICAgICAgICBzdHlsZT0ic3RvcC1jb2xvcjojZmZmZmZmO3N0b3Atb3BhY2l0eToxIgogICAgICAgICBvZmZzZXQ9IjEiCiAgICAgICAgIGlkPSJzdG9wMzkwOSIgLz4KICAgIDwvbGluZWFyR3JhZGllbnQ+CiAgICA8bGluZWFyR3JhZGllbnQKICAgICAgIGlua3NjYXBlOmNvbGxlY3Q9ImFsd2F5cyIKICAgICAgIGlkPSJsaW5lYXJHcmFkaWVudDYzNDkiPgogICAgICA8c3RvcAogICAgICAgICBzdHlsZT0ic3RvcC1jb2xvcjojMDAwMDAwO3N0b3Atb3BhY2l0eToxOyIKICAgICAgICAgb2Zmc2V0PSIwIgogICAgICAgICBpZD0ic3RvcDYzNTEiIC8+CiAgICAgIDxzdG9wCiAgICAgICAgIHN0eWxlPSJzdG9wLWNvbG9yOiMwMDAwMDA7c3RvcC1vcGFjaXR5OjA7IgogICAgICAgICBvZmZzZXQ9IjEiCiAgICAgICAgIGlkPSJzdG9wNjM1MyIgLz4KICAgIDwvbGluZWFyR3JhZGllbnQ+CiAgICA8bGluZWFyR3JhZGllbnQKICAgICAgIGlkPSJsaW5lYXJHcmFkaWVudDMzNzciPgogICAgICA8c3RvcAogICAgICAgICBzdHlsZT0ic3RvcC1jb2xvcjojMDAxOWEzO3N0b3Atb3BhY2l0eToxOyIKICAgICAgICAgb2Zmc2V0PSIwIgogICAgICAgICBpZD0ic3RvcDMzNzkiIC8+CiAgICAgIDxzdG9wCiAgICAgICAgIHN0eWxlPSJzdG9wLWNvbG9yOiMwMDY5ZmY7c3RvcC1vcGFjaXR5OjE7IgogICAgICAgICBvZmZzZXQ9IjEiCiAgICAgICAgIGlkPSJzdG9wMzM4MSIgLz4KICAgIDwvbGluZWFyR3JhZGllbnQ+CiAgICA8bGluZWFyR3JhZGllbnQKICAgICAgIGlua3NjYXBlOmNvbGxlY3Q9ImFsd2F5cyIKICAgICAgIHhsaW5rOmhyZWY9IiNsaW5lYXJHcmFkaWVudDMzNzciCiAgICAgICBpZD0ibGluZWFyR3JhZGllbnQzMzgzIgogICAgICAgeDE9IjkwMS4xODc1IgogICAgICAgeTE9IjExOTAuODc1IgogICAgICAgeDI9IjEyNjcuOTA2MiIKICAgICAgIHkyPSIxMTkwLjg3NSIKICAgICAgIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZU9uVXNlIgogICAgICAgZ3JhZGllbnRUcmFuc2Zvcm09Im1hdHJpeCgtMSwwLDAsMSwyMTk5LjM1NiwwKSIgLz4KICAgIDxpbmtzY2FwZTpwZXJzcGVjdGl2ZQogICAgICAgc29kaXBvZGk6dHlwZT0iaW5rc2NhcGU6cGVyc3AzZCIKICAgICAgIGlua3NjYXBlOnZwX3g9IjAgOiAzMiA6IDEiCiAgICAgICBpbmtzY2FwZTp2cF95PSIwIDogMTAwMCA6IDAiCiAgICAgICBpbmtzY2FwZTp2cF96PSI2NCA6IDMyIDogMSIKICAgICAgIGlua3NjYXBlOnBlcnNwM2Qtb3JpZ2luPSIzMiA6IDIxLjMzMzMzMyA6IDEiCiAgICAgICBpZD0icGVyc3BlY3RpdmU1ODI5IiAvPgogICAgPHJhZGlhbEdyYWRpZW50CiAgICAgICBpbmtzY2FwZTpjb2xsZWN0PSJhbHdheXMiCiAgICAgICB4bGluazpocmVmPSIjbGluZWFyR3JhZGllbnQ2MzQ5IgogICAgICAgaWQ9InJhZGlhbEdyYWRpZW50NjM1NSIKICAgICAgIGN4PSIxMTAzLjYzOTkiCiAgICAgICBjeT0iMTQyNC40NDY1IgogICAgICAgZng9IjExMDMuNjM5OSIKICAgICAgIGZ5PSIxNDI0LjQ0NjUiCiAgICAgICByPSIxOTQuNDA2MTQiCiAgICAgICBncmFkaWVudFRyYW5zZm9ybT0ibWF0cml4KC0xLjQzMDc0OTksLTEuMzYwNTE1NmUtNywtMS4yMDI3MTNlLTgsMC4xMjY0ODAxLDI2NzQuNzQ4OCwxMjQ0LjI4MjYpIgogICAgICAgZ3JhZGllbnRVbml0cz0idXNlclNwYWNlT25Vc2UiIC8+CiAgICA8bGluZWFyR3JhZGllbnQKICAgICAgIGlua3NjYXBlOmNvbGxlY3Q9ImFsd2F5cyIKICAgICAgIHhsaW5rOmhyZWY9IiNsaW5lYXJHcmFkaWVudDM4OTMiCiAgICAgICBpZD0ibGluZWFyR3JhZGllbnQzODk5IgogICAgICAgeDE9IjM1IgogICAgICAgeTE9IjUwIgogICAgICAgeDI9IjMxIgogICAgICAgeTI9IjE2IgogICAgICAgZ3JhZGllbnRVbml0cz0idXNlclNwYWNlT25Vc2UiIC8+CiAgICA8bGluZWFyR3JhZGllbnQKICAgICAgIGlua3NjYXBlOmNvbGxlY3Q9ImFsd2F5cyIKICAgICAgIGlkPSJsaW5lYXJHcmFkaWVudDM4OTMiPgogICAgICA8c3RvcAogICAgICAgICBzdHlsZT0ic3RvcC1jb2xvcjojZDNkN2NmO3N0b3Atb3BhY2l0eToxIgogICAgICAgICBvZmZzZXQ9IjAiCiAgICAgICAgIGlkPSJzdG9wMzg5NSIgLz4KICAgICAgPHN0b3AKICAgICAgICAgc3R5bGU9InN0b3AtY29sb3I6I2ZmZmZmZjtzdG9wLW9wYWNpdHk6MSIKICAgICAgICAgb2Zmc2V0PSIxIgogICAgICAgICBpZD0ic3RvcDM4OTciIC8+CiAgICA8L2xpbmVhckdyYWRpZW50PgogICAgPGxpbmVhckdyYWRpZW50CiAgICAgICBpbmtzY2FwZTpjb2xsZWN0PSJhbHdheXMiCiAgICAgICB4bGluazpocmVmPSIjbGluZWFyR3JhZGllbnQzMDI0IgogICAgICAgaWQ9ImxpbmVhckdyYWRpZW50MzAzMyIKICAgICAgIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZU9uVXNlIgogICAgICAgZ3JhZGllbnRUcmFuc2Zvcm09Im1hdHJpeCgwLjk2MjE0ODgsLTAuMjcyNTI0NjUsMC4yNzI1MjQ2NSwwLjk2MjE0ODgsNDguNjQ0MjgxLDE5LjQ0MzgwMikiCiAgICAgICB4MT0iMzQuMDkzNTg2IgogICAgICAgeTE9IjQ5LjcyOTg3NyIKICAgICAgIHgyPSIzMy44OTE2OTciCiAgICAgICB5Mj0iMTYuMTAzNjk3IiAvPgogICAgPGxpbmVhckdyYWRpZW50CiAgICAgICBpbmtzY2FwZTpjb2xsZWN0PSJhbHdheXMiCiAgICAgICB4bGluazpocmVmPSIjbGluZWFyR3JhZGllbnQzOTA1IgogICAgICAgaWQ9ImxpbmVhckdyYWRpZW50MzkxMSIKICAgICAgIHgxPSI4LjUiCiAgICAgICB5MT0iNDguNSIKICAgICAgIHgyPSI1LjUiCiAgICAgICB5Mj0iMzkuNSIKICAgICAgIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZU9uVXNlIiAvPgogICAgPGxpbmVhckdyYWRpZW50CiAgICAgICBpbmtzY2FwZTpjb2xsZWN0PSJhbHdheXMiCiAgICAgICB4bGluazpocmVmPSIjbGluZWFyR3JhZGllbnQzMDM2IgogICAgICAgaWQ9ImxpbmVhckdyYWRpZW50MzkxOSIKICAgICAgIHgxPSI5IgogICAgICAgeTE9IjUwIgogICAgICAgeDI9IjUiCiAgICAgICB5Mj0iMzgiCiAgICAgICBncmFkaWVudFVuaXRzPSJ1c2VyU3BhY2VPblVzZSIgLz4KICAgIDxsaW5lYXJHcmFkaWVudAogICAgICAgaW5rc2NhcGU6Y29sbGVjdD0iYWx3YXlzIgogICAgICAgeGxpbms6aHJlZj0iI2xpbmVhckdyYWRpZW50MzkyOSIKICAgICAgIGlkPSJsaW5lYXJHcmFkaWVudDM5MjciCiAgICAgICB4MT0iMTkiCiAgICAgICB5MT0iMzkiCiAgICAgICB4Mj0iMjgiCiAgICAgICB5Mj0iOSIKICAgICAgIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZU9uVXNlIiAvPgogICAgPGxpbmVhckdyYWRpZW50CiAgICAgICBpbmtzY2FwZTpjb2xsZWN0PSJhbHdheXMiCiAgICAgICB4bGluazpocmVmPSIjbGluZWFyR3JhZGllbnQzMDQyIgogICAgICAgaWQ9ImxpbmVhckdyYWRpZW50Mzk0MSIKICAgICAgIHgxPSIxOSIKICAgICAgIHkxPSIzOSIKICAgICAgIHgyPSIyOCIKICAgICAgIHkyPSI5IgogICAgICAgZ3JhZGllbnRVbml0cz0idXNlclNwYWNlT25Vc2UiIC8+CiAgICA8bGluZWFyR3JhZGllbnQKICAgICAgIGlua3NjYXBlOmNvbGxlY3Q9ImFsd2F5cyIKICAgICAgIHhsaW5rOmhyZWY9IiNsaW5lYXJHcmFkaWVudDMwMzAiCiAgICAgICBpZD0ibGluZWFyR3JhZGllbnQzOTQ5IgogICAgICAgeDE9IjI2IgogICAgICAgeTE9IjUzIgogICAgICAgeDI9IjIyIgogICAgICAgeTI9IjQwIgogICAgICAgZ3JhZGllbnRVbml0cz0idXNlclNwYWNlT25Vc2UiIC8+CiAgPC9kZWZzPgogIDxzb2RpcG9kaTpuYW1lZHZpZXcKICAgICBpZD0iYmFzZSIKICAgICBwYWdlY29sb3I9IiNmZmZmZmYiCiAgICAgYm9yZGVyY29sb3I9IiM2NjY2NjYiCiAgICAgYm9yZGVyb3BhY2l0eT0iMS4wIgogICAgIGlua3NjYXBlOnBhZ2VvcGFjaXR5PSIwLjAiCiAgICAgaW5rc2NhcGU6cGFnZXNoYWRvdz0iMiIKICAgICBpbmtzY2FwZTp6b29tPSI5LjY4NzUiCiAgICAgaW5rc2NhcGU6Y3g9IjMyIgogICAgIGlua3NjYXBlOmN5PSIzMiIKICAgICBpbmtzY2FwZTpjdXJyZW50LWxheWVyPSJsYXllcjEiCiAgICAgc2hvd2dyaWQ9InRydWUiCiAgICAgaW5rc2NhcGU6ZG9jdW1lbnQtdW5pdHM9InB4IgogICAgIGlua3NjYXBlOmdyaWQtYmJveD0idHJ1ZSIKICAgICBpbmtzY2FwZTp3aW5kb3ctd2lkdGg9IjE1MzYiCiAgICAgaW5rc2NhcGU6d2luZG93LWhlaWdodD0iODAxIgogICAgIGlua3NjYXBlOndpbmRvdy14PSItOCIKICAgICBpbmtzY2FwZTp3aW5kb3cteT0iLTgiCiAgICAgaW5rc2NhcGU6d2luZG93LW1heGltaXplZD0iMSIKICAgICBzaG93Z3VpZGVzPSJ0cnVlIgogICAgIGlua3NjYXBlOmd1aWRlLWJib3g9InRydWUiCiAgICAgaW5rc2NhcGU6c25hcC1nbG9iYWw9InRydWUiCiAgICAgaW5rc2NhcGU6c25hcC1iYm94PSJ0cnVlIj4KICAgIDxpbmtzY2FwZTpncmlkCiAgICAgICB0eXBlPSJ4eWdyaWQiCiAgICAgICBpZD0iZ3JpZDI5OTMiCiAgICAgICBlbXBzcGFjaW5nPSIyIgogICAgICAgdmlzaWJsZT0idHJ1ZSIKICAgICAgIGVuYWJsZWQ9InRydWUiCiAgICAgICBzbmFwdmlzaWJsZWdyaWRsaW5lc29ubHk9InRydWUiIC8+CiAgPC9zb2RpcG9kaTpuYW1lZHZpZXc+CiAgPG1ldGFkYXRhCiAgICAgaWQ9Im1ldGFkYXRhNTgyNiI+CiAgICA8cmRmOlJERj4KICAgICAgPGNjOldvcmsKICAgICAgICAgcmRmOmFib3V0PSIiPgogICAgICAgIDxkYzpmb3JtYXQ+aW1hZ2Uvc3ZnK3htbDwvZGM6Zm9ybWF0PgogICAgICAgIDxkYzp0eXBlCiAgICAgICAgICAgcmRmOnJlc291cmNlPSJodHRwOi8vcHVybC5vcmcvZGMvZGNtaXR5cGUvU3RpbGxJbWFnZSIgLz4KICAgICAgICA8ZGM6dGl0bGUgLz4KICAgICAgICA8ZGM6Y3JlYXRvcj4KICAgICAgICAgIDxjYzpBZ2VudD4KICAgICAgICAgICAgPGRjOnRpdGxlPltXYW5kZXJlckZhbl08L2RjOnRpdGxlPgogICAgICAgICAgPC9jYzpBZ2VudD4KICAgICAgICA8L2RjOmNyZWF0b3I+CiAgICAgICAgPGRjOnRpdGxlPlRlY2hEcmF3X0RpbWVuc2lvbl9BbmdsZTwvZGM6dGl0bGU+CiAgICAgICAgPGRjOmRhdGU+MjAxNi0wNC0yNzwvZGM6ZGF0ZT4KICAgICAgICA8ZGM6cmVsYXRpb24+aHR0cDovL3d3dy5mcmVlY2Fkd2ViLm9yZy93aWtpL2luZGV4LnBocD90aXRsZT1BcnR3b3JrPC9kYzpyZWxhdGlvbj4KICAgICAgICA8ZGM6cHVibGlzaGVyPgogICAgICAgICAgPGNjOkFnZW50PgogICAgICAgICAgICA8ZGM6dGl0bGU+RnJlZUNBRDwvZGM6dGl0bGU+CiAgICAgICAgICA8L2NjOkFnZW50PgogICAgICAgIDwvZGM6cHVibGlzaGVyPgogICAgICAgIDxkYzppZGVudGlmaWVyPkZyZWVDQUQvc3JjL01vZC9UZWNoRHJhdy9HdWkvUmVzb3VyY2VzL2ljb25zL1RlY2hEcmF3X0RpbWVuc2lvbl9BbmdsZS5zdmc8L2RjOmlkZW50aWZpZXI+CiAgICAgICAgPGRjOnJpZ2h0cz4KICAgICAgICAgIDxjYzpBZ2VudD4KICAgICAgICAgICAgPGRjOnRpdGxlPkZyZWVDQUQgTEdQTDIrPC9kYzp0aXRsZT4KICAgICAgICAgIDwvY2M6QWdlbnQ+CiAgICAgICAgPC9kYzpyaWdodHM+CiAgICAgICAgPGNjOmxpY2Vuc2UKICAgICAgICAgICByZGY6cmVzb3VyY2U9Imh0dHBzOi8vd3d3LmdudS5vcmcvbGljZW5zZXMvbGdwbC0zLjAuZW4uaHRtbCI+aHR0cHM6Ly93d3cuZ251Lm9yZy9jb3B5bGVmdC9sZXNzZXIuaHRtbDwvY2M6bGljZW5zZT4KICAgICAgICA8ZGM6Y29udHJpYnV0b3I+CiAgICAgICAgICA8Y2M6QWdlbnQ+CiAgICAgICAgICAgIDxkYzp0aXRsZT5bYWdyeXNvbl0gQWxleGFuZGVyIEdyeXNvbjwvZGM6dGl0bGU+CiAgICAgICAgICA8L2NjOkFnZW50PgogICAgICAgIDwvZGM6Y29udHJpYnV0b3I+CiAgICAgIDwvY2M6V29yaz4KICAgIDwvcmRmOlJERj4KICA8L21ldGFkYXRhPgogIDxnCiAgICAgaWQ9ImxheWVyMSIKICAgICBpbmtzY2FwZTpsYWJlbD0iTGF5ZXIgMSIKICAgICBpbmtzY2FwZTpncm91cG1vZGU9ImxheWVyIj4KICAgIDxnCiAgICAgICBpZD0iZzMwMjQiCiAgICAgICB0cmFuc2Zvcm09Im1hdHJpeCgxLjA2OTg2MTMsMCwwLDAuOTk0MDQxNjUsLTQ5LjQwMjc1NiwtOC40MzkxNTU5KSIKICAgICAgIHN0eWxlPSJzdHJva2U6IzMwMmIwMCIKICAgICAgIGlua3NjYXBlOmV4cG9ydC14ZHBpPSI0NSIKICAgICAgIGlua3NjYXBlOmV4cG9ydC15ZHBpPSI0NSI+CiAgICAgIDxwYXRoCiAgICAgICAgIHNvZGlwb2RpOm5vZGV0eXBlcz0iY2NjY2NjY2NjY2NjY2NjIgogICAgICAgICBpZD0icGF0aDM3NzAtMSIKICAgICAgICAgZD0ibSA4NC41MDcwNjEsMzQuNjkwMDY4IDIuMDQ2OTIsLTMuNDM2NTg1IEMgOTIsMzQgOTcsNDMgOTEuODI1MTU1LDUwLjg1MjQ1NyBsIC0zLjYwNzU4NCwtMS43Mjc4MTEgYyAxLjQwOTgyOSw0LjAwMTU0OCAxLjkxNzc2MSw3LjU3MTE0MSAxLjk1NTc1MSw5LjgwNjg4NiBsIDAuMDM3OTksMi4yMzU3NDUgMS43NjU4MDMsLTEuMzcxODM5IGMgMS43NjU4MDIsLTEuMzcxODM4IDQuODY1NDU0LC0zLjIxMzYyMSA4Ljg2Njk5NSwtNC42MjM0NSBMIDk3LjIzNjUzMSw1My40NDQxNzYgQyAxMDUsNDYgOTgsMzAgODkuNjI0MzU4LDI2LjA5ODYwNCBsIDIuMDQ2OTE5LC0zLjQzNjU4NiBjIC00LjExMjYyOCwxLjA0MjI0OSAtNy43MTM1MjcsMS4yMjUzNTQgLTkuOTQzNTUsMS4wNjEwNDEgbCAtMi4yMzAwMjMsLTAuMTY0MzE0IDEuMjA2NTYzLDEuODgyNjA3IGMgMS4yMDY1NjQsMS44ODI2MDUgMi43NjA1NDQsNS4xMzYwODggMy44MDI3OTQsOS4yNDg3MTYgeiIKICAgICAgICAgc3R5bGU9ImZvbnQtc2l6ZTptZWRpdW07Zm9udC1zdHlsZTpub3JtYWw7Zm9udC12YXJpYW50Om5vcm1hbDtmb250LXdlaWdodDpub3JtYWw7Zm9udC1zdHJldGNoOm5vcm1hbDt0ZXh0LWluZGVudDowO3RleHQtYWxpZ246c3RhcnQ7dGV4dC1kZWNvcmF0aW9uOm5vbmU7bGluZS1oZWlnaHQ6bm9ybWFsO2xldHRlci1zcGFjaW5nOm5vcm1hbDt3b3JkLXNwYWNpbmc6bm9ybWFsO3RleHQtdHJhbnNmb3JtOm5vbmU7ZGlyZWN0aW9uOmx0cjtibG9jay1wcm9ncmVzc2lvbjp0Yjt3cml0aW5nLW1vZGU6bHItdGI7dGV4dC1hbmNob3I6c3RhcnQ7YmFzZWxpbmUtc2hpZnQ6YmFzZWxpbmU7Y29sb3I6IzAwMDAwMDtmaWxsOnVybCgjbGluZWFyR3JhZGllbnQzMDMzKTtmaWxsLW9wYWNpdHk6MTtmaWxsLXJ1bGU6bm9uemVybztzdHJva2U6IzMwMmIwMDtzdHJva2Utd2lkdGg6MS45MzkzODQ3MDAwMDAwMDAwMDtzdHJva2UtbGluZWNhcDpidXR0O3N0cm9rZS1saW5lam9pbjpyb3VuZDtzdHJva2UtbWl0ZXJsaW1pdDo0O3N0cm9rZS1vcGFjaXR5OjE7c3Ryb2tlLWRhc2hhcnJheTpub25lO3N0cm9rZS1kYXNob2Zmc2V0OjA7dmlzaWJpbGl0eTp2aXNpYmxlO2Rpc3BsYXk6aW5saW5lO292ZXJmbG93OnZpc2libGU7ZW5hYmxlLWJhY2tncm91bmQ6YWNjdW11bGF0ZTtmb250LWZhbWlseTpzYW5zLXNlcmlmIgogICAgICAgICBpbmtzY2FwZTpjb25uZWN0b3ItY3VydmF0dXJlPSIwIiAvPgogICAgICA8cGF0aAogICAgICAgICBzb2RpcG9kaTpub2RldHlwZXM9ImNjIgogICAgICAgICBpbmtzY2FwZTpjb25uZWN0b3ItY3VydmF0dXJlPSIwIgogICAgICAgICBpZD0icGF0aDM4NjQiCiAgICAgICAgIGQ9Im0gODIuNDIyNTYsMjYuNDY0ODExIDMuMTA3OTYsNi41MDY5NjUiCiAgICAgICAgIHN0eWxlPSJmaWxsOm5vbmU7c3Ryb2tlOiNmY2U5NGY7c3Ryb2tlLXdpZHRoOjEuOTM5Mzg0NzAwMDAwMDAwMDA7c3Ryb2tlLWxpbmVjYXA6YnV0dDtzdHJva2UtbGluZWpvaW46bWl0ZXI7c3Ryb2tlLW9wYWNpdHk6MSIgLz4KICAgICAgPHBhdGgKICAgICAgICAgc29kaXBvZGk6bm9kZXR5cGVzPSJjYyIKICAgICAgICAgaW5rc2NhcGU6Y29ubmVjdG9yLWN1cnZhdHVyZT0iMCIKICAgICAgICAgaWQ9InBhdGgzODY0LTQiCiAgICAgICAgIGQ9Ik0gOTEuMjI4NjYxLDU2LjA0OTU0NSA5MC43NDQ2NDIsNTAuMzIyOTI5IgogICAgICAgICBzdHlsZT0iZmlsbDpub25lO3N0cm9rZTojZmNlOTRmO3N0cm9rZS13aWR0aDoxLjkzOTM4NDcwMDAwMDAwMDAwO3N0cm9rZS1saW5lY2FwOmJ1dHQ7c3Ryb2tlLWxpbmVqb2luOm1pdGVyO3N0cm9rZS1vcGFjaXR5OjEiIC8+CiAgICAgIDxwYXRoCiAgICAgICAgIHNvZGlwb2RpOm5vZGV0eXBlcz0iY2MiCiAgICAgICAgIGlua3NjYXBlOmNvbm5lY3Rvci1jdXJ2YXR1cmU9IjAiCiAgICAgICAgIGlkPSJwYXRoMzg2NiIKICAgICAgICAgZD0iTSA4Mi4xMjE2NzMsMjYuNjA4MzY1IEMgMTAwLDM1IDk3LjUxMzMwOCw0OCA5MS45MzYzMjUsNTMuMTQ4ODU2IgogICAgICAgICBzdHlsZT0iZmlsbDpub25lO3N0cm9rZTojZmNlOTRmO3N0cm9rZS13aWR0aDoxLjkzOTM4NDcwMDAwMDAwMDAwO3N0cm9rZS1saW5lY2FwOnJvdW5kO3N0cm9rZS1saW5lam9pbjptaXRlcjtzdHJva2Utb3BhY2l0eToxIiAvPgogICAgICA8cGF0aAogICAgICAgICBzb2RpcG9kaTpub2RldHlwZXM9ImNjIgogICAgICAgICBpbmtzY2FwZTpjb25uZWN0b3ItY3VydmF0dXJlPSIwIgogICAgICAgICBpZD0icGF0aDM4NjgiCiAgICAgICAgIGQ9Ik0gODYuNTUzOTgsMzEuMjUzNDgzIDg1LDI4IgogICAgICAgICBzdHlsZT0iZmlsbDpub25lO3N0cm9rZTojZmNlOTRmO3N0cm9rZS13aWR0aDoxLjkzOTM4NDcwMDAwMDAwMDAwO3N0cm9rZS1saW5lY2FwOmJ1dHQ7c3Ryb2tlLWxpbmVqb2luOm1pdGVyO3N0cm9rZS1vcGFjaXR5OjEiIC8+CiAgICAgIDxwYXRoCiAgICAgICAgIHNvZGlwb2RpOm5vZGV0eXBlcz0iY2MiCiAgICAgICAgIGlua3NjYXBlOmNvbm5lY3Rvci1jdXJ2YXR1cmU9IjAiCiAgICAgICAgIGlkPSJwYXRoMzg2OC04IgogICAgICAgICBkPSJNIDk0LjYyNjQzMSw0OS41NDExNDIgOTAuMTY2OTE2LDU4LjkzNzIxIgogICAgICAgICBzdHlsZT0iZmlsbDpub25lO3N0cm9rZTojZmNlOTRmO3N0cm9rZS13aWR0aDoxLjkzOTM4NDcwMDAwMDAwMDAwO3N0cm9rZS1saW5lY2FwOmJ1dHQ7c3Ryb2tlLWxpbmVqb2luOm1pdGVyO3N0cm9rZS1vcGFjaXR5OjEiIC8+CiAgICAgIDxwYXRoCiAgICAgICAgIHNvZGlwb2RpOm5vZGV0eXBlcz0iY2NjY2NjY2NjY2NjY2NjIgogICAgICAgICBpZD0icGF0aDM3NzAtOSIKICAgICAgICAgZD0ibSA4NC41MDcwNjEsMzQuNjkwMDY4IDIuMDQ2OTIsLTMuNDM2NTg1IEMgOTIsMzQgOTcsNDMgOTEuODI1MTU1LDUwLjg1MjQ1NyBsIC0zLjYwNzU4NCwtMS43Mjc4MTEgYyAxLjQwOTgyOSw0LjAwMTU0OCAxLjkxNzc2MSw3LjU3MTE0MSAxLjk1NTc1MSw5LjgwNjg4NiBsIDAuMDM3OTksMi4yMzU3NDUgMS43NjU4MDMsLTEuMzcxODM5IGMgMS43NjU4MDIsLTEuMzcxODM4IDQuODY1NDU0LC0zLjIxMzYyMSA4Ljg2Njk5NSwtNC42MjM0NSBMIDk3LjIzNjUzMSw1My40NDQxNzYgQyAxMDUsNDYgOTgsMzAgODkuNjI0MzU4LDI2LjA5ODYwNCBsIDIuMDQ2OTE5LC0zLjQzNjU4NiBjIC00LjExMjYyOCwxLjA0MjI0OSAtNy43MTM1MjcsMS4yMjUzNTQgLTkuOTQzNTUsMS4wNjEwNDEgbCAtMi4yMzAwMjMsLTAuMTY0MzE0IDEuMjA2NTYzLDEuODgyNjA3IGMgMS4yMDY1NjQsMS44ODI2MDUgMi43NjA1NDQsNS4xMzYwODggMy44MDI3OTQsOS4yNDg3MTYgeiIKICAgICAgICAgc3R5bGU9ImZvbnQtc2l6ZTptZWRpdW07Zm9udC1zdHlsZTpub3JtYWw7Zm9udC12YXJpYW50Om5vcm1hbDtmb250LXdlaWdodDpub3JtYWw7Zm9udC1zdHJldGNoOm5vcm1hbDt0ZXh0LWluZGVudDowO3RleHQtYWxpZ246c3RhcnQ7dGV4dC1kZWNvcmF0aW9uOm5vbmU7bGluZS1oZWlnaHQ6bm9ybWFsO2xldHRlci1zcGFjaW5nOm5vcm1hbDt3b3JkLXNwYWNpbmc6bm9ybWFsO3RleHQtdHJhbnNmb3JtOm5vbmU7ZGlyZWN0aW9uOmx0cjtibG9jay1wcm9ncmVzc2lvbjp0Yjt3cml0aW5nLW1vZGU6bHItdGI7dGV4dC1hbmNob3I6c3RhcnQ7YmFzZWxpbmUtc2hpZnQ6YmFzZWxpbmU7Y29sb3I6IzAwMDAwMDtmaWxsOm5vbmU7c3Ryb2tlOiMzMDJiMDA7c3Ryb2tlLXdpZHRoOjEuOTM5Mzg0NzAwMDAwMDAwMDA7c3Ryb2tlLWxpbmVjYXA6YnV0dDtzdHJva2UtbGluZWpvaW46cm91bmQ7c3Ryb2tlLW1pdGVybGltaXQ6NDtzdHJva2Utb3BhY2l0eToxO3N0cm9rZS1kYXNoYXJyYXk6bm9uZTtzdHJva2UtZGFzaG9mZnNldDowO3Zpc2liaWxpdHk6dmlzaWJsZTtkaXNwbGF5OmlubGluZTtvdmVyZmxvdzp2aXNpYmxlO2VuYWJsZS1iYWNrZ3JvdW5kOmFjY3VtdWxhdGU7Zm9udC1mYW1pbHk6c2Fucy1zZXJpZiIKICAgICAgICAgaW5rc2NhcGU6Y29ubmVjdG9yLWN1cnZhdHVyZT0iMCIgLz4KICAgIDwvZz4KICAgIDxwYXRoCiAgICAgICBzdHlsZT0iZmlsbDpub25lO3N0cm9rZTojMzAyYjAwO3N0cm9rZS13aWR0aDo4O3N0cm9rZS1saW5lY2FwOnJvdW5kO3N0cm9rZS1saW5lam9pbjptaXRlcjtzdHJva2Utb3BhY2l0eToxIgogICAgICAgZD0iTSA5LDQ0IDQ4Ljk1OTg0Myw1OC4xMTQyMTEiCiAgICAgICBpZD0icGF0aDMwMzktNyIKICAgICAgIGlua3NjYXBlOmNvbm5lY3Rvci1jdXJ2YXR1cmU9IjAiCiAgICAgICBzb2RpcG9kaTpub2RldHlwZXM9ImNjIgogICAgICAgaW5rc2NhcGU6dHJhbnNmb3JtLWNlbnRlci14PSItMTkuOTc5OTIxIgogICAgICAgaW5rc2NhcGU6dHJhbnNmb3JtLWNlbnRlci15PSI3LjA1NzEwNTUiCiAgICAgICBpbmtzY2FwZTpleHBvcnQteGRwaT0iNDUiCiAgICAgICBpbmtzY2FwZTpleHBvcnQteWRwaT0iNDUiIC8+CiAgICA8cGF0aAogICAgICAgc3R5bGU9ImZpbGw6bm9uZTtzdHJva2U6IzMwMmIwMDtzdHJva2Utd2lkdGg6ODtzdHJva2UtbGluZWNhcDpyb3VuZDtzdHJva2UtbGluZWpvaW46bWl0ZXI7c3Ryb2tlLW9wYWNpdHk6MSIKICAgICAgIGQ9Ik0gOSw0NCAzMy40NjU2NzksOS4zOTYwODk1IgogICAgICAgaWQ9InBhdGgzMDM5LTctNCIKICAgICAgIGlua3NjYXBlOmNvbm5lY3Rvci1jdXJ2YXR1cmU9IjAiCiAgICAgICBzb2RpcG9kaTpub2RldHlwZXM9ImNjIgogICAgICAgaW5rc2NhcGU6dHJhbnNmb3JtLWNlbnRlci14PSItMTIuMjMyODQiCiAgICAgICBpbmtzY2FwZTp0cmFuc2Zvcm0tY2VudGVyLXk9Ii0xNy4zMDE5NTUiCiAgICAgICBpbmtzY2FwZTpleHBvcnQteGRwaT0iNDUiCiAgICAgICBpbmtzY2FwZTpleHBvcnQteWRwaT0iNDUiIC8+CiAgICA8cGF0aAogICAgICAgc29kaXBvZGk6dHlwZT0iYXJjIgogICAgICAgc3R5bGU9ImZpbGw6dXJsKCNsaW5lYXJHcmFkaWVudDM5MTEpO2ZpbGwtb3BhY2l0eToxO3N0cm9rZTojMzAyYjAwO3N0cm9rZS13aWR0aDoxLjUwMDAwMDAwMDAwMDAwMDAwO3N0cm9rZS1saW5lY2FwOnJvdW5kO3N0cm9rZS1saW5lam9pbjptaXRlcjtzdHJva2UtbWl0ZXJsaW1pdDo0O3N0cm9rZS1vcGFjaXR5OjE7c3Ryb2tlLWRhc2hhcnJheTpub25lO3N0cm9rZS1kYXNob2Zmc2V0OjAiCiAgICAgICBpZD0icGF0aDMwMzciCiAgICAgICBzb2RpcG9kaTpjeD0iNyIKICAgICAgIHNvZGlwb2RpOmN5PSI0NCIKICAgICAgIHNvZGlwb2RpOnJ4PSI2IgogICAgICAgc29kaXBvZGk6cnk9IjYiCiAgICAgICBkPSJNIDEzLDQ0IEEgNiw2IDAgMSAxIDEsNDQgNiw2IDAgMSAxIDEzLDQ0IHoiCiAgICAgICB0cmFuc2Zvcm09Im1hdHJpeCgxLjMzMzMzMzMsMCwwLDEuMzMzMzMzMSwxLjY2NjY2NjksLTE0LjY2NjY1NSkiCiAgICAgICBpbmtzY2FwZTpleHBvcnQteGRwaT0iNDUiCiAgICAgICBpbmtzY2FwZTpleHBvcnQteWRwaT0iNDUiIC8+CiAgICA8cGF0aAogICAgICAgc3R5bGU9ImZpbGw6bm9uZTtzdHJva2U6dXJsKCNsaW5lYXJHcmFkaWVudDM5NDkpO3N0cm9rZS13aWR0aDo0O3N0cm9rZS1saW5lY2FwOnJvdW5kO3N0cm9rZS1saW5lam9pbjptaXRlcjtzdHJva2Utb3BhY2l0eToxIgogICAgICAgZD0iTSA5LDQ0IDQ4Ljk1OTg0Myw1OC4xMTQyMTEiCiAgICAgICBpZD0icGF0aDMwMzktNy0wIgogICAgICAgaW5rc2NhcGU6Y29ubmVjdG9yLWN1cnZhdHVyZT0iMCIKICAgICAgIHNvZGlwb2RpOm5vZGV0eXBlcz0iY2MiCiAgICAgICBpbmtzY2FwZTp0cmFuc2Zvcm0tY2VudGVyLXg9Ii0xOS45Nzk5MjEiCiAgICAgICBpbmtzY2FwZTp0cmFuc2Zvcm0tY2VudGVyLXk9IjcuMDU3MTA1NSIKICAgICAgIGlua3NjYXBlOmV4cG9ydC14ZHBpPSI0NSIKICAgICAgIGlua3NjYXBlOmV4cG9ydC15ZHBpPSI0NSIgLz4KICAgIDxwYXRoCiAgICAgICBzdHlsZT0iZmlsbDp1cmwoI2xpbmVhckdyYWRpZW50MzkyNyk7c3Ryb2tlOnVybCgjbGluZWFyR3JhZGllbnQzOTQxKTtzdHJva2Utd2lkdGg6NDtzdHJva2UtbGluZWNhcDpyb3VuZDtzdHJva2UtbGluZWpvaW46bWl0ZXI7c3Ryb2tlLW9wYWNpdHk6MTtmaWxsLW9wYWNpdHk6MSIKICAgICAgIGQ9Ik0gOSw0NCAzMy40NjU2NzksOS4zOTYwOSIKICAgICAgIGlkPSJwYXRoMzAzOS03LTQtOSIKICAgICAgIGlua3NjYXBlOmNvbm5lY3Rvci1jdXJ2YXR1cmU9IjAiCiAgICAgICBzb2RpcG9kaTpub2RldHlwZXM9ImNjIgogICAgICAgaW5rc2NhcGU6dHJhbnNmb3JtLWNlbnRlci14PSItMTIuMjMyODQiCiAgICAgICBpbmtzY2FwZTp0cmFuc2Zvcm0tY2VudGVyLXk9Ii0xNy4zMDE5NTUiCiAgICAgICBpbmtzY2FwZTpleHBvcnQteGRwaT0iNDUiCiAgICAgICBpbmtzY2FwZTpleHBvcnQteWRwaT0iNDUiIC8+CiAgICA8cGF0aAogICAgICAgc3R5bGU9ImZpbGw6bm9uZTtzdHJva2U6I2ZjZTk0ZjtzdHJva2Utd2lkdGg6MjtzdHJva2UtbGluZWNhcDpyb3VuZDtzdHJva2UtbGluZWpvaW46bWl0ZXI7c3Ryb2tlLW9wYWNpdHk6MSIKICAgICAgIGQ9Ik0gOSw0MyA0OS40ODcwOTMsNTcuMjc2NDQyIgogICAgICAgaWQ9InBhdGgzMDM5LTctMC00IgogICAgICAgaW5rc2NhcGU6Y29ubmVjdG9yLWN1cnZhdHVyZT0iMCIKICAgICAgIHNvZGlwb2RpOm5vZGV0eXBlcz0iY2MiCiAgICAgICBpbmtzY2FwZTp0cmFuc2Zvcm0tY2VudGVyLXg9Ii0xOS45Nzk5MjEiCiAgICAgICBpbmtzY2FwZTp0cmFuc2Zvcm0tY2VudGVyLXk9IjcuMDU3MTA1NSIKICAgICAgIGlua3NjYXBlOmV4cG9ydC14ZHBpPSI0NSIKICAgICAgIGlua3NjYXBlOmV4cG9ydC15ZHBpPSI0NSIgLz4KICAgIDxwYXRoCiAgICAgICBzdHlsZT0iZmlsbDpub25lO3N0cm9rZTojZmNlOTRmO3N0cm9rZS13aWR0aDoyO3N0cm9rZS1saW5lY2FwOnJvdW5kO3N0cm9rZS1saW5lam9pbjptaXRlcjtzdHJva2Utb3BhY2l0eToxIgogICAgICAgZD0iTSAxMCw0MSAzMi43NDE4OTMsOC43MTMyMTQiCiAgICAgICBpZD0icGF0aDMwMzktNy00LTktOCIKICAgICAgIGlua3NjYXBlOmNvbm5lY3Rvci1jdXJ2YXR1cmU9IjAiCiAgICAgICBzb2RpcG9kaTpub2RldHlwZXM9ImNjIgogICAgICAgaW5rc2NhcGU6dHJhbnNmb3JtLWNlbnRlci14PSItMTIuMjMyODQiCiAgICAgICBpbmtzY2FwZTp0cmFuc2Zvcm0tY2VudGVyLXk9Ii0xNy4zMDE5NTUiCiAgICAgICBpbmtzY2FwZTpleHBvcnQteGRwaT0iNDUiCiAgICAgICBpbmtzY2FwZTpleHBvcnQteWRwaT0iNDUiIC8+CiAgICA8cGF0aAogICAgICAgc29kaXBvZGk6dHlwZT0iYXJjIgogICAgICAgc3R5bGU9ImZpbGw6dXJsKCNsaW5lYXJHcmFkaWVudDM5MTkpO3N0cm9rZTojZmNlOTRmO3N0cm9rZS13aWR0aDoxLjk5OTk5OTY0MDAwMDAwMDAwO3N0cm9rZS1saW5lY2FwOnJvdW5kO3N0cm9rZS1saW5lam9pbjptaXRlcjtzdHJva2UtbWl0ZXJsaW1pdDo0O3N0cm9rZS1vcGFjaXR5OjE7c3Ryb2tlLWRhc2hhcnJheTpub25lO3N0cm9rZS1kYXNob2Zmc2V0OjA7ZmlsbC1vcGFjaXR5OjEiCiAgICAgICBpZD0icGF0aDMwMzctOCIKICAgICAgIHNvZGlwb2RpOmN4PSI3IgogICAgICAgc29kaXBvZGk6Y3k9IjQ0IgogICAgICAgc29kaXBvZGk6cng9IjYiCiAgICAgICBzb2RpcG9kaTpyeT0iNiIKICAgICAgIGQ9Ik0gMTMsNDQgQSA2LDYgMCAxIDEgMSw0NCA2LDYgMCAxIDEgMTMsNDQgeiIKICAgICAgIHRyYW5zZm9ybT0idHJhbnNsYXRlKDQsMCkiCiAgICAgICBpbmtzY2FwZTpleHBvcnQteGRwaT0iNDUiCiAgICAgICBpbmtzY2FwZTpleHBvcnQteWRwaT0iNDUiIC8+CiAgPC9nPgo8L3N2Zz4K
"""
Dim_Parallel_b64=\
"""
PD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0iVVRGLTgiIHN0YW5kYWxvbmU9Im5vIj8+CjwhLS0gQ3JlYXRlZCB3aXRoIElua3NjYXBlIChodHRwOi8vd3d3Lmlua3NjYXBlLm9yZy8pIC0tPgoKPHN2ZwogICB4bWxuczpkYz0iaHR0cDovL3B1cmwub3JnL2RjL2VsZW1lbnRzLzEuMS8iCiAgIHhtbG5zOmNjPSJodHRwOi8vY3JlYXRpdmVjb21tb25zLm9yZy9ucyMiCiAgIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyIKICAgeG1sbnM6c3ZnPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyIKICAgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIgogICB4bWxuczp4bGluaz0iaHR0cDovL3d3dy53My5vcmcvMTk5OS94bGluayIKICAgeG1sbnM6c29kaXBvZGk9Imh0dHA6Ly9zb2RpcG9kaS5zb3VyY2Vmb3JnZS5uZXQvRFREL3NvZGlwb2RpLTAuZHRkIgogICB4bWxuczppbmtzY2FwZT0iaHR0cDovL3d3dy5pbmtzY2FwZS5vcmcvbmFtZXNwYWNlcy9pbmtzY2FwZSIKICAgd2lkdGg9IjY0cHgiCiAgIGhlaWdodD0iNjRweCIKICAgaWQ9InN2ZzI3MjYiCiAgIHNvZGlwb2RpOnZlcnNpb249IjAuMzIiCiAgIGlua3NjYXBlOnZlcnNpb249IjAuOTIuMCByMTUyOTkiCiAgIHNvZGlwb2RpOmRvY25hbWU9IkRpc3RhbmNlX1BhcmFsbGVsLnN2ZyIKICAgaW5rc2NhcGU6b3V0cHV0X2V4dGVuc2lvbj0ib3JnLmlua3NjYXBlLm91dHB1dC5zdmcuaW5rc2NhcGUiCiAgIHZlcnNpb249IjEuMSI+CiAgPGRlZnMKICAgICBpZD0iZGVmczI3MjgiPgogICAgPGxpbmVhckdyYWRpZW50CiAgICAgICBpZD0ibGluZWFyR3JhZGllbnQzNzcwIgogICAgICAgaW5rc2NhcGU6Y29sbGVjdD0iYWx3YXlzIj4KICAgICAgPHN0b3AKICAgICAgICAgaWQ9InN0b3AzNzcyIgogICAgICAgICBvZmZzZXQ9IjAiCiAgICAgICAgIHN0eWxlPSJzdG9wLWNvbG9yOiMwNjk4OWE7c3RvcC1vcGFjaXR5OjEiIC8+CiAgICAgIDxzdG9wCiAgICAgICAgIGlkPSJzdG9wMzc3NCIKICAgICAgICAgb2Zmc2V0PSIxIgogICAgICAgICBzdHlsZT0ic3RvcC1jb2xvcjojMzRlMGUyO3N0b3Atb3BhY2l0eToxIiAvPgogICAgPC9saW5lYXJHcmFkaWVudD4KICAgIDxsaW5lYXJHcmFkaWVudAogICAgICAgaW5rc2NhcGU6Y29sbGVjdD0iYWx3YXlzIgogICAgICAgaWQ9ImxpbmVhckdyYWRpZW50Mzc2MCI+CiAgICAgIDxzdG9wCiAgICAgICAgIHN0eWxlPSJzdG9wLWNvbG9yOiMwNjk4OWE7c3RvcC1vcGFjaXR5OjEiCiAgICAgICAgIG9mZnNldD0iMCIKICAgICAgICAgaWQ9InN0b3AzNzYyIiAvPgogICAgICA8c3RvcAogICAgICAgICBzdHlsZT0ic3RvcC1jb2xvcjojMzRlMGUyO3N0b3Atb3BhY2l0eToxIgogICAgICAgICBvZmZzZXQ9IjEiCiAgICAgICAgIGlkPSJzdG9wMzc2NCIgLz4KICAgIDwvbGluZWFyR3JhZGllbnQ+CiAgICA8aW5rc2NhcGU6cGVyc3BlY3RpdmUKICAgICAgIHNvZGlwb2RpOnR5cGU9Imlua3NjYXBlOnBlcnNwM2QiCiAgICAgICBpbmtzY2FwZTp2cF94PSIwIDogMzIgOiAxIgogICAgICAgaW5rc2NhcGU6dnBfeT0iMCA6IDEwMDAgOiAwIgogICAgICAgaW5rc2NhcGU6dnBfej0iNjQgOiAzMiA6IDEiCiAgICAgICBpbmtzY2FwZTpwZXJzcDNkLW9yaWdpbj0iMzIgOiAyMS4zMzMzMzMgOiAxIgogICAgICAgaWQ9InBlcnNwZWN0aXZlMjczNCIgLz4KICAgIDxyYWRpYWxHcmFkaWVudAogICAgICAgaW5rc2NhcGU6Y29sbGVjdD0iYWx3YXlzIgogICAgICAgeGxpbms6aHJlZj0iI2xpbmVhckdyYWRpZW50MzE0NC00IgogICAgICAgaWQ9InJhZGlhbEdyYWRpZW50Mzg1MC05IgogICAgICAgZ3JhZGllbnRVbml0cz0idXNlclNwYWNlT25Vc2UiCiAgICAgICBncmFkaWVudFRyYW5zZm9ybT0ibWF0cml4KDEsMCwwLDAuNjk4NTI5NCwwLDIwMi44Mjg2MykiCiAgICAgICBjeD0iMjI1LjI2NDAyIgogICAgICAgY3k9IjY3Mi43OTczNiIKICAgICAgIGZ4PSIyMjUuMjY0MDIiCiAgICAgICBmeT0iNjcyLjc5NzM2IgogICAgICAgcj0iMzQuMzQ1MTg4IiAvPgogICAgPGxpbmVhckdyYWRpZW50CiAgICAgICBpbmtzY2FwZTpjb2xsZWN0PSJhbHdheXMiCiAgICAgICBpZD0ibGluZWFyR3JhZGllbnQzMTQ0LTQiPgogICAgICA8c3RvcAogICAgICAgICBzdHlsZT0ic3RvcC1jb2xvcjojZmZmZmZmO3N0b3Atb3BhY2l0eToxOyIKICAgICAgICAgb2Zmc2V0PSIwIgogICAgICAgICBpZD0ic3RvcDMxNDYtMiIgLz4KICAgICAgPHN0b3AKICAgICAgICAgc3R5bGU9InN0b3AtY29sb3I6I2ZmZmZmZjtzdG9wLW9wYWNpdHk6MDsiCiAgICAgICAgIG9mZnNldD0iMSIKICAgICAgICAgaWQ9InN0b3AzMTQ4LTAiIC8+CiAgICA8L2xpbmVhckdyYWRpZW50PgogICAgPGxpbmVhckdyYWRpZW50CiAgICAgICBpbmtzY2FwZTpjb2xsZWN0PSJhbHdheXMiCiAgICAgICB4bGluazpocmVmPSIjbGluZWFyR3JhZGllbnQzNzYwIgogICAgICAgaWQ9ImxpbmVhckdyYWRpZW50Mzc2NiIKICAgICAgIHgxPSItNTU2LjAyMzc0IgogICAgICAgeTE9Ii00MTguNDg2NDIiCiAgICAgICB4Mj0iLTQxMS43MDAwNyIKICAgICAgIHkyPSItMzA2LjUyMjM3IgogICAgICAgZ3JhZGllbnRVbml0cz0idXNlclNwYWNlT25Vc2UiIC8+CiAgICA8bGluZWFyR3JhZGllbnQKICAgICAgIGlua3NjYXBlOmNvbGxlY3Q9ImFsd2F5cyIKICAgICAgIHhsaW5rOmhyZWY9IiNsaW5lYXJHcmFkaWVudDM3NzAiCiAgICAgICBpZD0ibGluZWFyR3JhZGllbnQzNzY4IgogICAgICAgeDE9Ii01MDYuMjc3MzEiCiAgICAgICB5MT0iLTU1OS42NzUxMSIKICAgICAgIHgyPSItMzg1LjU1MjI1IgogICAgICAgeTI9Ii00NjEuODAwNzUiCiAgICAgICBncmFkaWVudFVuaXRzPSJ1c2VyU3BhY2VPblVzZSIgLz4KICAgIDxsaW5lYXJHcmFkaWVudAogICAgICAgaW5rc2NhcGU6Y29sbGVjdD0iYWx3YXlzIgogICAgICAgeGxpbms6aHJlZj0iI2xpbmVhckdyYWRpZW50Mzc3MC03IgogICAgICAgaWQ9ImxpbmVhckdyYWRpZW50Mzc2OC0xIgogICAgICAgeDE9Ii01MDYuMjc3MzEiCiAgICAgICB5MT0iLTU1OS42NzUxMSIKICAgICAgIHgyPSItMzg1LjU1MjI1IgogICAgICAgeTI9Ii00NjEuODAwNzUiCiAgICAgICBncmFkaWVudFVuaXRzPSJ1c2VyU3BhY2VPblVzZSIgLz4KICAgIDxsaW5lYXJHcmFkaWVudAogICAgICAgaWQ9ImxpbmVhckdyYWRpZW50Mzc3MC03IgogICAgICAgaW5rc2NhcGU6Y29sbGVjdD0iYWx3YXlzIj4KICAgICAgPHN0b3AKICAgICAgICAgaWQ9InN0b3AzNzcyLTQiCiAgICAgICAgIG9mZnNldD0iMCIKICAgICAgICAgc3R5bGU9InN0b3AtY29sb3I6IzA2OTg5YTtzdG9wLW9wYWNpdHk6MSIgLz4KICAgICAgPHN0b3AKICAgICAgICAgaWQ9InN0b3AzNzc0LTAiCiAgICAgICAgIG9mZnNldD0iMSIKICAgICAgICAgc3R5bGU9InN0b3AtY29sb3I6IzM0ZTBlMjtzdG9wLW9wYWNpdHk6MSIgLz4KICAgIDwvbGluZWFyR3JhZGllbnQ+CiAgICA8bGluZWFyR3JhZGllbnQKICAgICAgIGdyYWRpZW50VHJhbnNmb3JtPSJtYXRyaXgoNC4xMDE0ODI5LDQuMTU3NDI4LC00LjEwMTQ4MjksNC4xNTc0MjgsMTU3LjkyMjQ3LDMzOC4xMDEwOCkiCiAgICAgICB5Mj0iMjguMzk5MTg1IgogICAgICAgeDI9IjI1LjQ0NTIyMyIKICAgICAgIHkxPSI0MC4yMjc1MDkiCiAgICAgICB4MT0iNDMuMjg4ODkxIgogICAgICAgZ3JhZGllbnRVbml0cz0idXNlclNwYWNlT25Vc2UiCiAgICAgICBpZD0ibGluZWFyR3JhZGllbnQ0MDc1IgogICAgICAgeGxpbms6aHJlZj0iI2xpbmVhckdyYWRpZW50MzAyMCIKICAgICAgIGlua3NjYXBlOmNvbGxlY3Q9ImFsd2F5cyIgLz4KICAgIDxsaW5lYXJHcmFkaWVudAogICAgICAgaWQ9ImxpbmVhckdyYWRpZW50MzAyMCIKICAgICAgIGlua3NjYXBlOmNvbGxlY3Q9ImFsd2F5cyI+CiAgICAgIDxzdG9wCiAgICAgICAgIGlkPSJzdG9wMzAyMiIKICAgICAgICAgb2Zmc2V0PSIwIgogICAgICAgICBzdHlsZT0ic3RvcC1jb2xvcjojYzRhMDAwO3N0b3Atb3BhY2l0eToxIiAvPgogICAgICA8c3RvcAogICAgICAgICBpZD0ic3RvcDMwMjQiCiAgICAgICAgIG9mZnNldD0iMSIKICAgICAgICAgc3R5bGU9InN0b3AtY29sb3I6I2ZjZTk0ZjtzdG9wLW9wYWNpdHk6MSIgLz4KICAgIDwvbGluZWFyR3JhZGllbnQ+CiAgPC9kZWZzPgogIDxzb2RpcG9kaTpuYW1lZHZpZXcKICAgICBpZD0iYmFzZSIKICAgICBwYWdlY29sb3I9IiNmZmZmZmYiCiAgICAgYm9yZGVyY29sb3I9IiM2NjY2NjYiCiAgICAgYm9yZGVyb3BhY2l0eT0iMS4wIgogICAgIGlua3NjYXBlOnBhZ2VvcGFjaXR5PSIwLjAiCiAgICAgaW5rc2NhcGU6cGFnZXNoYWRvdz0iMiIKICAgICBpbmtzY2FwZTp6b29tPSI2Ljg1MDA5NjkiCiAgICAgaW5rc2NhcGU6Y3g9IjcuMTA5ODQxMSIKICAgICBpbmtzY2FwZTpjeT0iMzIiCiAgICAgaW5rc2NhcGU6Y3VycmVudC1sYXllcj0iZzQyODkiCiAgICAgc2hvd2dyaWQ9InRydWUiCiAgICAgaW5rc2NhcGU6ZG9jdW1lbnQtdW5pdHM9InB4IgogICAgIGlua3NjYXBlOmdyaWQtYmJveD0idHJ1ZSIKICAgICBpbmtzY2FwZTp3aW5kb3ctd2lkdGg9IjE1MzYiCiAgICAgaW5rc2NhcGU6d2luZG93LWhlaWdodD0iODAxIgogICAgIGlua3NjYXBlOndpbmRvdy14PSItOCIKICAgICBpbmtzY2FwZTp3aW5kb3cteT0iLTgiCiAgICAgaW5rc2NhcGU6d2luZG93LW1heGltaXplZD0iMSIKICAgICBpbmtzY2FwZTpzbmFwLWdsb2JhbD0iZmFsc2UiPgogICAgPGlua3NjYXBlOmdyaWQKICAgICAgIHR5cGU9Inh5Z3JpZCIKICAgICAgIGlkPSJncmlkMjk5MCIKICAgICAgIGVtcHNwYWNpbmc9IjIiCiAgICAgICB2aXNpYmxlPSJ0cnVlIgogICAgICAgZW5hYmxlZD0idHJ1ZSIKICAgICAgIHNuYXB2aXNpYmxlZ3JpZGxpbmVzb25seT0idHJ1ZSIgLz4KICA8L3NvZGlwb2RpOm5hbWVkdmlldz4KICA8ZwogICAgIGlkPSJsYXllcjEiCiAgICAgaW5rc2NhcGU6bGFiZWw9IkxheWVyIDEiCiAgICAgaW5rc2NhcGU6Z3JvdXBtb2RlPSJsYXllciI+CiAgICA8ZwogICAgICAgaWQ9Imc0Mjg5IgogICAgICAgdHJhbnNmb3JtPSJtYXRyaXgoMC4xNjIxMjgyLDAsMCwwLjE2MjEyODIsNi4zNjA1OTg2LC02Ni4xMDg4MDYpIj4KICAgICAgPGcKICAgICAgICAgaWQ9Imc4NzIiCiAgICAgICAgIHRyYW5zZm9ybT0ibWF0cml4KDAuODk0Mzc5NDYsMC4xNTU2NTQ4OCwtMC4xNTc3MDMyMywwLjg4Mjc2MjY4LDc3LjkxMDA0MSw4My4wNzcyNTgpIgogICAgICAgICBpbmtzY2FwZTpleHBvcnQteGRwaT0iNTEuMjAwMDY5IgogICAgICAgICBpbmtzY2FwZTpleHBvcnQteWRwaT0iNTEuMjAwMDY5Ij4KICAgICAgICA8cmVjdAogICAgICAgICAgIHRyYW5zZm9ybT0ibWF0cml4KC0wLjg0MTMyNzYxLC0wLjU0MDUyNTUzLDAuNTMzNTk5MDYsLTAuODQ1NzM3NTgsMCwwKSIKICAgICAgICAgICB5PSItNTIxLjg5ODYyIgogICAgICAgICAgIHg9Ii01OTkuNjE3NjgiCiAgICAgICAgICAgaGVpZ2h0PSI2Mi4wODA4NzUiCiAgICAgICAgICAgd2lkdGg9IjI4NS43MzI2NCIKICAgICAgICAgICBpZD0icmVjdDM5NDItNC05LTkiCiAgICAgICAgICAgc3R5bGU9ImNvbG9yOiMwMDAwMDA7ZGlzcGxheTppbmxpbmU7b3ZlcmZsb3c6dmlzaWJsZTt2aXNpYmlsaXR5OnZpc2libGU7ZmlsbDp1cmwoI2xpbmVhckdyYWRpZW50Mzc2OCk7ZmlsbC1vcGFjaXR5OjE7ZmlsbC1ydWxlOm5vbnplcm87c3Ryb2tlOiMwNDJhMmE7c3Ryb2tlLXdpZHRoOjEyLjMzNjEyNDQyO3N0cm9rZS1saW5lY2FwOmJ1dHQ7c3Ryb2tlLWxpbmVqb2luOnJvdW5kO3N0cm9rZS1taXRlcmxpbWl0OjQ7c3Ryb2tlLWRhc2hhcnJheTpub25lO3N0cm9rZS1kYXNob2Zmc2V0OjA7c3Ryb2tlLW9wYWNpdHk6MTttYXJrZXI6bm9uZTtlbmFibGUtYmFja2dyb3VuZDphY2N1bXVsYXRlIiAvPgogICAgICAgIDxwYXRoCiAgICAgICAgICAgc29kaXBvZGk6bm9kZXR5cGVzPSJjY2NjYyIKICAgICAgICAgICB0cmFuc2Zvcm09Im1hdHJpeCg2LjE2Nzk1ODQsMCwwLDYuMTY3OTU4NCwtMzkuMjMxOTA4LDQwNy43NTYzNykiCiAgICAgICAgICAgaW5rc2NhcGU6Y29ubmVjdG9yLWN1cnZhdHVyZT0iMCIKICAgICAgICAgICBpZD0icGF0aDM4MTAiCiAgICAgICAgICAgZD0iTSAxMC4wMTYwNzEsMjcuMTkyODQ3IDQ1LjYzNjM2NCw1MC4xMDIyNzMgNDIuNDA5MDkxLDU1LjI1IDYuNzcxMzg5MiwzMi4zNTcxNzYgWiIKICAgICAgICAgICBzdHlsZT0iZmlsbDpub25lO3N0cm9rZTojMzRlMGUyO3N0cm9rZS13aWR0aDoyO3N0cm9rZS1saW5lY2FwOmJ1dHQ7c3Ryb2tlLWxpbmVqb2luOm1pdGVyO3N0cm9rZS1vcGFjaXR5OjEiIC8+CiAgICAgIDwvZz4KICAgICAgPGcKICAgICAgICAgaWQ9Imc4NzYiCiAgICAgICAgIHRyYW5zZm9ybT0ibWF0cml4KDAuODgzMjc3NzksMC4xNTc0NDMzMywtMC4xNTU3NDU3MSwwLjg5MjkwNTUxLDE0Ny44ODYxNiw2LjE4MzQ1MykiCiAgICAgICAgIGlua3NjYXBlOmV4cG9ydC14ZHBpPSI1MS4yMDAwNjkiCiAgICAgICAgIGlua3NjYXBlOmV4cG9ydC15ZHBpPSI1MS4yMDAwNjkiPgogICAgICAgIDxyZWN0CiAgICAgICAgICAgdHJhbnNmb3JtPSJtYXRyaXgoLTAuODQxMzI3NjIsLTAuNTQwNTI1NTEsMC41MzM1OTkwNCwtMC44NDU3Mzc1OSwwLDApIgogICAgICAgICAgIHk9Ii0zODMuMjkwNSIKICAgICAgICAgICB4PSItNTk5LjY4MjI1IgogICAgICAgICAgIGhlaWdodD0iNjAuMDEzOTAxIgogICAgICAgICAgIHdpZHRoPSIyODUuMDQ4NTUiCiAgICAgICAgICAgaWQ9InJlY3QzOTQyLTQtOSIKICAgICAgICAgICBzdHlsZT0iY29sb3I6IzAwMDAwMDtkaXNwbGF5OmlubGluZTtvdmVyZmxvdzp2aXNpYmxlO3Zpc2liaWxpdHk6dmlzaWJsZTtmaWxsOnVybCgjbGluZWFyR3JhZGllbnQzNzY2KTtmaWxsLW9wYWNpdHk6MTtmaWxsLXJ1bGU6bm9uemVybztzdHJva2U6IzA0MmEyYTtzdHJva2Utd2lkdGg6MTIuMzM2MTI0NDI7c3Ryb2tlLWxpbmVjYXA6YnV0dDtzdHJva2UtbGluZWpvaW46cm91bmQ7c3Ryb2tlLW1pdGVybGltaXQ6NDtzdHJva2UtZGFzaGFycmF5Om5vbmU7c3Ryb2tlLWRhc2hvZmZzZXQ6MDtzdHJva2Utb3BhY2l0eToxO21hcmtlcjpub25lO2VuYWJsZS1iYWNrZ3JvdW5kOmFjY3VtdWxhdGUiIC8+CiAgICAgICAgPHBhdGgKICAgICAgICAgICBzb2RpcG9kaTpub2RldHlwZXM9ImNjY2NjIgogICAgICAgICAgIGlua3NjYXBlOmNvbm5lY3Rvci1jdXJ2YXR1cmU9IjAiCiAgICAgICAgICAgaWQ9InBhdGgzODEwLTQiCiAgICAgICAgICAgZD0iTSA5Ni4zNjgxNzEsNDU4LjEwNzQ3IDMxNi4wNzI2Niw1OTkuNDExODUgMjk2LjE2Njk4LDYzMS4xNjI4MiA3Ni4zNTUxMTEsNDg5Ljk2MDgzIFoiCiAgICAgICAgICAgc3R5bGU9ImZpbGw6bm9uZTtzdHJva2U6IzM0ZTBlMjtzdHJva2Utd2lkdGg6MTIuMzM1OTE2NTI7c3Ryb2tlLWxpbmVjYXA6YnV0dDtzdHJva2UtbGluZWpvaW46bWl0ZXI7c3Ryb2tlLW9wYWNpdHk6MSIgLz4KICAgICAgPC9nPgogICAgICA8ZwogICAgICAgICBpZD0iZzg2OCIKICAgICAgICAgaW5rc2NhcGU6ZXhwb3J0LXhkcGk9IjUxLjIwMDA2OSIKICAgICAgICAgaW5rc2NhcGU6ZXhwb3J0LXlkcGk9IjUxLjIwMDA2OSI+CiAgICAgICAgPHBhdGgKICAgICAgICAgICBpbmtzY2FwZTpleHBvcnQteWRwaT0iNTEuMjAwMDY5IgogICAgICAgICAgIGlua3NjYXBlOmV4cG9ydC14ZHBpPSI1MS4yMDAwNjkiCiAgICAgICAgICAgc29kaXBvZGk6bm9kZXR5cGVzPSJjY2NjY2NjY2NjY2NjY2MiCiAgICAgICAgICAgaWQ9InBhdGgzNzcwLTEiCiAgICAgICAgICAgZD0ibSAxNzQuMzI4NDEsNTI5LjM0Mjc2IDE2LjQwNTk0LDE2LjYyOTcxIC05MC4yMzI2Myw5MS40NjM0MyAtMTYuNDA1OTM1LC0xNi42Mjk3MyBjIDAsMjQuOTQ0NTggLTQuMTAxNDc2LDQ1LjczMTcyIC04LjIwMjk2NSw1OC4yMDQwMSBsIC00LjEwMTQ3NiwxMi40NzIyNyAxMi4zMDQ0NDEsLTQuMTU3NDIgYyAxMi4zMDQ0NDgsLTQuMTU3NDMgMzIuODExODY1LC04LjMxNDg1IDU3LjQyMDc2NSwtOC4zMTQ4NSBsIC0xNi40MDU5MywtMTYuNjI5NzIgOTAuMjMyNjEsLTkxLjQ2MzQyIDE2LjQwNTk0LDE2LjYyOTcyIGMgMCwtMjQuOTQ0NTggNC4xMDE0OCwtNDUuNzMxNzEgOC4yMDI5NywtNTguMjA0IGwgNC4xMDE0NywtMTIuNDcyMjggLTEyLjMwNDQ0LDQuMTU3NDIgYyAtMTIuMzA0NDUsNC4xNTc0MyAtMzIuODExODYsOC4zMTQ4NiAtNTcuNDIwNzYsOC4zMTQ4NiB6IgogICAgICAgICAgIHN0eWxlPSJjb2xvcjojMDAwMDAwO2ZvbnQtc3R5bGU6bm9ybWFsO2ZvbnQtdmFyaWFudDpub3JtYWw7Zm9udC13ZWlnaHQ6bm9ybWFsO2ZvbnQtc3RyZXRjaDpub3JtYWw7Zm9udC1zaXplOm1lZGl1bTtsaW5lLWhlaWdodDpub3JtYWw7Zm9udC1mYW1pbHk6c2Fucy1zZXJpZjt0ZXh0LWluZGVudDowO3RleHQtYWxpZ246c3RhcnQ7dGV4dC1kZWNvcmF0aW9uOm5vbmU7dGV4dC1kZWNvcmF0aW9uLWxpbmU6bm9uZTtsZXR0ZXItc3BhY2luZzpub3JtYWw7d29yZC1zcGFjaW5nOm5vcm1hbDt0ZXh0LXRyYW5zZm9ybTpub25lO3dyaXRpbmctbW9kZTpsci10YjtkaXJlY3Rpb246bHRyO2Jhc2VsaW5lLXNoaWZ0OmJhc2VsaW5lO3RleHQtYW5jaG9yOnN0YXJ0O2Rpc3BsYXk6aW5saW5lO292ZXJmbG93OnZpc2libGU7dmlzaWJpbGl0eTp2aXNpYmxlO2ZpbGw6dXJsKCNsaW5lYXJHcmFkaWVudDQwNzUpO2ZpbGwtb3BhY2l0eToxO2ZpbGwtcnVsZTpub256ZXJvO3N0cm9rZTpub25lO3N0cm9rZS13aWR0aDoxMi4zMzU5MTY1MjtzdHJva2UtbGluZWNhcDpidXR0O3N0cm9rZS1saW5lam9pbjpyb3VuZDtzdHJva2UtbWl0ZXJsaW1pdDo0O3N0cm9rZS1kYXNoYXJyYXk6bm9uZTtzdHJva2UtZGFzaG9mZnNldDowO3N0cm9rZS1vcGFjaXR5OjE7ZW5hYmxlLWJhY2tncm91bmQ6YWNjdW11bGF0ZSIKICAgICAgICAgICBpbmtzY2FwZTpjb25uZWN0b3ItY3VydmF0dXJlPSIwIiAvPgogICAgICAgIDxwYXRoCiAgICAgICAgICAgaW5rc2NhcGU6ZXhwb3J0LXlkcGk9IjUxLjIwMDA2OSIKICAgICAgICAgICBpbmtzY2FwZTpleHBvcnQteGRwaT0iNTEuMjAwMDY5IgogICAgICAgICAgIHNvZGlwb2RpOm5vZGV0eXBlcz0iY2MiCiAgICAgICAgICAgaW5rc2NhcGU6Y29ubmVjdG9yLWN1cnZhdHVyZT0iMCIKICAgICAgICAgICBpZD0icGF0aDM4NjQiCiAgICAgICAgICAgZD0ibSAyMjMuNTQ2Miw1MjkuMzQyNzYgLTQxLjAxNDgyLDguMzE0ODYiCiAgICAgICAgICAgc3R5bGU9ImZpbGw6bm9uZTtzdHJva2U6I2ZjZTk0ZjtzdHJva2Utd2lkdGg6MTIuMzM1OTE2NTI7c3Ryb2tlLWxpbmVjYXA6YnV0dDtzdHJva2UtbGluZWpvaW46bWl0ZXI7c3Ryb2tlLW9wYWNpdHk6MSIgLz4KICAgICAgICA8cGF0aAogICAgICAgICAgIGlua3NjYXBlOmV4cG9ydC15ZHBpPSI1MS4yMDAwNjkiCiAgICAgICAgICAgaW5rc2NhcGU6ZXhwb3J0LXhkcGk9IjUxLjIwMDA2OSIKICAgICAgICAgICBzb2RpcG9kaTpub2RldHlwZXM9ImNjIgogICAgICAgICAgIGlua3NjYXBlOmNvbm5lY3Rvci1jdXJ2YXR1cmU9IjAiCiAgICAgICAgICAgaWQ9InBhdGgzODY0LTQiCiAgICAgICAgICAgZD0ibSA4NC4wOTU3ODUsNjcwLjY5NTMxIDguMjAyOTY2LC00MS41NzQyNyIKICAgICAgICAgICBzdHlsZT0iZmlsbDpub25lO3N0cm9rZTojZmNlOTRmO3N0cm9rZS13aWR0aDoxMi4zMzU5MTY1MjtzdHJva2UtbGluZWNhcDpidXR0O3N0cm9rZS1saW5lam9pbjptaXRlcjtzdHJva2Utb3BhY2l0eToxIiAvPgogICAgICAgIDxwYXRoCiAgICAgICAgICAgaW5rc2NhcGU6ZXhwb3J0LXlkcGk9IjUxLjIwMDA2OSIKICAgICAgICAgICBpbmtzY2FwZTpleHBvcnQteGRwaT0iNTEuMjAwMDY5IgogICAgICAgICAgIHNvZGlwb2RpOm5vZGV0eXBlcz0iY2MiCiAgICAgICAgICAgaW5rc2NhcGU6Y29ubmVjdG9yLWN1cnZhdHVyZT0iMCIKICAgICAgICAgICBpZD0icGF0aDM4NjYiCiAgICAgICAgICAgZD0iTSAyMzEuNzQ5MTcsNTIxLjAyNzkgNzEuOTEyODI4LDY4Mi43MjQ4MyIKICAgICAgICAgICBzdHlsZT0iZmlsbDpub25lO3N0cm9rZTojZmNlOTRmO3N0cm9rZS13aWR0aDoxMi4zMzU5MTY1MjtzdHJva2UtbGluZWNhcDpyb3VuZDtzdHJva2UtbGluZWpvaW46bWl0ZXI7c3Ryb2tlLW9wYWNpdHk6MSIgLz4KICAgICAgICA8cGF0aAogICAgICAgICAgIGlua3NjYXBlOmV4cG9ydC15ZHBpPSI1MS4yMDAwNjkiCiAgICAgICAgICAgaW5rc2NhcGU6ZXhwb3J0LXhkcGk9IjUxLjIwMDA2OSIKICAgICAgICAgICBpbmtzY2FwZTpjb25uZWN0b3ItY3VydmF0dXJlPSIwIgogICAgICAgICAgIGlkPSJwYXRoMzg2OCIKICAgICAgICAgICBkPSJtIDE5MC43MzQzNSw1NDUuOTcyNDcgMjAuNTA3NCwtNC4xNTc0MiIKICAgICAgICAgICBzdHlsZT0iZmlsbDpub25lO3N0cm9rZTojZmNlOTRmO3N0cm9rZS13aWR0aDoxMi4zMzU5MTY1MjtzdHJva2UtbGluZWNhcDpidXR0O3N0cm9rZS1saW5lam9pbjptaXRlcjtzdHJva2Utb3BhY2l0eToxIiAvPgogICAgICAgIDxwYXRoCiAgICAgICAgICAgaW5rc2NhcGU6ZXhwb3J0LXlkcGk9IjUxLjIwMDA2OSIKICAgICAgICAgICBpbmtzY2FwZTpleHBvcnQteGRwaT0iNTEuMjAwMDY5IgogICAgICAgICAgIGlua3NjYXBlOmNvbm5lY3Rvci1jdXJ2YXR1cmU9IjAiCiAgICAgICAgICAgaWQ9InBhdGgzODY4LTgiCiAgICAgICAgICAgZD0ibSAxMDAuNTAxNzIsNjM3LjQzNTkgLTQuMTAxNDg3LDIwLjc4NzEzIgogICAgICAgICAgIHN0eWxlPSJmaWxsOm5vbmU7c3Ryb2tlOiNmY2U5NGY7c3Ryb2tlLXdpZHRoOjEyLjMzNTkxNjUyO3N0cm9rZS1saW5lY2FwOmJ1dHQ7c3Ryb2tlLWxpbmVqb2luOm1pdGVyO3N0cm9rZS1vcGFjaXR5OjEiIC8+CiAgICAgICAgPHBhdGgKICAgICAgICAgICBpbmtzY2FwZTpleHBvcnQteWRwaT0iNTEuMjAwMDY5IgogICAgICAgICAgIGlua3NjYXBlOmV4cG9ydC14ZHBpPSI1MS4yMDAwNjkiCiAgICAgICAgICAgc29kaXBvZGk6bm9kZXR5cGVzPSJjY2NjY2NjY2NjY2NjY2MiCiAgICAgICAgICAgaWQ9InBhdGgzNzcwLTkiCiAgICAgICAgICAgZD0ibSAxNzUuNzY1NTEsNTI1LjgyODcgMTcuNjIyNzQsMTcuNjIyNzUgLTk2LjkyNTA3OSw5Ni45MjUwNyAtMTcuNjIyNzMzLC0xNy42MjI3NSBjIDAsMjYuNDM0MTIgLTQuNDA1NjgsNDguNDYyNTQgLTguODExMzczLDYxLjY3OTYgbCAtNC40MDU2OCwxMy4yMTcwNCAxMy4yMTcwNTMsLTQuNDA1NjcgYyAxMy4yMTcwNTMsLTQuNDA1NjkgMzUuMjQ1NDcyLC04LjgxMTM3IDYxLjY3OTU5MiwtOC44MTEzNyBsIC0xNy42MjI3NCwtMTcuNjIyNzUgOTYuOTI1MDYsLTk2LjkyNTA2IDE3LjYyMjc1LDE3LjYyMjc0IGMgMCwtMjYuNDM0MTIgNC40MDU2OCwtNDguNDYyNTQgOC44MTEzNiwtNjEuNjc5NiBsIDQuNDA1NjgsLTEzLjIxNzA0IC0xMy4yMTcwNCw0LjQwNTY3IGMgLTEzLjIxNzA2LDQuNDA1NjkgLTM1LjI0NTQ4LDguODExMzcgLTYxLjY3OTU5LDguODExMzcgeiIKICAgICAgICAgICBzdHlsZT0iY29sb3I6IzAwMDAwMDtmb250LXN0eWxlOm5vcm1hbDtmb250LXZhcmlhbnQ6bm9ybWFsO2ZvbnQtd2VpZ2h0Om5vcm1hbDtmb250LXN0cmV0Y2g6bm9ybWFsO2ZvbnQtc2l6ZTptZWRpdW07bGluZS1oZWlnaHQ6bm9ybWFsO2ZvbnQtZmFtaWx5OnNhbnMtc2VyaWY7dGV4dC1pbmRlbnQ6MDt0ZXh0LWFsaWduOnN0YXJ0O3RleHQtZGVjb3JhdGlvbjpub25lO3RleHQtZGVjb3JhdGlvbi1saW5lOm5vbmU7bGV0dGVyLXNwYWNpbmc6bm9ybWFsO3dvcmQtc3BhY2luZzpub3JtYWw7dGV4dC10cmFuc2Zvcm06bm9uZTt3cml0aW5nLW1vZGU6bHItdGI7ZGlyZWN0aW9uOmx0cjtiYXNlbGluZS1zaGlmdDpiYXNlbGluZTt0ZXh0LWFuY2hvcjpzdGFydDtkaXNwbGF5OmlubGluZTtvdmVyZmxvdzp2aXNpYmxlO3Zpc2liaWxpdHk6dmlzaWJsZTtmaWxsOm5vbmU7c3Ryb2tlOiMzMDJiMDA7c3Ryb2tlLXdpZHRoOjEyLjMzNTkxNjUyO3N0cm9rZS1saW5lY2FwOmJ1dHQ7c3Ryb2tlLWxpbmVqb2luOnJvdW5kO3N0cm9rZS1taXRlcmxpbWl0OjQ7c3Ryb2tlLWRhc2hhcnJheTpub25lO3N0cm9rZS1kYXNob2Zmc2V0OjA7c3Ryb2tlLW9wYWNpdHk6MTtlbmFibGUtYmFja2dyb3VuZDphY2N1bXVsYXRlIgogICAgICAgICAgIGlua3NjYXBlOmNvbm5lY3Rvci1jdXJ2YXR1cmU9IjAiIC8+CiAgICAgIDwvZz4KICAgIDwvZz4KICA8L2c+CiAgPG1ldGFkYXRhCiAgICAgaWQ9Im1ldGFkYXRhNjU5MSI+CiAgICA8cmRmOlJERj4KICAgICAgPGNjOldvcmsKICAgICAgICAgcmRmOmFib3V0PSIiPgogICAgICAgIDxkYzpmb3JtYXQ+aW1hZ2Uvc3ZnK3htbDwvZGM6Zm9ybWF0PgogICAgICAgIDxkYzp0eXBlCiAgICAgICAgICAgcmRmOnJlc291cmNlPSJodHRwOi8vcHVybC5vcmcvZGMvZGNtaXR5cGUvU3RpbGxJbWFnZSIgLz4KICAgICAgICA8ZGM6dGl0bGUgLz4KICAgICAgICA8Y2M6bGljZW5zZQogICAgICAgICAgIHJkZjpyZXNvdXJjZT0iIiAvPgogICAgICAgIDxkYzpkYXRlPk1vbiBNYXIgMTIgMTc6MjA6MDMgMjAxMiAtMDMwMDwvZGM6ZGF0ZT4KICAgICAgICA8ZGM6Y3JlYXRvcj4KICAgICAgICAgIDxjYzpBZ2VudD4KICAgICAgICAgICAgPGRjOnRpdGxlPltZb3JpayB2YW4gSGF2cmVdPC9kYzp0aXRsZT4KICAgICAgICAgIDwvY2M6QWdlbnQ+CiAgICAgICAgPC9kYzpjcmVhdG9yPgogICAgICAgIDxkYzpyaWdodHM+CiAgICAgICAgICA8Y2M6QWdlbnQ+CiAgICAgICAgICAgIDxkYzp0aXRsZT5GcmVlQ0FEIExHUEwyKzwvZGM6dGl0bGU+CiAgICAgICAgICA8L2NjOkFnZW50PgogICAgICAgIDwvZGM6cmlnaHRzPgogICAgICAgIDxkYzpwdWJsaXNoZXI+CiAgICAgICAgICA8Y2M6QWdlbnQ+CiAgICAgICAgICAgIDxkYzp0aXRsZT5GcmVlQ0FEPC9kYzp0aXRsZT4KICAgICAgICAgIDwvY2M6QWdlbnQ+CiAgICAgICAgPC9kYzpwdWJsaXNoZXI+CiAgICAgICAgPGRjOmlkZW50aWZpZXI+RnJlZUNBRC9zcmMvTW9kL0RyYWZ0L1Jlc291cmNlcy9pY29ucy9TbmFwX1BhcmFsbGVsLnN2ZzwvZGM6aWRlbnRpZmllcj4KICAgICAgICA8ZGM6cmVsYXRpb24+aHR0cDovL3d3dy5mcmVlY2Fkd2ViLm9yZy93aWtpL2luZGV4LnBocD90aXRsZT1BcnR3b3JrPC9kYzpyZWxhdGlvbj4KICAgICAgICA8ZGM6Y29udHJpYnV0b3I+CiAgICAgICAgICA8Y2M6QWdlbnQ+CiAgICAgICAgICAgIDxkYzp0aXRsZT5bYWdyeXNvbl0gQWxleGFuZGVyIEdyeXNvbjwvZGM6dGl0bGU+CiAgICAgICAgICA8L2NjOkFnZW50PgogICAgICAgIDwvZGM6Y29udHJpYnV0b3I+CiAgICAgICAgPGRjOmRlc2NyaXB0aW9uPlR3byBwYXJhbGxlbCBsaW5lcyBhdCBhIHNsaWdodCBhbmdsZTwvZGM6ZGVzY3JpcHRpb24+CiAgICAgICAgPGRjOnN1YmplY3Q+CiAgICAgICAgICA8cmRmOkJhZz4KICAgICAgICAgICAgPHJkZjpsaT5saW5lPC9yZGY6bGk+CiAgICAgICAgICAgIDxyZGY6bGk+bGluZXM8L3JkZjpsaT4KICAgICAgICAgICAgPHJkZjpsaT5wYXJhbGxlbDwvcmRmOmxpPgogICAgICAgICAgPC9yZGY6QmFnPgogICAgICAgIDwvZGM6c3ViamVjdD4KICAgICAgPC9jYzpXb3JrPgogICAgPC9yZGY6UkRGPgogIDwvbWV0YWRhdGE+Cjwvc3ZnPgo=
"""




"""
    +-----------------------------------------------+
    |       add the command to the workbench        |
    +-----------------------------------------------+
"""
Gui.addCommand( 'Asm4_Measure', MeasureCmd() )

