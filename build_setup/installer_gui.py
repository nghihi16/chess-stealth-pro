# -*- coding: utf-8 -*-
"""
Chess Stealth - Pure Monochrome Luxury Glassmorphism Installer Wizard
Strictly Black & White palette. Custom monochrome diffused glow background.
English UI with pure black checkmark on white indicator.
Smooth 60fps animations for all features, buttons, progress, icons, and transitions.
"""

import sys
import os
import zipfile
import shutil
import subprocess
import threading
import time
import ctypes
import winreg
import re

GITHUB_REPO = "nghihi16/chess-stealth-pro"
APP_VERSION = "3.2.4"

def parse_version(tag):
    cleaned = re.sub(r'^[vV]', '', str(tag).strip())
    parts = []
    for p in cleaned.split('.'):
        digits = re.findall(r'\d+', p)
        parts.append(int(digits[0]) if digits else 0)
    return tuple(parts)


def _format_version_tag(ver, fallback=APP_VERSION):
    cleaned = re.sub(r'^[vV]+', '', str(ver or '').strip())
    if not cleaned:
        cleaned = re.sub(r'^[vV]+', '', str(fallback).strip())
    return f"v{cleaned}"


def resolve_installer_update_state(result, installed_version, bundled_version=APP_VERSION, is_update_mode=False):
    """Decide whether Setup uses bundled payload.zip or GitHub asset without downgrading."""
    bundled_tag = _format_version_tag(bundled_version)
    bundled_ver = parse_version(bundled_version)
    installed_raw = str(installed_version or bundled_version).strip() or bundled_version
    installed_tag = _format_version_tag(installed_raw, bundled_version)
    installed_ver = parse_version(installed_raw)

    res = result or {}
    remote_ok = bool(res.get("available"))
    remote_ver = res.get("version", (0, 0, 0)) if remote_ok else (0, 0, 0)
    remote_url = res.get("download_url") if remote_ok else None
    remote_tag = _format_version_tag(res.get("tag", "")) if (remote_ok and res.get("tag")) else ""

    use_remote = bool(remote_url) and (
        remote_ver > bundled_ver
        or (is_update_mode and installed_ver > bundled_ver and remote_ver >= installed_ver)
    )
    if use_remote:
        download_url = remote_url
        source_ver = remote_ver
        source_tag = remote_tag or bundled_tag
        source_label = "available on GitHub"
        new_version = source_tag
    else:
        download_url = None
        source_ver = bundled_ver
        source_tag = bundled_tag
        source_label = "ready to install"
        new_version = bundled_version

    if not is_update_mode:
        return {
            "download_url": download_url,
            "new_version": new_version,
            "badge_text": "",
            "highlight": False,
            "btn_text": "Get Started",
        }

    if source_ver > installed_ver:
        return {
            "download_url": download_url,
            "new_version": new_version,
            "badge_text": f"✦ New version {source_tag} {source_label}",
            "highlight": True,
            "btn_text": f"Update to {source_tag}",
        }

    badge_text = (
        f"✓ Chess Stealth {installed_tag} is up to date"
        if (remote_ok or bundled_ver >= installed_ver)
        else f"Installed: {installed_tag}"
    )
    return {
        "download_url": download_url,
        "new_version": installed_tag if (not use_remote and installed_ver > bundled_ver) else new_version,
        "badge_text": badge_text,
        "highlight": False,
        "btn_text": "Reinstall / Repair",
    }

