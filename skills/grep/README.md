# Tool: grep

Uses native OS grep to search for a specific keyword across files in a given directory. This is highly effective for finding variable definitions, specific functions, or TODO comments without reading entire files.

### How it is called internally
The agent executes this tool via the command line, passing the arguments as a single comma-separated string:
`python3 run.py "[keyword], [path]"`

### How to use this tool in your prompt
You must provide EXACTLY two arguments separated by a comma: the keyword and the directory path.
**Format:** `[Action: grep(keyword, path)]`
**Example 1:** `[Action: grep(Terminal, ./src)]`
**Example 2:** `[Action: grep(def parse, ./)]`

### Expected Output
Returns the matching lines from the files, including the file path and exact line number. This is critical for context if you later need to use `read_file` to see the surrounding code. Outputs longer than 8000 characters will be truncated.
**Example Output:**
./src/main.py:45: class Terminal:
./src/main.py:112: def parse_terminal_input():
