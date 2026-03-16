# Tool: read_file

Reads the contents of a specific file. It can read the entire file or target a specific 100-line context window if a line number is provided.

### How it is called internally
The agent executes this tool via the command line, passing the arguments as a single comma-separated string:
`python3 run.py "[filepath], [center_line]"`

### How to use this tool in your prompt
You must provide the filepath. You can optionally provide a line number separated by a comma if you only need a specific section (useful for large files).
**Format:** `[Action: read_file(filepath)]` OR `[Action: read_file(filepath, center_line)]`
**Example 1 (Whole file):** `[Action: read_file(./src/main.py)]`
**Example 2 (Context window):** `[Action: read_file(./src/main.py, 112)]`

### Expected Output
Returns the text content of the file. Every line is prefixed with its line number so you can accurately understand the code structure. If a `center_line` was provided, it returns 50 lines above and 50 lines below that target.
**Example Output:**
--- Showing lines 110 to 115 of ./src/main.py ---
110:     # Process the input
111:     text = text.strip()
112:     def parse_terminal_input():
113:         pass
114: 
115:     return text
