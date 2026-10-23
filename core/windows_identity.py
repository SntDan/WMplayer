"""Windows shell identity shared by the taskbar and media controls."""

from __future__ import annotations

import ctypes
import logging
import os
from pathlib import Path
import sys

APP_ID = "WMplayer.WMplayer"


def configure_windows_identity() -> None:
    if sys.platform != "win32":
        return
    frozen = getattr(sys, "frozen", False)
    try:
        set_app_id = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
        set_app_id.argtypes = [ctypes.c_wchar_p]
        set_app_id.restype = ctypes.c_long
        app_id = APP_ID if frozen else APP_ID + ".Development"
        if set_app_id(app_id) < 0:
            raise OSError("Could not set WMplayer's Windows application ID")
        if frozen:
            _register_shortcut()
    except Exception:
        logging.getLogger(__name__).warning(
            "Could not register WMplayer's Windows identity", exc_info=True
        )


def _register_shortcut() -> None:
    # Windows resolves the media session's name through a Start menu shortcut
    # carrying the same AppUserModelID. A process ID alone is insufficient.
    import pythoncom
    from win32com import storagecon
    from win32com.propsys import propsys, pscon
    from win32com.shell import shell, shellcon

    root = Path(__file__).resolve().parent.parent
    icon_source = root / "assets" / "wmplayer.ico"
    # A one-file PyInstaller extraction disappears at exit. Keep the shell icon
    # outside that temporary directory so it also works after the app closes.
    icon_path = Path(os.environ["LOCALAPPDATA"]) / "WMplayer" / "wmplayer.ico"
    icon_path.parent.mkdir(parents=True, exist_ok=True)
    icon_bytes = icon_source.read_bytes()
    if not icon_path.exists() or icon_path.read_bytes() != icon_bytes:
        icon_path.write_bytes(icon_bytes)

    programs = shell.SHGetFolderPath(0, shellcon.CSIDL_PROGRAMS, None, 0)
    shortcut = Path(programs) / "WMplayer.lnk"
    target = Path(sys.executable).resolve()
    working_dir = target.parent
    link = pythoncom.CoCreateInstance(
        shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER,
        shell.IID_IShellLink,
    )
    persist = link.QueryInterface(pythoncom.IID_IPersistFile)
    store = link.QueryInterface(propsys.IID_IPropertyStore)
    if shortcut.exists():
        persist.Load(str(shortcut), storagecon.STGM_READWRITE)
        if (
            link.GetPath(0)[0] == str(target)
            and link.GetArguments() == ""
            and link.GetWorkingDirectory() == str(working_dir)
            and link.GetIconLocation() == (str(icon_path), 0)
            and store.GetValue(pscon.PKEY_AppUserModel_ID).GetValue() == APP_ID
        ):
            return
    link.SetPath(str(target))
    link.SetArguments("")
    link.SetWorkingDirectory(str(working_dir))
    link.SetDescription("WMplayer")
    link.SetIconLocation(str(icon_path), 0)
    store.SetValue(pscon.PKEY_AppUserModel_ID, propsys.PROPVARIANTType(APP_ID))
    store.Commit()
    persist.Save(str(shortcut), True)
    shell.SHChangeNotify(shellcon.SHCNE_UPDATEITEM, shellcon.SHCNF_PATHW, str(shortcut), None)
