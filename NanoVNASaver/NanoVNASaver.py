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
import threading
from time import sleep, strftime, gmtime
from typing import List

import numpy as np
import serial
from PyQt5 import QtWidgets, QtCore, QtGui
from serial.tools import list_ports

from .Chart import Chart, PhaseChart, VSWRChart, PolarChart, SmithChart, LogMagChart
from .Calibration import CalibrationWindow, Calibration
from .Marker import Marker
from .SweepWorker import SweepWorker
from .Touchstone import Touchstone

Datapoint = collections.namedtuple('Datapoint', 'freq re im')

VID = 1155
PID = 22336


class NanoVNASaver(QtWidgets.QWidget):
    version = "0.0.7"

    def __init__(self):
        super().__init__()

        self.threadpool = QtCore.QThreadPool()
        print("Max thread count " + str(self.threadpool.maxThreadCount()))
        self.worker = SweepWorker(self)

        self.noSweeps = 1  # Number of sweeps to run

        self.serialLock = threading.Lock()
        self.serial = serial.Serial()

        self.dataLock = threading.Lock()
        self.data: List[Datapoint] = []
        self.data21: List[Datapoint] = []
        self.referenceS11data: List[Datapoint] = []
        self.referenceS21data: List[Datapoint] = []

        self.sweepSource = ""
        self.referenceSource = ""

        self.calibration = Calibration()

        self.markers = []

        self.serialPort = self.getport()
        # self.serialSpeed = "115200"

        self.color = QtGui.QColor(160, 140, 20, 128)
        self.referenceColor = QtGui.QColor(0, 0, 255, 32)

        self.baseTitle = "NanoVNA Saver " + NanoVNASaver.version
        self.updateTitle()
        layout = QtWidgets.QGridLayout()
        scrollarea = QtWidgets.QScrollArea()
        outer = QtWidgets.QVBoxLayout()
        outer.addWidget(scrollarea)
        self.setLayout(outer)
        scrollarea.setWidgetResizable(True)
        self.resize(1350, 950)
        scrollarea.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.MinimumExpanding)
        self.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.MinimumExpanding)
        widget = QtWidgets.QWidget()
        widget.setLayout(layout)
        scrollarea.setWidget(widget)

        self.s11SmithChart = SmithChart("S11 Smith Chart")
        self.s21PolarChart = PolarChart("S21 Polar Plot")
        self.s11LogMag = LogMagChart("S11 Return Loss")
        self.s21LogMag = LogMagChart("S21 Gain")
        self.s11Phase = PhaseChart("S11 Phase")
        self.s21Phase = PhaseChart("S21 Phase")
        self.s11VSWR = VSWRChart("S11 VSWR")

        self.s11charts: List[Chart] = []
        self.s11charts.append(self.s11SmithChart)
        self.s11charts.append(self.s11LogMag)
        self.s11charts.append(self.s11Phase)
        self.s11charts.append(self.s11VSWR)

        self.s21charts: List[Chart] = []
        self.s21charts.append(self.s21PolarChart)
        self.s21charts.append(self.s21LogMag)
        self.s21charts.append(self.s21Phase)

        self.charts = self.s11charts + self.s21charts

        left_column = QtWidgets.QVBoxLayout()
        marker_column = QtWidgets.QVBoxLayout()
        right_column = QtWidgets.QVBoxLayout()

        layout.addLayout(left_column, 0, 0)
        layout.addLayout(marker_column, 0, 1)
        layout.addLayout(right_column, 0, 2)

        ################################################################################################################
        #  Sweep control
        ################################################################################################################

        sweep_control_box = QtWidgets.QGroupBox()
        sweep_control_box.setMaximumWidth(250)
        sweep_control_box.setTitle("Sweep control")
        sweep_control_layout = QtWidgets.QFormLayout(sweep_control_box)

        self.sweepStartInput = QtWidgets.QLineEdit("")
        self.sweepStartInput.setAlignment(QtCore.Qt.AlignRight)

        sweep_control_layout.addRow(QtWidgets.QLabel("Sweep start"), self.sweepStartInput)

        self.sweepEndInput = QtWidgets.QLineEdit("")
        self.sweepEndInput.setAlignment(QtCore.Qt.AlignRight)

        sweep_control_layout.addRow(QtWidgets.QLabel("Sweep end"), self.sweepEndInput)

        self.sweepCountInput = QtWidgets.QLineEdit("")
        self.sweepCountInput.setAlignment(QtCore.Qt.AlignRight)
        self.sweepCountInput.setText("1")

        sweep_control_layout.addRow(QtWidgets.QLabel("Sweep count"), self.sweepCountInput)

        self.btnColorPicker = QtWidgets.QPushButton("█")
        self.btnColorPicker.setFixedWidth(20)
        self.setSweepColor(self.color)
        self.btnColorPicker.clicked.connect(lambda:self.setSweepColor(QtWidgets.QColorDialog.getColor(self.color,options=QtWidgets.QColorDialog.ShowAlphaChannel)))

        sweep_control_layout.addRow("Sweep color", self.btnColorPicker)

        self.sweepProgressBar = QtWidgets.QProgressBar()
        self.sweepProgressBar.setMaximum(100)
        self.sweepProgressBar.setValue(0)
        sweep_control_layout.addRow(self.sweepProgressBar)

        self.btnSweep = QtWidgets.QPushButton("Sweep")
        self.btnSweep.clicked.connect(self.sweep)
        sweep_control_layout.addRow(self.btnSweep)

        left_column.addWidget(sweep_control_box)

        ################################################################################################################
        #  Marker control
        ################################################################################################################

        marker_control_box = QtWidgets.QGroupBox()
        marker_control_box.setTitle("Markers")
        marker_control_box.setMaximumWidth(300)
        marker_control_layout = QtWidgets.QFormLayout(marker_control_box)

        mouse_marker = Marker("Mouse marker", QtGui.QColor(20, 255, 20))
        mouse_marker.updated.connect(self.dataUpdated)
        self.markers.append(mouse_marker)

        marker1 = Marker("Marker 1", QtGui.QColor(255, 0, 20))
        marker1.updated.connect(self.dataUpdated)
        label, layout = marker1.getRow()
        marker_control_layout.addRow(label, layout)
        self.markers.append(marker1)

        marker2 = Marker("Marker 2", QtGui.QColor(20, 0, 255))
        marker2.updated.connect(self.dataUpdated)
        label, layout = marker2.getRow()
        marker_control_layout.addRow(label, layout)
        self.markers.append(marker2)

        for c in self.charts:
            c.setMarkers(self.markers)

        self.mousemarker_frequency_label = QtWidgets.QLabel("")
        label, layout = mouse_marker.getRow()
        marker_control_layout.addRow(label, layout)
        mouse_marker.frequencyInput.setDisabled(True)
        marker_column.addWidget(marker_control_box)

        marker1_box = QtWidgets.QGroupBox("Marker 1")
        marker1_box_layout = QtWidgets.QFormLayout(marker1_box)

        marker_column.addWidget(marker1_box)

        self.marker1_impedance_label = QtWidgets.QLabel("")
        marker1_box_layout.addRow(QtWidgets.QLabel("Impedance:"), self.marker1_impedance_label)
        self.marker1_returnloss_label = QtWidgets.QLabel("")
        marker1_box_layout.addRow(QtWidgets.QLabel("Return loss:"), self.marker1_returnloss_label)
        self.marker1_vswr_label = QtWidgets.QLabel("")
        marker1_box_layout.addRow(QtWidgets.QLabel("VSWR:"), self.marker1_vswr_label)
        self.marker1_reactance_label = QtWidgets.QLabel("")
        marker1_box_layout.addRow(QtWidgets.QLabel("Reactance:"), self.marker1_reactance_label)
        self.marker1_gain_label = QtWidgets.QLabel("")
        marker1_box_layout.addRow(QtWidgets.QLabel("S21 Gain:"), self.marker1_gain_label)
        self.marker1_phase_label = QtWidgets.QLabel("")
        marker1_box_layout.addRow(QtWidgets.QLabel("S21 Phase:"), self.marker1_phase_label)

        marker2_box = QtWidgets.QGroupBox("Marker 2")
        marker2_box_layout = QtWidgets.QFormLayout(marker2_box)

        marker_column.addWidget(marker2_box)

        self.marker2_impedance_label = QtWidgets.QLabel("")
        marker2_box_layout.addRow(QtWidgets.QLabel("Impedance:"), self.marker2_impedance_label)
        self.marker2_returnloss_label = QtWidgets.QLabel("")
        marker2_box_layout.addRow(QtWidgets.QLabel("Return loss:"), self.marker2_returnloss_label)
        self.marker2_vswr_label = QtWidgets.QLabel("")
        marker2_box_layout.addRow(QtWidgets.QLabel("VSWR:"), self.marker2_vswr_label)
        self.marker2_reactance_label = QtWidgets.QLabel("")
        marker2_box_layout.addRow(QtWidgets.QLabel("Reactance:"), self.marker2_reactance_label)
        self.marker2_gain_label = QtWidgets.QLabel("")
        marker2_box_layout.addRow(QtWidgets.QLabel("S21 Gain:"), self.marker2_gain_label)
        self.marker2_phase_label = QtWidgets.QLabel("")
        marker2_box_layout.addRow(QtWidgets.QLabel("S21 Phase:"), self.marker2_phase_label)
        
        mousemarker_box = QtWidgets.QGroupBox("Mouse marker")
        mousemarker_box_layout = QtWidgets.QFormLayout(mousemarker_box)

        marker_column.addWidget(mousemarker_box)
        
        self.mousemarker_impedance_label = QtWidgets.QLabel("")
        mousemarker_box_layout.addRow(QtWidgets.QLabel("Impedance:"), self.mousemarker_impedance_label)
        self.mousemarker_returnloss_label = QtWidgets.QLabel("")
        mousemarker_box_layout.addRow(QtWidgets.QLabel("Return loss:"), self.mousemarker_returnloss_label)
        self.mousemarker_vswr_label = QtWidgets.QLabel("")
        mousemarker_box_layout.addRow(QtWidgets.QLabel("VSWR:"), self.mousemarker_vswr_label)
        self.mousemarker_reactance_label = QtWidgets.QLabel("")
        mousemarker_box_layout.addRow(QtWidgets.QLabel("Reactance:"), self.mousemarker_reactance_label)
        self.mousemarker_gain_label = QtWidgets.QLabel("")
        mousemarker_box_layout.addRow(QtWidgets.QLabel("S21 Gain:"), self.mousemarker_gain_label)
        self.mousemarker_phase_label = QtWidgets.QLabel("")
        mousemarker_box_layout.addRow(QtWidgets.QLabel("S21 Phase:"), self.mousemarker_phase_label)

        ################################################################################################################
        #  Statistics/analysis
        ################################################################################################################

        s11_control_box = QtWidgets.QGroupBox()
        s11_control_box.setTitle("S11")
        s11_control_layout = QtWidgets.QFormLayout()
        s11_control_box.setLayout(s11_control_layout)
        s11_control_box.setMaximumWidth(250)

        self.s11_min_swr_label = QtWidgets.QLabel()
        s11_control_layout.addRow("Min VSWR:", self.s11_min_swr_label)
        self.s11_min_rl_label = QtWidgets.QLabel()
        s11_control_layout.addRow("Return loss:", self.s11_min_rl_label)

        left_column.addWidget(s11_control_box)

        s21_control_box = QtWidgets.QGroupBox()
        s21_control_box.setTitle("S21")
        s21_control_layout = QtWidgets.QFormLayout()
        s21_control_box.setLayout(s21_control_layout)
        s21_control_box.setMaximumWidth(250)

        self.s21_min_gain_label = QtWidgets.QLabel()
        s21_control_layout.addRow("Min gain:", self.s21_min_gain_label)

        self.s21_max_gain_label = QtWidgets.QLabel()
        s21_control_layout.addRow("Max gain:", self.s21_max_gain_label)

        left_column.addWidget(s21_control_box)

        marker_column.addSpacerItem(QtWidgets.QSpacerItem(1, 1, QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Expanding))

        ################################################################################################################
        # TDR
        ################################################################################################################

        tdr_control_box = QtWidgets.QGroupBox()
        tdr_control_box.setTitle("TDR")
        tdr_control_layout = QtWidgets.QFormLayout()
        tdr_control_box.setLayout(tdr_control_layout)
        tdr_control_box.setMaximumWidth(250)

        self.tdr_velocity_dropdown = QtWidgets.QComboBox()
        self.tdr_velocity_dropdown.addItem("Jelly filled (0.64)", 0.64)
        self.tdr_velocity_dropdown.addItem("Polyethylene (0.66)", 0.66)
        self.tdr_velocity_dropdown.addItem("PTFE (Teflon) (0.70)", 0.70)
        self.tdr_velocity_dropdown.addItem("Pulp Insulation (0.72)", 0.72)
        self.tdr_velocity_dropdown.addItem("Foam or Cellular PE (0.78)", 0.78)
        self.tdr_velocity_dropdown.addItem("Semi-solid PE (SSPE) (0.84)", 0.84)
        self.tdr_velocity_dropdown.addItem("Air (Helical spacers) (0.94)", 0.94)
        self.tdr_velocity_dropdown.insertSeparator(7)
        self.tdr_velocity_dropdown.addItem("RG174 (0.66)", 0.66)
        self.tdr_velocity_dropdown.addItem("RG316 (0.69)", 0.69)
        self.tdr_velocity_dropdown.addItem("RG402 (0.695)", 0.695)
        self.tdr_velocity_dropdown.insertSeparator(11)
        self.tdr_velocity_dropdown.addItem("Custom", -1)

        self.tdr_velocity_dropdown.setCurrentIndex(1)  # Default to PE (0.66)

        self.tdr_velocity_dropdown.currentIndexChanged.connect(self.updateTDR)

        tdr_control_layout.addRow(self.tdr_velocity_dropdown)

        self.tdr_velocity_input = QtWidgets.QLineEdit()
        self.tdr_velocity_input.setDisabled(True)
        self.tdr_velocity_input.setText("0.66")
        self.tdr_velocity_input.textChanged.connect(self.updateTDR)

        tdr_control_layout.addRow("Velocity factor", self.tdr_velocity_input)

        self.tdr_result_label = QtWidgets.QLabel()
        tdr_control_layout.addRow("Estimated cable length:", self.tdr_result_label)

        left_column.addWidget(tdr_control_box)

        ################################################################################################################
        #  Calibration
        ################################################################################################################
        calibration_control_box = QtWidgets.QGroupBox("Calibration")
        calibration_control_box.setMaximumWidth(250)
        calibration_control_layout = QtWidgets.QFormLayout(calibration_control_box)
        b = QtWidgets.QPushButton("Calibration ...")
        self.calibrationWindow = CalibrationWindow(self)
        b.clicked.connect(self.displayCalibrationWindow)
        calibration_control_layout.addRow(b)
        left_column.addWidget(calibration_control_box)

        ################################################################################################################
        #  Spacer
        ################################################################################################################

        left_column.addSpacerItem(QtWidgets.QSpacerItem(1, 1, QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Expanding))

        ################################################################################################################
        #  Reference control
        ################################################################################################################

        reference_control_box = QtWidgets.QGroupBox()
        reference_control_box.setMaximumWidth(250)
        reference_control_box.setTitle("Reference sweep")
        reference_control_layout = QtWidgets.QFormLayout(reference_control_box)

        btnSetReference = QtWidgets.QPushButton("Set current as reference")
        btnSetReference.clicked.connect(self.setReference)
        self.btnResetReference = QtWidgets.QPushButton("Reset reference")
        self.btnResetReference.clicked.connect(self.resetReference)
        self.btnResetReference.setDisabled(True)
        self.btnReferenceColorPicker = QtWidgets.QPushButton("█")
        self.btnReferenceColorPicker.setFixedWidth(20)
        self.setReferenceColor(self.referenceColor)
        self.btnReferenceColorPicker.clicked.connect(lambda: self.setReferenceColor(
            QtWidgets.QColorDialog.getColor(self.referenceColor, options=QtWidgets.QColorDialog.ShowAlphaChannel)))

        set_reference_layout = QtWidgets.QHBoxLayout()
        set_reference_layout.addWidget(btnSetReference)
        set_reference_layout.addWidget(self.btnReferenceColorPicker)
        reference_control_layout.addRow(set_reference_layout)
        reference_control_layout.addRow(self.btnResetReference)

        left_column.addWidget(reference_control_box)

        ################################################################################################################
        #  Serial control
        ################################################################################################################

        serial_control_box = QtWidgets.QGroupBox()
        serial_control_box.setMaximumWidth(250)
        serial_control_box.setTitle("Serial port control")
        serial_control_layout = QtWidgets.QFormLayout(serial_control_box)
        self.serialPortInput = QtWidgets.QLineEdit(self.serialPort)
        self.serialPortInput.setAlignment(QtCore.Qt.AlignRight)
        # self.serialSpeedInput = QtWidgets.QLineEdit(str(self.serialSpeed))
        # self.serialSpeedInput.setValidator(QtGui.QIntValidator())
        # self.serialSpeedInput.setAlignment(QtCore.Qt.AlignRight)
        serial_control_layout.addRow(QtWidgets.QLabel("Serial port"), self.serialPortInput)
        # serial_control_layout.addRow(QtWidgets.QLabel("Speed"), self.serialSpeedInput)

        self.btnSerialToggle = QtWidgets.QPushButton("Connect to NanoVNA")
        self.btnSerialToggle.clicked.connect(self.serialButtonClick)
        serial_control_layout.addRow(self.btnSerialToggle)

        left_column.addWidget(serial_control_box)

        ################################################################################################################
        #  File control
        ################################################################################################################

        self.fileWindow = QtWidgets.QWidget()
        self.fileWindow.setWindowTitle("Files")
        file_window_layout = QtWidgets.QVBoxLayout()
        self.fileWindow.setLayout(file_window_layout)

        reference_file_control_box = QtWidgets.QGroupBox("Import file")
        reference_file_control_layout = QtWidgets.QFormLayout(reference_file_control_box)
        self.referenceFileNameInput = QtWidgets.QLineEdit("")
        btnReferenceFilePicker = QtWidgets.QPushButton("...")
        btnReferenceFilePicker.setMaximumWidth(25)
        btnReferenceFilePicker.clicked.connect(self.pickReferenceFile)
        referenceFileNameLayout = QtWidgets.QHBoxLayout()
        referenceFileNameLayout.addWidget(self.referenceFileNameInput)
        referenceFileNameLayout.addWidget(btnReferenceFilePicker)

        reference_file_control_layout.addRow(QtWidgets.QLabel("Filename"), referenceFileNameLayout)
        file_window_layout.addWidget(reference_file_control_box)

        btnLoadReference = QtWidgets.QPushButton("Load reference")
        btnLoadReference.clicked.connect(self.loadReferenceFile)
        btnLoadSweep = QtWidgets.QPushButton("Load as sweep")
        btnLoadSweep.clicked.connect(self.loadSweepFile)
        reference_file_control_layout.addRow(btnLoadReference)
        reference_file_control_layout.addRow(btnLoadSweep)

        file_control_box = QtWidgets.QGroupBox()
        file_control_box.setTitle("Export file")
        file_control_box.setMaximumWidth(300)
        file_control_layout = QtWidgets.QFormLayout(file_control_box)
        self.fileNameInput = QtWidgets.QLineEdit("")
        btnFilePicker = QtWidgets.QPushButton("...")
        btnFilePicker.setMaximumWidth(25)
        btnFilePicker.clicked.connect(self.pickFile)
        fileNameLayout = QtWidgets.QHBoxLayout()
        fileNameLayout.addWidget(self.fileNameInput)
        fileNameLayout.addWidget(btnFilePicker)

        file_control_layout.addRow(QtWidgets.QLabel("Filename"), fileNameLayout)

        self.btnExportFile = QtWidgets.QPushButton("Export data S1P")
        self.btnExportFile.clicked.connect(self.exportFileS1P)
        file_control_layout.addRow(self.btnExportFile)

        self.btnExportFile = QtWidgets.QPushButton("Export data S2P")
        self.btnExportFile.clicked.connect(self.exportFileS2P)
        file_control_layout.addRow(self.btnExportFile)

        file_window_layout.addWidget(file_control_box)

        file_control_box = QtWidgets.QGroupBox()
        file_control_box.setTitle("Files")
        file_control_box.setMaximumWidth(300)
        file_control_layout = QtWidgets.QFormLayout(file_control_box)
        btnOpenFileWindow = QtWidgets.QPushButton("Files ...")
        file_control_layout.addWidget(btnOpenFileWindow)
        btnOpenFileWindow.clicked.connect(self.displayFileWindow)

        left_column.addWidget(file_control_box)

        ################################################################################################################
        #  Display setup
        ################################################################################################################

        b = QtWidgets.QPushButton("Display setup ...")
        b.setMaximumWidth(250)
        self.display_setupWindow = DisplaySettingsWindow(self)
        b.clicked.connect(self.displaySettingsWindow)
        left_column.addWidget(b)

        btn_about = QtWidgets.QPushButton("About ...")
        btn_about.setMaximumWidth(250)
        btn_about.clicked.connect(lambda: QtWidgets.QMessageBox.about(self, "About NanoVNASaver",
                                                                      "NanoVNASaver version "
                                                                      + NanoVNASaver.version +
                                                                      "\n\n\N{COPYRIGHT SIGN} Copyright 2019 Rune B. Broberg\n" +
                                                                      "This program comes with ABSOLUTELY NO WARRANTY\n" +
                                                                      "This program is licensed under the GNU General Public License version 3\n\n" +
                                                                      "See https://github.com/mihtjel/nanovna-saver for further details"))
        left_column.addWidget(btn_about)

        ################################################################################################################
        #  Right side
        ################################################################################################################

        self.lister = QtWidgets.QPlainTextEdit()
        self.lister.setFixedHeight(200)
        self.lister.setMaximumWidth(300)
        self.charts_layout = QtWidgets.QGridLayout()
        self.charts_layout.addWidget(self.s11SmithChart, 0, 0)
        self.charts_layout.addWidget(self.s21PolarChart, 1, 0)
        self.charts_layout.addWidget(self.s11LogMag, 0, 1)
        self.charts_layout.addWidget(self.s21LogMag, 1, 1)

        right_column.addLayout(self.charts_layout)
        marker_column.addWidget(self.lister)

        self.worker.signals.updated.connect(self.dataUpdated)
        self.worker.signals.finished.connect(self.sweepFinished)

    # Get that windows port
    @staticmethod
    def getport() -> str:
        device_list = list_ports.comports()
        for d in device_list:
            if (d.vid == VID and
                    d.pid == PID):
                port = d.device
                return port

    def pickReferenceFile(self):
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(directory=self.referenceFileNameInput.text(),
                                                            filter="Touchstone Files (*.s1p *.s2p);;All files (*.*)")
        if filename != "":
            self.referenceFileNameInput.setText(filename)

    def pickFile(self):
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(directory=self.fileNameInput.text(),
                                                            filter="Touchstone Files (*.s1p *.s2p);;All files (*.*)")
        if filename != "":
            self.fileNameInput.setText(filename)

    def exportFileS1P(self):
        print("Save file to " + self.fileNameInput.text())
        if len(self.data) == 0:
            self.lister.appendPlainText("No data stored, nothing written.")
            return
        filename = self.fileNameInput.text()
        if filename == "":
            self.lister.appendPlainText("No filename entered.")
            return
        try:
            file = open(filename, "w+")
            self.lister.clear()
            self.lister.appendPlainText("# Hz S RI R 50")
            file.write("# Hz S RI R 50\n")
            for i in range(len(self.data)):
                if i == 0 or self.data[i].freq != self.data[i-1].freq:
                    self.lister.appendPlainText(str(self.data[i].freq) + " " + str(self.data[i].re) + " " + str(self.data[i].im))
                    file.write(str(self.data[i].freq) + " " + str(self.data[i].re) + " " + str(self.data[i].im) + "\n")
            file.close()
        except Exception as e:
            print("Error during file export: " + str(e))
            self.lister.appendPlainText("Error during file export: " + str(e))
            return

        self.lister.appendPlainText("")
        self.lister.appendPlainText("File " + filename + " written.")

    def exportFileS2P(self):
        print("Save file to " + self.fileNameInput.text())
        if len(self.data) == 0:
            self.lister.appendPlainText("No data stored, nothing written.")
            return
        filename = self.fileNameInput.text()
        if filename == "":
            self.lister.appendPlainText("No filename entered.")
            return
        try:
            file = open(filename, "w+")
            self.lister.clear()
            self.lister.appendPlainText("# Hz S RI R 50")
            file.write("# Hz S RI R 50\n")
            for i in range(len(self.data)):
                if i == 0 or self.data[i].freq != self.data[i-1].freq:
                    self.lister.appendPlainText(str(self.data[i].freq) + " " + str(self.data[i].re) + " " + str(self.data[i].im) + " " +
                                                str(self.data21[i].re) + " " + str(self.data21[i].im) + " 0 0 0 0")
                    file.write(str(self.data[i].freq) + " " + str(self.data[i].re) + " " + str(self.data[i].im) + " " +
                               str(self.data21[i].re) + " " + str(self.data21[i].im) + " 0 0 0 0\n")
            file.close()
        except Exception as e:
            print("Error during file export: " + str(e))
            self.lister.appendPlainText("Error during file export: " + str(e))
            return

        self.lister.appendPlainText("")
        self.lister.appendPlainText("File " + filename + " written.")

    def serialButtonClick(self):
        if self.serial.is_open:
            self.stopSerial()
        else:
            self.startSerial()
        return

    def flushSerialBuffers(self):
        if self.serialLock.acquire():
            self.serial.write(b"\r\n\r\n")
            sleep(0.1)
            self.serial.reset_input_buffer()
            self.serial.reset_output_buffer()
            sleep(0.1)
            self.serialLock.release()

    def startSerial(self):
        if self.serialLock.acquire():
            self.serialPort = self.serialPortInput.text()
            self.lister.appendPlainText("Opening serial port " + self.serialPort)
            try:
                self.serial = serial.Serial(port=self.serialPort, baudrate=115200)
                self.serial.timeout = 0.05
            except serial.SerialException as exc:
                self.lister.appendPlainText("Tried to open " + self.serialPort + " and failed: " + str(exc))
                self.serialLock.release()
                return
            self.btnSerialToggle.setText("Disconnect")

            self.serialLock.release()
            sleep(0.05)

            self.flushSerialBuffers()
            sleep(0.05)

            self.lister.appendPlainText(self.readFirmware())

            frequencies = self.readValues("frequencies")

            self.sweepStartInput.setText(str(frequencies[0]))
            self.sweepEndInput.setText(str(frequencies[100]))

            self.sweep()
            return

    def stopSerial(self):
        if self.serialLock.acquire():
            self.serial.close()
            self.serialLock.release()
            self.btnSerialToggle.setText("Connect to NanoVNA")

    def writeSerial(self, command):
        if not self.serial.is_open:
            print("Warning: Writing without serial port being opened (" + command + ")")
            return
        if self.serialLock.acquire():
            try:
                self.serial.write(str(command + "\r").encode('ascii'))
                self.serial.readline()
            except serial.SerialException as exc:
                print("Exception received: " + str(exc))
            self.serialLock.release()
        return

    def setSweep(self, start, stop):
        # print("Sending: " + "sweep " + str(start) + " " + str(stop) + " 101")
        self.writeSerial("sweep " + str(start) + " " + str(stop) + " 101")

    def sweep(self):
        # Run the serial port update
        if not self.serial.is_open:
            return

        self.sweepProgressBar.setValue(0)
        self.btnSweep.setDisabled(True)
        self.markers[0].frequencyInput.setText("")
        self.marker1_impedance_label.setText("")
        self.marker1_vswr_label.setText("")
        self.marker1_returnloss_label.setText("")
        self.marker1_reactance_label.setText("")
        self.marker1_gain_label.setText("")
        self.marker1_phase_label.setText("")
        self.marker2_impedance_label.setText("")
        self.marker2_vswr_label.setText("")
        self.marker2_returnloss_label.setText("")
        self.marker2_reactance_label.setText("")
        self.marker2_gain_label.setText("")
        self.marker2_phase_label.setText("")
        self.mousemarker_impedance_label.setText("")
        self.mousemarker_vswr_label.setText("")
        self.mousemarker_returnloss_label.setText("")
        self.mousemarker_reactance_label.setText("")
        self.mousemarker_gain_label.setText("")
        self.mousemarker_phase_label.setText("")
        self.s11_min_rl_label.setText("")
        self.s11_min_swr_label.setText("")
        self.s21_min_gain_label.setText("")
        self.s21_max_gain_label.setText("")
        self.tdr_result_label.setText("")

        self.threadpool.start(self.worker)

    def readFirmware(self):
        if self.serialLock.acquire():
            try:
                data = "a"
                while data != "":
                    data = self.serial.readline().decode('ascii')
                #  Then send the command to read data
                self.serial.write("info\r".encode('ascii'))
            except serial.SerialException as exc:
                print("Exception received: " + str(exc))
            result = ""
            data = ""
            sleep(0.01)
            while "ch>" not in data:
                data = self.serial.readline().decode('ascii')
                result += data
            self.serialLock.release()
            return result

    def readValues(self, value):
        if self.serialLock.acquire():
            try:
                data = "a"
                while data != "":
                    data = self.serial.readline().decode('ascii')

                #  Then send the command to read data
                self.serial.write(str(value + "\r").encode('ascii'))
            except serial.SerialException as exc:
                print("Exception received: " + str(exc))
            result = ""
            data = ""
            sleep(0.01)
            while "ch>" not in data:
                data = self.serial.readline().decode('ascii')
                result += data
            values = result.split("\r\n")
            self.serialLock.release()
            return values[1:102]

    def saveData(self, data, data12, source=None):
        if self.dataLock.acquire(blocking=True):
            self.data = data
            self.data21 = data12
        else:
            print("ERROR: Failed acquiring data lock while saving.")
        self.dataLock.release()
        if source is not None:
            self.sweepSource = source
        else:
            self.sweepSource = strftime("%Y-%m-%d %H:%M:%S", gmtime())

    def dataUpdated(self):
        if self.dataLock.acquire(blocking=True):
            for m in self.markers:
                m.findLocation(self.data)
            # TODO: Make a neater solution for showing data for markers
            if self.markers[0].location != -1:
                im50, re50, vswr = self.vswr(self.data[self.markers[0].location])
                if im50 < 0:
                    im50str = " - j" + str(round(-1*im50, 3))
                else:
                    im50str = " + j" + str(round(im50, 3))
                self.markers[0].frequencyInput.setText(self.formatFrequency(self.markers[0].frequency))
                self.mousemarker_impedance_label.setText(str(round(re50, 3)) + im50str)
                self.mousemarker_returnloss_label.setText(str(round(20*math.log10((vswr-1)/(vswr+1)), 3)) + " dB")
                reactance = self.reactanceEquivalent(im50, self.data[self.markers[0].location].freq)
                self.mousemarker_reactance_label.setText(reactance)
                self.mousemarker_vswr_label.setText(str(round(vswr, 3)))
                if len(self.data21) == len(self.data):
                    _, _, vswr = self.vswr(self.data21[self.markers[0].location])
                    self.mousemarker_gain_label.setText(str(round(20*math.log10((vswr-1)/(vswr+1)), 3)) + " dB")
                    self.mousemarker_phase_label.setText(str(round(PhaseChart.angle(self.data21[self.markers[0].location]), 2)) + "\N{DEGREE SIGN}")
            if self.markers[1].location != -1:
                im50, re50, vswr = self.vswr(self.data[self.markers[1].location])
                if im50 < 0:
                    im50str = " - j" + str(round(-1*im50, 3))
                else:
                    im50str = " + j" + str(round(im50, 3))
                self.marker1_impedance_label.setText(str(round(re50, 3)) + im50str)
                self.marker1_returnloss_label.setText(str(round(20*math.log10((vswr-1)/(vswr+1)), 3)) + " dB")
                reactance = self.reactanceEquivalent(im50, self.data[self.markers[1].location].freq)
                self.marker1_reactance_label.setText(reactance)
                self.marker1_vswr_label.setText(str(round(vswr, 3)))
                if len(self.data21) == len(self.data):
                    _, _, vswr = self.vswr(self.data21[self.markers[1].location])
                    self.marker1_gain_label.setText(str(round(20*math.log10((vswr-1)/(vswr+1)), 3)) + " dB")
                    self.marker1_phase_label.setText(str(round(PhaseChart.angle(self.data21[self.markers[1].location]), 2)) + "\N{DEGREE SIGN}")

            if self.markers[2].location != -1:
                im50, re50, vswr = self.vswr(self.data[self.markers[2].location])
                if im50 < 0:
                    im50str = " - j" + str(round(im50, 3))
                else:
                    im50str = " + j" + str(round(im50, 3))
                self.marker2_impedance_label.setText(str(round(re50, 3)) + im50str)
                self.marker2_returnloss_label.setText(str(round(20*math.log10((vswr-1)/(vswr+1)), 3)) + " dB")
                reactance = self.reactanceEquivalent(im50, self.data[self.markers[2].location].freq)
                self.marker2_reactance_label.setText(reactance)
                self.marker2_vswr_label.setText(str(round(vswr, 3)))
                if len(self.data21) == len(self.data):
                    _, _, vswr = self.vswr(self.data21[self.markers[2].location])
                    self.marker2_gain_label.setText(str(round(20*math.log10((vswr-1)/(vswr+1)), 3)) + " dB")
                    self.marker2_phase_label.setText(str(round(PhaseChart.angle(self.data21[self.markers[2].location]), 2)) + "\N{DEGREE SIGN}")

            for c in self.s11charts:
                c.setData(self.data)

            for c in self.s21charts:
                c.setData(self.data21)
            self.sweepProgressBar.setValue(self.worker.percentage)
            self.updateTDR()
            # Find the minimum S11 VSWR:
            minVSWR = 100
            minVSWRfreq = -1
            for d in self.data:
                _, _, vswr = self.vswr(d)
                if minVSWR > vswr > 0:
                    minVSWR = vswr
                    minVSWRfreq = d.freq

            if minVSWRfreq > -1:
                self.s11_min_swr_label.setText(str(round(minVSWR, 3)) + " @ " + self.formatFrequency(minVSWRfreq))
                self.s11_min_rl_label.setText(str(round(20*math.log10((minVSWR-1)/(minVSWR+1)), 3)) + " dB")

            minGain = 100
            minGainFreq = -1
            maxGain = -100
            maxGainFreq = -1
            for d in self.data21:
                gain = self.gain(d)
                if gain > maxGain:
                    maxGain = gain
                    maxGainFreq = d.freq
                if gain < minGain:
                    minGain = gain
                    minGainFreq = d.freq

            if maxGainFreq > -1:
                self.s21_min_gain_label.setText(str(round(minGain, 3)) + " dB @ " + self.formatFrequency(minGainFreq))
                self.s21_max_gain_label.setText(str(round(maxGain, 3)) + " dB @ " + self.formatFrequency(maxGainFreq))

        else:
            print("ERROR: Failed acquiring data lock while updating")
        self.updateTitle()
        self.dataLock.release()

    @staticmethod
    def vswr(data: Datapoint):
        re = data.re
        im = data.im
        re50 = 50 * (1 - re * re - im * im) / (1 + re * re + im * im - 2 * re)
        im50 = 50 * (2 * im) / (1 + re * re + im * im - 2 * re)
        mag = math.sqrt((re50 - 50) * (re50 - 50) + im50 * im50) / math.sqrt((re50 + 50) * (re50 + 50) + im50 * im50)
        # mag = math.sqrt(re * re + im * im)  # Is this even right?
        vswr = (1 + mag) / (1 - mag)
        return im50, re50, vswr

    @staticmethod
    def reactanceEquivalent(im50, freq) -> str:
        capacitance = 10**12/(freq * 2 * math.pi * im50)
        inductance = im50 / (freq * 2 * math.pi)
        if im50 < 0:
            return str(round(-capacitance, 3)) + " pF"
        else:
            return str(round(inductance * 1000000000, 3)) + " nH"

    @staticmethod
    def gain(data: Datapoint):
        re = data.re
        im = data.im
        re50 = 50 * (1 - re * re - im * im) / (1 + re * re + im * im - 2 * re)
        im50 = 50 * (2 * im) / (1 + re * re + im * im - 2 * re)
        # Calculate the gain / reflection coefficient
        mag = math.sqrt((re50 - 50) * (re50 - 50) + im50 * im50) / math.sqrt(
            (re50 + 50) * (re50 + 50) + im50 * im50)
        return 20 * math.log10(mag)

    def sweepFinished(self):
        self.sweepProgressBar.setValue(100)
        self.btnSweep.setDisabled(False)

    def updateTDR(self):
        c = 299792458
        if len(self.data) < 2:
            return

        if self.tdr_velocity_dropdown.currentData() == -1:
            self.tdr_velocity_input.setDisabled(False)
        else:
            self.tdr_velocity_input.setDisabled(True)
            self.tdr_velocity_input.setText(str(self.tdr_velocity_dropdown.currentData()))

        try:
            v = float(self.tdr_velocity_input.text())
        except ValueError:
            return

        step_size = self.data[1].freq - self.data[0].freq
        if step_size == 0:
            self.tdr_result_label.setText("")
            self.lister.appendPlainText("Cannot compute cable length at 0 span")
            return

        s11 = []
        for d in self.data:
            s11.append(np.complex(d.re, d.im))

        window = np.blackman(len(self.data))

        windowed_s11 = window * s11

        td = np.abs(np.fft.ifft(windowed_s11, 2**14))

        time_axis = np.linspace(0, 1/step_size, 2**14)
        distance_axis = time_axis * v * c

        # peak = np.max(td)  # We should check that this is an actual *peak*, and not just a vague maximum
        index_peak = np.argmax(td)

        self.tdr_result_label.setText(str(round(distance_axis[index_peak]/2, 3)) + " m")

    def setSweepColor(self, color: QtGui.QColor):
        if color.isValid():
            self.color = color
            p = self.btnColorPicker.palette()
            p.setColor(QtGui.QPalette.ButtonText, color)
            self.btnColorPicker.setPalette(p)

            for c in self.charts:
                c.setSweepColor(color)

    @staticmethod
    def formatFrequency(freq):
        if math.log10(freq) < 3:
            return str(freq) + " Hz"
        elif math.log10(freq) < 7:
            return "{:.3f}".format(freq/1000) + " kHz"
        elif math.log10(freq) < 8:
            return "{:.4f}".format(freq/1000000) + " MHz"
        else:
            return "{:.3f}".format(freq/1000000) + " MHz"

    @staticmethod
    def parseFrequency(freq: str):
        freq = freq.replace(" ", "")  # People put all sorts of weird whitespace in.
        if freq.isnumeric():
            return int(freq)

        multiplier = 1
        freq = freq.lower()

        if freq.endswith("k"):
            multiplier = 1000
            freq = freq[:-1]
        elif freq.endswith("m"):
            multiplier = 1000000
            freq = freq[:-1]

        if freq.isnumeric():
            return int(freq) * multiplier

        try:
            f = float(freq)
            return int(round(multiplier * f))
        except ValueError:
            # Okay, we couldn't parse this however much we tried.
            return -1

    def setReference(self, s11data=None, s21data=None, source=None):
        if not s11data:
            s11data = self.data
        if not s21data:
            s21data = self.data21
        self.referenceS11data = s11data
        for c in self.s11charts:
            c.setReference(s11data)

        self.referenceS21data = s21data
        for c in self.s21charts:
            c.setReference(s21data)
        self.btnResetReference.setDisabled(False)

        if source is not None:
            # Save the reference source info
            self.referenceSource = source
        else:
            self.referenceSource = self.sweepSource
        self.updateTitle()

    def updateTitle(self):
        title = self.baseTitle
        insert = ""
        if self.sweepSource != "":
            insert += "Sweep: " + self.sweepSource + " @ " + str(len(self.data)) + " points"
        if self.referenceSource != "":
            if insert != "":
                insert += ", "
            insert += "Reference: " + self.referenceSource + " @ " + str(len(self.referenceS11data)) + " points"
        if insert != "":
            title = title + " (" + insert + ")"
        self.setWindowTitle(title)

    def resetReference(self):
        self.referenceS11data = []
        self.referenceS21data = []
        self.referenceSource = ""
        for c in self.charts:
            c.resetReference()
        self.btnResetReference.setDisabled(True)

    def setReferenceColor(self, color):
        if color.isValid():
            self.referenceColor = color
            p = self.btnReferenceColorPicker.palette()
            p.setColor(QtGui.QPalette.ButtonText, color)
            self.btnReferenceColorPicker.setPalette(p)

            for c in self.charts:
                c.setReferenceColor(color)

    def loadReferenceFile(self):
        filename = self.referenceFileNameInput.text()
        if filename is not "":
            self.resetReference()
            t = Touchstone(filename)
            t.load()
            self.setReference(t.s11data, t.s21data, filename)

    def loadSweepFile(self):
        filename = self.referenceFileNameInput.text()
        if filename is not "":
            self.data = []
            self.data21 = []
            t = Touchstone(filename)
            t.load()
            self.saveData(t.s11data, t.s21data, filename)
            self.dataUpdated()

    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(1100, 950)

    def displaySettingsWindow(self):
        self.display_setupWindow.show()
        QtWidgets.QApplication.setActiveWindow(self.display_setupWindow)

    def displayCalibrationWindow(self):
        self.calibrationWindow.show()
        QtWidgets.QApplication.setActiveWindow(self.calibrationWindow)

    def displayFileWindow(self):
        self.fileWindow.show()
        QtWidgets.QApplication.setActiveWindow(self.fileWindow)


