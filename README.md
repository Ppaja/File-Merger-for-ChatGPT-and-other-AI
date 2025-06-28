# File Merger for ChatGPT and Other AI
<sup>
Please note that I created this tool primarily for my own use, as I was frustrated with having to copy and paste numerous code snippets into every new AI chat. 
95 % done by AI!
</sup>

## New version:
* added open/collapse and select/unselect all buttons
* added some settings
* new GUI (claude ^^)
* File Preview
* Optional Project system

## Description

One of the tools I’ve been using privately for a long time on a regular basis, so I thought maybe others could find it useful too. 

This Single File Merger is for ChatGPT and Other AIs. Its designed to quickly merge relevant files for interaction with AI systems like ChatGPT or Claude. It allows you to select a directory containing your files, choose which files to include, and generate a single output file with the merged content. This streamlines the process of providing code or text content to AI systems, making it easier to share and process the information.

## Features  
- **Graphical Interface** – Select files and folders easily  
- **Structured Output** – Preserves file paths and hierarchy  
- **Quick Access** – Open the output folder with one click from the GUI

## Installation

1. Download the latest release [here](https://github.com/Ppaja/File-Merger-for-ChatGPT-and-other-AI/archive/refs/heads/main.zip).
2. Extract the ZIP file to a location of your choice.
3. Run the `install.bat` file to install the required dependencies (one-time setup).

## Usage

1. Run the `start.bat` file to launch the File Merger application.

2.  **Browse for a Directory:** Click **"Browse Folder"** or use the folder icon in the toolbar to load your project's root directory.

3.  **Select Files:** Use the checkboxes in the file tree to select the files and folders you want to include.

4.  **Configure (Optional):**
    -   Navigate to the **"Settings"** tab to change the output format, destination folder, and other processing options.
    -   Edit the ignore patterns directly in the text area.

5.  **Merge Files:** Click **"Merge Selected Files"**. The progress will be shown in the status bar.

6.  **Get the Output:** A confirmation dialog will appear upon completion. The output file will be in the configured folder (defaults to `outputFolder`).

## Keyboard Shortcuts

| Shortcut          | Action                       |
| :---------------- | :--------------------------- |
| `Ctrl+N`          | Create New Project           |
| `Ctrl+O`          | Open Project                 |
| `Ctrl+S`          | Save Project                 |
| `Ctrl+Q`          | Quit Application             |
| `Ctrl+A`          | Select All Files             |
| `Ctrl+D`          | Deselect All Files           |
| `Ctrl+F`          | Focus the Search Bar         |
| `F5`              | Refresh File Tree            |

## Configuration

### Ignore Patterns

The application ignores common development files and folders by default (e.g., `__pycache__`, `.git`). You can customize this list in two ways:

1.  **In the GUI:** Add patterns in the "Settings" tab under the "Ignore Patterns" section.
2.  **Via `ignore.txt`:** Create an `ignore.txt` file in the application's root directory. Each pattern should be on a new line.

### Project Files

Use `Ctrl+S` to save your current session (selected directory, file choices, settings) to a `.json` file. You can reload this session later using `Ctrl+O`.

<details>
<summary>Example Markdown Output</summary>

````markdown
# File Merge Report

**Generated:** 2025-06-28 15:00:00
**Source Directory:** `C:/path/to/your/project`

## File Structure

```
├── ✓ src
│   ├── ✓ main.py (15.2KB)
│   └── ✓ utils.py (4.1KB)
├── ✗ tests
├── ✓ README.md (3.3KB)
└── ✗ .gitignore
```

## File Contents

### 📄 main.py

**Path:** `src/main.py`

```python
import sys
from PyQt5.QtWidgets import QApplication

def main():
    """Main application entry point"""
    app = QApplication(sys.argv)
    # ... rest of the code
```

### 📄 utils.py

**Path:** `src/utils.py`

```python
def format_file_size(size_bytes):
    """Format file size in human readable format"""
    if size_bytes < 1024:
        return f"{size_bytes}B"
    # ... rest of the code
```

### 📄 README.md

**Path:** `README.md`

```markdown
# My Project Title

This is the README for my project.
```
````
</details>