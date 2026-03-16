import sys
import os

def main():
    # If no argument is passed, default to "./"
    path = sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1].strip() else "./"

    if not os.path.exists(path):
        print(f"Error: '{path}' does not exist.")
        return

    try:
        items = [
            "[DIR] " + e.name if e.is_dir() else "[FILE] " + e.name
            for e in os.scandir(path)
        ]
        print("\n".join(sorted(items)) if items else "Directory is empty.")
    except Exception as e:
        print(f"Error listing directory: {e}")

if __name__ == "__main__":
    main()
