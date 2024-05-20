import os
import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QFileDialog, QTreeWidgetItem, QTreeWidget, QPushButton, QVBoxLayout, QWidget
from PyQt5.QtCore import Qt

def list_files(startpath):
    structure = []
    root_item = QTreeWidgetItem([os.path.basename(startpath)])
    root_item.setCheckState(0, Qt.Checked)
    for root, dirs, files in os.walk(startpath):
        level = root.replace(startpath, '').count(os.sep)
        if level == 0:
            for file in files:
                file_path = os.path.join(root, file)
                file_item = QTreeWidgetItem([file])
                file_item.setData(0, Qt.UserRole, file_path)
                file_item.setCheckState(0, Qt.Checked)
                root_item.addChild(file_item)
        else:
            dir_item = QTreeWidgetItem([os.path.basename(root)])
            dir_item.setCheckState(0, Qt.Checked)
            root_item.addChild(dir_item)
            for file in files:
                file_path = os.path.join(root, file)
                file_item = QTreeWidgetItem([file])
                file_item.setData(0, Qt.UserRole, file_path)
                file_item.setCheckState(0, Qt.Checked)
                dir_item.addChild(file_item)
    structure.append(root_item)
    return structure

def merge_files(startpath, output_file, items):
    def write_tree(item, outfile, prefix=""):
        # Überprüfen, ob das Element ein Verzeichnis oder eine Datei ist
        if item.childCount() > 0:  # Verzeichnis
            outfile.write(f"{prefix}{item.text(0)}\n")
            new_prefix = "│   " if prefix else ""
            for i in range(item.childCount()):
                child = item.child(i)
                if i == item.childCount() - 1:
                    child_prefix = prefix + "└── "
                else:
                    child_prefix = prefix + "├── "
                write_tree(child, outfile, child_prefix)
        else:  # Datei
            inclusion_status = "" if item.checkState(0) == Qt.Checked else " (not included)"
            outfile.write(f"{prefix}{item.text(0)}{inclusion_status}\n")

    with open(output_file, 'w', encoding='utf-8') as outfile:
        outfile.write("File tree:\n\n")
        for item in items:
            write_tree(item, outfile)
        outfile.write("\nFILES:\n\n")
        for item in items:
            for i in range(item.childCount()):
                child = item.child(i)
                if child.checkState(0) == Qt.Checked and child.childCount() == 0:
                    data = child.data(0, Qt.UserRole)
                    if data is not None:
                        file_path = os.path.join(startpath, data)
                        relative_path = os.path.relpath(file_path, startpath)
                        with open(file_path, 'r', encoding='utf-8') as infile:
                            outfile.write(f"{relative_path}:\n")
                            outfile.write(infile.read())
                            outfile.write("\n")

                            
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("File Merger")
        self.setGeometry(100, 100, 800, 600)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout()
        central_widget.setLayout(layout)

        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabels(["Files"])
        layout.addWidget(self.tree_widget)

        button_layout = QVBoxLayout()
        layout.addLayout(button_layout)

        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self.browse_folder)
        button_layout.addWidget(browse_button)

        merge_button = QPushButton("Merge")
        merge_button.clicked.connect(self.merge_files)
        button_layout.addWidget(merge_button)

        # Connect the itemChanged signal to a slot
        self.tree_widget.itemChanged.connect(self.update_check_state)

    def update_check_state(self, item, column):
        # Apply the check state of the parent item to all its children
        check_state = item.checkState(column)
        for i in range(item.childCount()):
            child = item.child(i)
            child.setCheckState(column, check_state)

    def browse_folder(self):
        folder_path = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder_path:
            self.tree_widget.clear()
            items = list_files(folder_path)
            self.tree_widget.addTopLevelItems(items)
            self.startpath = folder_path

    def merge_files(self):
        output_dir = os.path.join(self.startpath, 'outputMerge')
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        output_file = os.path.join(output_dir, 'merged.txt')
        items = self.tree_widget.findItems("", Qt.MatchContains | Qt.MatchRecursive)
        merge_files(self.startpath, output_file, items)
        print(f"Merged file created at: {output_file}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())