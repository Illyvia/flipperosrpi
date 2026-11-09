#!/usr/bin/env python3
"""Compatibility entry point; configure-display.py now supports DSI and HDMI."""
import os, pathlib, sys
os.execv(sys.executable,[sys.executable,str(pathlib.Path(__file__).with_name('configure-display.py')),*sys.argv[1:]])
