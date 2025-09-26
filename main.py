import sys
import os
import logging
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                               QListWidget, QTextEdit, QPushButton, QLabel, QDialog, 
                               QSplitter, QStyle, QSizeGrip, QLineEdit, QProgressBar)
from PySide6.QtCore import Qt, QPoint, QTimer, QThread, Signal
from PySide6.QtGui import QFont, QFontDatabase, QTextDocument, QTextCursor, QIcon
import markdown
import requests
from rapidfuzz import process, fuzz, utils
import subprocess 


def resource_path(relative_path):
    """
    Get absolute path to resource, works for dev and PyInstaller
    """
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)
    

class CustomTitleBar(QWidget):
    def __init__(self, parent, title=""):
        super().__init__(parent)
        self.parent_window = parent
        self.setObjectName("titleBar")
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 0, 5, 0)
        
        title_label = QLabel(title)
        title_label.setFont(QFont("Inter", 12, QFont.Bold))
        layout.addWidget(title_label)
        
        layout.addStretch()
        
        if self.parent_window.windowFlags() & Qt.WindowMinimizeButtonHint:
            minimize_button = QPushButton("—")
            minimize_button.setObjectName("minimizeButton")
            minimize_button.clicked.connect(self.parent_window.showMinimized)
            layout.addWidget(minimize_button)

        close_button = QPushButton("✕")
        close_button.setObjectName("closeButton")
        close_button.clicked.connect(self.parent_window.close)
        layout.addWidget(close_button)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.parent_window.old_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            delta = QPoint(event.globalPosition().toPoint() - self.parent_window.old_pos)
            self.parent_window.move(self.parent_window.x() + delta.x(), self.parent_window.y() + delta.y())
            self.parent_window.old_pos = event.globalPosition().toPoint()

class LogDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Logs")
        self.setMinimumSize(1200, 300)
        
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        container = QWidget()
        container.setObjectName("dialogContainer")
        main_layout.addWidget(container)
        
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(1, 1, 1, 1)

        self.title_bar = CustomTitleBar(self, "Logs")
        container_layout.addWidget(self.title_bar)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        container_layout.addWidget(self.log_text)
        
        self.load_logs()
        self.old_pos = self.pos()
    
    def load_logs(self):
        try:
            with open("launcher_logs.txt", "r") as file:
                self.log_text.setText(file.read())
        except FileNotFoundError:
            self.log_text.setText("No logs found.")

class Downloader(QThread):
    setTotalProgress = Signal(int)
    setCurrentProgress = Signal(int)
    succeeded = Signal()
    failed = Signal(str)
    
    def __init__(self, url, filename):
        super().__init__()
        self._url = url
        self._filename = filename
    
    def run(self):
        try:
            response = requests.get(self._url, stream=True)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            self.setTotalProgress.emit(total_size)
            
            downloaded_size = 0
            chunk_size = 8192
            
            with open(self._filename, 'wb') as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        self.setCurrentProgress.emit(downloaded_size)
            
            self.succeeded.emit()
            
        except Exception as e:
            self.failed.emit(str(e))

