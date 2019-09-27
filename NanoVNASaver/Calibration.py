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
import logging
import math

from PyQt5 import QtWidgets, QtCore
from typing import List
import numpy as np

logger = logging.getLogger(__name__)


Datapoint = collections.namedtuple('Datapoint', 'freq re im')


class CalibrationWindow(QtWidgets.QWidget):
    nextStep = -1

    def __init__(self, app):
        super().__init__()

        from .NanoVNASaver import NanoVNASaver

        self.app: NanoVNASaver = app

        self.setMinimumSize(600, 320)
        self.setWindowTitle("Calibration")

        shortcut = QtWidgets.QShortcut(QtCore.Qt.Key_Escape, self, self.hide)

        top_layout = QtWidgets.QHBoxLayout()
        left_layout = QtWidgets.QVBoxLayout()
        right_layout = QtWidgets.QVBoxLayout()
        top_layout.addLayout(left_layout)
        top_layout.addLayout(right_layout)
        self.setLayout(top_layout)

        calibration_status_group = QtWidgets.QGroupBox("Active calibration")
        calibration_status_layout = QtWidgets.QFormLayout()
        self.calibration_status_label = QtWidgets.QLabel("Device calibration")
        calibration_status_layout.addRow("Calibration active:", self.calibration_status_label)
        calibration_status_group.setLayout(calibration_status_layout)
        left_layout.addWidget(calibration_status_group)

        calibration_instructions_group = QtWidgets.QGroupBox("Instructions")
        calibration_instructions_layout = QtWidgets.QVBoxLayout(calibration_instructions_group)
        calibration_instructions_layout.addWidget(QtWidgets.QLabel("Instructions for use"))
        instructions = QtWidgets.QLabel("For each calibration standard, first sweep in the main application window, " +
                                        "then press the relevant button in this window. Short, open and load are " +
                                        "sufficient for 1-port calibration.  Sweep all standards with the same sweep " +
                                        "count.")
        instructions.setWordWrap(True)
        calibration_instructions_layout.addWidget(instructions)

        left_layout.addWidget(calibration_instructions_group)

        calibration_control_group = QtWidgets.QGroupBox("Calibrate")
        calibration_control_layout = QtWidgets.QFormLayout(calibration_control_group)
        btn_cal_short = QtWidgets.QPushButton("Short")
        btn_cal_short.clicked.connect(self.saveShort)
        self.cal_short_label = QtWidgets.QLabel("Uncalibrated")
        
        btn_cal_open = QtWidgets.QPushButton("Open")
        btn_cal_open.clicked.connect(self.saveOpen)
        self.cal_open_label = QtWidgets.QLabel("Uncalibrated")
        
        btn_cal_load = QtWidgets.QPushButton("Load")
        btn_cal_load.clicked.connect(self.saveLoad)
        self.cal_load_label = QtWidgets.QLabel("Uncalibrated")

        btn_cal_through = QtWidgets.QPushButton("Through")
        btn_cal_through.clicked.connect(self.saveThrough)
        # btn_cal_through.setDisabled(True)
        self.cal_through_label = QtWidgets.QLabel("Uncalibrated")

        btn_cal_isolation = QtWidgets.QPushButton("Isolation")
        btn_cal_isolation.clicked.connect(self.saveIsolation)
        # btn_cal_isolation.setDisabled(True)
        self.cal_isolation_label = QtWidgets.QLabel("Uncalibrated")

        calibration_control_layout.addRow(btn_cal_short, self.cal_short_label)
        calibration_control_layout.addRow(btn_cal_open, self.cal_open_label)
        calibration_control_layout.addRow(btn_cal_load, self.cal_load_label)
        calibration_control_layout.addRow(btn_cal_through, self.cal_through_label)
        calibration_control_layout.addRow(btn_cal_isolation, self.cal_isolation_label)

        calibration_control_layout.addRow(QtWidgets.QLabel(""))

        self.btn_automatic = QtWidgets.QPushButton("Calibration assistant")
        calibration_control_layout.addRow(self.btn_automatic)
        self.btn_automatic.clicked.connect(self.automaticCalibration)

        btn_apply = QtWidgets.QPushButton("Apply")
        calibration_control_layout.addRow(btn_apply)
        btn_apply.clicked.connect(self.calculate)

        btn_reset = QtWidgets.QPushButton("Reset")
        calibration_control_layout.addRow(btn_reset)
        btn_reset.clicked.connect(self.reset)

        left_layout.addWidget(calibration_control_group)

        file_box = QtWidgets.QGroupBox()
        file_layout = QtWidgets.QFormLayout(file_box)
        filename_input = QtWidgets.QLineEdit(self.app.settings.value("CalibrationFile", ""))
        file_layout.addRow("Filename", filename_input)
        btn_save_file = QtWidgets.QPushButton("Save calibration")
        btn_save_file.clicked.connect(lambda: self.saveCalibration(filename_input.text()))
        file_layout.addRow(btn_save_file)
        btn_load_file = QtWidgets.QPushButton("Load calibration")
        btn_load_file.clicked.connect(lambda: self.loadFile(filename_input.text()))
        file_layout.addRow(btn_load_file)

        left_layout.addWidget(file_box)

        cal_standard_box = QtWidgets.QGroupBox("Calibration standards")
        cal_standard_layout = QtWidgets.QFormLayout(cal_standard_box)
        self.use_ideal_values = QtWidgets.QCheckBox("Use ideal values")
        self.use_ideal_values.setChecked(True)
        self.use_ideal_values.stateChanged.connect(self.idealCheckboxChanged)
        cal_standard_layout.addRow(self.use_ideal_values)

        self.cal_short_box = QtWidgets.QGroupBox("Short")
        cal_short_form = QtWidgets.QFormLayout(self.cal_short_box)
        self.cal_short_box.setDisabled(True)
        self.short_l0_input = QtWidgets.QLineEdit("0")
        self.short_l1_input = QtWidgets.QLineEdit("0")
        self.short_l2_input = QtWidgets.QLineEdit("0")
        self.short_l3_input = QtWidgets.QLineEdit("0")
        self.short_length = QtWidgets.QLineEdit("0")
        cal_short_form.addRow("L0 (F(e-12))", self.short_l0_input)
        cal_short_form.addRow("L1 (F(e-24))", self.short_l1_input)
        cal_short_form.addRow("L2 (F(e-33))", self.short_l2_input)
        cal_short_form.addRow("L3 (F(e-42))", self.short_l3_input)
        cal_short_form.addRow("Delay (ps)", self.short_length)

        self.cal_open_box = QtWidgets.QGroupBox("Open")
        cal_open_form = QtWidgets.QFormLayout(self.cal_open_box)
        self.cal_open_box.setDisabled(True)
        self.open_c0_input = QtWidgets.QLineEdit("50")
        self.open_c1_input = QtWidgets.QLineEdit("0")
        self.open_c2_input = QtWidgets.QLineEdit("0")
        self.open_c3_input = QtWidgets.QLineEdit("0")
        self.open_length = QtWidgets.QLineEdit("0")
        cal_open_form.addRow("C0 (H(e-15))", self.open_c0_input)
        cal_open_form.addRow("C1 (H(e-27))", self.open_c1_input)
        cal_open_form.addRow("C2 (H(e-36))", self.open_c2_input)
        cal_open_form.addRow("C3 (H(e-45))", self.open_c3_input)
        cal_open_form.addRow("Delay (ps)", self.open_length)

        self.cal_load_box = QtWidgets.QGroupBox("Load")
        cal_load_form = QtWidgets.QFormLayout(self.cal_load_box)
        self.cal_load_box.setDisabled(True)
        self.load_resistance = QtWidgets.QLineEdit("50")
        self.load_inductance = QtWidgets.QLineEdit("0")
        cal_load_form.addRow("Resistance (\N{OHM SIGN})", self.load_resistance)
        cal_load_form.addRow("Inductance (H(e-12)", self.load_inductance)

        cal_standard_layout.addWidget(self.cal_short_box)
        cal_standard_layout.addWidget(self.cal_open_box)
        cal_standard_layout.addWidget(self.cal_load_box)
        right_layout.addWidget(cal_standard_box)

    def saveShort(self):
        self.app.calibration.s11short = self.app.data
        self.cal_short_label.setText("Calibrated (" + str(len(self.app.calibration.s11short)) + " points)")

    def saveOpen(self):
        self.app.calibration.s11open = self.app.data
        self.cal_open_label.setText("Calibrated (" + str(len(self.app.calibration.s11open)) + " points)")

    def saveLoad(self):
        self.app.calibration.s11load = self.app.data
        self.cal_load_label.setText("Calibrated (" + str(len(self.app.calibration.s11load)) + " points)")

    def saveIsolation(self):
        self.app.calibration.s21isolation = self.app.data21
        self.cal_isolation_label.setText("Calibrated (" + str(len(self.app.calibration.s21isolation)) + " points)")

    def saveThrough(self):
        self.app.calibration.s21through = self.app.data21
        self.cal_through_label.setText("Calibrated (" + str(len(self.app.calibration.s21through)) + " points)")

    def reset(self):
        self.app.calibration = Calibration()
        self.cal_short_label.setText("Uncalibrated")
        self.cal_open_label.setText("Uncalibrated")
        self.cal_load_label.setText("Uncalibrated")
        self.cal_through_label.setText("Uncalibrated")
        self.cal_isolation_label.setText("Uncalibrated")
        self.calibration_status_label.setText("Device calibration")

    def calculate(self):
        # TODO: Error handling for all the fields.
        if self.use_ideal_values.isChecked():
            self.app.calibration.useIdealShort = True
            self.app.calibration.useIdealOpen = True
            self.app.calibration.useIdealLoad = True
        else:
            # We are using custom calibration standards
            self.app.calibration.shortL0 = float(self.short_l0_input.text())/10**12
            self.app.calibration.shortL1 = float(self.short_l1_input.text())/10**24
            self.app.calibration.shortL2 = float(self.short_l2_input.text())/10**33
            self.app.calibration.shortL3 = float(self.short_l3_input.text())/10**42
            self.app.calibration.shortLength = float(self.short_length.text())/10**12
            self.app.calibration.useIdealShort = False

            self.app.calibration.openC0 = float(self.open_c0_input.text())/10**15
            self.app.calibration.openC1 = float(self.open_c1_input.text())/10**27
            self.app.calibration.openC2 = float(self.open_c2_input.text())/10**36
            self.app.calibration.openC3 = float(self.open_c3_input.text())/10**45
            self.app.calibration.openLength = float(self.open_length.text())/10**12
            self.app.calibration.useIdealOpen = False

            self.app.calibration.loadR = float(self.load_resistance.text())
            self.app.calibration.loadL = float(self.load_inductance.text())/10**12
            self.app.calibration.useIdealLoad = False

        if self.app.calibration.calculateCorrections():
            self.calibration_status_label.setText("Application calibration (" + str(len(self.app.calibration.s11short)) + " points)")

    def loadFile(self, filename):
        self.app.calibration.loadCalibration(filename)
        if self.app.calibration.isValid1Port():
            self.cal_short_label.setText("Loaded (" + str(len(self.app.calibration.s11short)) + ")")
            self.cal_open_label.setText("Loaded (" + str(len(self.app.calibration.s11open)) + ")")
            self.cal_load_label.setText("Loaded (" + str(len(self.app.calibration.s11load)) + ")")
            if self.app.calibration.isValid2Port():
                self.cal_through_label.setText("Loaded (" + str(len(self.app.calibration.s21through)) + ")")
                self.cal_isolation_label.setText("Loaded (" + str(len(self.app.calibration.s21isolation)) + ")")
            self.calculate()
            self.app.settings.setValue("CalibrationFile", filename)

    def saveCalibration(self, filename):
        if self.app.calibration.saveCalibration(filename):
            self.app.settings.setValue("CalibrationFile", filename)

    def idealCheckboxChanged(self):
        self.cal_short_box.setDisabled(self.use_ideal_values.isChecked())
        self.cal_open_box.setDisabled(self.use_ideal_values.isChecked())
        self.cal_load_box.setDisabled(self.use_ideal_values.isChecked())

    def automaticCalibration(self):
        self.btn_automatic.setDisabled(True)
        introduction = QtWidgets.QMessageBox(QtWidgets.QMessageBox.Information,
                                             "Calibration assistant",
                                             "This calibration assistant will help you create a calibration in the " +
                                             "NanoVNASaver application.  It will sweep the standards for you, and "+
                                             "guide you through the process.\n\n" +
                                             "Before starting, ensure you have Open, Short and Load standards " +
                                             "available, and the cables you wish to have calibrated with the device " +
                                             "connected.\n\n" +
                                             "If you want a 2-port calibration, also have a \"through\" connector " +
                                             "to hand.\n\n" +
                                             "The best results are achieved by having the NanoVNA calibrated " +
                                             "on-device for the full span of interest and saved to save slot 0 " +
                                             "before starting.\n\n" +
                                             "Once you are ready to proceed, press Ok",
                                             QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel)
        response = introduction.exec()
        if response != QtWidgets.QMessageBox.Ok:
            self.btn_automatic.setDisabled(False)
            return
        logger.info("Starting automatic calibration assistant.")

        if not self.app.serial.is_open:
            QtWidgets.QMessageBox(QtWidgets.QMessageBox.Information, "NanoVNA not connected",
                                  "Please ensure the NanoVNA is connected before attempting calibration.").exec()
            self.btn_automatic.setDisabled(False)
            return

        open_step = QtWidgets.QMessageBox(QtWidgets.QMessageBox.Information,
                                          "Calibrate open",
                                          "Please connect the \"open\" standard to port 0 of the NanoVNA.\n\n" +
                                          "Either use a supplied open, or leave the end of the cable unconnected " +
                                          "if desired.\n\n" +
                                          "Press Ok when you are ready to continue.",
                                          QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel)

        response = open_step.exec()
        if response != QtWidgets.QMessageBox.Ok:
            self.btn_automatic.setDisabled(False)
            return
        self.reset()
        self.nextStep = 0
        self.app.worker.signals.finished.connect(self.automaticCalibrationStep)
        self.app.sweep()
        return

    def automaticCalibrationStep(self):
        if self.nextStep == -1:
            self.app.worker.signals.finished.disconnect(self.automaticCalibrationStep)
        if self.nextStep == 0:
            # Open
            self.saveOpen()
            self.nextStep = 1
            short_step = QtWidgets.QMessageBox(QtWidgets.QMessageBox.Information,
                                               "Calibrate short",
                                               "Please connect the \"short\" standard to port 0 of the NanoVNA.\n\n" +
                                               "Press Ok when you are ready to continue.",
                                               QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel)

            response = short_step.exec()
            if response != QtWidgets.QMessageBox.Ok:
                self.nextStep = -1
                self.btn_automatic.setDisabled(False)
                self.app.worker.signals.finished.disconnect(self.automaticCalibrationStep)
                return
            else:
                self.app.sweep()
                return

        elif self.nextStep == 1:
            # Short
            self.saveShort()
            self.nextStep = 2
            load_step = QtWidgets.QMessageBox(QtWidgets.QMessageBox.Information,
                                              "Calibrate load",
                                              "Please connect the \"load\" standard to port 0 of the NanoVNA.\n\n" +
                                              "Press Ok when you are ready to continue.",
                                              QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel)

            response = load_step.exec()
            if response != QtWidgets.QMessageBox.Ok:
                self.btn_automatic.setDisabled(False)
                self.nextStep = -1
                self.app.worker.signals.finished.disconnect(self.automaticCalibrationStep)
                return
            else:
                self.app.sweep()
                return

        if self.nextStep == 2:
            # Load
            self.saveLoad()
            self.nextStep = 3
            continue_step = QtWidgets.QMessageBox(QtWidgets.QMessageBox.Information,
                                                  "1-port calibration complete",
                                                  "The required steps for a 1-port calibration are now complete.\n\n" +
                                                  "If you wish to continue and perform a 2-port calibration, press " +
                                                  "\"Yes\".  To apply the 1-port calibration and stop, press \"Apply\"",
                                                  QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Apply |
                                                  QtWidgets.QMessageBox.Cancel)

            response = continue_step.exec()
            if response == QtWidgets.QMessageBox.Apply:
                self.calculate()
                self.nextStep = -1
                self.app.worker.signals.finished.disconnect(self.automaticCalibrationStep)
                self.btn_automatic.setDisabled(False)
                return
            elif response != QtWidgets.QMessageBox.Ok:
                self.btn_automatic.setDisabled(False)
                self.nextStep = -1
                self.app.worker.signals.finished.disconnect(self.automaticCalibrationStep)
                return
            else:
                isolation_step = QtWidgets.QMessageBox(QtWidgets.QMessageBox.Information,
                                                       "Calibrate isolation",
                                                       "Please connect the \"load\" standard to port 1 of the NanoVNA.\n\n" +
                                                       "If available, also connect a load standard to port 0.\n\n" +
                                                       "Press Ok when you are ready to continue.",
                                                       QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel)

                response = isolation_step.exec()
                if response != QtWidgets.QMessageBox.Ok:
                    self.btn_automatic.setDisabled(False)
                    self.nextStep = -1
                    self.app.worker.signals.finished.disconnect(self.automaticCalibrationStep)
                    return
                else:
                    self.app.sweep()
                    return

        elif self.nextStep == 3:
            # Isolation
            self.saveIsolation()
            self.nextStep = 4
            through_step = QtWidgets.QMessageBox(QtWidgets.QMessageBox.Information,
                                              "Calibrate through",
                                              "Please connect the \"through\" standard between port 0 and port 1 " +
                                              "of the NanoVNA.\n\n" +
                                              "Press Ok when you are ready to continue.",
                                              QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel)

            response = through_step.exec()
            if response != QtWidgets.QMessageBox.Ok:
                self.btn_automatic.setDisabled(False)
                self.nextStep = -1
                self.app.worker.signals.finished.disconnect(self.automaticCalibrationStep)
                return
            else:
                self.app.sweep()
                return

        elif self.nextStep == 4:
            # Done
            self.saveThrough()
            apply_step = QtWidgets.QMessageBox(QtWidgets.QMessageBox.Information,
                                              "Calibrate complete",
                                              "The calibration process is now complete.  Press \"Apply\" to apply the " +
                                              "calibration parameters.",
                                              QtWidgets.QMessageBox.Apply | QtWidgets.QMessageBox.Cancel)

            response = apply_step.exec()
            if response != QtWidgets.QMessageBox.Apply:
                self.btn_automatic.setDisabled(False)
                self.nextStep = -1
                self.app.worker.signals.finished.disconnect(self.automaticCalibrationStep)
                return
            else:
                self.calculate()
                self.btn_automatic.setDisabled(False)
                return
        return


