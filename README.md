NanoVNASaver
============
A small tool to save touchstone files from the NanoVNA, and to allow sweeping frequency spans in sections to gain more than 101 data points.

Copyright 2019 Rune B. Broberg

### Introduction
This software connects to a NanoVNA and extracts the data for display on a computer, and for saving to Touchstone files.

Current features:
- Reading data from a NanoVNA
- Splitting a frequency range into multiple segments to increase resolution (tried up to >10k points)
- Displaying data on Smith charts and logmag-charts for both S11 and S21
- Displaying two markers, and the impedance and VSWR (against 50 ohm) at these locations
- Exporting 1-port and 2-port Touchstone files
- TDR function (measurement of cable length)

Expected features:
- Mouse control of markers
- Further data readout for markers, such as return loss/forward gain
- Reading and displaying Touchstone files

0.0.2:
![Screenshot of version 0.0.1](https://i.imgur.com/eoLwv35.png)
0.0.1:
![Screenshot of version 0.0.1](https://i.imgur.com/kcCC2eK.png)

### Windows

The software was written in Python on Windows, using Pycharm, and the modules PyQT5, numpy and pyserial.

### Linux

In order to run this app in Linux environment, you'll need the following packages:

* `python3-serial`
* `python3-pyqt5`
* `numpy`

### To Run

```sh
python3 nanovna-saver.py
```

### License
This software is licensed under version 3 of the GNU General Public License. It comes with NO WARRANTY.

You can use it, commercially as well. You may make changes to the code, but I (and the license) ask that you give these changes back to the community.

### Credits
Original application by Rune B. Broberg (5Q5R)

TDR inspiration shamelessly stolen from the work of Salil (VU2CWA) at https://nuclearrambo.com/wordpress/accurately-measuring-cable-length-with-nanovna/

Thanks to everyone who's tested, commented and inspired.