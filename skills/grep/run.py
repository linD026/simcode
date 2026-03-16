import sys
import os
import subprocess

def main():
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print("Error: Keyword is required. Format: keyword, path")
        return

    # Parse the comma-separated arguments from the LLM
    args = [arg.strip() for arg in sys.argv[1].split(",")]
    keyword = args[0]
    # Default to "./" if no path is provided
    path = args[1] if len(args) > 1 and args[1] else "./"

    if not os.path.exists(path):
        print(f"Error: '{path}' does not exist.")
        return

    try:
        # -r: recursive, -n: line numbers, -I: ignore binaries
        res = subprocess.run(
            ["grep", "-rnI", keyword, path], capture_output=True, text=True
        )
        if res.returncode == 0:
            if len(res.stdout) > 8000:
                print(res.stdout[:8000] + "\n...[TRUNCATED]")
            else:
                print(res.stdout)
        else:
            print(f"No matches found for '{keyword}' in '{path}'.")
    except Exception as e:
        print(f"Error executing grep: {e}")

if __name__ == "__main__":
    main()
