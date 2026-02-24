"""py2app setup for FocusQuest.

Build a macOS .app bundle:
    pip install py2app
    python setup.py py2app
"""

from setuptools import setup

APP = ["main.py"]
DATA_FILES = []
OPTIONS = {
    "argv_emulation": False,
    "iconfile": None,  # Replace with .icns path when a proper icon exists
    "plist": {
        "CFBundleName": "FocusQuest",
        "CFBundleDisplayName": "FocusQuest",
        "CFBundleIdentifier": "com.focusquest.app",
        "CFBundleVersion": "0.1.0",
        "CFBundleShortVersionString": "0.1.0",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "13.0",
    },
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
    name="FocusQuest",
    version="0.1.0",
    packages=["focusquest"],
)
