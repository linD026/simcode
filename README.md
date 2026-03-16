# Local Terminal Agent Framework

A lightweight, fully local LLM Agent framework designed to run in your terminal. Powered by Ollama (defaulting to `qwen3.5:2b`), this agent uses a ReAct (Reasoning + Acting) loop to plan tasks, execute command-line tools, and report back—all formatted beautifully in native terminal markdown.

## Features

- **Local & Private:** Runs entirely on your machine using Ollama.
- **Dynamic Skill System:** Add new tools just by dropping a script and a README into the `skills/` folder. No core code changes required.
- **Cognitive Pipeline:** Separates thinking into distinct steps (e.g., "Plan" then "Execute") to get highly accurate results from smaller models.
- **Native Markdown Terminal UI:** Renders headers, lists, and code blocks in colored ANSI text.
- **Direct Bash Execution:** Type `/bash <command>` to bypass the LLM and run system commands directly in the same terminal context.

## Prerequisites

1. **Python 3.8+**
2. **Ollama:** Installed and running locally.
3. **LLM Model:** Pull the default model before running:
   ```bash
   ollama run qwen3.5:2b

## Project Structure

```text
.
├── simcode.py              # The core Agent and Terminal script
├── steps/                  # System prompts for the cognitive pipeline
│   ├── plan.md             # Instructs the LLM how to break down tasks
│   └── execute.md          # Instructs the LLM how to loop and use tools
└── skills/                 # Directory for dynamic tools
    ├── list_directory/
    │   ├── README.md       # Teaches the LLM how to use this tool
    │   └── run.py          # The actual tool execution script
    ├── grep/
    └── read_file/

```

## Usage Guide

### Chatting with the Agent

Simply type your prompt at the `└─>` symbol.
To write a **multiline prompt**, end your line with a backslash (`\`) and press Enter. The agent will wait for you to finish.

```text
└─> Find all TODOs in my src directory \
└─> and save them to a file.

```

### Bypassing the Agent (Direct Bash)

If you just need to run a quick command without LLM interference, prefix it with `/bash`.

```text
└─> /bash ls -la

```

## Adding New Skills (Tools)

The agent automatically loads tools on startup. To create a new tool:

1. Create a new folder in `skills/` (e.g., `skills/my_tool/`).
2. Add a `run.py` (or `run.sh`). This script must accept arguments via the command line (e.g., `sys.argv[1]`).
3. Add a `README.md`. The contents of this file are injected directly into the LLM's system prompt.

**Example `README.md` structure:**

```markdown
# Tool: my_tool
Brief description of what the tool does.
Format: `[Action: my_tool(arg1, arg2)]`

```

## How the Pipeline Works

By default, the agent runs a two-step pipeline:

1. **Plan (`once: True`):** The agent reads the user prompt and generates a checklist. It does not use tools here.
2. **Execute (`once: False`):** The agent iterates over the checklist. It outputs `[Action: tool(args)]`, the framework pauses the LLM, executes the local script, captures the `STDOUT`, and feeds it back to the LLM as an `Observation:`. This loop continues until the LLM outputs `[STATUS: FINISHED]`.
