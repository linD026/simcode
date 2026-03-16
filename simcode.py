import sys
import os
import json
import urllib.request
import re
import shlex
import subprocess


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
        self.backend = "http://localhost:11434/api/generate"
        self.model = "qwen3.5:2b"
        # self.model = "qwen3.5:2b-q4_K_M"
        self.max_steps = 5
        self.tools = {}  # Format: {"name": {"script": str, "desc": str}}
        self.pipeline = []
        self.terminal = Terminal()

    def set_config(self, backend: str, model: str, max_steps: int = 8):
        self.backend = backend
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
                readme_path = os.path.join(tool_path, "README.md")

                # Check for executable scripts (Python or Bash)
                script_path = None
                if os.path.exists(os.path.join(tool_path, "run.py")):
                    script_path = f"python3 {os.path.join(tool_path, 'run.py')}"
                elif os.path.exists(os.path.join(tool_path, "run.sh")):
                    script_path = f"bash {os.path.join(tool_path, 'run.sh')}"

                if script_path and os.path.exists(readme_path):
                    with open(readme_path, "r", encoding="utf-8") as f:
                        desc = f.read().strip()
                    self.tools[item] = {"script": script_path, "desc": desc}
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
        match = re.search(r"\[Action:\s*([a-zA-Z0-9_-]+)\((.*?)\)\]", llm_output)
        if not match:
            return "No valid action found."

        tool_name = match.group(1).strip()
        args = match.group(2).strip()

        if tool_name not in self.tools:
            return f"Error: Tool '{tool_name}' not found."

        script_cmd = self.tools[tool_name]["script"]

        clean_args = args.replace('"', "").replace("'", "")

        cmd_list = shlex.split(
            script_cmd
        )  # e.g., turns "python skills/read_file/run.py" into a list
        cmd_list.append(
            clean_args
        )  # appends the entire args string safely to sys.argv[1]

        self.terminal.append_log(
            f"=> Executing Tool: {tool_name}({clean_args})", "warning"
        )

        try:
            result = subprocess.run(cmd_list, capture_output=True, text=True)
            output = result.stdout if result.stdout else result.stderr
            return output.strip()
        except Exception as e:
            return f"Tool Execution Failed: {str(e)}"

    def stream_llm(self, user_prompt: str, system_prompt: str, use_tool: bool):
        # We want the all the prompt know which tools we can use
        tool_descriptions = "\n".join(
            [f"- {name}: {data['desc']}" for name, data in self.tools.items()]
        )

        if use_tool and self.tools:
            full_system_prompt = (
                f"{system_prompt}\n\n"
                f"Following are available tools:\n"
                f"{tool_descriptions}\n"
                f"To use a tool, output EXACTLY: [Action: tool_name(args)]"
            )
            stop_sequences = ["[Observation:"]
        else:
            # full_system_prompt = (
            #    f"{system_prompt}\n\n"
            #    f"Following are available tools please reference it for the works:\n"
            #    f"{tool_descriptions}\n"
            # )
            full_system_prompt = system_prompt
            stop_sequences = []

        payload = json.dumps(
            {
                "model": self.model,
                "prompt": user_prompt,
                "system": full_system_prompt,
                "stream": True,
                "stop": stop_sequences,
            }
        ).encode("utf-8")

        if True:
            self.terminal.append_log(
                "user prompt\n" + user_prompt, text_type="comment", flush=True
            )
            self.terminal.append_log(
                "system prompt\n" + full_system_prompt, text_type="comment", flush=True
            )

        req = urllib.request.Request(
            self.backend,
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(req) as response:
                for line in response:
                    if line:
                        yield json.loads(line.decode("utf-8")).get("response", "")
        except Exception as e:
            yield f"\n[Backend Error: {e}]"

    def do_step(self, step_idx, step_config, step_completed, iterations, current_ctx):
        step_name = step_config["name"]
        system_prompt = step_config["system_prompt"]
        use_tool = step_config["tool"]

        self.terminal.append_log(
            f"=== Step {step_idx + 1}-{iterations}: {step_name.upper()} ===", "status"
        )

        llm_output = ""

        # Stream the LLM output in real-time
        for chunk in self.stream_llm(current_ctx, system_prompt, use_tool):
            self.terminal.append_log(
                chunk, text_type="md", sys=False, end="", flush=True
            )
            llm_output += chunk

        self.terminal.append_log("")  # Newline after generation

        # If the LLM says it's finished, break the loop and move to next step
        if step_config["once"] or "[STATUS: FINISHED]" in llm_output:
            self.terminal.append_log("=> Plan Execution Complete.", "status")
            step_completed = True
            # Pass the final output to the next step (if there is one)
            current_ctx = current_ctx.replace("Previous Context Start\n", "")
            current_ctx = current_ctx.replace("Previous Context End\n", "")
            current_ctx = f"Previous Context Start\n{current_ctx}\n\n"
            current_ctx += f"Final Output:\n{llm_output}\n"
            current_ctx += f"Previous Context End\n"
            return (1, step_completed, current_ctx)

        # Handle tool calling
        if use_tool and "[Action:" in llm_output:
            observation = self.use_tool(llm_output)
            self.terminal.append_log(
                f"Observation: {observation}", "comment", sys=False
            )

            # Append the observation to the context and LOOP AGAIN within
            # the same step
            current_ctx = f"{current_ctx}\n\n"
            current_ctx += f"Action Taken:\n{llm_output}\n\n"
            current_ctx += f"Observation:\n{observation}"
        else:
            # If no tool was used and it didn't explicitly finish,
            # we assume this step is done (like the Plan step)
            step_completed = True

            current_ctx = current_ctx.replace("Previous Context Start\n", "")
            current_ctx = current_ctx.replace("Previous Context End\n", "")
            current_ctx = f"Previous Context Start\n{current_ctx}\n\n"
            current_ctx += f"Output:\n{llm_output}\n"
            current_ctx += f"Previous Context End\n"

        return (0, step_completed, current_ctx)

    def do_pipeline(self, initial_ctx: str):
        current_ctx = initial_ctx

        for step_idx, step_config in enumerate(self.pipeline):
            step_completed = False
            iterations = 0
            max_iterations = self.max_steps

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