class programLauncher(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("iijwLauncher")
        self.setWindowIcon(QIcon(resource_path(r".\resources\icons\icon.ico")))
        self.setMinimumSize(800, 500)
        self.setMaximumSize(800, 500)

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowMinimizeButtonHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self.setup_ui()
        self.setup_logging()
        self.load_data()
        self.load_custom_font()
        
        self.log("Application started")
        self.old_pos = self.pos()
        self.downloader = None

    def load_custom_font(self):
        font_path = resource_path(r".\resources\fonts\Inter-Regular.ttf")
        if os.path.exists(font_path) and QFontDatabase.addApplicationFont(font_path) >= 0:
            app_font = QFont("Inter", 10)
            QApplication.setFont(app_font)
            self.log("Custom font loaded successfully")
        else:
            self.log("Custom font not found or failed to load. Using system default.")
    
    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)

        background_container = QWidget()
        background_container.setObjectName("backgroundContainer")
        main_layout.addWidget(background_container)
        
        container_layout = QVBoxLayout(background_container)
        container_layout.setContentsMargins(1, 1, 1, 1)

        self.title_bar = CustomTitleBar(self, "iijwLauncher")
        container_layout.addWidget(self.title_bar)
        
        splitter = QSplitter(Qt.Horizontal)
        splitter.setObjectName("mainSplitter")
        
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(10, 10, 5, 10)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search...")
        self.search_input.textChanged.connect(self.filter_programs)
        left_layout.addWidget(self.search_input)
        
        self.program_list = QListWidget()
        self.program_list.currentRowChanged.connect(self.on_program_selected)
        left_layout.addWidget(self.program_list)
        
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(5, 10, 10, 10)
        
        self.readme_text = QTextEdit()
        self.readme_text.setReadOnly(True)
        right_layout.addWidget(self.readme_text)
        
        buttons_layout = QHBoxLayout()
        buttons_layout.setContentsMargins(0, 10, 0, 0)
        
        self.launch_button = QPushButton("Launch")
        self.launch_button.setObjectName("launchButton")
        self.launch_button.clicked.connect(self.launch_program)
        buttons_layout.addWidget(self.launch_button)
        
        self.progress_container = QWidget()
        progress_layout = QHBoxLayout(self.progress_container)
        progress_layout.setContentsMargins(10, 0, 0, 0)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        progress_layout.addWidget(self.progress_bar)
        
        buttons_layout.addWidget(self.progress_container)
        buttons_layout.setStretch(1, 1)
        
        self.logs_button = QPushButton()
        self.logs_button.setIcon(self.style().standardIcon(QStyle.SP_FileDialogDetailedView))
        self.logs_button.setToolTip("Logs")
        self.logs_button.clicked.connect(self.show_logs)
        self.logs_button.setObjectName("iconButton")
        buttons_layout.addWidget(self.logs_button)
        
        right_layout.addLayout(buttons_layout)
        
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([250, 650])
        
        container_layout.addWidget(splitter)
        
        footer_widget = QWidget()
        footer_widget.setObjectName("footerWidget")
        footer_widget.setMaximumHeight(80)
        footer_layout = QVBoxLayout(footer_widget)
        footer_layout.setContentsMargins(10, 5, 10, 5)
        
        footer_label = QLabel("Latest Logs:")
        footer_label.setObjectName("footerLabel")
        footer_layout.addWidget(footer_label)
        
        self.footer_log_text = QTextEdit()
        self.footer_log_text.setReadOnly(True)
        self.footer_log_text.setMaximumHeight(50)
        self.footer_log_text.setObjectName("footerLogText")
        footer_layout.addWidget(self.footer_log_text)
        
        container_layout.addWidget(footer_widget)
        
        grip = QSizeGrip(self)
        container_layout.addWidget(grip, 0, Qt.AlignBottom | Qt.AlignRight)
            
    def setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[logging.FileHandler("launcher_logs.txt"), logging.StreamHandler()]
        )
    
    def log(self, message):
        logging.info(message)
        self.update_footer_log(message)
    
    def update_footer_log(self, message):
        current_text = self.footer_log_text.toPlainText()
        timestamp = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s').format(
            logging.LogRecord(None, logging.INFO, "", 0, message, (), None)
        )
        
        lines = current_text.split('\n')
        lines.append(timestamp)
        if len(lines) > 3:
            lines = lines[-3:]
        
        self.footer_log_text.setText('\n'.join(lines))
        cursor = self.footer_log_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.footer_log_text.setTextCursor(cursor)
    
    
    def load_data(self):
        url = "https://raw.githubusercontent.com/iijwlts/iijwLauncherData/refs/heads/main/data.json"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json() 

        if isinstance(data, dict):
            self.program_data = [data]
        else:
            self.program_data = data

        self.original_program_data = self.program_data.copy()

        self.search_choices = []
        for program in self.original_program_data:
            combined_text = f"{program['program']} {program['version']} {program['README']}"
            self.search_choices.append((combined_text, program))

        self.program_list.clear()
        for program in self.program_data:
            self.program_list.addItem(program["program"])

        if self.program_data:
            self.program_list.setCurrentRow(0)
    
    def filter_programs(self, search_text):
        if not search_text.strip():
            self.program_data = self.original_program_data.copy()
        else:
            choice_texts = [choice[0] for choice in self.search_choices]
            
            results = process.extract(
                search_text, 
                choice_texts, 
                scorer=fuzz.WRatio,
                processor=utils.default_process, 
                limit=len(choice_texts)
            )
            
            filtered_programs = []
            for result in results:
                score, index = result[1], choice_texts.index(result[0])
                if score >= 60: 
                    filtered_programs.append(self.search_choices[index][1])
            
            self.program_data = filtered_programs
        
        self.program_list.clear()
        for program in self.program_data:
            self.program_list.addItem(program["program"])
        
        if self.program_data:
            self.program_list.setCurrentRow(0)
    
    def on_program_selected(self, index):
        if 0 <= index < len(self.program_data):
            program_data = self.program_data[index]
            readme_html = markdown.markdown(program_data["README"], extensions=['fenced_code', 'codehilite'])
            document = QTextDocument()
            document.setDefaultStyleSheet(
                "body { color: #E0E0E0; } "
                "h1, h2, h3 { color: #FFFFFF; } "
                "code { background-color: rgba(0,0,0,0.3); padding: 2px 4px; border-radius: 4px; }"
                "pre { background-color: rgba(0,0,0,0.3); padding: 10px; border-radius: 8px; }"
            )
            document.setHtml(readme_html)
            self.readme_text.setDocument(document)
    
    def launch_program(self):
        self.log("Launch button pressed")
        current_row = self.program_list.currentRow()
        
        if not (0 <= current_row < len(self.program_data)):
            self.log("No program selected")
            return
            
        program_data = self.program_data[current_row]
        program_name, binary_url = program_data["program"], program_data["binary_url"]
        binary_path = fr".\bin\{program_name.replace(' ', '_')}.exe"
        
        if not os.path.exists(binary_path):
            self.log(f"Starting download of {program_name}")
            
            bin_dir = os.path.dirname(binary_path)
            if not os.path.exists(bin_dir):
                os.makedirs(bin_dir)
                self.log(f"Created directory: {bin_dir}")
            
            self.progress_container.setVisible(True)
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)
            self.launch_button.setEnabled(False)
            self.launch_button.setText("Downloading...")
            
            self.downloader = Downloader(binary_url, binary_path)
            
            self.downloader.setTotalProgress.connect(self.progress_bar.setMaximum)
            self.downloader.setCurrentProgress.connect(self.progress_bar.setValue)
            self.downloader.succeeded.connect(self.download_succeeded)
            self.downloader.failed.connect(self.download_failed)
            self.downloader.finished.connect(self.download_finished)
            
            self.downloader.start()
        else:
            self.launch_existing_program(binary_path)
    
    def download_succeeded(self):
        self.log("Binary downloaded successfully")
        current_row = self.program_list.currentRow()
        if 0 <= current_row < len(self.program_data):
            program_data = self.program_data[current_row]
            binary_path = fr".\bin\{program_data['program'].replace(' ', '_')}.exe"
            self.launch_existing_program(binary_path)
    
    def download_failed(self, error_message):
        self.log(f"Download failed: {error_message}")
        self.launch_button.setText("Launch Failed")
    
    def download_finished(self):
        self.launch_button.setEnabled(True)
        self.launch_button.setText("Launch")
        
        if self.downloader:
            self.downloader.deleteLater()
            self.downloader = None
    
    def launch_existing_program(self, binary_path):
        self.log(f"Starting: {binary_path}")
        try:
            subprocess.Popen([binary_path], shell=True)
            self.log(f"{binary_path} started successfully")
        except Exception as e:
            self.log(f"Error starting: {e}")
    
    def show_logs(self):
        self.log("Logs window opened")
        dialog = LogDialog(self)
        dialog.exec()

