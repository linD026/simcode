import sys
import os

def main():
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print("Error: Filepath is required. Format: filepath, center_line")
        return

    # Parse arguments
    args = [arg.strip() for arg in sys.argv[1].split(",")]
    filepath = args[0]
    center_line = args[1] if len(args) > 1 else ""

    if not os.path.exists(filepath):
        print(f"Error: '{filepath}' does not exist.")
        return

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # If the LLM provided a line number, return a context window
        if center_line and center_line.isdigit():
            line_num = int(center_line)
            start = max(0, line_num - 50)
            end = min(len(lines), line_num + 50)

            snippet = [f"--- Showing lines {start+1} to {end} of {filepath} ---"]
            for i in range(start, end):
                snippet.append(f"{i+1}: {lines[i].rstrip()}")
            
            print("\n".join(snippet))
            return

        # Fallback: return the whole file
        content = "".join(lines)
        if len(content) > 8000:
            print(content[:8000] + "\n...[TRUNCATED]")
        else:
            print(content)

    except Exception as e:
        print(f"Error reading file: {e}")

if __name__ == "__main__":
    main()
