# File Merger for ChatGPT and Other AI
<sup>
Please note that I created this tool primarily for my own use, as I was frustrated with having to copy and paste numerous code snippets into every new AI chat. With the increasing token context limits of AI language models, I believe this tool offers a convenient solution for larger codebases, allowing you to quickly provide all relevant information to the AI. For me, it fulfills all my needs, but that might not be the case for you. Feel free to modify the tool according to your requirements.
</sup>

## Description

This File Merger is for ChatGPT and Other AIs. Its designed to quickly merge relevant files for interaction with AI systems like ChatGPT or Claude. It allows you to select a directory containing your files, choose which files to include, and generate a single output file with the merged content. This streamlines the process of providing code or text content to AI systems, making it easier to share and process the information.

## Features

- Graphical user interface for easy file and folder selection
- Checkbox-based selection to include or exclude specific files and folders
- Generates a single output file containing a filetree and the merged content of selected files
- Displays a file tree structure at the beginning of the output file
- Includes file paths and names for each merged file in the output
- Quick access button to open the output folder directly

## Installation

1. Download the latest release [here](https://github.com/Ppaja/File-Merger-for-ChatGPT-and-other-AI/archive/refs/heads/main.zip).
2. Extract the ZIP file to a location of your choice.
3. Run the `install.bat` file to install the required dependencies (one-time setup).

## Usage

1. Run the `start.bat` file to launch the File Merger application.
2. Click the "Browse" button to select your projects root directory containing your files.
3. In the file tree, check or uncheck the files and folders you want to include or exclude from the merge.
4. Click the "Merge" button to generate the output file with the merged content.
5. The output file (`mergeOutput.txt`) will be created in the `outputFolder` directory within the application's folder.
6. Click the "Open Output Folder" button to quickly access the `outputFolder` directory.
7. Copy and paste the contents of `mergeOutput.txt` into your favorite AI system to easily share the relevant part of your Code

(You can of course also create a shortcut to the `start.bat` file on your desktop for quick access.)

## Requirements

This application is built using Python and the PyQt5 library. The required dependencies are automatically installed when you run the `install.bat` file.

## Contributing

This project is open-source and freely available for anyone to modify and build upon.

<details>
<summary>Example-Output</summary>

```bash
File Tree:
├── css
│   └── style.css
├── firebase
│   └── firebase.js (not included)
├── index.html
└── js
    ├── generate.js (not included)
    ├── logic.js (not included)
    ├── nav.js (not included)
    └── subjs
        └── sub.js


Merged Files:
style.css:
css\style.css
/* this is the css file */
.container {
    color: red;
}


index.html:
index.html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Document</title>
</head>
<body>
    <h1>this is the index file</h1>
</body>
</html>
sub.js:
js\subjs\sub.js

this is the subfolder js file

```
</details>
