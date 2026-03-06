import os

def fix_files():
    # Folder containing the files
    target_folder = 'outputFolder'
    
    # Extensions to process
    extensions = ('.txt', '.md')
    
    if not os.path.exists(target_folder):
        print(f"Folder '{target_folder}' not found.")
        return

    count = 0
    print(f"Scanning '{target_folder}' for text files to fix encoding...")

    for root, dirs, files in os.walk(target_folder):
        for filename in files:
            if filename.lower().endswith(extensions):
                filepath = os.path.join(root, filename)
                
                try:
                    # Read the file assuming it's UTF-8 (or already has BOM)
                    # 'utf-8-sig' handles both: it consumes the BOM if present, 
                    # or reads as normal UTF-8 if not.
                    with open(filepath, 'r', encoding='utf-8-sig', errors='replace') as f:
                        content = f.read()
                    
                    # Write the file back with UTF-8-SIG (forces BOM)
                    with open(filepath, 'w', encoding='utf-8-sig') as f:
                        f.write(content)
                        
                    print(f"Fixed: {filename}")
                    count += 1
                except Exception as e:
                    print(f"Error processing {filename}: {e}")

    print(f"\nDone! Fixed {count} files.")
    print("Your files should now display correctly in Windows editors.")

if __name__ == "__main__":
    fix_files()

