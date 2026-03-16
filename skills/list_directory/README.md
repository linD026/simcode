# Tool: list_directory

Lists files and directories in the specified path to help you understand the project structure. 

### How it is called internally
The agent executes this tool via the command line:
`python3 run.py "[path]"`
*(If no path is provided, it defaults to the current directory `./`)*

### How to use this tool in your prompt
You must provide the path as a single argument inside the Action format.
**Format:** `[Action: list_directory(path)]`
**Example 1:** `[Action: list_directory(./src)]`
**Example 2:** `[Action: list_directory(./)]`

### Expected Output
Returns a newline-separated list of items in the directory. Each item is prefixed with `[DIR]` or `[FILE]` so you know if you can read it or if you need to list it further.
**Example Output:**
[DIR] components
[DIR] utils
[FILE] main.py
[FILE] config.json