def kill_running_process(process_name="ChessStealth.exe"):
    try:
        subprocess.run(
            ["taskkill", "/f", "/t", "/im", process_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=0x08000000,
            timeout=5,
            check=False,
        )
        deadline = time.time() + 3.0
        while time.time() < deadline:
            probe = subprocess.run(
                ["tasklist", "/fi", f"IMAGENAME eq {process_name}", "/nh"],
                capture_output=True,
                text=True,
                creationflags=0x08000000,
                timeout=3,
                check=False,
            )
            running = any(
                line.strip().lower().startswith(process_name.lower())
                for line in (probe.stdout or "").splitlines()
            )
            if not running:
                break
            time.sleep(0.15)
        time.sleep(0.25)
    except Exception:
        pass


def _extract_member_with_retry(zf, item, target_dir, retries=12, delay_sec=0.35):
    """Extract a zip member, retrying if Windows still holds a transient handle on an exiting EXE."""
    name = getattr(item, "filename", item)
    dest = os.path.join(target_dir, name)
    for attempt in range(retries):
        try:
            return zf.extract(item, target_dir)
        except PermissionError:
            if attempt == retries - 1:
                if os.path.isfile(dest):
                    try:
                        stale = f"{dest}.old_{int(time.time() * 1000)}"
                        os.replace(dest, stale)
                        return zf.extract(item, target_dir)
                    except OSError:
                        pass
                raise
            if delay_sec > 0:
                time.sleep(delay_sec)

def get_installed_info():
    try:
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\ChessStealth"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            install_loc, _ = winreg.QueryValueEx(key, "InstallLocation")
            version, _ = winreg.QueryValueEx(key, "DisplayVersion")
            exe_path = os.path.join(install_loc, "ChessStealth.exe")
            if os.path.exists(exe_path):
                return {
                    "installed": True,
                    "location": install_loc,
                    "version": version,
                    "exe_path": exe_path
                }
    except Exception:
        pass
    
    default_dir = os.path.join(
        os.environ.get("LOCALAPPDATA", r"C:\Program Files"),
        "Programs",
        "ChessStealth"
    )
    exe_path = os.path.join(default_dir, "ChessStealth.exe")
    if os.path.exists(exe_path):
        return {
            "installed": True,
            "location": default_dir,
            "version": APP_VERSION,
            "exe_path": exe_path
        }
    return {"installed": False, "location": default_dir, "version": "", "exe_path": ""}

from PySide6.QtCore import (
    Qt,
    QThread,
    Signal,
    QPoint,
    QRectF,
    QSize,
    QPropertyAnimation,
    QEasingCurve,
    QParallelAnimationGroup,
    Property,
)
from PySide6.QtGui import (
    QColor,
    QPainter,
    QPainterPath,
    QPen,
    QBrush,
    QFont,
    QIcon,
    QPixmap,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QCheckBox,
    QFileDialog,
    QProgressBar,
    QStackedWidget,
    QFrame,
    QGraphicsOpacityEffect,
)

# -------------------------------------------------------------
# RESOURCE & PATH RESOLUTION
# -------------------------------------------------------------
def get_resource_path(relative_path):
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    p1 = os.path.join(base_dir, relative_path)
    if os.path.exists(p1):
        return p1
    p2 = os.path.join(base_dir, "build_setup", relative_path)
    if os.path.exists(p2):
        return p2
    return relative_path

def get_free_space_mb(folder):
    try:
        if not os.path.exists(folder):
            drive = os.path.splitdrive(os.path.abspath(folder))[0] + "\\"
        else:
            drive = folder
        free_bytes = ctypes.c_ulonglong(0)
        ctypes.windll.kernel32.GetDiskFreeSpaceExW(
            ctypes.c_wchar_p(drive), None, None, ctypes.byref(free_bytes)
        )
        return free_bytes.value // (1024 * 1024)
    except Exception:
        return 50000

def create_windows_shortcut(target_exe, shortcut_path, icon_path=None, description="Chess Stealth"):
    try:
        vbs_lines = [
            'Set oWS = WScript.CreateObject("WScript.Shell")',
            f'Set oLink = oWS.CreateShortcut("{shortcut_path}")',
            f'oLink.TargetPath = "{target_exe}"',
            f'oLink.WorkingDirectory = "{os.path.dirname(target_exe)}"',
            f'oLink.Description = "{description}"',
        ]
        if icon_path and os.path.exists(icon_path):
            vbs_lines.append(f'oLink.IconLocation = "{icon_path},0"')
        vbs_lines.append('oLink.Save')
        
        temp_dir = os.environ.get("TEMP", os.path.dirname(shortcut_path))
        vbs_path = os.path.join(temp_dir, f"_mk_sc_{int(time.time()*1000)}.vbs")
        with open(vbs_path, "w", encoding="utf-8") as f:
            f.write("\n".join(vbs_lines))
        subprocess.run(["cscript", "//nologo", vbs_path], creationflags=0x08000000, check=False)
        try:
            os.remove(vbs_path)
        except Exception:
            pass
    except Exception as e:
        print(f"Error creating shortcut: {e}")

def register_uninstall(install_dir, exe_path, icon_path, version=APP_VERSION):
    try:
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\ChessStealth"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, "Chess Stealth")
            winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, str(version))
            winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, "Chess Stealth")
            winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, install_dir)
            winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, icon_path)
            uninst_bat = os.path.join(install_dir, "uninstall.bat")
            winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, f'cmd.exe /c "{uninst_bat}"')
            winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
    except Exception as e:
        print(f"Registry registration error: {e}")

# -------------------------------------------------------------
# MINIMAL VECTOR ICONS (MONOCHROME)
# -------------------------------------------------------------
SVG_SUCCESS_CHECK = """<svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
  <circle cx="24" cy="24" r="22" fill="#18181b" stroke="#ffffff" stroke-width="2"/>
  <path d="M15 24L21 30L33 18" stroke="#ffffff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
</svg>"""

SVG_CLOSE = """<svg viewBox="0 0 24 24" fill="none" stroke="#a1a1aa" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg">
  <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
</svg>"""

SVG_MIN = """<svg viewBox="0 0 24 24" fill="none" stroke="#a1a1aa" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg">
  <line x1="5" y1="12" x2="19" y2="12"/>
</svg>"""

def render_svg(svg_str, width, height):
    renderer = QSvgRenderer(svg_str.encode("utf-8"))
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return pixmap

# -------------------------------------------------------------
# ANIMATED BUTTON WITH HOVER GLOW & TACTILE SCALE PRESS
# -------------------------------------------------------------
class AnimatedButton(QPushButton):
    def __init__(self, text, is_primary=True, min_width=110, parent=None):
        super().__init__(text, parent)
        self.is_primary = is_primary
        self.setMinimumWidth(min_width)
        self.setMinimumHeight(38)
        self.setCursor(Qt.PointingHandCursor)
        self._hover_progress = 0.0
        self._press_progress = 0.0

        self._hover_anim = QPropertyAnimation(self, b"hover_progress", self)
        self._hover_anim.setDuration(160)
        self._hover_anim.setEasingCurve(QEasingCurve.OutCubic)

        self._press_anim = QPropertyAnimation(self, b"press_progress", self)
        self._press_anim.setDuration(90)
        self._press_anim.setEasingCurve(QEasingCurve.OutCubic)

    def get_hover_progress(self):
        return self._hover_progress

    def set_hover_progress(self, val):
        self._hover_progress = val
        self.update()

    hover_progress = Property(float, get_hover_progress, set_hover_progress)

    def get_press_progress(self):
        return self._press_progress

    def set_press_progress(self, val):
        self._press_progress = val
        self.update()

    press_progress = Property(float, get_press_progress, set_press_progress)

    def enterEvent(self, event):
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_progress)
        self._hover_anim.setEndValue(1.0)
        self._hover_anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_progress)
        self._hover_anim.setEndValue(0.0)
        self._hover_anim.start()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press_anim.stop()
            self._press_anim.setStartValue(self._press_progress)
            self._press_anim.setEndValue(1.0)
            self._press_anim.start()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._press_anim.stop()
        self._press_anim.setStartValue(self._press_progress)
        self._press_anim.setEndValue(0.0)
        self._press_anim.start()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Tactile press scale (scale down to 0.96 on press)
        scale = 1.0 - (0.04 * self._press_progress)
        if scale != 1.0:
            cx = self.width() / 2.0
            cy = self.height() / 2.0
            painter.translate(cx, cy)
            painter.scale(scale, scale)
            painter.translate(-cx, -cy)

        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(rect, 7, 7)

        hp = self._hover_progress
        if self.is_primary:
            # Base white to subtle platinum on hover
            r = int(255 - hp * 25 - self._press_progress * 16)
            g = int(255 - hp * 25 - self._press_progress * 16)
            b = int(255 - hp * 22 - self._press_progress * 15)
            bg_color = QColor(r, g, b)

            if hp > 0.01:
                glow_pen = QPen(QColor(255, 255, 255, int(150 + hp * 105)), 1.5)
                painter.setPen(glow_pen)
            else:
                painter.setPen(QPen(QColor(255, 255, 255), 1.0))
            painter.setBrush(QBrush(bg_color))
            painter.drawPath(path)

            painter.setPen(QColor(9, 9, 11))
            f = self.font()
            f.setPixelSize(13)
            f.setBold(True)
            painter.setFont(f)
            painter.drawText(self.rect(), Qt.AlignCenter, self.text())
        else:
            # Secondary dark zinc button
            r = int(39 + hp * 24)
            g = int(39 + hp * 24)
            b = int(42 + hp * 28)
            bg_color = QColor(r, g, b)

            br_r = int(63 + hp * 50)
            br_g = int(63 + hp * 50)
            br_b = int(70 + hp * 52)
            painter.setPen(QPen(QColor(br_r, br_g, br_b), 1.0))
            painter.setBrush(QBrush(bg_color))
            painter.drawPath(path)

            text_val = int(244 + hp * 11)
            painter.setPen(QColor(text_val, text_val, text_val))
            f = self.font()
            f.setPixelSize(13)
            f.setWeight(QFont.Weight.DemiBold)
            painter.setFont(f)
            painter.drawText(self.rect(), Qt.AlignCenter, self.text())

