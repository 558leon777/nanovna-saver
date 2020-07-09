#  NanoVNASaver
#
#  A python program to view and export Touchstone data from a NanoVNA
#  Copyright (C) 2019, 2020  Rune B. Broberg
#  Copyright (C) 2020 NanoVNA-Saver Authors
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
import logging
from time import sleep
from typing import List, Tuple

import numpy as np
from PyQt5 import QtCore, QtWidgets
from PyQt5.QtCore import pyqtSlot, pyqtSignal

from NanoVNASaver.Calibration import correct_delay
from NanoVNASaver.Formatting import parse_frequency
from NanoVNASaver.RFTools import Datapoint

logger = logging.getLogger(__name__)


def truncate(values: List[List[Tuple]], count: int) -> List[List[Tuple]]:
    """truncate drops extrema from data list if averaging is active"""
    keep = len(values) - count
    logger.debug("Truncating from %d values to %d", len(values), keep)
    if count < 1 or keep < 1:
        logger.info("Not doing illegal truncate")
        return values
    truncated = []
    for valueset in np.swapaxes(values, 0, 1).tolist():
        avg = complex(*np.average(valueset, 0))
        truncated.append(
            sorted(valueset,
                   key=lambda v, a=avg:
                   abs(a - complex(*v)))[:keep])
    return np.swapaxes(truncated, 0, 1).tolist()


class WorkerSignals(QtCore.QObject):
    updated = pyqtSignal()
    finished = pyqtSignal()
    sweepError = pyqtSignal()
    fatalSweepError = pyqtSignal()


class Sweep():
    def __init__(self, start: int = 3600000, end: int = 30000000,
                 points: int = 101, sweeps: int = 1):
        self.start = start
        self.end = end
        self.points = points
        self.sweeps = sweeps
        self.span = self.end - self.start
        self.step = self.stepsize()
        self.check()

    def __repr__(self) -> str:
        return (
            f"Sweep({self.start}, {self.end}, {self.points} {self.sweeps})")

    def __eq__(self, other) -> bool:
        return(self.start == other.start and
               self.end == other.end and
               self.points == other.points and
               self.sweeps == other.sweeps)

    def check(self):
        if not(self.sweeps > 0 and
               self.points > 0 and
               self.start > 0 and
               self.end > 0 and
               self.step >= 1):
            raise ValueError(f"Illegal sweep settings: {self}")

    def stepsize(self) -> int:
        return int(self.span / (self.points * self.sweeps - 1))

    def get_index_range(self, index: int) -> Tuple[int, int]:
        start = self.start + index * self.points * self.step
        end = start + (self.points -1) * self.step
        return (start, end)


