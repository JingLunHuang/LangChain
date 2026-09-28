import os
import glob

def install_and_import():
    try:
        import opencc
    except ImportError:
        import subprocess
        import sys
        subprocess.check_call([sys.executable, "-m", "pip", "install", "opencc-python-reimplemented"])
        import opencc

install_and_import()
import opencc

converter = opencc.OpenCC('s2t')

def translate_file(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        return
    
    translated = converter.convert(content)
    
    if translated != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(translated)
        print(f"Translated: {filepath}")

def main():
    base_dir = r"d:\github project\LangChain"
    extensions = ["*.py", "*.md", "*.txt"]
    
    for ext in extensions:
        pattern = os.path.join(base_dir, "**", ext)
        for filepath in glob.glob(pattern, recursive=True):
            if ".venv" in filepath or ".git" in filepath or "__pycache__" in filepath:
                continue
            translate_file(filepath)

if __name__ == "__main__":
    main()