class DisplaySettingsWindow(QtWidgets.QWidget):
    def __init__(self, app: NanoVNASaver):
        super().__init__()

        self.app = app
        self.setWindowTitle("Display settings")

        layout = QtWidgets.QVBoxLayout()
        self.setLayout(layout)

        display_options_box = QtWidgets.QGroupBox("Options")
        display_options_layout = QtWidgets.QFormLayout(display_options_box)

        self.show_lines_option = QtWidgets.QCheckBox("Show lines")
        show_lines_label = QtWidgets.QLabel("Displays a thin line between data points")
        self.show_lines_option.stateChanged.connect(self.changeShowLines)
        display_options_layout.addRow(self.show_lines_option, show_lines_label)

        self.dark_mode_option = QtWidgets.QCheckBox("Dark mode")
        dark_mode_label = QtWidgets.QLabel("Black background with white text")
        self.dark_mode_option.stateChanged.connect(self.changeDarkMode)
        display_options_layout.addRow(self.dark_mode_option, dark_mode_label)

        layout.addWidget(display_options_box)

        charts_box = QtWidgets.QGroupBox("Displayed charts")
        charts_layout = QtWidgets.QGridLayout(charts_box)

        # selections = ["S11 Smith chart",
        #               "S11 LogMag",
        #               "S11 VSWR",
        #               "S11 Phase",
        #               "S21 Smith chart",
        #               "S21 LogMag",
        #               "S21 Phase",
        #               "None"]

        selections = []

        for c in self.app.charts:
            selections.append(c.name)

        selections.append("None")

        chart00_selection = QtWidgets.QComboBox()
        chart00_selection.addItems(selections)
        chart00_selection.setCurrentIndex(selections.index("S11 Smith Chart"))
        chart00_selection.currentTextChanged.connect(lambda: self.changeChart(0, 0, chart00_selection.currentText()))
        charts_layout.addWidget(chart00_selection, 0, 0)

        chart01_selection = QtWidgets.QComboBox()
        chart01_selection.addItems(selections)
        chart01_selection.setCurrentIndex(selections.index("S11 Return Loss"))
        chart01_selection.currentTextChanged.connect(lambda: self.changeChart(0, 1, chart01_selection.currentText()))
        charts_layout.addWidget(chart01_selection, 0, 1)
        
        chart02_selection = QtWidgets.QComboBox()
        chart02_selection.addItems(selections)
        chart02_selection.setCurrentIndex(len(selections)-1)
        chart02_selection.currentTextChanged.connect(lambda: self.changeChart(0, 2, chart02_selection.currentText()))
        charts_layout.addWidget(chart02_selection, 0, 2)

        chart10_selection = QtWidgets.QComboBox()
        chart10_selection.addItems(selections)
        chart10_selection.setCurrentIndex(selections.index("S21 Polar Plot"))
        chart10_selection.currentTextChanged.connect(lambda: self.changeChart(1, 0, chart10_selection.currentText()))
        charts_layout.addWidget(chart10_selection, 1, 0)

        chart11_selection = QtWidgets.QComboBox()
        chart11_selection.addItems(selections)
        chart11_selection.setCurrentIndex(selections.index("S21 Gain"))
        chart11_selection.currentTextChanged.connect(lambda: self.changeChart(1, 1, chart11_selection.currentText()))
        charts_layout.addWidget(chart11_selection, 1, 1)

        chart12_selection = QtWidgets.QComboBox()
        chart12_selection.addItems(selections)
        chart12_selection.setCurrentIndex(len(selections)-1)
        chart12_selection.currentTextChanged.connect(lambda: self.changeChart(1, 2, chart12_selection.currentText()))
        charts_layout.addWidget(chart12_selection, 1, 2)

        layout.addWidget(charts_box)

    def changeChart(self, x, y, chart):
        found = None
        for c in self.app.charts:
            if c.name == chart:
                found = c

        oldWidget = self.app.charts_layout.itemAtPosition(x, y)
        if oldWidget is not None:
            w = oldWidget.widget()
            self.app.charts_layout.removeWidget(w)
            w.hide()
        if found is not None:
            self.app.charts_layout.addWidget(found, x, y)
            if found.isHidden():
                found.show()

    def changeShowLines(self):
        state = self.show_lines_option.isChecked()
        for c in self.app.charts:
            c.setDrawLines(state)

    def changeDarkMode(self):
        state = self.dark_mode_option.isChecked()
        if state:
            for c in self.app.charts:
                c.setBackgroundColor(QtGui.QColor(QtCore.Qt.black))
                c.setTextColor(QtGui.QColor(QtCore.Qt.white))
        else:
            for c in self.app.charts:
                c.setBackgroundColor(QtGui.QColor(QtCore.Qt.white))
                c.setTextColor(QtGui.QColor(QtCore.Qt.black))
