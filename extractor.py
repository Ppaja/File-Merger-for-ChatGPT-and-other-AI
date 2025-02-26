import os
import subprocess
from PyQt5.QtWidgets import QApplication, QMainWindow, QFileDialog, QTreeWidget, QTreeWidgetItem, QPushButton, QVBoxLayout, QWidget, QMessageBox
from PyQt5.QtCore import Qt

class FileMergerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('File Merger')
        self.setGeometry(100, 100, 800, 600)
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        self.layout = QVBoxLayout(self.central_widget)
        
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(['Files and Folders'])
        self.tree.setState(True)  # Aktiviere Tri-State-Checkboxen (teilweise aktiviert)
        self.tree.itemChanged.connect(self.handle_item_changed)
        self.layout.addWidget(self.tree)
        
        self.browse_button = QPushButton('Browse')
        self.browse_button.clicked.connect(self.browse_folder)
        self.layout.addWidget(self.browse_button)
        
        self.merge_button = QPushButton('Merge')
        self.merge_button.clicked.connect(self.merge_files)
        self.layout.addWidget(self.merge_button)
        
        self.open_folder_button = QPushButton('Open Output Folder')
        self.open_folder_button.clicked.connect(self.open_output_folder)
        self.layout.addWidget(self.open_folder_button)
        
        self.root_directory = None
        self.output_folder = "outputFolder"
        self.ignore_list = self.load_ignore_list()
        self.updating = False  # Verhindert rekursive Signalverarbeitung

    def load_ignore_list(self):
        ignore_list = []
        if os.path.exists('ignore.txt'):
            with open('ignore.txt', 'r', encoding='utf-8') as file:
                ignore_list = [line.strip() for line in file if line.strip()]
        return ignore_list

    def browse_folder(self):
        folder_selected = QFileDialog.getExistingDirectory(self, "Select Directory")
        if folder_selected:
            self.root_directory = folder_selected
            self.populate_tree()

    def populate_tree(self):
        self.tree.clear()
        self.add_items(self.tree.invisibleRootItem(), self.root_directory)

    def add_items(self, parent_item, path):
        for item in os.listdir(path):
            if item in self.ignore_list:
                continue
            full_path = os.path.join(path, item)
            tree_item = QTreeWidgetItem(parent_item, [item])
            tree_item.setCheckState(0, Qt.Checked)
            tree_item.setData(0, Qt.UserRole, full_path)
            if os.path.isdir(full_path):
                self.add_items(tree_item, full_path)

    def handle_item_changed(self, item, column):
        if self.updating:
            return
        
        self.updating = True
        self.tree.blockSignals(True)  # Blockiere Signale während der Aktualisierung
        
        # Aktualisiere Kinder basierend auf dem Elternstatus
        if item.checkState(column) == Qt.Checked:
            self.check_all_children(item, Qt.Checked)
        elif item.checkState(column) == Qt.Unchecked:
            self.check_all_children(item, Qt.Unchecked)
        
        # Aktualisiere Elternstatus basierend auf Kinderstatus
        self.update_parent_state(item.parent())
        
        self.tree.blockSignals(False)  # Aktiviere Signale wieder
        self.updating = False
    
    def check_all_children(self, item, check_state):
        for i in range(item.childCount()):
            child = item.child(i)
            child.setCheckState(0, check_state)
            self.check_all_children(child, check_state)

    def update_parent_state(self, parent):
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
        
        # Aktualisiere rekursiv den Elternstatus des Elternelements
        self.update_parent_state(parent.parent())

    def merge_files(self):
        if not os.path.exists(self.output_folder):
            os.makedirs(self.output_folder)
        merge_filename = os.path.join(self.output_folder, 'mergeOutput.txt')
        try:
            with open(merge_filename, 'w', encoding='utf-8') as merge_file:
                # Schreiben des Dateibaums in die Ausgabedatei
                merge_file.write("File Tree:\n")
                self.write_tree_summary(self.tree.invisibleRootItem(), merge_file)
                merge_file.write("\n\nMerged Files:\n")
                # Schreiben der zusammengeführten Dateien
                self.write_files(self.tree.invisibleRootItem(), merge_file)
            QMessageBox.information(self, "Success", f"Merged files into {merge_filename}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred: {e}")

    def write_tree_summary(self, tree_item, merge_file, prefix="", is_last=True):
        for index in range(tree_item.childCount()):
            child = tree_item.child(index)
            full_path = child.data(0, Qt.UserRole)
            is_last_child = index == tree_item.childCount() - 1
            check_state = child.checkState(0)

            if os.path.isdir(full_path):
                folder_included = check_state != Qt.Unchecked
                if folder_included:
                    merge_file.write(f"{prefix}{'└── ' if is_last_child else '├── '}{os.path.basename(full_path)}\n")
                    new_prefix = prefix + ("    " if is_last_child else "│   ")
                    self.write_tree_summary(child, merge_file, new_prefix, is_last_child)
                else:
                    merge_file.write(f"{prefix}{'└── ' if is_last_child else '├── '}{os.path.basename(full_path)} (not included)\n")
            else:
                if check_state == Qt.Checked:
                    merge_file.write(f"{prefix}{'└── ' if is_last_child else '├── '}{os.path.basename(full_path)}\n")
                else:
                    merge_file.write(f"{prefix}{'└── ' if is_last_child else '├── '}{os.path.basename(full_path)} (not included)\n")

    def write_files(self, tree_item, merge_file):
        for index in range(tree_item.childCount()):
            child = tree_item.child(index)
            full_path = child.data(0, Qt.UserRole)
            check_state = child.checkState(0)
            
            if check_state == Qt.Checked and os.path.isfile(full_path):
                try:
                    with open(full_path, 'r', encoding='utf-8') as f:
                        merge_file.write(f"{os.path.basename(full_path)}:\n")
                        merge_file.write(f"{os.path.relpath(full_path, self.root_directory)}\n")
                        merge_file.write(f.read() + "\n")
                except:
                    merge_file.write(f"{os.path.basename(full_path)}:\n")
                    merge_file.write(f"{os.path.relpath(full_path, self.root_directory)}\n")
                    merge_file.write("Could not read file\n")
            elif os.path.isdir(full_path) and check_state != Qt.Unchecked:
                # Verarbeite sowohl vollständig als auch teilweise ausgewählte Ordner
                self.write_files(child, merge_file)

    def open_output_folder(self):
        path = os.path.abspath(self.output_folder)
        if os.name == 'nt':  # Windows
            os.startfile(path)
        elif os.name == 'posix':  # macOS, Linux
            subprocess.Popen(['open', path])

if __name__ == "__main__":
    app = QApplication([])
    window = FileMergerApp()
    window.show()
    app.exec_()