class Calibration:
    s11short: List[Datapoint] = []
    s11open: List[Datapoint] = []
    s11load: List[Datapoint] = []
    s21through: List[Datapoint] = []
    s21isolation: List[Datapoint] = []

    frequencies = []

    # 1-port
    e00 = []     # Directivity
    e11 = []     # Port match
    deltaE = []  # Tracking

    # 2-port
    e30 = []     # Port match
    e10e32 = []  # Transmission

    shortIdeal = np.complex(-1, 0)
    useIdealShort = True
    shortL0 = 5.7 * 10E-12
    shortL1 = -8960 * 10E-24
    shortL2 = -1100 * 10E-33
    shortL3 = -41200 * 10E-42
    shortLength = -34.2  # Picoseconds
    # These numbers look very large, considering what Keysight suggests their numbers are.

    useIdealOpen = True
    openIdeal = np.complex(1, 0)
    openC0 = 2.1 * 10E-14  # Subtract 50fF for the nanoVNA calibration if nanoVNA is calibrated?
    openC1 = 5.67 * 10E-23
    openC2 = -2.39 * 10E-31
    openC3 = 2.0 * 10E-40
    openLength = 0

    useIdealLoad = True
    loadR = 25
    loadL = 0
    loadIdeal = np.complex(0, 0)

    isCalculated = False

    def isValid2Port(self):
        return len(self.s21through) > 0 and len(self.s21isolation) > 0 and self.isValid1Port()

    def isValid1Port(self):
        return len(self.s11short) > 0 and len(self.s11open) > 0 and len(self.s11load) > 0

    def calculateCorrections(self):
        if not self.isValid1Port():
            return False
        self.frequencies = [int] * len(self.s11short)
        self.e00 = [np.complex] * len(self.s11short)
        self.e11 = [np.complex] * len(self.s11short)
        self.deltaE = [np.complex] * len(self.s11short)
        self.e30 = [np.complex] * len(self.s11short)
        self.e10e32 = [np.complex] * len(self.s11short)
        for i in range(len(self.s11short)):
            self.frequencies[i] = self.s11short[i].freq
            f = self.s11short[i].freq
            pi = math.pi

            if self.useIdealShort:
                g1 = self.shortIdeal
            else:
                Zsp = np.complex(0, 1) * 2 * pi * f * (self.shortL0 +
                                                       self.shortL1 * f +
                                                       self.shortL2 * f**2 +
                                                       self.shortL3 * f**3)
                gammaShort = ((Zsp/50) - 1) / ((Zsp/50) + 1)
                # (lower case) gamma = 2*pi*f
                # e^j*2*gamma*length
                # Referencing https://arxiv.org/pdf/1606.02446.pdf (18) - (21)
                g1 = gammaShort * np.exp(np.complex(0, 1) * 2 * 2 * math.pi * f * self.shortLength * -1)

            if self.useIdealOpen:
                g2 = self.openIdeal
            else:
                divisor = (2 * pi * f * (self.openC0 + self.openC1 * f + self.openC2 * f**2 + self.openC3 * f**3))
                if divisor != 0:
                    Zop = np.complex(0, -1) / divisor
                    gammaOpen = ((Zop/50) - 1) / ((Zop/50) + 1)
                    g2 = gammaOpen * np.exp(np.complex(0, 1) * 2 * 2 * math.pi * f * self.openLength * -1)
                else:
                    g2 = self.openIdeal
            if self.useIdealLoad:
                g3 = self.loadIdeal
            else:
                Zl = self.loadR + 2 * math.pi * f * self.loadL
                g3 = ((Zl/50)-1) / ((Zl/50)+1)

            gm1 = np.complex(self.s11short[i].re, self.s11short[i].im)
            gm2 = np.complex(self.s11open[i].re, self.s11open[i].im)
            gm3 = np.complex(self.s11load[i].re, self.s11load[i].im)

            try:
                denominator = g1*(g2-g3)*gm1 + g2*g3*gm2 - g2*g3*gm3 - (g2*gm2-g3*gm3)*g1
                self.e00[i] = - ((g2*gm3 - g3*gm3)*g1*gm2 - (g2*g3*gm2 - g2*g3*gm3 - (g3*gm2 - g2*gm3)*g1)*gm1) / denominator
                self.e11[i] = ((g2-g3)*gm1-g1*(gm2-gm3)+g3*gm2-g2*gm3) / denominator
                self.deltaE[i] = - ((g1*(gm2-gm3)-g2*gm2+g3*gm3)*gm1+(g2*gm3-g3*gm3)*gm2) / denominator
            except ZeroDivisionError:
                self.isCalculated = False
                logger.error("Division error - did you use the same measurement for two of short, open and load?")
                return

            if self.isValid2Port():
                self.e30[i] = np.complex(self.s21isolation[i].re, self.s21isolation[i].im)
                s21m = np.complex(self.s21through[i].re, self.s21through[i].im)
                self.e10e32[i] = (s21m - self.e30[i]) * (1 - (self.e11[i]*self.e11[i]))

        self.isCalculated = True
        return self.isCalculated

    def correct11(self, re, im, freq):
        s11m = np.complex(re, im)
        distance = 10**10
        index = 0
        for i in range(len(self.s11short)):
            if abs(self.s11short[i].freq - freq) < distance:
                index = i
                distance = abs(self.s11short[i].freq - freq)
        # TODO: Interpolate with the adjacent data point to get better corrections?

        s11 = (s11m - self.e00[index]) / ((s11m * self.e11[index]) - self.deltaE[index])
        return s11.real, s11.imag

    def correct21(self, re, im, freq):
        s21m = np.complex(re, im)
        distance = 10**10
        index = 0
        for i in range(len(self.s21through)):
            if abs(self.s21through[i].freq - freq) < distance:
                index = i
                distance = abs(self.s21through[i].freq - freq)
        s21 = (s21m - self.e30[index]) / self.e10e32[index]
        return s21.real, s21.imag

    def saveCalibration(self, filename):
        # Save the calibration data to file
        if filename == "" or not self.isValid1Port():
            return False
        try:
            file = open(filename, "w+")
            file.write("# Calibration data for NanoVNA-Saver\n")
            file.write("# Hz ShortR ShortI OpenR OpenI LoadR LoadI ThroughR ThroughI IsolationR IsolationI\n")
            for i in range(len(self.s11short)):
                freq = str(self.s11short[i].freq)
                shortr = str(self.s11short[i].re)
                shorti = str(self.s11short[i].im)
                openr = str(self.s11open[i].re)
                openi = str(self.s11open[i].im)
                loadr = str(self.s11load[i].re)
                loadi = str(self.s11load[i].im)
                file.write(freq + " " + shortr + " " + shorti + " " + openr + " " + openi + " " + loadr + " " + loadi)
                if self.isValid2Port():
                    throughr = str(self.s21through[i].re)
                    throughi = str(self.s21through[i].im)
                    isolationr = str(self.s21isolation[i].re)
                    isolationi = str(self.s21isolation[i].im)
                    file.write(" " + throughr + " " + throughi + " " + isolationr + " " + isolationi)
                file.write("\n")
            file.close()
            return True
        except Exception as e:
            logger.exception("Error saving calibration data: %s", e)
            return False

    def loadCalibration(self, filename):
        # Load calibration data from file
        if filename == "":
            return

        self.s11short = []
        self.s11open  = []
        self.s11load  = []

        self.s21through   = []
        self.s21isolation = []

        try:
            file = open(filename, "r")
            lines = file.readlines()
            parsed_header = False
            for l in lines:
                l = l.strip()
                if l.startswith("!"):
                    continue
                if l.startswith("#") and not parsed_header:
                    # Check that this is a valid header
                    if l == "# Hz ShortR ShortI OpenR OpenI LoadR LoadI ThroughR ThroughI IsolationR IsolationI":
                        parsed_header = True
                        continue
                    else:
                        # This is some other comment line
                        continue
                if not parsed_header:
                    logger.warning("Warning: Read line without having read header: %s", l)
                    continue

                try:
                    if l.count(" ") == 6:
                        freq, shortr, shorti, openr, openi, loadr, loadi = l.split(" ")
                        self.s11short.append(Datapoint(int(freq), float(shortr), float(shorti)))
                        self.s11open.append(Datapoint(int(freq), float(openr), float(openi)))
                        self.s11load.append(Datapoint(int(freq), float(loadr), float(loadi)))

                    else:
                        freq, shortr, shorti, openr, openi, loadr, loadi, throughr, throughi, isolationr, isolationi = l.split(" ")
                        self.s11short.append(Datapoint(int(freq), float(shortr), float(shorti)))
                        self.s11open.append(Datapoint(int(freq), float(openr), float(openi)))
                        self.s11load.append(Datapoint(int(freq), float(loadr), float(loadi)))
                        self.s21through.append(Datapoint(int(freq), float(throughr), float(throughi)))
                        self.s21isolation.append(Datapoint(int(freq), float(isolationr), float(isolationi)))

                except ValueError as e:
                    logger.exception("Error parsing calibration data \"%s\": %s", l, e)
            file.close()
        except Exception as e:
            logger.exception("Failed loading calibration data: %s", e)