import os
import subprocess
from simcode import AgentApp

# ==========================================
# 1. DEFINE YOUR TOOLS (Python Functions)
# ==========================================


def list_directory(path: str = "./") -> str:
    """Lists files and directories in the specified path."""
    if not os.path.exists(path):
        return f"Error: '{path}' does not exist."
    try:
        items = [
            "[DIR] " + e.name if e.is_dir() else "[FILE] " + e.name
            for e in os.scandir(path)
        ]
        return "\n".join(sorted(items)) if items else "Directory is empty."
    except Exception as e:
        return f"Error listing directory: {e}"


def grep(keyword: str, path: str = "./") -> str:
    """Uses native OS grep to find a keyword and its exact line number."""
    if not os.path.exists(path):
        return f"Error: '{path}' does not exist."
    try:
        # -r: recursive, -n: print line numbers (CRITICAL for context), -I: ignore binaries
        res = subprocess.run(
            ["grep", "-rnI", keyword, path], capture_output=True, text=True
        )
        if res.returncode == 0:
            return (
                res.stdout[:8000] + "\n...[TRUNCATED]"
                if len(res.stdout) > 8000
                else res.stdout
            )
        return f"No matches found for '{keyword}' in '{path}'."
    except Exception as e:
        return f"Error executing grep: {e}"


def read_file(filepath: str, center_line: str = "") -> str:
    """
    Reads a file. If 'center_line' is provided, it returns a 100-line
    window around that line, complete with line numbers.
    """
    if not os.path.exists(filepath):
        return f"Error: '{filepath}' does not exist."
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # If the LLM provided a line number, return a context window
        if center_line and center_line.isdigit():
            line_num = int(center_line)
            # Read 50 lines above and 50 lines below the target line
            start = max(0, line_num - 50)
            end = min(len(lines), line_num + 50)

            snippet = []
            snippet.append(f"--- Showing lines {start+1} to {end} of {filepath} ---")
            for i in range(start, end):
                # Add line numbers to the output so the LLM doesn't get lost
                snippet.append(f"{i+1}: {lines[i].rstrip()}")

            return "\n".join(snippet)

        # Fallback: If no line number is provided, return the whole file
        content = "".join(lines)
        return content[:8000] + "\n...[TRUNCATED]" if len(content) > 8000 else content

    except Exception as e:
        return f"Error reading file: {e}"


# ==========================================
# 2. DEFINE YOUR PROMPTS (The Pipeline)
# ==========================================

# STEP 1: The Precondition (Planning & Analysis)
PLANNER_PROMPT = """You are an expert systems architect and planner.
The user has provided a request. Your job is ONLY to analyze the request and write a clear, step-by-step logical plan on how to solve it. 

Do NOT attempt to use tools. Do NOT output code. 
Just explain the steps you will take to find the information or solve the problem."""

# STEP 2: The Execution (ReAct Tool Loop)
EXECUTOR_PROMPT = """You are an autonomous CLI agent. 
You operate in a loop: Thought -> Action -> Observation -> Thought...

Read the plan generated in the previous step, then execute it.

CRITICAL INSTRUCTIONS:
1. Always start your exploration from the current directory using the relative path './'.
2. Strictly use relative paths (e.g., './src', '../lib'). Do NOT use absolute paths.
3. If you need to use a tool, you MUST use this exact format:
   [TOOL: func_name("arg1", "arg2")]

Wait for the observation. Do not hallucinate the output of tools.
When you have finished the plan and have the final answer, output it to the user."""

# ==========================================
# 3. INITIALIZE AND RUN SIMCODE
# ==========================================

if __name__ == "__main__":
    # 1. Initialize the App
    simcode = AgentApp()

    # 2. Dynamically set the Dashboard Config
    simcode.set_config(
        backend="http://localhost:11434/api/generate",
        model="qwen3.5:2b",  # Change to your preferred local model
        max_steps=10,
    )

    # 3. Register Tools
    simcode.add_tool(
        name="read_file", description="Reads the content of a file.", func=read_file
    )
    simcode.add_tool(
        name="list_directory",
        description="Lists files and folders.",
        func=list_directory,
    )
    simcode.add_tool(
        name="grep",
        description="Recursively searches for a keyword in a file or directory.",
        func=grep,
    )

    # 4. Build the Execution Pipeline

    # Step 1: Analyze and Plan (Tools Disabled)
    simcode.create_step_precondition(PLANNER_PROMPT, enable_tool_use=False)

    # Step 2: Execute the Plan (Tools Enabled)
    simcode.create_step(EXECUTOR_PROMPT, enable_tool_use=True)

    # 5. Launch the CLI GUI
    simcode.run()
