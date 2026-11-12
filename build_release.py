# -*- coding: utf-8 -*-
"""
Chess Stealth - Release Packager for GitHub Releases
Packages the latest ChessStealth payload into payload.zip ready for GitHub Releases upload.
"""

import os
import sys
import zipfile
import shutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PAYLOAD_DIR = os.path.join(BASE_DIR, "build_setup", "payload")
PAYLOAD_ZIP_SETUP = os.path.join(BASE_DIR, "build_setup", "payload.zip")
DESKTOP_DIR = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")
DESKTOP_ZIP = os.path.join(DESKTOP_DIR, "payload.zip")

def package_release(tag=None):
    if not tag and len(sys.argv) > 1:
        tag = sys.argv[1].strip()
    if not tag:
        tag = "v3.2.3"
    if not tag.startswith("v"):
        tag = "v" + tag

    print(f"==================================================")
    print(f" Packaging Chess Stealth Release for: {tag}")
    print(f"==================================================")

    # Check payload directory
    if not os.path.exists(PAYLOAD_DIR):
        print(f"Error: Payload folder not found at {PAYLOAD_DIR}")
        return False

    exe_file = os.path.join(PAYLOAD_DIR, "ChessStealth.exe")
    if not os.path.exists(exe_file):
        print(f"Error: ChessStealth.exe not found in {PAYLOAD_DIR}")
        return False

    print(f"Compressing {PAYLOAD_DIR} -> payload.zip...")
    with zipfile.ZipFile(PAYLOAD_ZIP_SETUP, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(PAYLOAD_DIR):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, PAYLOAD_DIR)
                zf.write(full_path, rel_path)

    # Copy to Desktop for easy drag & drop upload
    shutil.copyfile(PAYLOAD_ZIP_SETUP, DESKTOP_ZIP)
    size_mb = os.path.getsize(DESKTOP_ZIP) / (1024 * 1024)

    print(f"\nSUCCESS!")
    print(f"1. Created: {DESKTOP_ZIP} ({size_mb:.1f} MB)")
    print(f"\nTO PUBLISH UPDATE ON GITHUB:")
    print(f"  1. Open: https://github.com/nghihi16/chess-stealth-pro/releases/new")
    print(f"  2. Choose tag: {tag}")
    print(f"  3. Release title: Release {tag}")
    print(f"  4. Drag & drop 'payload.zip' from your Desktop into Attach binaries.")
    print(f"  5. Click 'Publish release'.")
    print(f"\nWhen users open Setup_ChessStealth.exe, it will automatically detect {tag} and update in 1 click!")
    return True

if __name__ == "__main__":
    package_release()
