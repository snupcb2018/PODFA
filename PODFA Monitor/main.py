#!/usr/bin/env python3
"""
PBS 2.0 Main Application
========================

PBS Meter 2.0 Main Application

Features:
- Beautiful line charts
- Window scrolling
- Mouse hover value display
- Enhanced Excel export (current window area)
- Sophisticated UI/UX

Usage:
    python main.py
"""

import sys
import os
import logging
from pathlib import Path

# Add current script directory to Python path
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import Qt

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s:%(lineno)d: %(message)s',
    handlers=[
        logging.FileHandler('pbs_2.0.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


class PBS2Application(QApplication):
    """PBS 2.0 main application class"""

    def __init__(self, argv):
        super().__init__(argv)

        # Set application information
        self.setApplicationName("PODFA")
        self.setApplicationVersion("2.0.0")
        self.setOrganizationName("PBS Team")
        self.setOrganizationDomain("pbs.local")

        # Set style
        self.setStyle('Fusion')

        # High DPI support (automatically handled in PyQt6)
        try:
            self.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling)
            self.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps)
        except AttributeError:
            # PyQt6 supports High DPI by default
            logger.info("High DPI settings are supported by default in PyQt6")

        logger.info("PBS 2.0 application initialization complete")

    def show_error_message(self, title: str, message: str):
        """Show error message"""
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.exec()


def check_dependencies():
    """Check for required dependency packages"""
    required_packages = [
        'PyQt6',
        'matplotlib',
        'numpy',
        'pandas',
        'serial',
        'openpyxl',
        'qtawesome',
        'polars',
        'scipy',
        'PIL'  # Pillow
    ]

    missing_packages = []

    for package in required_packages:
        try:
            __import__(package)
            logger.debug(f"✓ {package} package verified")
        except ImportError:
            missing_packages.append(package)
            logger.error(f"✗ {package} package not found")

    if missing_packages:
        error_msg = (
            f"The following packages are not installed:\n\n"
            f"{', '.join(missing_packages)}\n\n"
            f"To install them, run:\n"
            f"pip install {' '.join(missing_packages)}"
        )

        return False, error_msg

    return True, "All dependency packages are installed"


def main():
    """Main function"""
    try:
        # Required settings for QtWebEngine (must be before QApplication creation)
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)

        # Create application
        app = PBS2Application(sys.argv)

        logger.info("Starting PBS Meter 2.0")
        logger.info(f"Python version: {sys.version}")
        logger.info(f"PyQt6 version: {app.applicationVersion()}")
        logger.info(f"Current working directory: {os.getcwd()}")

        # Check dependencies
        deps_ok, deps_msg = check_dependencies()
        if not deps_ok:
            logger.error("Dependency check failed")
            app.show_error_message("Dependency Error", deps_msg)
            return 1

        logger.info("Dependency check passed")

        # Import main window (after dependency check)
        try:
            from ui.main_window import MainWindow
        except ImportError as e:
            logger.error(f"Main window import failed: {e}")
            app.show_error_message(
                "Module Error",
                f"Cannot load main window:\n{str(e)}\n\n"
                f"Please verify all files are in the correct location."
            )
            return 1

        # Create and display main window
        try:
            main_window = MainWindow()
            main_window.show()
            logger.info("Main window displayed successfully")
        except Exception as e:
            logger.error(f"Main window creation failed: {e}")
            app.show_error_message(
                "Initialization Error",
                f"Cannot create main window:\n{str(e)}"
            )
            return 1

        # Welcome message
        logger.info("PBS 2.0 ready!")
        print("\n" + "="*50)
        print("* PBS Meter 2.0 - Next Generation Measurement! *")
        print("="*50)
        print("+ Beautiful line charts")
        print("+ Mouse hover value display")
        print("+ Window scrolling")
        print("+ Enhanced Excel export (current window area)")
        print("+ Sophisticated UI/UX")
        print("="*50)
        print("Usage:")
        print("1. Select COM port")
        print("2. Create workbench")
        print("3. Add charts")
        print("4. Click Start button to begin measurement")
        print("5. Hover mouse over charts!")
        print("="*50)

        # Start event loop
        exit_code = app.exec()

        logger.info(f"PBS 2.0 terminated (exit code: {exit_code})")
        return exit_code
        
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 0
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)