class SweepWorker(QtCore.QRunnable):
    def __init__(self, app: QtWidgets.QWidget):
        super().__init__()
        logger.info("Initializing SweepWorker")
        self.signals = WorkerSignals()
        self.app = app
        self.vna: app.vna
        self.sweep = Sweep()
        self.setAutoDelete(False)
        self.percentage = 0
        self.data11: List[Datapoint] = []
        self.data21: List[Datapoint] = []
        self.rawData11: List[Datapoint] = []
        self.rawData21: List[Datapoint] = []
        self.stopped = False
        self.running = False
        self.continuousSweep = False
        self.averaging = False
        self.averages = 3
        self.truncates = 0
        self.error_message = ""
        self.offsetDelay = 0

    @pyqtSlot()
    def run(self):
        logger.info("Initializing SweepWorker")
        self.running = True
        self.percentage = 0
        if not self.vna.connected():
            logger.debug(
                "Attempted to run without being connected to the NanoVNA")
            self.running = False
            return
        try:
            sweep = Sweep(
                parse_frequency(self.app.sweepStartInput.text()),
                parse_frequency(self.app.sweepEndInput.text()),
                self.vna.datapoints,
                int(self.app.sweepCountInput.text())
            )
        except ValueError:
            self.error_message = (
                "Unable to parse frequency inputs"
                " - check start and stop fields.")
            self.stopped = True
            self.running = False
            self.signals.sweepError.emit()
            return

        if self.averaging:
            logger.info("%d averages", self.averages)

        values11 = []
        values21 = []
        frequencies = []

        first_sweep = sweep != self.sweep
        self.sweep = sweep
        finished = False
        while not finished:
            for i in range(self.sweep.sweeps):
                logger.debug("Sweep segment no %d", i)
                if self.stopped:
                    logger.debug("Stopping sweeping as signalled")
                    finished = True
                    break
                start, stop = self.sweep.get_index_range(i)

                try:
                    if self.averaging:
                        freq, val11, val21 = self.readAveragedSegment(
                            start, stop, self.averages)
                    else:
                        freq, val11, val21 = self.readSegment(start, stop)
                    self.percentage = (i + 1) * 100 / self.sweep.sweeps

                    if not first_sweep:
                        self.updateData(values11, values21, i, self.sweep.points)
                    else:
                        frequencies.extend(freq)
                        values11.extend(val11)
                        values21.extend(val21)
                        self.saveData(frequencies, values11, values21)

                except ValueError as e:
                    self.error_message = str(e)
                    self.stopped = True
                    self.running = False
                    self.signals.sweepError.emit()

            if not self.continuousSweep:
                finished = True
            first_sweep = False

        if self.sweep.sweeps > 1:
            start = parse_frequency(self.app.sweepStartInput.text())
            end = parse_frequency(self.app.sweepEndInput.text())
            logger.debug("Resetting NanoVNA sweep to full range: %d to %d",
                         start, end)
            self.vna.resetSweep(start, end)

        self.percentage = 100
        logger.debug('Sending "finished" signal')
        self.signals.finished.emit()
        self.running = False

    def updateData(self, values11, values21, offset, segment_size=101):
        # Update the data from (i*101) to (i+1)*101
        logger.debug(
            "Calculating data and inserting in existing data at offset %d",
            offset)
        for i, val11 in enumerate(values11):
            re, im = val11
            re21, im21 = values21[i]
            freq = self.data11[offset * segment_size + i].freq
            raw_data11 = Datapoint(freq, re, im)
            raw_data21 = Datapoint(freq, re21, im21)
            data11, data21 = self.applyCalibration([raw_data11], [raw_data21])

            self.data11[offset * segment_size + i] = data11[0]
            self.data21[offset * segment_size + i] = data21[0]
            self.rawData11[offset * segment_size + i] = raw_data11
            self.rawData21[offset * segment_size + i] = raw_data21
        logger.debug("Saving data to application (%d and %d points)",
                     len(self.data11), len(self.data21))
        self.app.saveData(self.data11, self.data21)
        logger.debug('Sending "updated" signal')
        self.signals.updated.emit()

    def saveData(self, frequencies, values11, values21):
        logger.debug("Freqs: %d, values11: %d, values21: %d",
                     len(frequencies), len(values11), len(values21))
        v11 = values11[:]
        v21 = values21[:]
        raw_data11 = []
        raw_data21 = []
        logger.debug("Calculating data including corrections")
        for freq in frequencies:
            real11, imag11 = v11.pop(0)
            real21, imag21 = v21.pop(0)
            raw_data11.append(Datapoint(freq, real11, imag11))
            raw_data21.append(Datapoint(freq, real21, imag21))
        self.rawData11 = raw_data11
        self.rawData21 = raw_data21
        self.data11, self.data21 = self.applyCalibration(
            raw_data11, raw_data21)
        logger.debug("Saving data to application (%d and %d points)",
                     len(self.data11), len(self.data21))
        self.app.saveData(self.data11, self.data21)
        logger.debug("Sending \"updated\" signal")
        self.signals.updated.emit()

    def applyCalibration(self,
                         raw_data11: List[Datapoint],
                         raw_data21: List[Datapoint]
                         ) -> Tuple[List[Datapoint], List[Datapoint]]:
        if self.offsetDelay != 0:
            tmp = []
            for dp in raw_data11:
                tmp.append(correct_delay(dp, self.offsetDelay, reflect=True))
            raw_data11 = tmp
            tmp = []
            for dp in raw_data21:
                tmp.append(correct_delay(dp, self.offsetDelay))
            raw_data21 = tmp

        if not self.app.calibration.isCalculated:
            return raw_data11, raw_data21

        data11: List[Datapoint] = []
        data21: List[Datapoint] = []

        if self.app.calibration.isValid1Port():
            for dp in raw_data11:
                data11.append(self.app.calibration.correct11(dp))
        else:
            data11 = raw_data11

        if self.app.calibration.isValid2Port():
            for dp in raw_data21:
                data21.append(self.app.calibration.correct21(dp))
        else:
            data21 = raw_data21
        return data11, data21

    def readAveragedSegment(self, start, stop, averages):
        val11 = []
        val21 = []
        freq = []
        logger.info("Reading %d averages from %d to %d", averages, start, stop)
        for i in range(averages):
            if self.stopped:
                logger.debug("Stopping averaging as signalled")
                break
            logger.debug("Reading average no %d / %d", i+1, averages)
            freq, tmp11, tmp21 = self.readSegment(start, stop)
            val11.append(tmp11)
            val21.append(tmp21)
            self.percentage += 100 / (self.sweep.sweeps * averages)
            self.signals.updated.emit()

        logger.debug("Post-processing averages")
        logger.debug("Truncating %d values by %d", len(val11), self.truncates)
        val11 = truncate(val11, self.truncates)
        val21 = truncate(val21, self.truncates)
        logger.debug("Averaging %d values", len(val11))

        return11 = np.average(val11, 0).tolist()
        return21 = np.average(val21, 0).tolist()

        return freq, return11, return21

    def readSegment(self, start, stop):
        logger.debug("Setting sweep range to %d to %d", start, stop)
        self.vna.setSweep(start, stop)

        # Let's check the frequencies first:
        frequencies = self.vna.readFrequencies()
        # S11
        values11 = self.readData("data 0")
        # S21
        values21 = self.readData("data 1")

        if (len(frequencies) != len(values11) or
                len(frequencies) != len(values21)):
            logger.info("No valid data during this run")
            # TODO: display gui warning
            return [], [], []
        return frequencies, values11, values21

    def readData(self, data):
        logger.debug("Reading %s", data)
        done = False
        returndata = []
        count = 0
        while not done:
            done = True
            returndata = []
            tmpdata = self.vna.readValues(data)
            logger.debug("Read %d values", len(tmpdata))
            for d in tmpdata:
                a, b = d.split(" ")
                try:
                    if self.vna.validateInput and (
                            abs(float(a)) > 9.5 or
                            abs(float(b)) > 9.5):
                        logger.warning(
                            "Got a non plausible data value: (%s)", d)
                        done = False
                        break
                    returndata.append((float(a), float(b)))
                except ValueError as exc:
                    logger.exception("An exception occurred reading %s: %s",
                                     data, exc)
                    done = False
            if not done:
                logger.debug("Re-reading %s", data)
                sleep(0.2)
                count += 1
                if count == 5:
                    logger.error("Tried and failed to read %s %d times.",
                                 data, count)
                if count >= 10:
                    logger.critical(
                        "Tried and failed to read %s %d times. Giving up.",
                        data, count)
                    raise IOError(
                        f"Failed reading {data} {count} times.\n"
                        f"Data outside expected valid ranges,"
                        f" or in an unexpected format.\n\n"
                        f"You can disable data validation on the"
                        f"device settings screen.")
        return returndata

    def setContinuousSweep(self, continuous_sweep: bool):
        self.continuousSweep = continuous_sweep

    def setAveraging(self, averaging: bool, averages: str, truncates: str):
        self.averaging = averaging
        try:
            self.averages = int(averages)
            self.truncates = int(truncates)
        except ValueError:
            return

    def setVNA(self, vna):
        self.vna = vna