def get_stylesheet():
    return """
    #backgroundContainer, #dialogContainer {
        background-color: rgba(25, 25, 40, 0.85);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 15px;
    }
    QMainWindow, QDialog {
        background-color: transparent;
        color: #E0E0E0;
    }
    #titleBar {
        background-color: transparent;
        min-height: 40px;
    }
    #titleBar QLabel {
        color: #FFFFFF;
        padding-left: 5px;
    }
    #titleBar QPushButton {
        background-color: transparent;
        color: #E0E0E0;
        border: none;
        font-size: 16px;
        min-width: 40px;
        min-height: 40px;
    }
    #minimizeButton:hover {
        background-color: rgba(255, 255, 255, 0.2);
    }
    #closeButton:hover {
        background-color: rgba(232, 17, 35, 0.9);
        color: #FFFFFF;
    }
    
    QListWidget, QTextEdit, QLineEdit {
        background-color: rgba(255, 255, 255, 0.05);
        border-radius: 8px;
        border: 1px solid transparent;
        padding: 8px;
        color: #E0E0E0;
    }
    
    QLineEdit {
        padding: 8px 12px;
        font-size: 14px;
    }
    
    QListWidget::item {
        padding: 10px;
        border-radius: 5px;
    }
    QListWidget::item:hover {
        background-color: rgba(255, 255, 255, 0.1);
    }
    QListWidget::item:selected {
        background-color: rgba(80, 120, 220, 0.5);
        color: #FFFFFF;
    }
    
    QPushButton {
        background-color: rgba(255, 255, 255, 0.1);
        border: 1px solid rgba(255, 255, 255, 0.15);
        border-radius: 8px;
        padding: 0 15px;
        color: #E0E0E0;
        min-height: 40px;
    }
    QPushButton:hover {
        background-color: rgba(255, 255, 255, 0.2);
        border: 1px solid rgba(255, 255, 255, 0.25);
    }
    QPushButton:pressed {
        background-color: rgba(0, 0, 0, 0.1);
    }
    #launchButton {
        font-weight: bold;
        background-color: rgba(80, 120, 220, 0.7);
        padding: 0 25px;
        min-width: 100px;
    }
    #launchButton:hover {
        background-color: rgba(90, 140, 240, 0.8);
    }
    #iconButton {
        min-width: 40px;
        max-width: 40px;
        padding: 0;
    }
    
    QProgressBar {
        background-color: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 4px;
        text-align: center;
        height: 24px;
    }
    
    QProgressBar::chunk {
        background-color: rgba(80, 120, 220, 0.8);
        border-radius: 3px;
    }
    
    #footerWidget {
        background-color: rgba(20, 20, 35, 0.7);
        border-top: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 0 0 15px 15px;
    }
    
    #footerLabel {
        color: #B0B0B0;
        font-size: 11px;
        font-weight: bold;
    }
    
    #footerLogText {
        background-color: rgba(0, 0, 0, 0.2);
        border: 1px solid rgba(255, 255, 255, 0.05);
        font-size: 10px;
        font-family: monospace;
    }
    
    QSplitter::handle { background: transparent; }
    QSplitter::handle:horizontal { width: 2px; }
    
    QScrollBar:vertical {
        background: transparent; width: 10px; margin: 0;
    }
    QScrollBar::handle:vertical {
        background: rgba(255, 255, 255, 0.2); min-height: 20px; border-radius: 5px;
    }
    QScrollBar::add-line, QScrollBar::sub-line { height: 0px; }
    
    QScrollBar:horizontal {
        background: transparent; height: 10px; margin: 0;
    }
    QScrollBar::handle:horizontal {
        background: rgba(255, 255, 255, 0.2); min-width: 20px; border-radius: 5px;
    }
    QScrollBar::add-line, QScrollBar::sub-line { width: 0px; }

    QSizeGrip { width: 16px; height: 16px; image: none; }
    """

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(get_stylesheet())
    window = programLauncher()
    window.show()
    sys.exit(app.exec())
