#  Copyright (c) 2019 Rune B. Broberg
import collections
import threading
from time import sleep
from typing import List

import serial
from PyQt5 import QtWidgets, QtCore, QtGui

from Marker import Marker
from SmithChart import SmithChart
from SweepWorker import SweepWorker

Datapoint = collections.namedtuple('Datapoint', 'freq re im')


class NanoVNASaver(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()

        self.threadpool = QtCore.QThreadPool()
        print("Max thread count " + str(self.threadpool.maxThreadCount()))
        self.worker = SweepWorker(self)

        self.noSweeps = 1  # Number of sweeps to run

        self.serialLock = threading.Lock()
        self.serial = serial.Serial()

        self.dataLock = threading.Lock()
        self.values = []
        self.frequencies = []
        self.data : List[Datapoint] = []

        self.serialPort = "COM11"
        # self.serialSpeed = "115200"

        self.setWindowTitle("NanoVNA Saver")
        layout = QtWidgets.QGridLayout()
        self.setLayout(layout)

        self.smithChart = SmithChart()

        left_column = QtWidgets.QVBoxLayout()
        right_column = QtWidgets.QVBoxLayout()

        layout.addLayout(left_column, 0, 0)
        layout.addLayout(right_column, 0, 1)

        ################################################################################################################
        #  Sweep control
        ################################################################################################################

        sweep_control_box = QtWidgets.QGroupBox()
        sweep_control_box.setMaximumWidth(400)
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
        marker_control_box.setMaximumWidth(400)
        marker_control_layout = QtWidgets.QFormLayout(marker_control_box)

        self.marker1 = Marker("Marker 1", QtGui.QColor(255, 0, 20))
        label, layout = self.marker1.getRow()
        marker_control_layout.addRow(label, layout)

        self.marker2 = Marker("Marker 2", QtGui.QColor(20, 0, 255))
        label, layout = self.marker2.getRow()
        marker_control_layout.addRow(label, layout)

        self.marker1label = QtWidgets.QLabel("")
        marker_control_layout.addRow(QtWidgets.QLabel("Marker 1: "), self.marker1label)

        self.marker2label = QtWidgets.QLabel("")
        marker_control_layout.addRow(QtWidgets.QLabel("Marker 2: "), self.marker2label)

        left_column.addWidget(marker_control_box)

        left_column.addSpacerItem(QtWidgets.QSpacerItem(1, 1, QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Expanding))

        ################################################################################################################
        #  Serial control
        ################################################################################################################

        serial_control_box = QtWidgets.QGroupBox()
        serial_control_box.setMaximumWidth(400)
        serial_control_box.setTitle("Serial port control")
        serial_control_layout = QtWidgets.QFormLayout(serial_control_box)
        self.serialPortInput = QtWidgets.QLineEdit(self.serialPort)
        self.serialPortInput.setAlignment(QtCore.Qt.AlignRight)
        # self.serialSpeedInput = QtWidgets.QLineEdit(str(self.serialSpeed))
        # self.serialSpeedInput.setValidator(QtGui.QIntValidator())
        # self.serialSpeedInput.setAlignment(QtCore.Qt.AlignRight)
        serial_control_layout.addRow(QtWidgets.QLabel("Serial port"), self.serialPortInput)
        # serial_control_layout.addRow(QtWidgets.QLabel("Speed"), self.serialSpeedInput)

        self.btnSerialToggle = QtWidgets.QPushButton("Open serial")
        self.btnSerialToggle.clicked.connect(self.serialButtonClick)
        serial_control_layout.addRow(self.btnSerialToggle)

        left_column.addWidget(serial_control_box)

        ################################################################################################################
        #  File control
        ################################################################################################################

        file_control_box = QtWidgets.QGroupBox()
        file_control_box.setTitle("Export file")
        file_control_box.setMaximumWidth(400)
        file_control_layout = QtWidgets.QFormLayout(file_control_box)
        self.fileNameInput = QtWidgets.QLineEdit("")
        self.fileNameInput.setAlignment(QtCore.Qt.AlignRight)

        file_control_layout.addRow(QtWidgets.QLabel("Filename"), self.fileNameInput)

        self.btnExportFile = QtWidgets.QPushButton("Export data")
        self.btnExportFile.clicked.connect(self.exportFile)
        file_control_layout.addRow(self.btnExportFile)

        left_column.addWidget(file_control_box)

        ################################################################################################################
        #  Right side
        ################################################################################################################

        self.lister = QtWidgets.QPlainTextEdit()
        self.lister.setFixedHeight(200)
        right_column.addWidget(self.lister)
        right_column.addWidget(self.smithChart)

        self.worker.signals.updated.connect(self.dataUpdated)

    def exportFile(self):
        print("Save file to " + self.fileNameInput.text())
        filename = self.fileNameInput.text()
        # TODO: Make some proper file handling here?
        file = open(filename, "w+")
        self.lister.clear()
        self.lister.appendPlainText("# Hz S RI R 50")
        file.write("# Hz S RI R 50\n")
        for i in range(len(self.values)):
            if i > 0 and self.frequencies[i] != self.frequencies[i-1]:
                self.lister.appendPlainText(self.frequencies[i] + " " + self.values[i])
                file.write(self.frequencies[i] + " " + self.values[i] + "\n")
        file.close()

    def serialButtonClick(self):
        if self.serial.is_open:
            self.stopSerial()
        else:
            self.startSerial()
        return

    def startSerial(self):
        self.lister.appendPlainText("Opening serial port " + self.serialPort)

        if self.serialLock.acquire():
            self.serialPort = self.serialPortInput.text()
            try:
                self.serial = serial.Serial(port=self.serialPort, baudrate=115200)
            except serial.SerialException as exc:
                self.lister.appendPlainText("Tried to open " + self.serialPort + " and failed.")
                self.serialLock.release()
                return
            self.btnSerialToggle.setText("Close serial")
            self.serial.timeout = 0.05

            self.serialLock.release()
            sleep(0.25)
            self.sweep()
            return

    def stopSerial(self):
        if self.serialLock.acquire():
            self.serial.close()
            self.serialLock.release()
            self.btnSerialToggle.setText("Open serial")

    def writeSerial(self, command):
        if not self.serial.is_open:
            print("Warning: Writing without serial port being opened (" + command + ")")
            return
        if self.serialLock.acquire():
            try:
                self.serial.write(str(command + "\r").encode('ascii'))
                self.serial.readline()
            except serial.SerialException as exc:
                print("Exception received")
            self.serialLock.release()
        return

    def setSweep(self, start, stop):
        print("Sending: " + "sweep " + str(start) + " " + str(stop) + " 101")
        self.writeSerial("sweep " + str(start) + " " + str(stop) + " 101")

    def sweep(self):
        # Run the serial port update
        if not self.serial.is_open:
            return

        self.sweepProgressBar.setValue(0)
        self.btnSweep.setDisabled(True)

        self.threadpool.start(self.worker)

        # TODO: Make markers into separate objects, and integrate updating them.
        # if self.smithChart.marker1Location != -1:
        #     reStr, imStr = self.values[self.smithChart.marker1Location].split(" ")
        #     re = float(reStr)
        #     im = float(imStr)
        #
        #     re50 = 50*(1-re*re-im*im)/(1+re*re+im*im-2*re)
        #     im50 = 50*(2*im)/(1+re*re+im*im-2*re)
        #
        #     mag = math.sqrt(re*re+im*im)
        #     vswr = (1+mag)/(1-mag)
        #     self.marker1label.setText(str(round(re50, 3)) + " + j" + str(round(im50, 3)) + " VSWR: 1:" + str(round(vswr, 3)))
        #
        # if self.smithChart.marker2Location != -1:
        #     reStr, imStr = self.values[self.smithChart.marker2Location].split(" ")
        #     re = float(reStr)
        #     im = float(imStr)
        #
        #     re50 = 50*(1-re*re-im*im)/(1+re*re+im*im-2*re)
        #     im50 = 50*(2*im)/(1+re*re+im*im-2*re)
        #
        #     mag = math.sqrt(re*re+im*im)
        #     vswr = (1+mag)/(1-mag)
        #     self.marker2label.setText(str(round(re50, 3)) + " + j" + str(round(im50, 3)) + " VSWR: 1:" + str(round(vswr, 3)))
        return

    def readValues(self, value):
        if self.serialLock.acquire():
            print("### Reading " + str(value) + " ###")
            try:
                data = "a"
                while data != "":
                    data = self.serial.readline().decode('ascii')

                #  Then send the command to read data
                self.serial.write(str(value + "\r").encode('ascii'))
            except serial.SerialException as exc:
                print("Exception received")
            result = ""
            data = ""
            sleep(0.01)
            while "ch>" not in data:
                data = self.serial.readline().decode('ascii')
                result += data
            print("### Done reading ###")
            values = result.split("\r\n")
            print("Total values: " + str(len(values) - 2))
            self.serialLock.release()
            return values[1:102]

    def setMarker1Color(self, color):
        self.smithChart.marker1Color = color
        p = self.btnMarker1ColorPicker.palette()
        p.setColor(QtGui.QPalette.ButtonText, color)
        self.btnMarker1ColorPicker.setPalette(p)

    def setMarker2Color(self, color):
        self.smithChart.marker2Color = color
        p = self.btnMarker2ColorPicker.palette()
        p.setColor(QtGui.QPalette.ButtonText, color)
        self.btnMarker2ColorPicker.setPalette(p)

    def saveData(self, data):
        if self.dataLock.acquire(blocking=True):
            self.data = data
        else:
            print("ERROR: Failed acquiring data lock while saving.")
        self.dataLock.release()

    def dataUpdated(self):
        if self.dataLock.acquire(blocking=True):
            self.smithChart.setData(self.data)
            self.sweepProgressBar.setValue(self.worker.percentage)
        else:
            print("ERROR: Failed acquiring data lock while updating")
        self.dataLock.release()

    def sweepFinished(self):
        self.sweepProgressBar.setValue(100)
        self.btnSweep.setDisabled(False)