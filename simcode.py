import sys
import os
import json
import re
import shlex
import subprocess
from openai import OpenAI

class Terminal:
    def __init__(self):
        self.log_types = {
            # system
            "default": "#DCDCDC",
            "exec": "#98C379",
            "comment": "#abb2bf",
            "warning": "#E5C07B",
            "status": "#C678DD",
            "error": "#E06C75",
            # Markdown
            "md": "#DCDCDC",
            "h1": "#E06C75",  # Red
            "h2": "#98C379",  # Green
            "bold": "#E5C07B",  # Yellow
            "italic": "#C678DD",  # Purple
            "code": "#56B6C2",  # Cyan
            "link": "#61AFEF",  # Blue
        }
        self.running = True

    def md_parse(self, text):
        # 1. Headings
        text = re.sub(
            r"^# (.*)$",
            lambda m: self.color_text(m.group(1).upper(), "h1"),
            text,
            flags=re.M,
        )
        text = re.sub(
            r"^## (.*)$", lambda m: self.color_text(m.group(1), "h2"), text, flags=re.M
        )
        # 2. Bold
        text = re.sub(
            r"\*\*(.*?)\*\*", lambda m: self.color_text(m.group(1), "bold"), text
        )
        # 3. Italic
        text = re.sub(
            r"\*(.*?)\*", lambda m: self.color_text(m.group(1), "italic"), text
        )
        # 4. Inline Code
        text = re.sub(
            r"`(.*?)`", lambda m: self.color_text(f" {m.group(1)} ", "code"), text
        )
        # 5. Links
        text = re.sub(
            r"\[(.*?)\]\((.*?)\)",
            lambda m: f"{self.color_text(m.group(1), 'link')} ({m.group(2)})",
            text,
        )
        return text

    def color_text(self, text: str, text_type="default"):
        color = self.log_types.get(text_type, "default").lstrip("#")
        r, g, b = tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))
        return f"\033[38;2;{r};{g};{b}m{text}\033[0m"

    def exec_cmd(self, cmd_text: str):
        cmd = cmd_text.strip()
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        self.append_log(result.stdout)
        if result.stderr:
            self.append_log(result.stderr, text_type="error")

    def append_log(
        self, text: str, text_type="default", sys=True, end="\n", flush=False
    ):
        if sys:
            # For standard logging or streaming chunks
            print("[simcode] " + self.color_text(text, text_type), end=end, flush=True)
        else:
            # For full markdown blocks, parse and print
            print(self.md_parse(text), end=end, flush=flush)

    def recv_input(self, model: str):
        prefix = f"{os.path.abspath('.')}"
        status = self.color_text(f"({model})", text_type="status")

        self.append_log(f"┌ {prefix} {status}", text_type="default", sys=False)
        lines = []
        while True:
            line = input(f"└─> ")
            if not line.endswith("\\"):
                lines.append(line)
                break
            else:
                lines.append(line[:-1])  # Remove the '\'

        text = "\n".join(lines).strip()

        if text.startswith("/bash"):
            cmd = text.replace("/bash ", "")
            prefix_txt = self.color_text("run", text_type="exec")
            cmd_txt = self.color_text(cmd, text_type="comment")
            self.append_log(f"[{prefix_txt}] {cmd_txt}", sys=False)
            self.exec_cmd(cmd)
            return ""  # Return empty so pipeline doesn't trigger on raw bash
        return text


