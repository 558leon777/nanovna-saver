#  NanoVNASaver - a python program to view and export Touchstone data from a NanoVNA
#  Copyright (C) 2019.  Rune B. Broberg
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.
import collections
import math
from typing import List

from PyQt5 import QtGui, QtWidgets, QtCore
from PyQt5.QtCore import pyqtSignal

Datapoint = collections.namedtuple('Datapoint', 'freq re im')


class Marker(QtCore.QObject):
    name = "Marker"
    frequency = 0
    color = QtGui.QColor()
    location = -1

    updated = pyqtSignal()

    def __init__(self, name, initialColor, frequency=""):
        super().__init__()
        self.name = name

        if frequency.isnumeric():
            self.frequency = int(frequency)
        self.frequencyInput = QtWidgets.QLineEdit(frequency)
        self.frequencyInput.setAlignment(QtCore.Qt.AlignRight)
        self.frequencyInput.returnPressed.connect(lambda: self.setFrequency(self.frequencyInput.text()))

        ################################################################################################################
        # Data display label
        ################################################################################################################

        self.frequency_label = QtWidgets.QLabel("")
        self.frequency_label.setMinimumWidth(100)
        self.impedance_label = QtWidgets.QLabel("")
        self.returnloss_label = QtWidgets.QLabel("")
        self.returnloss_label.setMinimumWidth(80)
        self.vswr_label = QtWidgets.QLabel("")
        self.inductance_label = QtWidgets.QLabel("")
        self.capacitance_label = QtWidgets.QLabel("")
        self.gain_label = QtWidgets.QLabel("")
        self.phase_label = QtWidgets.QLabel("")
        self.quality_factor_label = QtWidgets.QLabel("")

        ################################################################################################################
        # Marker control layout
        ################################################################################################################

        self.btnColorPicker = QtWidgets.QPushButton("█")
        self.btnColorPicker.setFixedWidth(20)
        self.setColor(initialColor)
        self.btnColorPicker.clicked.connect(lambda: self.setColor(QtWidgets.QColorDialog.getColor(self.color, options=QtWidgets.QColorDialog.ShowAlphaChannel)))
        self.radioButton = QtWidgets.QRadioButton()

        self.layout = QtWidgets.QHBoxLayout()
        self.layout.addWidget(self.frequencyInput)
        self.layout.addWidget(self.btnColorPicker)
        self.layout.addWidget(self.radioButton)

        ################################################################################################################
        # Data display layout
        ################################################################################################################

        self.group_box = QtWidgets.QGroupBox(self.name)
        box_layout = QtWidgets.QHBoxLayout(self.group_box)

        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.VLine)
        #line.setFrameShadow(QtWidgets.QFrame.Sunken)

        left_form = QtWidgets.QFormLayout()
        right_form = QtWidgets.QFormLayout()
        box_layout.addLayout(left_form)
        box_layout.addWidget(line)
        box_layout.addLayout(right_form)

        # Left side
        left_form.addRow(QtWidgets.QLabel("Frequency:"), self.frequency_label)
        left_form.addRow(QtWidgets.QLabel("Impedance:"), self.impedance_label)
        left_form.addRow(QtWidgets.QLabel("L equiv.:"), self.inductance_label)
        left_form.addRow(QtWidgets.QLabel("C equiv.:"), self.capacitance_label)
        left_form.addRow(QtWidgets.QLabel("Q:"), self.quality_factor_label)

        # Right side
        right_form.addRow(QtWidgets.QLabel("Return loss:"), self.returnloss_label)
        right_form.addRow(QtWidgets.QLabel("VSWR:"), self.vswr_label)
        right_form.addRow(QtWidgets.QLabel("S21 Gain:"), self.gain_label)
        right_form.addRow(QtWidgets.QLabel("S21 Phase:"), self.phase_label)

    def setFrequency(self, frequency):
        from .NanoVNASaver import NanoVNASaver
        f = NanoVNASaver.parseFrequency(frequency)
        if f > 0:
            self.frequency = f
            self.updated.emit()
        else:
            self.frequency = 0
            self.updated.emit()
            return

    def setColor(self, color):
        if color.isValid():
            self.color = color
            p = self.btnColorPicker.palette()
            p.setColor(QtGui.QPalette.ButtonText, self.color)
            self.btnColorPicker.setPalette(p)

    def getRow(self):
        return (QtWidgets.QLabel(self.name), self.layout)

    def findLocation(self, data: List[Datapoint]):
        self.location = -1
        if self.frequency == 0:
            # No frequency set for this marker
            return
        if len(data) == 0:
            # Set the frequency before loading any data
            return

        stepsize = data[1].freq-data[0].freq
        for i in range(len(data)):
            if abs(data[i].freq-self.frequency) <= (stepsize/2):
                self.location = i
                return

    def getGroupBox(self):
        return self.group_box
    
    def resetLabels(self):
        self.frequency_label.setText("")
        self.impedance_label.setText("")
        self.vswr_label.setText("")
        self.returnloss_label.setText("")
        self.inductance_label.setText("")
        self.capacitance_label.setText("")
        self.gain_label.setText("")
        self.phase_label.setText("")
        self.quality_factor_label.setText("")

    def updateLabels(self, s11data: List[Datapoint], s21data: List[Datapoint]):
        from NanoVNASaver.Chart import PhaseChart
        from NanoVNASaver.NanoVNASaver import NanoVNASaver
        if self.location != -1:
            im50, re50, vswr = NanoVNASaver.vswr(s11data[self.location])
            if im50 < 0:
                im50str = " -j" + str(round(-1 * im50, 3))
            else:
                im50str = " +j" + str(round(im50, 3))
            self.frequency_label.setText(NanoVNASaver.formatFrequency(s11data[self.location].freq))
            self.impedance_label.setText(str(round(re50, 3)) + im50str)
            self.returnloss_label.setText(str(round(20 * math.log10((vswr - 1) / (vswr + 1)), 3)) + " dB")
            capacitance = NanoVNASaver.capacitanceEquivalent(im50, s11data[self.location].freq)
            inductance = NanoVNASaver.inductanceEquivalent(im50, s11data[self.location].freq)
            self.inductance_label.setText(inductance)
            self.capacitance_label.setText(capacitance)
            vswr = round(vswr, 3)
            if vswr < 0:
                vswr = "-"
            self.vswr_label.setText(str(vswr))
            self.quality_factor_label.setText(str(round(NanoVNASaver.qualifyFactor(s11data[self.location]), 1)))
            if len(s21data) == len(s11data):
                _, _, vswr = NanoVNASaver.vswr(s21data[self.location])
                self.gain_label.setText(str(round(20 * math.log10((vswr - 1) / (vswr + 1)), 3)) + " dB")
                self.phase_label.setText(
                    str(round(PhaseChart.angle(s21data[self.location]), 2)) + "\N{DEGREE SIGN}")
