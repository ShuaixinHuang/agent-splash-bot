# Dependencies

Aurora Boot v0.2 contains newly implemented application code and procedural graphics. Its application source is released under the Unlicense. It does not bundle animation videos, external character artwork, fonts, or sound recordings.

The source license does not replace the licenses of installed dependencies:

- **PySide6 / Qt for Python**: LGPL v3, GPL v3, or commercial terms depending on distribution and components. This application uses the Qt Core, Gui and Widgets modules. See <https://doc.qt.io/qtforpython-6/licenses.html> and the license files installed with the PySide6 packages.
- **python-xlib** (Linux X11): LGPL v2 or later. See <https://github.com/python-xlib/python-xlib> and the installed distribution's license files.
- **PyObjC** (macOS): MIT. See <https://pyobjc.readthedocs.io/en/latest/license.html> and the installed distribution's license files.

Dependencies are installed separately by pip. Their copyright, license and other required notices remain applicable. The release distributes Python source and a pure-Python wheel; it does not freeze or bundle these libraries into a native executable.
