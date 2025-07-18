import os
import sys
import json
import logging
import subprocess
import threading
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import fnmatch

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QTreeWidget, QTreeWidgetItem, 
    QPushButton, QVBoxLayout, QHBoxLayout, QWidget, QMessageBox, QLabel, 
    QSplitter, QStatusBar, QToolBar, QAction, QFrame, QSizePolicy, QTextEdit,
    QTabWidget, QProgressBar, QSpinBox, QCheckBox, QComboBox, QGroupBox,
    QGridLayout, QLineEdit, QSlider, QMenuBar, QMenu, QShortcut, QDialog,
    QListWidget, QListWidgetItem, QDialogButtonBox
)
from PyQt5.QtCore import Qt, QSize, QThread, pyqtSignal, QTimer, QSettings
from PyQt5.QtGui import QIcon, QFont, QPixmap, QKeySequence

# Try to import optional dependencies
try:
    import chardet
    HAS_CHARDET = True
except ImportError:
    HAS_CHARDET = False


class TreeLoaderThread(QThread):
    """Background thread for loading file tree with optimal performance"""
    progress_updated = pyqtSignal(int)
    status_updated = pyqtSignal(str)
    tree_data_chunk = pyqtSignal(list)
    tree_loaded = pyqtSignal(list)
    loading_finished = pyqtSignal(bool)
    
    def __init__(self, root_directory: str, ignore_list: List[str], include_hidden: bool):
        super().__init__()
        self.root_directory = root_directory
        self.ignore_list = ignore_list
        self.include_hidden = include_hidden
        self.should_cancel = False
        
    def run(self):
        """Main thread execution"""
        try:
            self.load_tree_data()
        except Exception as e:
            logging.error(f"Tree loading error: {str(e)}", exc_info=True)
            self.loading_finished.emit(False)
    
    def cancel(self):
        """Cancel the loading operation"""
        self.should_cancel = True

    def load_tree_data(self):
        """Load all file tree data in a single efficient pass"""
        self.status_updated.emit("Scanning directory structure...")
        
        tree_data = []
        chunk_size = 100
        processed_items = 0
        
        try:
            for root, dirs, files in os.walk(self.root_directory, topdown=True):
                if self.should_cancel:
                    break
                
                # Filter directories in-place to prevent traversal
                dirs[:] = [d for d in dirs if not self.should_ignore_path(os.path.join(root, d))]
                
                # Process directories
                for dir_name in sorted(dirs, key=str.lower):
                    if self.should_cancel:
                        break
                    
                    full_path = os.path.join(root, dir_name)
                    item_data = self._create_item_data(dir_name, full_path, root, is_dir=True)
                    if item_data:
                        tree_data.append(item_data)
                
                # Process files
                for file_name in sorted(files, key=str.lower):
                    if self.should_cancel:
                        break
                    
                    full_path = os.path.join(root, file_name)
                    if self.should_ignore_path(full_path):
                        continue
                    
                    item_data = self._create_item_data(file_name, full_path, root, is_dir=False)
                    if item_data:
                        tree_data.append(item_data)

                processed_items += len(dirs) + len(files)
                self.status_updated.emit(f"Found {processed_items} items...")

                # Emit chunk if we have enough items
                if len(tree_data) >= chunk_size:
                    self.tree_data_chunk.emit(tree_data.copy())
                    tree_data.clear()

            # Emit any remaining data
            if tree_data and not self.should_cancel:
                self.tree_data_chunk.emit(tree_data)
            
            if not self.should_cancel:
                self.tree_loaded.emit([])
                self.loading_finished.emit(True)
            
        except Exception as e:
            logging.error(f"Error loading tree data: {str(e)}")
            self.loading_finished.emit(False)

    def _create_item_data(self, name: str, full_path: str, parent_path: str, is_dir: bool) -> Optional[Dict]:
        """Create item data dictionary for a file or directory"""
        try:
            stat_info = os.stat(full_path)
            return {
                'name': name,
                'full_path': full_path,
                'is_dir': is_dir,
                'size': 0 if is_dir else stat_info.st_size,
                'modified': datetime.fromtimestamp(stat_info.st_mtime),
                'parent_path': parent_path
            }
        except (OSError, PermissionError) as e:
            logging.debug(f"Cannot access {full_path}: {e}")
            return None
    
    def should_ignore_path(self, path: str) -> bool:
        """Check if a path should be ignored based on patterns"""
        item = os.path.basename(path)
        
        # Hidden files check
        if not self.include_hidden and item.startswith('.'):
            return True
        
        # Direct matches
        if item in self.ignore_list:
            return True
            
        # Pattern matches
        for pattern in self.ignore_list:
            if pattern.startswith('*') and item.endswith(pattern[1:]):
                return True
            elif pattern.endswith('*') and item.startswith(pattern[:-1]):
                return True
            elif '*' in pattern:
                if fnmatch.fnmatch(item, pattern):
                    return True
        
        return False