# -------------------------------------------------------------
# ANIMATED ICON BUTTON (HEADER CONTROLS)
# -------------------------------------------------------------
class AnimatedIconButton(QPushButton):
    def __init__(self, icon_pixmap, is_close=False, parent=None):
        super().__init__(parent)
        self.setFixedSize(30, 30)
        self.setCursor(Qt.PointingHandCursor)
        self.icon_pixmap = icon_pixmap
        self.is_close = is_close
        self._hover_progress = 0.0
        self._press_progress = 0.0

        self._hover_anim = QPropertyAnimation(self, b"hover_progress", self)
        self._hover_anim.setDuration(140)
        self._hover_anim.setEasingCurve(QEasingCurve.OutCubic)

        self._press_anim = QPropertyAnimation(self, b"press_progress", self)
        self._press_anim.setDuration(80)
        self._press_anim.setEasingCurve(QEasingCurve.OutCubic)

    def get_hover_progress(self):
        return self._hover_progress

    def set_hover_progress(self, val):
        self._hover_progress = val
        self.update()

    hover_progress = Property(float, get_hover_progress, set_hover_progress)

    def get_press_progress(self):
        return self._press_progress

    def set_press_progress(self, val):
        self._press_progress = val
        self.update()

    press_progress = Property(float, get_press_progress, set_press_progress)

    def enterEvent(self, event):
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_progress)
        self._hover_anim.setEndValue(1.0)
        self._hover_anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_progress)
        self._hover_anim.setEndValue(0.0)
        self._hover_anim.start()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press_anim.stop()
            self._press_anim.setStartValue(self._press_progress)
            self._press_anim.setEndValue(1.0)
            self._press_anim.start()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._press_anim.stop()
        self._press_anim.setStartValue(self._press_progress)
        self._press_anim.setEndValue(0.0)
        self._press_anim.start()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        scale = 1.0 - (0.08 * self._press_progress)
        if scale != 1.0:
            cx = self.width() / 2.0
            cy = self.height() / 2.0
            painter.translate(cx, cy)
            painter.scale(scale, scale)
            painter.translate(-cx, -cy)

        if self._hover_progress > 0.01:
            rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
            path = QPainterPath()
            path.addRoundedRect(rect, 6, 6)
            alpha = int(self._hover_progress * (36 if not self.is_close else 55))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(255, 255, 255, alpha)))
            painter.drawPath(path)

        if not self.icon_pixmap.isNull():
            ix = (self.width() - self.icon_pixmap.width()) // 2
            iy = (self.height() - self.icon_pixmap.height()) // 2
            painter.drawPixmap(ix, iy, self.icon_pixmap)