class Agent:
    def __init__(self):
        self.base_url = "http://localhost:11434/api/generate"
        self.api_key = "DUMP"
        self.model = "qwen3.5:2b"
        # self.model = "qwen3.5:2b-q4_K_M"
        self.max_steps = 8
        # Format: {"name": {"script": str, "abstract": str, "desc": str}}
        self.tools = {}
        self.pipeline = []
        self.terminal = Terminal()

        # status
        self.tool_available = False

    def set_config(self, base_url: str = "", api_key_file: str = "",
                   model: str = "", max_steps: int = 8):
        if base_url:
            self.base_url = base_url
            
        if api_key_file:
            try:
                with open(api_key_file, "r", encoding="utf-8") as f:
                    # CRITICAL: .strip() removes the hidden newline that crashes the OpenAI client
                    self.api_key = f.read().strip()
            except FileNotFoundError:
                self.terminal.append_log(f"[!] Error: API key file '{api_key_file}' not found.", "error")
                # Fallback to an empty string so the script
                #doesn't hard-crash immediately
                self.api_key = "" 
                
        if model:
            self.model = model
            
        self.max_steps = max_steps
        return self

    def load_skills(self, skills_dir="skills"):
        """Scans the skills/ directory and loads tools automatically."""
        if not os.path.exists(skills_dir):
            os.makedirs(skills_dir)
            self.terminal.append_log(
                f"Created {skills_dir}/ directory. Add tools here.", "comment"
            )
            return self

        for item in os.listdir(skills_dir):
            tool_path = os.path.join(skills_dir, item)
            if os.path.isdir(tool_path):
                abstract_path = os.path.join(tool_path, "ABSTRACT.md")
                readme_path = os.path.join(tool_path, "README.md")

                # Check for executable scripts (Python or Bash)
                script_path = None
                if os.path.exists(os.path.join(tool_path, "run.py")):
                    script_path = f"python3 {os.path.join(tool_path, 'run.py')}"
                elif os.path.exists(os.path.join(tool_path, "run.sh")):
                    script_path = f"bash {os.path.join(tool_path, 'run.sh')}"

                if (
                    script_path
                    and os.path.exists(readme_path)
                    and os.path.exists(abstract_path)
                ):
                    with open(readme_path, "r", encoding="utf-8") as f:
                        desc = f.read().strip()
                    with open(abstract_path, "r", encoding="utf-8") as f:
                        abstract = f.read().strip()
                    self.tools[item] = {
                        "script": script_path,
                        "abstract": abstract,
                        "desc": desc,
                    }
                    self.terminal.append_log(f"Loaded tool: {item}", "exec")
        return self

    def __load_prompt(self, prompt_source: str) -> str:
        if os.path.exists(prompt_source):
            with open(prompt_source, "r", encoding="utf-8") as f:
                return f.read()
        return prompt_source

    def create_step_precondition(self, prompt_source: str, tool: bool = False):
        prompt = self.__load_prompt(prompt_source)
        self.pipeline.append(
            {"name": "plan", "once": True, "system_prompt": prompt, "tool": tool}
        )
        return self

    def create_step(self, prompt_source: str, tool: bool = True):
        prompt = self.__load_prompt(prompt_source)
        self.pipeline.append(
            {"name": "execute", "once": False, "system_prompt": prompt, "tool": tool}
        )
        return self

    def use_tool(self, llm_output: str) -> str:
        """Parses output for [Action: tool_name(args)] and executes it via subprocess."""
        # 1. Use findall instead of search to capture every instance
        matches = re.findall(r"\[Action:\s*([a-zA-Z0-9_-]+)\((.*?)\)\]", llm_output)
        if not matches:
            return "No valid action found."

        # 2. Grab the LAST match in the list (index -1) to ignore thoughts
        actual_action = matches[-1]

        tool_name = actual_action[0].strip()
        args = actual_action[1].strip()
        args = args.replace('"', "").replace("'", "")

        if not self.tool_available:
            if tool_name == "get_tool_manual":
                if args in self.tools:
                    self.terminal.append_log(
                        f"=> Reading Manual for: {args}", "warning", flush=True
                    )
                    text = f"MANUAL FOR '{args}':\n"
                    text += f"{self.tools[args]['desc']}\n\n"
                    text += f"You may now use [Action: {args}(...)]"
                    self.tool_available = True
                    return text
                else:
                    return f"Error: Tool '{args}' does not exist."
            else:
                return f"Error: Use get_tool_manual to read the manual first."

        if tool_name not in self.tools:
            return f"Error: Tool '{tool_name}' not found."

        script_cmd = self.tools[tool_name]["script"]

        cmd_list = shlex.split(
            script_cmd
        )  # e.g., turns "python skills/read_file/run.py" into a list
        cmd_list.append(args)  # appends the entire args string safely to sys.argv[1]

        self.terminal.append_log(f"=> Executing Tool: {tool_name}({args})", "warning")

        try:
            result = subprocess.run(cmd_list, capture_output=True, text=True)
            output = result.stdout if result.stdout else result.stderr
            self.tool_available = False
            return output.strip()
        except Exception as e:
            return f"Tool Execution Failed: {str(e)}"

    def stream_llm(self, user_prompt: str, system_prompt: str, use_tool: bool):
        if not self.api_key:
            yield "\n[Error: API key not set. Please set it in set_config.]\n"
            return

        # Initialize the OpenAI client with dynamic base URL
        client = OpenAI(base_url=self.base_url, api_key=self.api_key)

        # We want all the prompt to know which tools we can use
        if use_tool and self.tools:
            if self.tool_available:
                full_system_prompt = (
                    f"{system_prompt}\n\n"
                    f"To use a tool, output EXACTLY: [Action: tool_name(args)]"
                )
                stop_sequences = ["[Observation:"]
            else:
                tool_abstracts = "\n".join(
                    [
                        f"- {name}: {data['abstract']}"
                        for name, data in self.tools.items()
                    ]
                )

                full_system_prompt = (
                    f"{system_prompt}\n\n"
                    f"=== AVAILABLE TOOLS ===\n"
                    f"{tool_abstracts}\n\n"
                    f"CRITICAL RULES FOR TOOLS:\n"
                    f"1. You CANNOT use a tool until you read its manual.\n"
                    f"2. To read a manual, output EXACTLY: [Action: get_tool_manual(tool_name)]\n"
                    f"3. Once you read the manual, you can use the tool by outputting: [Action: tool_name(args)]"
                )
                stop_sequences = []
        else:
            full_system_prompt = system_prompt
            stop_sequences = []

        if True:
            self.terminal.append_log(
                "system prompt\n" + full_system_prompt, text_type="comment", flush=True
            )
            self.terminal.append_log(
                "user prompt\n" + user_prompt, text_type="comment", flush=True
            )

        messages = [
            {"role": "system", "content": full_system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        # 1. Prepare the base arguments
        api_kwargs = {
            "model": self.model,
            "messages": messages,
            "stream": True,
        }

        # 2. Conditionally add 'stop' ONLY if it is not empty
        if stop_sequences:
            api_kwargs["stop"] = stop_sequences

        try:
            # 3. Pass the arguments using **kwargs unpacking
            response = client.chat.completions.create(**api_kwargs)

            # Stream chunks exactly as they arrive
            for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            yield f"\n[Backend Error: {e}]\n\n--- DEBUG INFO ---\n{error_details}\n------------------\n"

    def check_step_finished(self, llm_output):
        keywords = [
            "[STATUS: END]",
            "[STATUS: FINISH]",
            "[STATUS: FINISHED]",
            "[STATUS: COMPLETE]",
            "[STATUS: COMPLETED]",
        ]

        for keyword in keywords:
            if keyword in llm_output:
                return True
        return False

    def do_step(self, step_idx, step_config, step_completed, iterations, current_ctx):
        step_name = step_config["name"]
        system_prompt = step_config["system_prompt"]
        use_tool = step_config["tool"]

        self.terminal.append_log(
            f"=== Step {step_idx + 1}-{iterations}: {step_name.upper()} - tool_available: {self.tool_available} ===",
            "status",
        )

        llm_output = ""

        # Stream the LLM output in real-time
        for chunk in self.stream_llm(current_ctx, system_prompt, use_tool):
            self.terminal.append_log(
                chunk, text_type="md", sys=False, end="", flush=True
            )
            llm_output += chunk
        # Newline after generation
        self.terminal.append_log("", flush=True, sys=False)

        # If the LLM says it's finished, break the loop and move to next step
        if step_config["once"] or self.check_step_finished(llm_output):
            self.terminal.append_log("=> Plan Execution Complete.", "status")
            step_completed = True
            # Pass the final output to the next step (if there is one)
            current_ctx = current_ctx.replace("===Previous Context Start===\n", "")
            current_ctx = current_ctx.replace("===Previous Context End===\n---\n", "")
            current_ctx = f"===Previous Context Start===\n{current_ctx}\n\n"
            current_ctx += f"Final Output:\n{llm_output}\n"
            current_ctx += f"===Previous Context End===\n---\n"
            return (1, step_completed, current_ctx)

        # Handle tool calling
        if use_tool and "[Action:" in llm_output:
            observation = self.use_tool(llm_output)
            self.terminal.append_log(
                f"Observation: {observation}", "comment", sys=False
            )

            # Append the observation to the context and LOOP AGAIN within
            # the same step
            current_ctx = current_ctx.replace("===Previous Context Start===\n", "")
            current_ctx = current_ctx.replace("===Previous Context End===\n---\n", "")
            current_ctx = f"===Previous Context Start===\n{current_ctx}\n\n"
            current_ctx += f"Action Taken:\n{llm_output}\n\n"
            current_ctx += f"Observation:\n{observation}\n"
            current_ctx += f"===Previous Context End===\n---\n"
        else:
            # If no tool was used and it didn't explicitly finish,
            # we assume this step is done (like the Plan step)
            step_completed = True

            current_ctx = current_ctx.replace("===Previous Context Start===\n", "")
            current_ctx = current_ctx.replace("===Previous Context End===\n---\n", "")
            current_ctx = f"===Previous Context Start===\n{current_ctx}\n\n"
            current_ctx += f"Output:\n{llm_output}\n"
            current_ctx += f"===Previous Context End===\n---\n"

        return (0, step_completed, current_ctx)

    def do_pipeline(self, initial_ctx: str):
        current_ctx = initial_ctx

        for step_idx, step_config in enumerate(self.pipeline):
            step_completed = False
            iterations = 0
            max_iterations = self.max_steps
            self.tool_available = False

            # The Execution Loop (Runs once for Plan, multiple times for Execute)
            while not step_completed and iterations < max_iterations:
                iterations += 1

                ret, step_completed, current_ctx = self.do_step(
                    step_idx, step_config, step_completed, iterations, current_ctx
                )
                if ret == 1:
                    break

                if iterations >= max_iterations:
                    self.terminal.append_log(
                        "[!] Step halted: Reached max iterations.", "error"
                    )

    def run(self):
        # Load tools from the skills directory on startup
        self.load_skills()
        while True:
            ctx = self.terminal.recv_input(self.model)
            # Only run pipeline if there's actual text (ignores pure /bash cmds)
            if ctx:
                self.do_pipeline(ctx)


def main():
    agent = Agent()

    agent.set_config(
        # Ollama
        #base_url="http://localhost:11434/v1",

        # gemini
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        api_key_file="api_key.txt",
        model="gemini-2.5-flash"
    )
    # Ensure the steps directory exists
    if not os.path.exists("steps"):
        os.makedirs("steps")
        print("Created steps/ directory. Please add plan.md and execute.md")
        return

    # Load the steps from the directory
    agent.create_step_precondition("steps/plan.md", tool=False)
    agent.create_step("steps/execute.md", tool=True)

    agent.run()


if __name__ == "__main__":
    main()