class FileProcessor(QThread):
    """Background thread for file processing and merging"""
    progress_updated = pyqtSignal(int)
    status_updated = pyqtSignal(str)
    finished_processing = pyqtSignal(str, bool)
    
    def __init__(self, tree_widget: QTreeWidget, root_directory: str, output_settings: Dict):
        super().__init__()
        self.tree_widget = tree_widget
        self.root_directory = root_directory
        self.output_settings = output_settings
        self.should_cancel = False
        
    def run(self):
        """Main thread execution"""
        try:
            self.process_files()
        except Exception as e:
            logging.error(f"File processing error: {str(e)}", exc_info=True)
            self.finished_processing.emit("", False)
    
    def cancel(self):
        """Cancel the processing operation"""
        self.should_cancel = True
    
    def process_files(self):
        """Process and merge selected files"""
        output_folder = self.output_settings.get('output_folder', 'outputFolder')
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_format = self.output_settings.get('format', 'txt')
        merge_filename = os.path.join(output_folder, f'merged_{timestamp}.{output_format}')
        
        try:
            total_files = self._count_selected_files(self.tree_widget.invisibleRootItem())
            processed_files = 0
            
            with open(merge_filename, 'w', encoding='utf-8') as merge_file:
                # Write header based on format
                self._write_header(merge_file, output_format)
                
                # Write file tree
                merge_file.write(self._get_section_header("File Structure", output_format))
                self._write_tree_summary(self.tree_widget.invisibleRootItem(), merge_file)
                
                # Write merged files
                merge_file.write(self._get_section_header("File Contents", output_format, is_content=True))
                processed_files = self._write_files(
                    self.tree_widget.invisibleRootItem(), 
                    merge_file, 
                    processed_files, 
                    total_files
                )
                
                # Write footer if needed
                if output_format == 'html':
                    merge_file.write("</body></html>")
            
            if not self.should_cancel:
                self.finished_processing.emit(merge_filename, True)
            
        except Exception as e:
            logging.error(f"Error during file processing: {str(e)}")
            self.finished_processing.emit("", False)
    
    def _count_selected_files(self, tree_item: QTreeWidgetItem) -> int:
        """Count total selected files recursively"""
        count = 0
        for index in range(tree_item.childCount()):
            child = tree_item.child(index)
            if self.should_cancel:
                break
                
            full_path = child.data(0, Qt.UserRole)
            check_state = child.checkState(0)
            
            if check_state == Qt.Checked and os.path.isfile(full_path):
                count += 1
            elif os.path.isdir(full_path) and check_state != Qt.Unchecked:
                count += self._count_selected_files(child)
        return count
    
    def _write_header(self, file, format_type: str):
        """Write file header based on format"""
        if format_type == 'md':
            file.write(f"# File Merge Report\n\n")
            file.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            file.write(f"**Source Directory:** `{self.root_directory}`\n\n")
        else:
            file.write("FILE MERGE REPORT\n")
            file.write("="*80 + "\n\n")
            file.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            file.write(f"Source Directory: {self.root_directory}\n")
            file.write(f"Output Settings: {self.output_settings}\n\n")
    
    def _get_section_header(self, title: str, format_type: str, is_content: bool = False) -> str:
        """Get section header based on format"""
        if format_type == 'md':
            if is_content:
                return f"\n```\n\n## {title}\n\n"
            return f"\n## {title}\n\n```\n"
        else:
            return f"\n\n{'='*80}\n{title.center(80)}\n{'='*80}\n\n"
    
    def _write_tree_summary(self, tree_item: QTreeWidgetItem, merge_file, prefix: str = "", is_last: bool = True):
        """Write tree structure summary"""
        for index in range(tree_item.childCount()):
            if self.should_cancel:
                break
                
            child = tree_item.child(index)
            full_path = child.data(0, Qt.UserRole)
            is_last_child = index == tree_item.childCount() - 1
            check_state = child.checkState(0)
            
            connector = "└── " if is_last_child else "├── "
            status_icon = "✓" if check_state == Qt.Checked else "◐" if check_state == Qt.PartiallyChecked else "✗"
            
            merge_file.write(f"{prefix}{connector}{status_icon} {os.path.basename(full_path)}")
            
            if os.path.isfile(full_path) and check_state == Qt.Checked:
                try:
                    size = os.path.getsize(full_path)
                    merge_file.write(f" ({self._format_file_size(size)})")
                except:
                    pass
            
            merge_file.write("\n")
            
            if os.path.isdir(full_path) and check_state != Qt.Unchecked:
                new_prefix = prefix + ("    " if is_last_child else "│   ")
                self._write_tree_summary(child, merge_file, new_prefix, is_last_child)
    
    def _write_files(self, tree_item: QTreeWidgetItem, merge_file, processed_files: int, total_files: int) -> int:
        """Write file contents recursively"""
        for index in range(tree_item.childCount()):
            if self.should_cancel:
                break
                
            child = tree_item.child(index)
            full_path = child.data(0, Qt.UserRole)
            check_state = child.checkState(0)
            
            if check_state == Qt.Checked and os.path.isfile(full_path):
                processed_files += 1
                progress = int((processed_files / total_files) * 100) if total_files > 0 else 0
                self.progress_updated.emit(progress)
                self.status_updated.emit(f"Processing: {os.path.basename(full_path)}")
                
                self._write_single_file(full_path, merge_file)
                
            elif os.path.isdir(full_path) and check_state != Qt.Unchecked:
                processed_files = self._write_files(child, merge_file, processed_files, total_files)
        
        return processed_files
    
    def _write_single_file(self, full_path: str, merge_file):
        """Write a single file's content"""
        try:
            file_size = os.path.getsize(full_path)
            max_size = self.output_settings.get('max_file_size', 10_000_000)
            
            if file_size > max_size:
                self._write_file_header(full_path, merge_file, f"⚠️ Skipped - File too large ({self._format_file_size(file_size)})")
                return
            
            # Detect encoding
            encoding = self._detect_encoding(full_path)
            
            with open(full_path, 'r', encoding=encoding, errors='replace') as f:
                content = f.read()
                
                # Check if content is binary
                if self._is_binary_content(content):
                    self._write_file_header(full_path, merge_file, f"📎 Binary file ({self._format_file_size(file_size)})")
                    return
                
                self._write_file_header(full_path, merge_file)
                self._write_file_content(full_path, content, merge_file)
                
        except Exception as e:
            self._write_file_header(full_path, merge_file, f"❌ Error: {str(e)}")
            logging.error(f"Error processing file {full_path}: {str(e)}")
    
    def _write_file_header(self, full_path: str, merge_file, status: str = ""):
        """Write file header"""
        format_type = self.output_settings.get('format', 'txt')
        filename = os.path.basename(full_path)
        rel_path = os.path.relpath(full_path, self.root_directory)
        
        if format_type == 'md':
            merge_file.write(f"\n### 📄 {filename}\n\n")
            merge_file.write(f"**Path:** `{rel_path}`\n")
            if status:
                merge_file.write(f"**Status:** {status}\n")
            merge_file.write("\n")
        else:
            merge_file.write(f"\n{'='*80}\n")
            merge_file.write(f"📄 File: {filename}\n")
            merge_file.write(f"📁 Path: {rel_path}\n")
            if status:
                merge_file.write(f"⚠️ Status: {status}\n")
            merge_file.write(f"{'='*80}\n\n")
    
    def _write_file_content(self, full_path: str, content: str, merge_file):
        """Write file content with syntax highlighting if applicable"""
        format_type = self.output_settings.get('format', 'txt')
        ext = os.path.splitext(full_path)[1].lower()
        
        if format_type == 'md':
            lang_map = {
                '.py': 'python', '.js': 'javascript', '.java': 'java', 
                '.cpp': 'cpp', '.cs': 'csharp', '.html': 'html', 
                '.css': 'css', '.json': 'json', '.xml': 'xml',
                '.php': 'php', '.rb': 'ruby', '.go': 'go',
                '.rs': 'rust', '.kt': 'kotlin', '.swift': 'swift'
            }
            lang = lang_map.get(ext, 'text')
            merge_file.write(f"```{lang}\n{content}\n```\n\n")
        else:
            merge_file.write(content + "\n\n")
    
    def _detect_encoding(self, filepath: str) -> str:
        """Detect file encoding"""
        if HAS_CHARDET:
            try:
                with open(filepath, 'rb') as f:
                    raw_data = f.read(10000)
                    result = chardet.detect(raw_data)
                    if result['confidence'] > 0.7:
                        return result['encoding']
            except:
                pass
        return 'utf-8'
    
    def _is_binary_content(self, content: str) -> bool:
        """Check if content appears to be binary"""
        if len(content) == 0:
            return False
        # Check for null bytes
        if '\x00' in content:
            return True
        # Check ratio of non-printable characters
        non_printable = sum(1 for c in content[:1000] if ord(c) < 32 and c not in '\t\n\r')
        return non_printable / min(len(content), 1000) > 0.3
    
    def _format_file_size(self, size_bytes: int) -> str:
        """Format file size in human readable format"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f}{unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f}TB"
    
    def _html_escape(self, text: str) -> str:
        """Escape HTML special characters"""
        return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


class FileRestorer(QThread):
    """Background thread for restoring files from merge file"""
    progress_updated = pyqtSignal(int)
    status_updated = pyqtSignal(str)
    finished_restoring = pyqtSignal(bool, str)
    
    def __init__(self, merge_file_path: str, output_directory: str):
        super().__init__()
        self.merge_file_path = merge_file_path
        self.output_directory = output_directory
        self.should_cancel = False
        
    def run(self):
        """Main thread execution"""
        try:
            success, message = self.restore_files()
            self.finished_restoring.emit(success, message)
        except Exception as e:
            logging.error(f"File restoration error: {str(e)}", exc_info=True)
            self.finished_restoring.emit(False, str(e))
    
    def cancel(self):
        """Cancel the restoration operation"""
        self.should_cancel = True
    
    def restore_files(self) -> Tuple[bool, str]:
        """Parse merge file and restore original files"""
        try:
            with open(self.merge_file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            return False, f"Could not read merge file: {e}"
        
        # Find the file contents section
        content_marker = "File Contents"
        content_start = content.find(content_marker)
        if content_start == -1:
            return False, "Could not find 'File Contents' section in merge file"
        
        # Extract files
        relevant_content = content[content_start:]
        file_blocks = self._extract_file_blocks(relevant_content)
        
        if not file_blocks:
            return False, "No files found to restore"
        
        # Create output directory
        os.makedirs(self.output_directory, exist_ok=True)
        
        # Restore each file
        total_files = len(file_blocks)
        restored_count = 0
        
        for i, (file_path, file_content) in enumerate(file_blocks):
            if self.should_cancel:
                return False, "Restoration cancelled"
            
            try:
                full_path = os.path.join(self.output_directory, file_path)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(file_content)
                
                restored_count += 1
                progress = int((restored_count / total_files) * 100)
                self.progress_updated.emit(progress)
                self.status_updated.emit(f"Restored: {file_path}")
                
            except Exception as e:
                logging.error(f"Error restoring {file_path}: {e}")
        
        return True, f"Successfully restored {restored_count} of {total_files} files"
    
    def _extract_file_blocks(self, content: str) -> List[Tuple[str, str]]:
        """Extract file paths and contents from merge file (supports txt and md)"""
        file_blocks = []
        if '### 📄 ' in content:
            # Markdown Format
            # Find all file headers
            header_pattern = r'^### 📄 ([^\n]+)\n+\*\*Path:\*\* `([^`]+)`(?:\n\*\*Status:\*\* ([^\n]+))?\n+```[\w\d]*\n'  # up to the start of the code block
            headers = list(re.finditer(header_pattern, content, re.MULTILINE))
            for i, match in enumerate(headers):
                file_path = match.group(2).strip()
                content_start = match.end()
                if i + 1 < len(headers):
                    content_end = headers[i + 1].start()
                else:
                    content_end = len(content)
                file_content = content[content_start:content_end].strip()
                # Remove markdown code block wrappers if present
                code_block_pattern = r'^([\s\S]*?)```[\w\d]*\n([\s\S]*?)\n```'
                code_match = re.search(r'^([\s\S]*?)```[\w\d]*\n([\s\S]*?)\n```', file_content, re.MULTILINE)
                if code_match:
                    file_content = code_match.group(2)
                else:
                    # fallback: try to remove a single code block
                    if file_content.startswith('```'):
                        file_content = file_content[3:]
                        if '\n```' in file_content:
                            file_content = file_content.split('\n```', 1)[0]
                # Entferne evtl. verbleibende abschließende ``` und Leerzeilen
                file_content = file_content.rstrip('`\n ')
                if file_path and file_content:
                    file_blocks.append((file_path, file_content))
            if not file_blocks:
                logging.warning('No files found in markdown merge file. Check header_pattern and file structure.')
        else:
            # TXT Format (Fallback)
            header_pattern = r'\n={80}\n📄 File: ([^\n]+)\n📁 Path: ([^\n]+)\n(?:⚠️ Status: [^\n]+\n)?={80}\n'
            headers = list(re.finditer(header_pattern, content))
            for i, match in enumerate(headers):
                file_path = match.group(2).strip()
                content_start = match.end()
                if i + 1 < len(headers):
                    content_end = headers[i + 1].start()
                else:
                    content_end = len(content)
                file_content = content[content_start:content_end].strip()
                while file_content.endswith('\n' + '=' * 80):
                    file_content = file_content[:-81].rstrip()
                if file_path and file_content:
                    file_blocks.append((file_path, file_content))
        return file_blocks


class RestoreDialog(QDialog):
    """Dialog for file restoration from merge files"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_file = None
        self.output_directory = None
        self.init_ui()
        self.load_merge_files()
        
    def init_ui(self):
        """Initialize the restoration dialog UI"""
        self.setWindowTitle("Restore Files from Merge")
        self.setModal(True)
        self.resize(800, 600)
        
        layout = QVBoxLayout(self)
        
        # Header
        header = QLabel("Select a merge file to restore:")
        header.setFont(QFont("Segoe UI", 12))
        layout.addWidget(header)
        
        # File list
        self.file_list = QListWidget()
        self.file_list.setAlternatingRowColors(True)
        self.file_list.itemClicked.connect(self.on_file_selected)
        layout.addWidget(self.file_list)
        
        # Output directory selection
        output_layout = QHBoxLayout()
        output_layout.addWidget(QLabel("Output Directory:"))
        
        self.output_edit = QLineEdit()
        output_layout.addWidget(self.output_edit)
        
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self.browse_output_directory)
        output_layout.addWidget(browse_btn)
        
        layout.addLayout(output_layout)
        
        # Dialog buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal, self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.ok_button = buttons.button(QDialogButtonBox.Ok)
        self.ok_button.setEnabled(False)
        
        layout.addWidget(buttons)
        
    def load_merge_files(self):
        """Load available merge files from output folder"""
        output_folder = self.parent().output_folder_edit.text() if self.parent() else "outputFolder"
        
        if not os.path.exists(output_folder):
            return
        
        merge_files = []
        for filename in os.listdir(output_folder):
            # Nur .txt und .md Dateien anzeigen
            if filename.endswith((".txt", ".md")):
                full_path = os.path.join(output_folder, filename)
                try:
                    mod_time = os.path.getmtime(full_path)
                    merge_files.append((filename, full_path, mod_time))
                except OSError:
                    continue
                
        # Sort by modification time, newest first
        merge_files.sort(key=lambda x: x[2], reverse=True)
        
        # Add to list widget
        for filename, full_path, mod_time in merge_files:
            item = QListWidgetItem()
            mod_time_str = datetime.fromtimestamp(mod_time).strftime('%Y-%m-%d %H:%M:%S')
            item.setText(f"{filename} ({mod_time_str})")
            item.setData(Qt.UserRole, full_path)
            self.file_list.addItem(item)
    
    def on_file_selected(self, item):
        """Handle file selection"""
        self.selected_file = item.data(Qt.UserRole)
        
        # Set default output directory
        base_name = os.path.splitext(os.path.basename(self.selected_file))[0]
        output_folder = os.path.dirname(self.selected_file)
        default_output = os.path.join(output_folder, f"{base_name}_restored")
        self.output_edit.setText(default_output)
        
        self.ok_button.setEnabled(True)
    
    def browse_output_directory(self):
        """Browse for output directory"""
        directory = QFileDialog.getExistingDirectory(
            self, "Select Output Directory",
            self.output_edit.text()
        )
        if directory:
            self.output_edit.setText(directory)
    
    def get_selected_values(self) -> Tuple[str, str]:
        """Get selected file and output directory"""
        return self.selected_file, self.output_edit.text()