# -------------------------------------------------------------
# SMOOTH SLIDING STACKED WIDGET (CINEMATIC SCENE TRANSITIONS)
# -------------------------------------------------------------
class SlidingStackedWidget(QStackedWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_animating = False
        self._anim_group = None

    def setCurrentIndex(self, next_idx):
        if next_idx == self.currentIndex():
            return
        if self.currentIndex() == -1 or not self.isVisible() or self.width() <= 0:
            super().setCurrentIndex(next_idx)
            return
        if self._is_animating:
            return

        self.slide_to_index(next_idx)

    def slide_to_index(self, next_idx, duration=260):
        if self._is_animating:
            return
        curr_idx = self.currentIndex()
        if next_idx == curr_idx or next_idx < 0 or next_idx >= self.count():
            return

        self._is_animating = True
        curr_widget = self.widget(curr_idx)
        next_widget = self.widget(next_idx)

        width = self.width()
        height = self.height()

        forward = next_idx > curr_idx
        start_x = width if forward else -width

        next_widget.setGeometry(start_x, 0, width, height)
        next_widget.show()
        next_widget.raise_()

        eff_curr = QGraphicsOpacityEffect(curr_widget)
        curr_widget.setGraphicsEffect(eff_curr)
        eff_next = QGraphicsOpacityEffect(next_widget)
        next_widget.setGraphicsEffect(eff_next)

        self._anim_group = QParallelAnimationGroup(self)

        # Slide next widget in from edge
        anim_next_pos = QPropertyAnimation(next_widget, b"pos")
        anim_next_pos.setDuration(duration)
        anim_next_pos.setEasingCurve(QEasingCurve.OutCubic)
        anim_next_pos.setStartValue(QPoint(start_x, 0))
        anim_next_pos.setEndValue(QPoint(0, 0))
        self._anim_group.addAnimation(anim_next_pos)

        # Slide current widget slightly away
        anim_curr_pos = QPropertyAnimation(curr_widget, b"pos")
        anim_curr_pos.setDuration(duration)
        anim_curr_pos.setEasingCurve(QEasingCurve.OutCubic)
        anim_curr_pos.setStartValue(QPoint(0, 0))
        anim_curr_pos.setEndValue(QPoint(-int(start_x * 0.35), 0))
        self._anim_group.addAnimation(anim_curr_pos)

        # Cross-fade next widget in
        anim_next_op = QPropertyAnimation(eff_next, b"opacity")
        anim_next_op.setDuration(duration)
        anim_next_op.setEasingCurve(QEasingCurve.OutCubic)
        anim_next_op.setStartValue(0.0)
        anim_next_op.setEndValue(1.0)
        self._anim_group.addAnimation(anim_next_op)

        # Cross-fade current widget out
        anim_curr_op = QPropertyAnimation(eff_curr, b"opacity")
        anim_curr_op.setDuration(duration)
        anim_curr_op.setEasingCurve(QEasingCurve.OutCubic)
        anim_curr_op.setStartValue(1.0)
        anim_curr_op.setEndValue(0.0)
        self._anim_group.addAnimation(anim_curr_op)

        def on_finished():
            curr_widget.setGraphicsEffect(None)
            next_widget.setGraphicsEffect(None)
            super(SlidingStackedWidget, self).setCurrentIndex(next_idx)
            curr_widget.hide()
            curr_widget.move(0, 0)
            self._is_animating = False

        self._anim_group.finished.connect(on_finished)
        self._anim_group.start()

# -------------------------------------------------------------
# SMOOTH GLIDING PROGRESS BAR
# -------------------------------------------------------------
class SmoothProgressBar(QProgressBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._animated_val = 0.0
        self._anim = QPropertyAnimation(self, b"animated_val", self)
        self._anim.setDuration(240)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    def get_animated_val(self):
        return self._animated_val

    def set_animated_val(self, val):
        self._animated_val = val
        super().setValue(int(round(val)))

    animated_val = Property(float, get_animated_val, set_animated_val)

    def setSmoothValue(self, target_val):
        self._anim.stop()
        self._anim.setStartValue(self._animated_val)
        self._anim.setEndValue(float(target_val))
        self._anim.start()

# -------------------------------------------------------------
# ANIMATED SUCCESS CHECKMARK (STEP 5 POP-IN)
# -------------------------------------------------------------
class AnimatedSuccessIcon(QWidget):
    def __init__(self, svg_str, size=48, parent=None):
        super().__init__(parent)
        self.setFixedSize(size + 12, size + 12)
        self.svg_pixmap = render_svg(svg_str, size, size)
        self._scale = 1.0
        self._opacity = 1.0

        self._anim_scale = QPropertyAnimation(self, b"scale_val", self)
        self._anim_scale.setDuration(420)
        self._anim_scale.setEasingCurve(QEasingCurve.OutBack)

        self._anim_op = QPropertyAnimation(self, b"opacity_val", self)
        self._anim_op.setDuration(260)
        self._anim_op.setEasingCurve(QEasingCurve.OutCubic)

    def get_scale(self):
        return self._scale

    def set_scale(self, val):
        self._scale = val
        self.update()

    scale_val = Property(float, get_scale, set_scale)

    def get_opacity(self):
        return self._opacity

    def set_opacity(self, val):
        self._opacity = val
        self.update()

    opacity_val = Property(float, get_opacity, set_opacity)

    def play_pop(self):
        self._scale = 0.4
        self._opacity = 0.0
        self._anim_scale.stop()
        self._anim_scale.setStartValue(0.4)
        self._anim_scale.setEndValue(1.0)
        self._anim_scale.start()

        self._anim_op.stop()
        self._anim_op.setStartValue(0.0)
        self._anim_op.setEndValue(1.0)
        self._anim_op.start()

    def paintEvent(self, event):
        if self._opacity <= 0.001 or self._scale <= 0.001:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setOpacity(self._opacity)

        cx = self.width() / 2.0
        cy = self.height() / 2.0
        painter.translate(cx, cy)
        painter.scale(self._scale, self._scale)
        painter.translate(-cx, -cy)

        ix = (self.width() - self.svg_pixmap.width()) // 2
        iy = (self.height() - self.svg_pixmap.height()) // 2
        painter.drawPixmap(ix, iy, self.svg_pixmap)

# -------------------------------------------------------------
# CUSTOM MONOCHROME GLASS FRAME WITH DIFFUSED GLOW
# -------------------------------------------------------------
class GlassFrame(QFrame):
    def __init__(self, bg_image_path=None, parent=None):
        super().__init__(parent)
        self.setObjectName("GlassCard")
        self.bg_pixmap = None
        if bg_image_path and os.path.exists(bg_image_path):
            self.bg_pixmap = QPixmap(bg_image_path)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, 14, 14)

        # Clip painting inside rounded rect
        painter.save()
        painter.setClipPath(path)

        # Fill base obsidian black
        painter.fillRect(self.rect(), QColor(10, 11, 14))

        # Paint monochrome diffused aura
        if self.bg_pixmap and not self.bg_pixmap.isNull():
            scaled = self.bg_pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.setOpacity(0.92)
            painter.drawPixmap(x, y, scaled)
            painter.setOpacity(1.0)

            # Dark glass tint overlay for readability & WCAG contrast
            painter.fillRect(self.rect(), QColor(8, 10, 14, 165))

        painter.restore()

        # Crisp frosted glass border
        pen = QPen(QColor(255, 255, 255, 45), 1.0)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

# -------------------------------------------------------------
# ASYNCHRONOUS GITHUB RELEASES UPDATE CHECKER
# -------------------------------------------------------------
class GitHubCheckThread(QThread):
    checked = Signal(dict)

    def __init__(self, repo=GITHUB_REPO):
        super().__init__()
        self.repo = repo

    def run(self):
        import urllib.request
        import json
        api_url = f"https://api.github.com/repos/{self.repo}/releases/latest"
        try:
            req = urllib.request.Request(
                api_url,
                headers={"User-Agent": "ChessStealthInstaller/1.0"}
            )
            with urllib.request.urlopen(req, timeout=4) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    tag = data.get("tag_name", "")
                    assets = data.get("assets", [])
                    payload_asset = next((a for a in assets if a.get("name") == "payload.zip"), None)
                    download_url = payload_asset.get("browser_download_url") if payload_asset else None
                    self.checked.emit({
                        "available": True,
                        "tag": tag,
                        "version": parse_version(tag),
                        "download_url": download_url,
                        "body": data.get("body", "")
                    })
                    return
        except Exception as e:
            self.checked.emit({"available": False, "error": str(e)})

# -------------------------------------------------------------
# WORKER THREAD FOR EXTRACTION & UPDATE
# -------------------------------------------------------------
class InstallWorker(QThread):
    progress = Signal(int, str)
    finished_success = Signal(str)
    failed = Signal(str)

    def __init__(self, target_dir, create_desktop_sc, create_start_menu_sc, download_url=None, new_version=APP_VERSION):
        super().__init__()
        self.target_dir = target_dir
        self.create_desktop_sc = create_desktop_sc
        self.create_start_menu_sc = create_start_menu_sc
        self.download_url = download_url
        self.new_version = new_version

    def run(self):
        temp_download_zip = None
        try:
            self.progress.emit(3, "Closing active Chess Stealth instances...")
            kill_running_process("ChessStealth.exe")
            kill_running_process("ChessPro.exe")
            os.makedirs(self.target_dir, exist_ok=True)
            time.sleep(0.1)

            if self.download_url:
                self.progress.emit(6, "Connecting to GitHub Releases...")
                import urllib.request
                req = urllib.request.Request(
                    self.download_url,
                    headers={"User-Agent": "ChessStealthInstaller/1.0"}
                )
                temp_dir = os.environ.get("TEMP", os.path.dirname(self.target_dir))
                temp_download_zip = os.path.join(temp_dir, f"_cs_update_{int(time.time()*1000)}.zip")
                
                with urllib.request.urlopen(req, timeout=60) as resp:
                    total_size = int(resp.headers.get("content-length", 0))
                    downloaded = 0
                    chunk_size = 64 * 1024
                    with open(temp_download_zip, "wb") as f:
                        while True:
                            chunk = resp.read(chunk_size)
                            if not chunk:
                                break
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                pct = 6 + int((downloaded / total_size) * 44)
                                mb_down = downloaded / (1024 * 1024)
                                mb_total = total_size / (1024 * 1024)
                                self.progress.emit(pct, f"Downloading update: {mb_down:.1f} MB / {mb_total:.1f} MB ({pct}%)")
                payload_zip = temp_download_zip
            else:
                payload_zip = get_resource_path("payload.zip")
                if not os.path.exists(payload_zip):
                    raise FileNotFoundError(f"Package archive not found: {payload_zip}")

            self.progress.emit(52, "Unpacking and updating files...")
            with zipfile.ZipFile(payload_zip, "r") as zf:
                all_files = zf.infolist()
                total_files = len(all_files)
                for idx, item in enumerate(all_files, start=1):
                    _extract_member_with_retry(zf, item, self.target_dir)
                    percent = 52 + int((idx / total_files) * 42)
                    fname = os.path.basename(item.filename)
                    if fname:
                        self.progress.emit(percent, f"Updating: {fname}")
                    time.sleep(0.02)

            if temp_download_zip and os.path.exists(temp_download_zip):
                try:
                    os.remove(temp_download_zip)
                except Exception:
                    pass

            exe_path = os.path.join(self.target_dir, "ChessStealth.exe")
            icon_path = os.path.join(self.target_dir, "app_icon.ico")
            if not os.path.exists(icon_path):
                icon_path = exe_path

            if self.create_desktop_sc:
                desktop_folder = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")
                sc_desktop = os.path.join(desktop_folder, "Chess Stealth.lnk")
                create_windows_shortcut(exe_path, sc_desktop, icon_path, "Chess Stealth")

            if self.create_start_menu_sc:
                appdata = os.environ.get("APPDATA", "")
                programs_dir = os.path.join(appdata, r"Microsoft\Windows\Start Menu\Programs")
                sc_start = os.path.join(programs_dir, "Chess Stealth.lnk")
                create_windows_shortcut(exe_path, sc_start, icon_path, "Chess Stealth")

            register_uninstall(self.target_dir, exe_path, icon_path, version=self.new_version)
            self.progress.emit(100, "Update complete!" if self.download_url else "Installation complete!")
            time.sleep(0.2)
            self.finished_success.emit(exe_path)

        except Exception as e:
            if temp_download_zip and os.path.exists(temp_download_zip):
                try:
                    os.remove(temp_download_zip)
                except Exception:
                    pass
            self.failed.emit(str(e))

# -------------------------------------------------------------
# MAIN MONOCHROME GLASS SETUP WIZARD WINDOW
# -------------------------------------------------------------
class SetupWizardWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.drag_position = QPoint()
        self.installed_info = get_installed_info()
        self.is_update_mode = self.installed_info.get("installed", False)
        
        default_dir = os.path.join(
            os.environ.get("LOCALAPPDATA", r"C:\Program Files"),
            "Programs",
            "ChessStealth"
        )
        if self.is_update_mode and self.installed_info.get("location"):
            self.target_directory = self.installed_info["location"]
        else:
            self.target_directory = default_dir

        self.installed_exe_path = ""
        self._is_closing = False
        self.github_release = None
        self.download_url = None
        self.new_version = APP_VERSION

        self.init_ui()

        # Start background update check
        self.check_thread = GitHubCheckThread(GITHUB_REPO)
        self.check_thread.checked.connect(self.on_github_checked)
        self.check_thread.start()

    def init_ui(self):
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.resize(580, 420)
        self.setMinimumSize(540, 380)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(12, 12, 12, 12)

        bg_path = get_resource_path("monochrome_bg.png")
        self.glass_card = GlassFrame(bg_path)
        card_layout = QVBoxLayout(self.glass_card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        header = self.build_header_bar()
        card_layout.addWidget(header)

        # Smooth sliding stacked widget for cinematic page transitions
        self.stack = SlidingStackedWidget()
        self.page_welcome = self.build_page_welcome()
        self.page_location = self.build_page_location()
        self.page_options = self.build_page_options()
        self.page_installing = self.build_page_installing()
        self.page_finish = self.build_page_finish()

        self.stack.addWidget(self.page_welcome)     # 0
        self.stack.addWidget(self.page_location)    # 1
        self.stack.addWidget(self.page_options)     # 2
        self.stack.addWidget(self.page_installing)  # 3
        self.stack.addWidget(self.page_finish)      # 4

        card_layout.addWidget(self.stack)
        root_layout.addWidget(self.glass_card)

        self.apply_monochrome_style()

    def showEvent(self, event):
        super().showEvent(event)
        if not hasattr(self, "_shown_once"):
            self._shown_once = True
            self.play_window_fade_in()
            self.play_welcome_entrance()

    def play_window_fade_in(self):
        self.setWindowOpacity(0.0)
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_anim.setDuration(220)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._fade_anim.start()

    def play_welcome_entrance(self):
        eff = QGraphicsOpacityEffect(self.page_welcome)
        self.page_welcome.setGraphicsEffect(eff)
        self._welcome_anim = QPropertyAnimation(eff, b"opacity", self)
        self._welcome_anim.setDuration(350)
        self._welcome_anim.setStartValue(0.0)
        self._welcome_anim.setEndValue(1.0)
        self._welcome_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._welcome_anim.finished.connect(lambda: self.page_welcome.setGraphicsEffect(None))
        self._welcome_anim.start()

    def animate_close(self):
        if self._is_closing:
            return
        self._is_closing = True
        self._close_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._close_anim.setDuration(160)
        self._close_anim.setStartValue(self.windowOpacity())
        self._close_anim.setEndValue(0.0)
        self._close_anim.setEasingCurve(QEasingCurve.InCubic)
        self._close_anim.finished.connect(self.close)
        self._close_anim.start()

    def apply_monochrome_style(self):
        chk_path = get_resource_path("checkmark_black.png").replace("\\", "/")
        self.setStyleSheet(f"""
            #GlassCard {{
                background: transparent;
                border: none;
            }}
            #OptionsCard {{
                background: rgba(17, 18, 21, 0.75);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
            }}
            #OptionsCard QCheckBox {{
                background: transparent;
                border: none;
            }}
            QLabel {{
                color: #ffffff;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            }}
            QLineEdit {{
                background: rgba(9, 9, 11, 0.85);
                border: 1px solid #27272a;
                border-radius: 8px;
                color: #ffffff;
                padding: 8px 12px;
                font-size: 13px;
                font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
            }}
            QLineEdit:hover {{
                border-color: #3f3f46;
            }}
            QLineEdit:focus {{
                border-color: #ffffff;
                background: rgba(16, 17, 20, 0.95);
            }}
            QCheckBox {{
                color: #e4e4e7;
                font-size: 13px;
                spacing: 10px;
            }}
            QCheckBox:hover {{
                color: #ffffff;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 1px solid #52525b;
                background: rgba(18, 18, 22, 0.85);
            }}
            QCheckBox::indicator:hover {{
                border-color: #ffffff;
                background: rgba(30, 30, 38, 0.95);
            }}
            QCheckBox::indicator:checked {{
                background: #ffffff;
                border: 1px solid #ffffff;
                image: url('{chk_path}');
            }}
            QProgressBar {{
                background: rgba(24, 24, 27, 0.8);
                border: 1px solid #27272a;
                border-radius: 6px;
                height: 8px;
                text-align: center;
                color: transparent;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #71717a, stop:1 #ffffff);
                border-radius: 5px;
            }}
        """)

    def build_header_bar(self):
        header = QFrame()
        header.setFixedHeight(46)
        header.setStyleSheet("background: transparent; border-bottom: 1px solid rgba(255, 255, 255, 0.08);")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(16, 0, 10, 0)

        # Official App Logo (compact 20x20 matching main app)
        logo_lbl = QLabel()
        logo_path = get_resource_path("queen_light.png")
        if os.path.exists(logo_path):
            pix = QPixmap(logo_path).scaled(20, 20, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            logo_lbl.setPixmap(pix)
            logo_lbl.setFixedSize(20, 20)
        else:
            logo_lbl.setPixmap(render_svg(SVG_SUCCESS_CHECK, 18, 18))

        title_lbl = QLabel("Chess Stealth")
        title_lbl.setStyleSheet("font-size: 13px; font-weight: 700; color: #ffffff;")

        h_layout.addWidget(logo_lbl)
        h_layout.addSpacing(8)
        h_layout.addWidget(title_lbl)
        h_layout.addStretch()

        min_btn = AnimatedIconButton(render_svg(SVG_MIN, 12, 12), is_close=False)
        min_btn.setToolTip("Minimize")
        min_btn.clicked.connect(self.showMinimized)

        close_btn = AnimatedIconButton(render_svg(SVG_CLOSE, 12, 12), is_close=True)
        close_btn.setToolTip("Close")
        close_btn.clicked.connect(self.animate_close)

        h_layout.addWidget(min_btn)
        h_layout.addWidget(close_btn)
        return header

    # ---------------------------------------------------------
    # PAGE 1: WELCOME (HERO STEALTH CENTERED + UPDATE BADGE + ACTION BUTTON)
    # ---------------------------------------------------------
    def build_page_welcome(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 16, 20, 24)
        layout.setSpacing(0)

        layout.addStretch(10)

        # Hero Wordmark: Metallic chrome STEALTH in center
        hero_lbl = QLabel()
        hero_lbl.setAlignment(Qt.AlignCenter)
        hero_path = get_resource_path("hero_flanked_stealth.png")
        if os.path.exists(hero_path):
            pix = QPixmap(hero_path)
            if not pix.isNull():
                pix.setDevicePixelRatio(pix.width() / 340.0)
                hero_lbl.setPixmap(pix)
                hero_lbl.setFixedSize(340, int(round(pix.height() / (pix.width() / 340.0))))
        layout.addWidget(hero_lbl, 0, Qt.AlignCenter)

        layout.addSpacing(18)

        # Dynamic update/version status badge
        self.update_badge_lbl = QLabel("")
        self.update_badge_lbl.setAlignment(Qt.AlignCenter)
        self.update_badge_lbl.setStyleSheet("""
            font-size: 11px;
            font-weight: 600;
            color: #a1a1aa;
            padding: 4px 14px;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 10px;
        """)
        self.update_badge_lbl.hide()
        layout.addWidget(self.update_badge_lbl, 0, Qt.AlignCenter)

        layout.addSpacing(18)

        btn_box = QVBoxLayout()
        btn_box.setAlignment(Qt.AlignCenter)
        btn_box.setSpacing(8)

        btn_text = "Update Now" if self.is_update_mode else "Get Started"
        btn_w = 170 if self.is_update_mode else 160
        self.start_btn = self.create_primary_button(btn_text, btn_w)
        self.start_btn.clicked.connect(self.on_welcome_primary_clicked)
        btn_box.addWidget(self.start_btn, 0, Qt.AlignCenter)

        self.custom_opt_btn = QPushButton("Custom options...")
        self.custom_opt_btn.setCursor(Qt.PointingHandCursor)
        self.custom_opt_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #71717a;
                font-size: 11px;
                font-weight: 500;
                padding: 4px;
            }
            QPushButton:hover {
                color: #e4e4e7;
                text-decoration: underline;
            }
        """)
        self.custom_opt_btn.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        if not self.is_update_mode:
            self.custom_opt_btn.hide()
        btn_box.addWidget(self.custom_opt_btn, 0, Qt.AlignCenter)

        layout.addLayout(btn_box)

        layout.addStretch(11)

        return page

    # ---------------------------------------------------------
    # PAGE 2: LOCATION
    # ---------------------------------------------------------
    def build_page_location(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(14)

        title = QLabel("Installation Folder")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #ffffff;")
        layout.addWidget(title)

        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        self.path_edit = QLineEdit(self.target_directory)
        self.path_edit.textChanged.connect(self.on_path_changed)

        browse_btn = self.create_secondary_button("Browse...", 90)
        browse_btn.clicked.connect(self.browse_folder)

        input_row.addWidget(self.path_edit)
        input_row.addWidget(browse_btn)
        layout.addLayout(input_row)

        free_mb = get_free_space_mb(self.target_directory)
        self.space_lbl = QLabel(f"Required: ~180 MB   •   Available: {free_mb:,} MB")
        self.space_lbl.setStyleSheet("font-size: 12px; color: #a1a1aa;")
        layout.addWidget(self.space_lbl)

        layout.addStretch()

        btn_box = QHBoxLayout()
        back_btn = self.create_secondary_button("Back", 100)
        back_btn.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        btn_box.addWidget(back_btn)
        btn_box.addStretch()

        next_btn = self.create_primary_button("Next", 110)
        next_btn.clicked.connect(lambda: self.stack.setCurrentIndex(2))
        btn_box.addWidget(next_btn)

        layout.addLayout(btn_box)
        return page

    # ---------------------------------------------------------
    # PAGE 3: OPTIONS
    # ---------------------------------------------------------
    def build_page_options(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(14)

        title = QLabel("Setup Options")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #ffffff;")
        layout.addWidget(title)

        options_card = QFrame()
        options_card.setObjectName("OptionsCard")
        options_card.setStyleSheet("padding: 14px 16px;")
        opt_layout = QVBoxLayout(options_card)
        opt_layout.setContentsMargins(16, 14, 16, 14)
        opt_layout.setSpacing(12)

        self.cb_desktop = QCheckBox("Create a Desktop shortcut")
        self.cb_desktop.setCursor(Qt.PointingHandCursor)
        self.cb_desktop.setChecked(True)
        opt_layout.addWidget(self.cb_desktop)

        self.cb_start_menu = QCheckBox("Add to Start Menu")
        self.cb_start_menu.setCursor(Qt.PointingHandCursor)
        self.cb_start_menu.setChecked(True)
        opt_layout.addWidget(self.cb_start_menu)

        layout.addWidget(options_card)
        layout.addStretch()

        btn_box = QHBoxLayout()
        back_btn = self.create_secondary_button("Back", 100)
        back_btn.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        btn_box.addWidget(back_btn)
        btn_box.addStretch()

        install_btn = self.create_primary_button("Install", 110)
        install_btn.clicked.connect(self.start_installation)
        btn_box.addWidget(install_btn)

        layout.addLayout(btn_box)
        return page

    # ---------------------------------------------------------
    # PAGE 4: INSTALLING / UPDATING PROGRESS
    # ---------------------------------------------------------
    def build_page_installing(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 32, 32, 24)
        layout.setSpacing(14)

        self.install_title_lbl = QLabel("Installing Chess Stealth...")
        self.install_title_lbl.setStyleSheet("font-size: 16px; font-weight: 700; color: #ffffff;")
        layout.addWidget(self.install_title_lbl)

        layout.addSpacing(12)

        self.status_lbl = QLabel("Preparing installation...")
        self.status_lbl.setStyleSheet("font-size: 12px; color: #a1a1aa;")
        layout.addWidget(self.status_lbl)

        # Smooth animated gliding progress bar
        self.progress_bar = SmoothProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(8)
        layout.addWidget(self.progress_bar)

        layout.addStretch()
        return page

    # ---------------------------------------------------------
    # PAGE 5: FINISH
    # ---------------------------------------------------------
    def build_page_finish(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(12)

        layout.addStretch()

        # Animated success checkmark icon with spring pop-in
        self.succ_icon = AnimatedSuccessIcon(SVG_SUCCESS_CHECK, 48)
        icon_box = QHBoxLayout()
        icon_box.setAlignment(Qt.AlignCenter)
        icon_box.addWidget(self.succ_icon)
        layout.addLayout(icon_box)

        layout.addSpacing(4)

        self.finish_title_lbl = QLabel("Setup Complete")
        self.finish_title_lbl.setAlignment(Qt.AlignCenter)
        self.finish_title_lbl.setStyleSheet("font-size: 20px; font-weight: 800; color: #ffffff;")
        layout.addWidget(self.finish_title_lbl)

        layout.addSpacing(10)

        cb_container = QHBoxLayout()
        cb_container.setAlignment(Qt.AlignCenter)
        self.cb_launch_now = QCheckBox("Launch Chess Stealth now")
        self.cb_launch_now.setCursor(Qt.PointingHandCursor)
        self.cb_launch_now.setChecked(True)
        self.cb_launch_now.setStyleSheet("font-weight: 600; color: #ffffff;")
        cb_container.addWidget(self.cb_launch_now)
        layout.addLayout(cb_container)

        layout.addStretch()

        btn_box = QHBoxLayout()
        btn_box.setAlignment(Qt.AlignCenter)
        finish_btn = self.create_primary_button("Finish", 140)
        finish_btn.clicked.connect(self.on_finish_clicked)
        btn_box.addWidget(finish_btn)
        layout.addLayout(btn_box)

        return page

    # ---------------------------------------------------------
    # HELPERS & EVENT HANDLERS
    # ---------------------------------------------------------
    def create_primary_button(self, text, min_width=110):
        return AnimatedButton(text, is_primary=True, min_width=min_width)

    def create_secondary_button(self, text, min_width=90):
        return AnimatedButton(text, is_primary=False, min_width=min_width)

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Installation Folder", self.path_edit.text())
        if folder:
            self.target_directory = folder
            self.path_edit.setText(folder)

    def on_path_changed(self, new_path):
        self.target_directory = new_path.strip()
        free_mb = get_free_space_mb(self.target_directory)
        self.space_lbl.setText(f"Required: ~180 MB   •   Available: {free_mb:,} MB")

    def on_welcome_primary_clicked(self):
        if self.is_update_mode:
            self.start_update()
        else:
            self.stack.setCurrentIndex(1)

    def start_update(self):
        self.install_title_lbl.setText("Updating Chess Stealth...")
        self.status_lbl.setText("Connecting...")
        self.stack.setCurrentIndex(3)
        self.worker = InstallWorker(
            self.target_directory,
            create_desktop_sc=True,
            create_start_menu_sc=True,
            download_url=self.download_url,
            new_version=self.new_version
        )
        self.worker.progress.connect(self.on_install_progress)
        self.worker.finished_success.connect(self.on_install_success)
        self.worker.failed.connect(self.on_install_failed)
        self.worker.start()

    def on_github_checked(self, result):
        decision = resolve_installer_update_state(
            result,
            installed_version=self.installed_info.get("version", APP_VERSION),
            bundled_version=APP_VERSION,
            is_update_mode=self.is_update_mode,
        )
        self.download_url = decision["download_url"]
        self.new_version = decision["new_version"]

        if decision["badge_text"]:
            self.update_badge_lbl.setText(decision["badge_text"])
            if decision["highlight"]:
                self.update_badge_lbl.setStyleSheet("""
                    font-size: 11px;
                    font-weight: 600;
                    color: #ffffff;
                    padding: 4px 12px;
                    background: rgba(255, 255, 255, 0.12);
                    border: 1px solid rgba(255, 255, 255, 0.25);
                    border-radius: 10px;
                """)
            else:
                self.update_badge_lbl.setStyleSheet("""
                    font-size: 11px;
                    font-weight: 600;
                    color: #a1a1aa;
                    padding: 4px 14px;
                    background: rgba(255, 255, 255, 0.05);
                    border: 1px solid rgba(255, 255, 255, 0.12);
                    border-radius: 10px;
                """)
            self.update_badge_lbl.show()

        if self.is_update_mode:
            self.start_btn.setText(decision["btn_text"])
            if decision["highlight"]:
                self.start_btn.setMinimumWidth(180)
            self.custom_opt_btn.show()

    def start_installation(self):
        self.install_title_lbl.setText("Installing Chess Stealth...")
        self.status_lbl.setText("Preparing installation...")
        self.stack.setCurrentIndex(3)
        self.target_directory = self.path_edit.text().strip()
        self.worker = InstallWorker(
            self.target_directory,
            self.cb_desktop.isChecked(),
            self.cb_start_menu.isChecked(),
            download_url=self.download_url,
            new_version=self.new_version
        )
        self.worker.progress.connect(self.on_install_progress)
        self.worker.finished_success.connect(self.on_install_success)
        self.worker.failed.connect(self.on_install_failed)
        self.worker.start()

    def on_install_progress(self, percent, msg):
        self.progress_bar.setSmoothValue(percent)
        self.status_lbl.setText(msg)

    def on_install_success(self, exe_path):
        self.installed_exe_path = exe_path
        if self.is_update_mode:
            self.finish_title_lbl.setText("Update Complete")
        else:
            self.finish_title_lbl.setText("Setup Complete")
        self.stack.setCurrentIndex(4)
        if hasattr(self, "succ_icon"):
            self.succ_icon.play_pop()

    def on_install_failed(self, error_msg):
        self.status_lbl.setText(f"Error: {error_msg}")
        self.status_lbl.setStyleSheet("font-size: 12px; color: #ef4444; font-weight: 600;")

    def on_finish_clicked(self):
        if self.cb_launch_now.isChecked() and self.installed_exe_path and os.path.exists(self.installed_exe_path):
            subprocess.Popen([self.installed_exe_path], cwd=os.path.dirname(self.installed_exe_path))
        self.animate_close()

    # Window Dragging
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and not self.drag_position.isNull():
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

# -------------------------------------------------------------
# APPLICATION ENTRYPOINT
# -------------------------------------------------------------
def main():
    app = QApplication(sys.argv)
    win = SetupWizardWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