class FileMergerApp(QMainWindow):
    """Main application window for File Merger"""
    
    def __init__(self):
        super().__init__()
        self.settings = QSettings('FileMerger', 'FileMergerApp')
        self.processor_thread = None
        self.tree_loader_thread = None
        self.restorer_thread = None
        
        # Initialize variables before UI creation
        self.root_directory = None
        self.output_folder = "outputFolder"
        self.ignore_list = self.load_ignore_list()
        self.updating = False
        self.items_by_path = {}
        self.pending_items = []
        
        self.setup_logging()
        self.init_ui()
        self.load_settings()
        
    def setup_logging(self):
        """Configure application logging"""
        logging.basicConfig(
            filename='file_merger.log',
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            filemode='a'
        )
        
    def init_ui(self):
        """Initialize the main UI"""
        self.setWindowTitle('File Merger Pro 2.1')
        self.setGeometry(100, 100, 1200, 800)
        self.setWindowIcon(self.get_icon('merge'))
        
        # Create UI components
        self.create_menu_bar()
        self.create_status_bar()
        self.create_toolbar()
        self.create_main_widget()
        
        # Apply modern stylesheet
        self.apply_stylesheet()
        
        # Setup keyboard shortcuts
        self.setup_shortcuts()
        
    def create_menu_bar(self):
        """Create application menu bar"""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu('&File')
        
        actions = [
            ('&New Project', 'Ctrl+N', self.new_project),
            ('&Open Project', 'Ctrl+O', self.open_project),
            ('&Save Project', 'Ctrl+S', self.save_project),
            (None, None, None),  # Separator
            ('E&xit', 'Ctrl+Q', self.close)
        ]
        
        for action_data in actions:
            if action_data[0] is None:
                file_menu.addSeparator()
            else:
                action = QAction(action_data[0], self)
                if action_data[1]:
                    action.setShortcut(action_data[1])
                action.triggered.connect(action_data[2])
                file_menu.addAction(action)
        
        # View menu
        view_menu = menubar.addMenu('&View')
        
        expand_action = QAction('&Expand All', self)
        expand_action.triggered.connect(self.expand_all_files)
        view_menu.addAction(expand_action)
        collapse_action = QAction('&Collapse All', self)
        collapse_action.triggered.connect(self.collapse_all_files)
        view_menu.addAction(collapse_action)
        view_menu.addSeparator()
        refresh_action = QAction('&Refresh', self)
        refresh_action.triggered.connect(self.refresh_tree)
        view_menu.addAction(refresh_action)
        
        # Tools menu
        tools_menu = menubar.addMenu('&Tools')
        
        restore_action = QAction('&Restore from Merge File...', self)
        restore_action.setShortcut('Ctrl+R')
        restore_action.triggered.connect(self.show_restore_dialog)
        tools_menu.addAction(restore_action)
        
        tools_menu.addSeparator()
        
        settings_action = QAction('&Preferences...', self)
        settings_action.triggered.connect(self.show_preferences)
        tools_menu.addAction(settings_action)
        
        # Help menu
        help_menu = menubar.addMenu('&Help')
        
        about_action = QAction('&About', self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        
    def create_status_bar(self):
        """Create application status bar"""
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumWidth(200)
        self.statusBar.addPermanentWidget(self.progress_bar)
        
        # Cancel button
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setVisible(False)
        self.cancel_button.setMaximumWidth(80)
        self.cancel_button.clicked.connect(self.cancel_processing)
        self.statusBar.addPermanentWidget(self.cancel_button)
        
        self.statusBar.showMessage('Ready')
        
    def create_toolbar(self):
        """Create main toolbar"""
        self.toolbar = QToolBar("Main Toolbar")
        self.toolbar.setIconSize(QSize(24, 24))
        self.toolbar.setMovable(False)
        self.addToolBar(self.toolbar)
        
        toolbar_actions = [
            (self.get_icon('folder-open'), "Browse", self.browse_folder, "Select a folder to process"),
            (None, None, None, None),  # Separator
            ("Select All", "Select All", self.select_all_files, "Select all files"),
            ("Select None", "Select None", self.select_no_files, "Deselect all files"),
            (None, None, None, None),  # Separator
            (self.get_icon('merge'), "Merge Files", self.merge_files, "Merge selected files"),
            (self.get_icon('folder'), "Open Output", self.open_output_folder, "Open output folder"),
        ]
        
        for action_data in toolbar_actions:
            if action_data[0] is None:
                self.toolbar.addSeparator()
            else:
                if isinstance(action_data[0], QIcon):
                    action = QAction(action_data[0], action_data[1], self)
                else:
                    action = QAction(action_data[1], self)
                action.triggered.connect(action_data[2])
                action.setStatusTip(action_data[3])
                self.toolbar.addAction(action)
        
    def create_main_widget(self):
        """Create main widget with tabs"""
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        # Create tab widget
        self.tab_widget = QTabWidget()
        
        # Files tab
        self.files_tab = self.create_files_tab()
        self.tab_widget.addTab(self.files_tab, "📁 Files")
        
        # Settings tab
        self.settings_tab = self.create_settings_tab()
        self.tab_widget.addTab(self.settings_tab, "⚙️ Settings")
        
        # Preview tab
        self.preview_tab = self.create_preview_tab()
        self.tab_widget.addTab(self.preview_tab, "👁️ Preview")
        
        # Main layout
        main_layout = QVBoxLayout(self.central_widget)
        main_layout.addWidget(self.tab_widget)
        
    def create_files_tab(self):
        """Create files tab content"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        # Header
        header_layout = QHBoxLayout()
        header_label = QLabel("File Merger Pro")
        header_label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        header_layout.addWidget(header_label)
        header_layout.addStretch()
        layout.addLayout(header_layout)
        
        # Path display
        self.path_label = QLabel("No folder selected")
        self.path_label.setFont(QFont("Segoe UI", 9))
        self.path_label.setStyleSheet("color: #666; padding: 5px; background: #f0f0f0; border-radius: 3px;")
        layout.addWidget(self.path_label)
        
        # Search box
        search_layout = QHBoxLayout()
        search_label = QLabel("Search:")
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Filter files and folders...")
        self.search_box.textChanged.connect(self.filter_tree)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_box)
        layout.addLayout(search_layout)
        
        # Tree widget
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(['Files and Folders', 'Size', 'Modified'])
        self.tree.setFont(QFont("Segoe UI", 10))
        self.tree.setAlternatingRowColors(True)
        self.tree.setAnimated(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setIconSize(QSize(20, 20))
        self.tree.itemChanged.connect(self.handle_item_changed)
        self.tree.itemDoubleClicked.connect(self.preview_file)
        layout.addWidget(self.tree)
        
        # Button layout
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        
        self.browse_button = QPushButton('📁 Browse Folder')
        self.browse_button.setFont(QFont("Segoe UI", 10))
        self.browse_button.clicked.connect(self.browse_folder)
        self.browse_button.setMinimumHeight(40)
        button_layout.addWidget(self.browse_button)
        
        self.merge_button = QPushButton('🔀 Merge Selected Files')
        self.merge_button.setFont(QFont("Segoe UI", 10))
        self.merge_button.clicked.connect(self.merge_files)
        self.merge_button.setMinimumHeight(40)
        button_layout.addWidget(self.merge_button)
        
        self.open_folder_button = QPushButton('📂 Open Output Folder')
        self.open_folder_button.setFont(QFont("Segoe UI", 10))
        self.open_folder_button.clicked.connect(self.open_output_folder)
        self.open_folder_button.setMinimumHeight(40)
        button_layout.addWidget(self.open_folder_button)
        
        layout.addLayout(button_layout)
        return widget
        
    def create_settings_tab(self):
        """Create settings tab content"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)
        
        # Output Settings Group
        output_group = QGroupBox("Output Settings")
        output_layout = QGridLayout(output_group)
        
        # Output format
        output_layout.addWidget(QLabel("Output Format:"), 0, 0)
        self.format_combo = QComboBox()
        self.format_combo.addItems(["txt", "md"])
        self.format_combo.setCurrentText("txt")
        output_layout.addWidget(self.format_combo, 0, 1)
        
        # Output folder
        output_layout.addWidget(QLabel("Output Folder:"), 1, 0)
        folder_layout = QHBoxLayout()
        self.output_folder_edit = QLineEdit("outputFolder")
        folder_browse_btn = QPushButton("Browse")
        folder_browse_btn.clicked.connect(self.browse_output_folder)
        folder_layout.addWidget(self.output_folder_edit)
        folder_layout.addWidget(folder_browse_btn)
        output_layout.addLayout(folder_layout, 1, 1)
        
        layout.addWidget(output_group)
        
        # File Processing Group
        processing_group = QGroupBox("File Processing")
        processing_layout = QGridLayout(processing_group)
        
        # Max file size
        processing_layout.addWidget(QLabel("Max File Size (MB):"), 0, 0)
        self.max_size_spin = QSpinBox()
        self.max_size_spin.setRange(1, 1000)
        self.max_size_spin.setValue(10)
        self.max_size_spin.setSuffix(" MB")
        processing_layout.addWidget(self.max_size_spin, 0, 1)
        
        # Include binary files
        self.include_binary_check = QCheckBox("Include binary files (as references)")
        processing_layout.addWidget(self.include_binary_check, 1, 0, 1, 2)
        
        # Include hidden files
        self.include_hidden_check = QCheckBox("Include hidden files")
        processing_layout.addWidget(self.include_hidden_check, 2, 0, 1, 2)
        
        layout.addWidget(processing_group)
        
        # Ignore Patterns Group
        ignore_group = QGroupBox("Ignore Patterns")
        ignore_layout = QVBoxLayout(ignore_group)
        
        self.ignore_text = QTextEdit()
        self.ignore_text.setMaximumHeight(150)
        self.ignore_text.setPlainText("\n".join(self.ignore_list))
        ignore_layout.addWidget(self.ignore_text)
        
        ignore_help = QLabel("Enter patterns to ignore (one per line). Supports wildcards like *.pyc, __pycache__, etc.")
        ignore_help.setStyleSheet("color: #666; font-size: 11px;")
        ignore_layout.addWidget(ignore_help)
        
        layout.addWidget(ignore_group)
        
        layout.addStretch()
        return widget
        
    def create_preview_tab(self):
        """Create preview tab content"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)
        
        preview_label = QLabel("File Preview")
        preview_label.setFont(QFont("Segoe UI", 14, QFont.Bold))
        layout.addWidget(preview_label)
        
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setFont(QFont("Consolas", 10))
        self.preview_text.setPlainText("Double-click a file in the tree to preview it here...")
        layout.addWidget(self.preview_text)
        
        return widget
        
    def setup_shortcuts(self):
        """Setup keyboard shortcuts"""
        shortcuts = [
            ("Ctrl+A", self.select_all_files),
            ("Ctrl+D", self.select_no_files),
            ("F5", self.refresh_tree),
            ("Ctrl+F", lambda: self.search_box.setFocus()),
        ]
        
        for key_sequence, callback in shortcuts:
            QShortcut(QKeySequence(key_sequence), self, callback)
        
    def get_icon(self, icon_name: str) -> QIcon:
        """Get system icons"""
        style = QApplication.style()
        icon_map = {
            'folder-open': style.SP_DirOpenIcon,
            'folder': style.SP_DirIcon,
            'file': style.SP_FileIcon,
            'merge': style.SP_DialogSaveButton,
            'settings': style.SP_ComputerIcon,
            'preview': style.SP_FileDialogDetailedView
        }
        return style.standardIcon(icon_map.get(icon_name, style.SP_FileIcon))

    def apply_stylesheet(self):
        """Apply modern stylesheet to application"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f8f9fa;
            }
            QTabWidget::pane {
                border: 1px solid #dee2e6;
                background-color: white;
                border-radius: 4px;
            }
            QTabWidget::tab-bar {
                alignment: left;
            }
            QTabBar::tab {
                background-color: #e9ecef;
                padding: 8px 16px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: white;
                border-bottom: 2px solid #007bff;
            }
            QTreeWidget {
                border: 1px solid #dee2e6;
                border-radius: 4px;
                background-color: white;
                alternate-background-color: #f8f9fa;
                gridline-color: #e9ecef;
            }
            QTreeWidget::item {
                padding: 6px;
                border-bottom: 1px solid #f1f3f4;
            }
            QTreeWidget::item:selected {
                background-color: #007bff;
                color: white;
            }
            QTreeWidget::item:hover {
                background-color: #e3f2fd;
            }
            QPushButton {
                background-color: #007bff;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px 20px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
            QPushButton:pressed {
                background-color: #004085;
            }
            QPushButton:disabled {
                background-color: #6c757d;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #dee2e6;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 8px 0 8px;
                color: #495057;
            }
            QLineEdit, QComboBox, QSpinBox {
                border: 1px solid #ced4da;
                border-radius: 4px;
                padding: 8px;
                background-color: white;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
                border-color: #007bff;
                outline: none;
            }
            QTextEdit {
                border: 1px solid #ced4da;
                border-radius: 4px;
                background-color: white;
            }
            QCheckBox {
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border: 2px solid #6c757d;
                border-radius: 3px;
                background-color: white;
            }
            QCheckBox::indicator:checked {
                border: 2px solid #007bff;
                background-color: #007bff;
                image: url(data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTIiIGhlaWdodD0iOSIgdmlld0JveD0iMCAwIDEyIDkiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CjxwYXRoIGQ9Ik0xIDQuNUw0LjUgOEwxMSAxIiBzdHJva2U9IndoaXRlIiBzdHJva2Utd2lkdGg9IjIiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCIvPgo8L3N2Zz4K);
            }
            QProgressBar {
                border: 1px solid #dee2e6;
                border-radius: 4px;
                text-align: center;
                background-color: #e9ecef;
            }
            QProgressBar::chunk {
                background-color: #28a745;
                border-radius: 3px;
            }
            QStatusBar {
                background-color: #f8f9fa;
                border-top: 1px solid #dee2e6;
                color: #495057;
            }
            QToolBar {
                background-color: #ffffff;
                border-bottom: 1px solid #dee2e6;
                spacing: 8px;
                padding: 8px;
            }
            QToolBar QToolButton {
                border: none;
                border-radius: 4px;
                padding: 6px;
                margin: 2px;
            }
            QToolBar QToolButton:hover {
                background-color: #e9ecef;
            }
            QListWidget {
                border: 1px solid #dee2e6;
                border-radius: 4px;
                background-color: white;
                alternate-background-color: #f8f9fa;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #f1f3f4;
            }
            QListWidget::item:selected {
                background-color: #007bff;
                color: white;
            }
            QListWidget::item:hover {
                background-color: #e3f2fd;
            }
        """)

    def load_ignore_list(self) -> List[str]:
        """Load ignore patterns from file"""
        default_ignores = [
            '__pycache__', '*.pyc', '*.pyo', '*.pyd',
            '.git', '.svn', '.hg', '.bzr',
            'node_modules', '.npm', '.yarn',
            '.DS_Store', 'Thumbs.db', 'desktop.ini',
            '*.log', '*.tmp', '*.temp',
            '.vscode', '.idea', '*.swp', '*.swo',
            'venv', 'dist', 'build', 'env'
        ]
        
        ignore_list = default_ignores.copy()
        if os.path.exists('ignore.txt'):
            try:
                with open('ignore.txt', 'r', encoding='utf-8') as file:
                    custom_ignores = [line.strip() for line in file if line.strip()]
                    ignore_list.extend(custom_ignores)
            except Exception as e:
                logging.warning(f"Could not load ignore.txt: {e}")
        
        return list(set(ignore_list))

    def save_ignore_list(self):
        """Save current ignore patterns to file"""
        try:
            ignore_patterns = self.ignore_text.toPlainText().strip().split('\n')
            ignore_patterns = [p.strip() for p in ignore_patterns if p.strip()]
            
            with open('ignore.txt', 'w', encoding='utf-8') as file:
                file.write('\n'.join(ignore_patterns))
            
            self.ignore_list = ignore_patterns
            logging.info("Ignore patterns saved successfully")
        except Exception as e:
            logging.error(f"Error saving ignore patterns: {e}")
            QMessageBox.warning(self, "Warning", f"Could not save ignore patterns: {e}")

    def browse_folder(self):
        """Browse for source folder"""
        folder_selected = QFileDialog.getExistingDirectory(
            self, "Select Directory", 
            self.settings.value('last_directory', '')
        )
        if folder_selected:
            self.root_directory = folder_selected
            self.settings.setValue('last_directory', folder_selected)
            self.path_label.setText(f"📁 {folder_selected}")
            self.statusBar.showMessage(f"Loading directory: {folder_selected}")
            
            # Start threaded loading
            self.start_tree_loading()

    def start_tree_loading(self):
        """Start threaded tree loading"""
        if self.tree_loader_thread and self.tree_loader_thread.isRunning():
            self.tree_loader_thread.cancel()
            self.tree_loader_thread.wait(1000)
        
        self.tree.clear()
        self.items_by_path = {}
        self.pending_items = []
        
        # Set progress bar to busy mode
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.cancel_button.setVisible(True)
        self.browse_button.setEnabled(False)
        
        # Get current settings
        current_ignores = self.ignore_text.toPlainText().strip().split('\n')
        current_ignores = [p.strip() for p in current_ignores if p.strip()]
        include_hidden = self.include_hidden_check.isChecked()
        
        self.tree_loader_thread = TreeLoaderThread(self.root_directory, current_ignores, include_hidden)
        self.tree_loader_thread.status_updated.connect(self.statusBar.showMessage)
        self.tree_loader_thread.tree_data_chunk.connect(self.update_tree_data)
        self.tree_loader_thread.tree_loaded.connect(self.finalize_tree_building)
        self.tree_loader_thread.loading_finished.connect(self.on_tree_loading_finished)
        self.tree_loader_thread.start()

    def update_tree_data(self, tree_data_chunk: List[Dict]):
        """Update tree widget with new data chunk"""
        try:
            # Sort chunk: directories first, then by name
            tree_data_chunk.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
            
            for item_data in tree_data_chunk:
                if self.tree_loader_thread.should_cancel:
                    break
                
                # Create tree item
                tree_item = QTreeWidgetItem()
                tree_item.setText(0, item_data['name'])
                tree_item.setCheckState(0, Qt.Checked)
                tree_item.setData(0, Qt.UserRole, item_data['full_path'])
                
                if item_data['is_dir']:
                    tree_item.setIcon(0, self.get_icon('folder'))
                    tree_item.setText(1, "")
                else:
                    tree_item.setIcon(0, self.get_icon('file'))
                    tree_item.setText(1, self.format_file_size(item_data['size']))
                
                tree_item.setText(2, item_data['modified'].strftime("%Y-%m-%d %H:%M"))
                
                # Find parent and add item
                parent_path = item_data['parent_path']
                if parent_path == self.root_directory:
                    self.tree.addTopLevelItem(tree_item)
                else:
                    parent_item = self.items_by_path.get(parent_path)
                    if parent_item:
                        parent_item.addChild(tree_item)
                    else:
                        self.pending_items.append((tree_item, parent_path))
                
                # Store item for future reference
                self.items_by_path[item_data['full_path']] = tree_item
            
            # Process pending items
            self.process_pending_items()
            
            # Update columns periodically
            if len(self.items_by_path) % 100 == 0:
                for i in range(3):
                    self.tree.resizeColumnToContents(i)
            
        except Exception as e:
            logging.error(f"Error updating tree data: {e}")

    def process_pending_items(self):
        """Process items that were waiting for their parents"""
        remaining_pending = []
        
        for tree_item, parent_path in self.pending_items:
            parent_item = self.items_by_path.get(parent_path)
            if parent_item:
                parent_item.addChild(tree_item)
            else:
                remaining_pending.append((tree_item, parent_path))
        
        self.pending_items = remaining_pending

    def finalize_tree_building(self, all_data: List):
        """Finalize tree building after all data is loaded"""
        try:
            # Process any remaining pending items
            self.process_pending_items()
            
            # Expand first two levels
            self.tree.expandToDepth(1)
            
            # Final column resize
            for i in range(3):
                self.tree.resizeColumnToContents(i)
            
            # Restore selection if available
            if hasattr(self, '_pending_selection') and self._pending_selection:
                self.restore_selected_files(self._pending_selection)
                self._pending_selection = []
            
            # Clear caches
            self.items_by_path.clear()
            self.pending_items.clear()
            
        except Exception as e:
            logging.error(f"Error finalizing tree building: {e}")

    def restore_selected_files(self, selected_files: List[str]):
        """Set check state for files in selected_files (relative paths)"""
        root = self.tree.invisibleRootItem()
        root_dir = self.root_directory
        # Build a set for fast lookup
        selected_set = set(os.path.normpath(p) for p in selected_files)
        def set_checked(item):
            full_path = item.data(0, Qt.UserRole)
            if os.path.isfile(full_path):
                rel_path = os.path.normpath(os.path.relpath(full_path, root_dir))
                if rel_path in selected_set:
                    item.setCheckState(0, Qt.Checked)
                else:
                    item.setCheckState(0, Qt.Unchecked)
            for i in range(item.childCount()):
                set_checked(item.child(i))
        for i in range(root.childCount()):
            set_checked(root.child(i))

    def on_tree_loading_finished(self, success: bool):
        """Handle tree loading completion"""
        # Reset progress bar
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        self.cancel_button.setVisible(False)
        self.browse_button.setEnabled(True)
        
        if success:
            file_count = self.count_all_files(self.tree.invisibleRootItem())
            self.statusBar.showMessage(f"Loaded {file_count} files successfully", 3000)
        else:
            self.statusBar.showMessage("Error loading files", 5000)
            QMessageBox.warning(self, "Error", "Failed to load directory. Check the log for details.")

    def browse_output_folder(self):
        """Browse for output folder"""
        folder_selected = QFileDialog.getExistingDirectory(
            self, "Select Output Directory",
            self.output_folder_edit.text()
        )
        if folder_selected:
            self.output_folder_edit.setText(folder_selected)

    def format_file_size(self, size_bytes: int) -> str:
        """Format file size in human readable format"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f}{unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f}TB"

    def count_all_files(self, tree_item: QTreeWidgetItem) -> int:
        """Count total files in tree"""
        count = 0
        for index in range(tree_item.childCount()):
            child = tree_item.child(index)
            full_path = child.data(0, Qt.UserRole)
            if os.path.isfile(full_path):
                count += 1
            else:
                count += self.count_all_files(child)
        return count

    def filter_tree(self, text: str):
        """Filter tree items based on search text"""
        def filter_item(item):
            text_lower = text.lower()
            item_text = item.text(0).lower()
            
            # Check if current item matches
            matches = text_lower in item_text
            
            visible_children = 0
            for i in range(item.childCount()):
                child = item.child(i)
                if filter_item(child):
                    visible_children += 1
            
            # Show item if it matches or has visible children
            should_show = matches or visible_children > 0 or not text
            item.setHidden(not should_show)
            
            return should_show
        
        # Apply filter to all top-level items
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            filter_item(root.child(i))

    def handle_item_changed(self, item: QTreeWidgetItem, column: int):
        """Handle tree item check state changes"""
        if self.updating or column != 0:
            return
        
        self.updating = True
        
        # Update children based on parent status
        check_state = item.checkState(column)
        if check_state in [Qt.Checked, Qt.Unchecked]:
            self.check_all_children(item, check_state)
        
        # Update parent status
        self.update_parent_state(item.parent())
        
        self.updating = False
    
    def check_all_children(self, item: QTreeWidgetItem, check_state: Qt.CheckState):
        """Recursively check/uncheck all children"""
        for i in range(item.childCount()):
            child = item.child(i)
            child.setCheckState(0, check_state)
            self.check_all_children(child, check_state)

    def update_parent_state(self, parent: Optional[QTreeWidgetItem]):
        """Update parent check state based on children"""
        if parent is None:
            return
        
        checked_count = 0
        partially_checked_count = 0
        total_count = parent.childCount()
        
        for i in range(total_count):
            child_state = parent.child(i).checkState(0)
            if child_state == Qt.Checked:
                checked_count += 1
            elif child_state == Qt.PartiallyChecked:
                partially_checked_count += 1
        
        if checked_count == total_count:
            parent.setCheckState(0, Qt.Checked)
        elif checked_count == 0 and partially_checked_count == 0:
            parent.setCheckState(0, Qt.Unchecked)
        else:
            parent.setCheckState(0, Qt.PartiallyChecked)
        
        # Recursively update parent's parent
        self.update_parent_state(parent.parent())

    def select_all_files(self):
        """Select all files in tree"""
        self.updating = True
        
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            child = root.child(i)
            child.setCheckState(0, Qt.Checked)
            self.check_all_children(child, Qt.Checked)
        
        self.updating = False

    def select_no_files(self):
        """Deselect all files in tree"""
        self.updating = True
        
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            child = root.child(i)
            child.setCheckState(0, Qt.Unchecked)
            self.check_all_children(child, Qt.Unchecked)
        
        self.updating = False

    def refresh_tree(self):
        """Refresh the file tree"""
        if self.root_directory:
            self.start_tree_loading()

    def preview_file(self, item: QTreeWidgetItem, column: int):
        """Preview selected file in preview tab"""
        full_path = item.data(0, Qt.UserRole)
        if not os.path.isfile(full_path):
            return
            
        try:
            file_size = os.path.getsize(full_path)
            if file_size > 1_000_000:  # 1MB limit for preview
                self.preview_text.setPlainText(f"File too large for preview ({self.format_file_size(file_size)})")
                return
            
            # Detect encoding
            encoding = 'utf-8'
            if HAS_CHARDET:
                try:
                    with open(full_path, 'rb') as f:
                        raw_data = f.read(10000)
                        result = chardet.detect(raw_data)
                        if result['confidence'] > 0.7:
                            encoding = result['encoding']
                except:
                    pass
            
            with open(full_path, 'r', encoding=encoding, errors='replace') as f:
                content = f.read()
                
                # Check if binary
                if '\x00' in content:
                    self.preview_text.setPlainText("Binary file - cannot preview")
                    return
                
                # Add file info header
                header = f"File: {os.path.basename(full_path)}\n"
                header += f"Path: {os.path.relpath(full_path, self.root_directory)}\n"
                header += f"Size: {self.format_file_size(file_size)}\n"
                header += f"Encoding: {encoding}\n"
                header += "=" * 50 + "\n\n"
                
                self.preview_text.setPlainText(header + content)
                
                # Switch to preview tab
                self.tab_widget.setCurrentIndex(2)
                
        except Exception as e:
            self.preview_text.setPlainText(f"Error previewing file: {str(e)}")

    def merge_files(self):
        """Start file merging process"""
        if not self.root_directory:
            QMessageBox.warning(self, "Warning", "Please select a folder first")
            return
        
        # Save current ignore patterns
        self.save_ignore_list()
        
        # Get output settings
        output_settings = {
            'output_folder': self.output_folder_edit.text(),
            'format': self.format_combo.currentText(),
            'max_file_size': self.max_size_spin.value() * 1024 * 1024,
            'include_binary': self.include_binary_check.isChecked(),
            'include_hidden': self.include_hidden_check.isChecked()
        }
        
        # Update output folder
        self.output_folder = output_settings['output_folder']
        
        # Show progress
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.cancel_button.setVisible(True)
        self.merge_button.setEnabled(False)
        
        # Start processing thread
        self.processor_thread = FileProcessor(self.tree, self.root_directory, output_settings)
        self.processor_thread.progress_updated.connect(self.progress_bar.setValue)
        self.processor_thread.status_updated.connect(self.statusBar.showMessage)
        self.processor_thread.finished_processing.connect(self.on_merge_finished)
        self.processor_thread.start()

    def cancel_processing(self):
        """Cancel current processing"""
        if self.processor_thread and self.processor_thread.isRunning():
            self.processor_thread.cancel()
            self.statusBar.showMessage("Cancelling...", 2000)
        elif self.tree_loader_thread and self.tree_loader_thread.isRunning():
            self.tree_loader_thread.cancel()
            self.statusBar.showMessage("Cancelling...", 2000)
        elif self.restorer_thread and self.restorer_thread.isRunning():
            self.restorer_thread.cancel()
            self.statusBar.showMessage("Cancelling...", 2000)

    def on_merge_finished(self, filepath: str, success: bool):
        """Handle merge completion"""
        self.progress_bar.setVisible(False)
        self.cancel_button.setVisible(False)
        self.merge_button.setEnabled(True)
        
        if success and filepath:
            self.statusBar.showMessage(f"Files merged successfully: {os.path.basename(filepath)}", 5000)
            
            # Show success dialog with options
            msg = QMessageBox(self)
            msg.setWindowTitle("Merge Complete")
            msg.setText(f"Files merged successfully!")
            msg.setInformativeText(f"Output file: {os.path.basename(filepath)}")
            msg.setStandardButtons(QMessageBox.Ok)
            
            open_file_btn = msg.addButton("Open File", QMessageBox.ActionRole)
            open_folder_btn = msg.addButton("Open Folder", QMessageBox.ActionRole)
            
            msg.exec_()
            
            if msg.clickedButton() == open_file_btn:
                self.open_file(filepath)
            elif msg.clickedButton() == open_folder_btn:
                self.open_output_folder()
        else:
            self.statusBar.showMessage("Merge failed", 5000)
            QMessageBox.critical(self, "Error", "An error occurred during file merging. Check the log for details.")

    def open_file(self, filepath: str):
        """Open a file with system default application"""
        try:
            if sys.platform == 'win32':
                os.startfile(filepath)
            elif sys.platform == 'darwin':
                subprocess.run(['open', filepath], check=True)
            else:
                subprocess.run(['xdg-open', filepath], check=True)
        except Exception as e:
            logging.error(f"Error opening file {filepath}: {e}")
            QMessageBox.warning(self, "Error", f"Could not open file: {e}")

    def open_output_folder(self):
        """Open output folder"""
        folder_path = self.output_folder_edit.text()
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
            
        try:
            if sys.platform == 'win32':
                os.startfile(folder_path)
            elif sys.platform == 'darwin':
                subprocess.run(['open', folder_path], check=True)
            else:
                subprocess.run(['xdg-open', folder_path], check=True)
                
            self.statusBar.showMessage(f"Opened: {folder_path}", 3000)
        except Exception as e:
            logging.error(f"Error opening folder {folder_path}: {e}")
            QMessageBox.warning(self, "Error", f"Could not open folder: {e}")

    def show_restore_dialog(self):
        """Show dialog for restoring files from merge"""
        dialog = RestoreDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            merge_file, output_dir = dialog.get_selected_values()
            if merge_file and output_dir:
                self.start_file_restoration(merge_file, output_dir)

    def start_file_restoration(self, merge_file: str, output_dir: str):
        """Start the file restoration process"""
        # Show progress
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.cancel_button.setVisible(True)
        
        # Start restoration thread
        self.restorer_thread = FileRestorer(merge_file, output_dir)
        self.restorer_thread.progress_updated.connect(self.progress_bar.setValue)
        self.restorer_thread.status_updated.connect(self.statusBar.showMessage)
        self.restorer_thread.finished_restoring.connect(self.on_restore_finished)
        self.restorer_thread.start()

    def on_restore_finished(self, success: bool, message: str):
        """Handle restoration completion"""
        self.progress_bar.setVisible(False)
        self.cancel_button.setVisible(False)
        
        if success:
            self.statusBar.showMessage(message, 5000)
            QMessageBox.information(self, "Restoration Complete", message)
        else:
            self.statusBar.showMessage("Restoration failed", 5000)
            QMessageBox.critical(self, "Restoration Failed", message)

    def show_preferences(self):
        """Show preferences dialog (placeholder)"""
        QMessageBox.information(self, "Preferences", "Preferences dialog coming soon!")

    def new_project(self):
        """Create new project"""
        self.root_directory = None
        self.tree.clear()
        self.path_label.setText("No folder selected")
        self.preview_text.setPlainText("Double-click a file in the tree to preview it here...")
        self.search_box.clear()
        self.statusBar.showMessage("New project created", 2000)

    def save_project(self):
        """Save current project configuration"""
        if not self.root_directory:
            QMessageBox.warning(self, "Warning", "No project to save")
            return
            
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Project", "", "JSON Files (*.json)"
        )
        
        if filename:
            try:
                project_data = {
                    'root_directory': self.root_directory,
                    'output_folder': self.output_folder_edit.text(),
                    'output_format': self.format_combo.currentText(),
                    'max_file_size': self.max_size_spin.value(),
                    'include_binary': self.include_binary_check.isChecked(),
                    'include_hidden': self.include_hidden_check.isChecked(),
                    'ignore_patterns': self.ignore_text.toPlainText().strip().split('\n'),
                    'selected_files': self.get_selected_files()
                }
                
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(project_data, f, indent=2)
                
                self.statusBar.showMessage(f"Project saved: {os.path.basename(filename)}", 3000)
                
            except Exception as e:
                logging.error(f"Error saving project: {e}")
                QMessageBox.critical(self, "Error", f"Could not save project: {e}")

    def open_project(self):
        """Open saved project configuration"""
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open Project", "", "JSON Files (*.json)"
        )
        
        if filename:
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    project_data = json.load(f)
                
                # Restore settings
                self.root_directory = project_data.get('root_directory')
                self.output_folder_edit.setText(project_data.get('output_folder', 'outputFolder'))
                self.format_combo.setCurrentText(project_data.get('output_format', 'txt'))
                self.max_size_spin.setValue(project_data.get('max_file_size', 10))
                self.include_binary_check.setChecked(project_data.get('include_binary', False))
                self.include_hidden_check.setChecked(project_data.get('include_hidden', False))
                
                ignore_patterns = project_data.get('ignore_patterns', [])
                self.ignore_text.setPlainText('\n'.join(ignore_patterns))
                
                # Reload tree
                if self.root_directory and os.path.exists(self.root_directory):
                    self.path_label.setText(f"📁 {self.root_directory}")
                    self.start_tree_loading()
                    
                    # Store selection for later restoration
                    self._pending_selection = project_data.get('selected_files', [])
                
                self.statusBar.showMessage(f"Project loaded: {os.path.basename(filename)}", 3000)
                
            except Exception as e:
                logging.error(f"Error opening project: {e}")
                QMessageBox.critical(self, "Error", f"Could not open project: {e}")

    def get_selected_files(self) -> List[str]:
        """Get list of selected file paths"""
        selected = []
        
        def collect_selected(item):
            full_path = item.data(0, Qt.UserRole)
            if item.checkState(0) == Qt.Checked and os.path.isfile(full_path):
                rel_path = os.path.relpath(full_path, self.root_directory)
                selected.append(rel_path)
            
            for i in range(item.childCount()):
                collect_selected(item.child(i))
        
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            collect_selected(root.child(i))
        
        return selected

    def show_about(self):
        """Show about dialog"""
        about_text = """
        <h2>File Merger Pro 2.1</h2>
        <p><b>Professional File Merger for AI and Development</b></p>
        
        <p>Features:</p>
        <ul>
        <li>📄 Multiple output formats (TXT, Markdown)</li>
        <li>🔍 Smart file filtering and ignore patterns</li>
        <li>👁️ File preview functionality</li>
        <li>💾 Save/Load project configurations</li>
        <li>🔄 Restore files from merge output</li>
        <li>🔎 Search and filter files</li>
        <li>📊 Progress tracking with cancellation</li>
        <li>🎨 Modern, responsive UI</li>
        <li>⚡ Background processing</li>
        </ul>
        
        <p><b>Keyboard Shortcuts:</b></p>
        <ul>
        <li>Ctrl+N - New Project</li>
        <li>Ctrl+O - Open Project</li>
        <li>Ctrl+S - Save Project</li>
        <li>Ctrl+R - Restore from Merge</li>
        <li>Ctrl+A - Select All Files</li>
        <li>Ctrl+D - Deselect All Files</li>
        <li>Ctrl+F - Focus Search</li>
        <li>F5 - Refresh Tree</li>
        </ul>
        
        <p><i>Built with PyQt5 for cross-platform compatibility</i></p>
        <p><i>Version 2.1 - Enhanced Edition</i></p>
        """
        
        QMessageBox.about(self, "About File Merger Pro", about_text)

    def load_settings(self):
        """Load application settings"""
        try:
            # Window geometry
            geometry = self.settings.value('geometry')
            if geometry:
                self.restoreGeometry(geometry)
            
            # Output settings
            self.output_folder_edit.setText(
                self.settings.value('output_folder', 'outputFolder')
            )
            self.format_combo.setCurrentText(
                self.settings.value('output_format', 'txt')
            )
            self.max_size_spin.setValue(
                int(self.settings.value('max_file_size', 10))
            )
            self.include_binary_check.setChecked(
                self.settings.value('include_binary', False, type=bool)
            )
            self.include_hidden_check.setChecked(
                self.settings.value('include_hidden', False, type=bool)
            )
            
        except Exception as e:
            logging.warning(f"Error loading settings: {e}")

    def save_settings(self):
        """Save application settings"""
        try:
            # Window geometry
            self.settings.setValue('geometry', self.saveGeometry())
            
            # Output settings
            self.settings.setValue('output_folder', self.output_folder_edit.text())
            self.settings.setValue('output_format', self.format_combo.currentText())
            self.settings.setValue('max_file_size', self.max_size_spin.value())
            self.settings.setValue('include_binary', self.include_binary_check.isChecked())
            self.settings.setValue('include_hidden', self.include_hidden_check.isChecked())
            
        except Exception as e:
            logging.warning(f"Error saving settings: {e}")

    def closeEvent(self, event):
        """Handle application close event"""
        # Cancel any running processing
        running_threads = [
            self.processor_thread,
            self.tree_loader_thread,
            self.restorer_thread
        ]
        
        if any(thread and thread.isRunning() for thread in running_threads):
            reply = QMessageBox.question(
                self, 'File Merger Pro', 
                'Processing is in progress. Do you want to cancel and exit?',
                QMessageBox.Yes | QMessageBox.No, 
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                for thread in running_threads:
                    if thread and thread.isRunning():
                        thread.cancel()
                        thread.wait(3000)
            else:
                event.ignore()
                return
        
        # Save settings
        self.save_settings()
        
        # Save ignore patterns
        self.save_ignore_list()
        
        event.accept()

    def expand_all_files(self):
        """Expand all items in the file tree"""
        if hasattr(self, 'tree') and self.tree:
            self.tree.expandAll()
    def collapse_all_files(self):
        """Collapse all items in the file tree"""
        if hasattr(self, 'tree') and self.tree:
            self.tree.collapseAll()


def main():
    """Main application entry point"""
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('file_merger.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Enable high DPI scaling
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    app = QApplication(sys.argv)
    app.setApplicationName("File Merger Pro")
    app.setApplicationVersion("2.1")
    app.setOrganizationName("FileMerger")
    app.setStyle('Fusion')
    
    # Set application icon
    try:
        app.setWindowIcon(QApplication.style().standardIcon(
            QApplication.style().SP_ComputerIcon
        ))
    except:
        pass
    
    try:
        # Create and show main window
        window = FileMergerApp()
        window.show()
        
        # Log startup
        logging.info("File Merger Pro 2.1 started successfully")
        
        # Run application
        sys.exit(app.exec_())
        
    except Exception as e:
        logging.critical(f"Application crashed during startup: {str(e)}", exc_info=True)
        
        # Show error dialog
        error_msg = QMessageBox()
        error_msg.setIcon(QMessageBox.Critical)
        error_msg.setWindowTitle("Critical Error")
        error_msg.setText("Application failed to start")
        error_msg.setInformativeText(str(e))
        error_msg.setDetailedText(f"Check file_merger.log for details")
        error_msg.exec_()
        
        sys.exit(1)


if __name__ == "__main__":
    main()