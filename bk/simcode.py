import sys
import os
import json
import urllib.request
import queue
import re
import time
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QLineEdit,
    QLabel,
    QFrame,
    QSplitter,
    QFormLayout,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QTextCursor, QColor, QTextCharFormat, QBrush

# ==========================================
# STATE MANAGEMENT
# ==========================================


class AppState:
    def __init__(self):
        self.backend = "http://localhost:11434/api/generate"
        self.model = "qwen3.5:2b"
        self.status = "Awaiting Input"
        self.running = True
        self.max_steps = 8
        self.tools = {}  # Format: {"name": {"func": callable, "desc": str}}
        self.pipeline = []  # Sequence of execution steps


# ==========================================
# BACKGROUND AGENT THREAD (THE PIPELINE)
# ==========================================


class AgentThread(QThread):
    chat_append = pyqtSignal(str, str)
    chat_chunk = pyqtSignal(str)
    log_append = pyqtSignal(str, str)
    status_update = pyqtSignal(str)

    def __init__(self, state: AppState, task_queue: queue.Queue):
        super().__init__()
        self.state = state
        self.task_queue = task_queue

    def run(self):
        while self.state.running:
            try:
                user_text = self.task_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            self.status_update.emit("Initializing...")

            # The context persists across all steps in the pipeline
            context = "System Context: Your current working directory is './'. Use relative paths from here.\n"
            context += f"User Request: {user_text}\n"

            # Iterate through the defined steps (Precondition -> Main Loop)
            for step_idx, step_config in enumerate(self.state.pipeline):
                if not self.state.running:
                    break

                sys_prompt = step_config["prompt"]
                tools_enabled = step_config["enable_tool_use"]
                step_name = step_config["name"]

                self.status_update.emit(f"Running: {step_name}...")

                # --- NO-TOOL PHASE (E.G., PLANNING) ---
                if not tools_enabled:
                    self.chat_append.emit(
                        f"├─[{step_name}]\n│ ", "#ff8800"
                    )  # Orange for planning

                    llm_text = ""
                    for chunk in self.stream_llm(
                        context, sys_prompt, tools_enabled=False
                    ):
                        llm_text += chunk
                        self.chat_chunk.emit(chunk.replace("\n", "\n│ "))

                    context += f"\nAssistant ({step_name}): {llm_text}\n"
                    self.chat_append.emit("\n", "#ffffff")

                # --- TOOL-ENABLED PHASE (REACT LOOP) ---
                else:
                    react_step = 0
                    while react_step < self.state.max_steps and self.state.running:
                        self.status_update.emit(
                            f"Reasoning ({react_step+1}/{self.state.max_steps})..."
                        )
                        self.chat_append.emit(
                            f"├─[{step_name}]\n│ ", "#00ff00"
                        )  # Green for action

                        llm_text = ""
                        for chunk in self.stream_llm(
                            context, sys_prompt, tools_enabled=True
                        ):
                            llm_text += chunk
                            self.chat_chunk.emit(chunk.replace("\n", "\n│ "))

                        context += f"\nAssistant: {llm_text}\n"

                        # Parse tools
                        tool_calls = re.findall(
                            r"\[TOOL:\s*([a-zA-Z_]+)\((.*?)\)\]", llm_text
                        )

                        if not tool_calls:
                            break  # No tools called, loop finished

                        observation_text = ""
                        for func_name, args_raw in tool_calls:
                            args = re.findall(r'[\'"](.*?)[\'"]', args_raw)
                            args_display = ", ".join([f"'{a}'" for a in args])

                            ts = f"[{time.time()%1000:.2f}]"
                            self.log_append.emit(
                                f"{ts} [EXEC] {func_name}({args_display})", "#ffff00"
                            )

                            if func_name in self.state.tools:
                                try:
                                    res = self.state.tools[func_name]["func"](*args)
                                except Exception as e:
                                    res = f"Error executing tool {func_name}: {e}"
                            else:
                                res = f"Error: Unknown tool '{func_name}'"

                            self.log_append.emit(f"{res}\n", "#00e5ff")
                            observation_text += f"\n[Observation: {func_name}({args_display}) returned:\n{res}\n]\n"
                            self.chat_append.emit(
                                f"\n├─[System] ⚙️ Executing {func_name}({args_display})\n",
                                "#ffff00",
                            )

                        context += observation_text
                        react_step += 1

                    if react_step >= self.state.max_steps:
                        self.chat_append.emit(
                            "\n├─[System] ⚠ Max steps reached.", "#ff0000"
                        )
                        self.log_append.emit(
                            f"[{time.time()%1000:.2f}] [WARN] Max steps reached.",
                            "#ff0000",
                        )

            # Close out the conversation tree after all phases complete
            self.chat_append.emit(
                "\n╰────────────────────────────────────────\n\n", "#6c7883"
            )
            self.status_update.emit("Awaiting Input")

    def stream_llm(self, prompt_context: str, system_prompt: str, tools_enabled: bool):
        # Inject tool descriptions ONLY if tools are enabled for this step
        if tools_enabled and self.state.tools:
            tool_descriptions = "\n".join(
                [f"- {name}: {data['desc']}" for name, data in self.state.tools.items()]
            )
            full_system_prompt = (
                f"{system_prompt}\n\nAVAILABLE TOOLS:\n{tool_descriptions}"
            )
            stop_sequences = ["[Observation:"]
        else:
            full_system_prompt = system_prompt
            stop_sequences = []  # Let it generate freely without stopping for tools

        payload = json.dumps(
            {
                "model": self.state.model,
                "prompt": prompt_context,
                "system": full_system_prompt,
                "stream": True,
                "stop": stop_sequences,
            }
        ).encode("utf-8")

        req = urllib.request.Request(
            self.state.backend,
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


# ==========================================
# UI COMPONENTS (Unchanged from previous)
# ==========================================


class TerminalConsole(QTextEdit):
    def __init__(self, title=""):
        super().__init__()
        self.setReadOnly(True)
        self.setStyleSheet(
            "QTextEdit { background-color: #0d1117; color: #c9d1d9; border: none; padding: 10px; selection-background-color: #264f78; }"
        )
        self.setFont(QFont("Consolas", 11))
        if title:
            self.append_text(f"--- {title} ---\n\n", "#6c7883")

    def append_text(self, text, color_hex="#c9d1d9"):
        self.moveCursor(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QBrush(QColor(color_hex)))
        self.textCursor().insertText(text, fmt)
        self.ensureCursorVisible()

    def stream_text(self, text):
        self.moveCursor(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QBrush(QColor("#c9d1d9")))
        self.textCursor().insertText(text, fmt)
        self.ensureCursorVisible()


class DashboardHeader(QFrame):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.setStyleSheet(
            "background-color: #161b22; border-bottom: 2px solid #30363d;"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)

        form_layout = QFormLayout()
        input_style = "background-color: #0d1117; color: #58a6ff; border: 1px solid #30363d; font-family: Consolas; padding: 2px;"

        self.model_input = QLineEdit(self.state.model)
        self.model_input.setStyleSheet(input_style)
        self.model_input.textChanged.connect(self.update_model)

        self.backend_input = QLineEdit(self.state.backend)
        self.backend_input.setStyleSheet(input_style)
        self.backend_input.textChanged.connect(self.update_backend)

        form_layout.addRow(
            QLabel("<font color='#8b949e' face='Consolas'>MODEL:</font>"),
            self.model_input,
        )
        form_layout.addRow(
            QLabel("<font color='#8b949e' face='Consolas'>API_URL:</font>"),
            self.backend_input,
        )
        layout.addLayout(form_layout)
        layout.addStretch()

        self.status_label = QLabel(
            f"<font color='#3fb950' face='Consolas'>[STATUS: {self.state.status}]</font>"
        )
        layout.addWidget(self.status_label)

    def update_model(self, text):
        self.state.model = text

    def update_backend(self, text):
        self.state.backend = text

    def set_status(self, text):
        color = "#3fb950" if text == "Awaiting Input" else "#d29922"
        self.status_label.setText(
            f"<font color='{color}' face='Consolas'>[STATUS: {text}]</font>"
        )


class CLIInput(QLineEdit):
    def __init__(self):
        super().__init__()
        self.setStyleSheet(
            "QLineEdit { background-color: #0d1117; color: #ffffff; border: none; border-top: 1px solid #30363d; padding: 10px; font-family: Consolas; font-size: 12pt; }"
        )


class MainWindow(QMainWindow):
    def __init__(self, state: AppState, task_queue: queue.Queue):
        super().__init__()
        self.state = state
        self.task_queue = task_queue
        self.setWindowTitle("SimCode Agent CLI")
        self.resize(1200, 800)
        self.setStyleSheet("background-color: #0d1117;")

        self.central = QWidget()
        self.setCentralWidget(self.central)
        self.main_layout = QHBoxLayout(self.central)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setStyleSheet(
            "QSplitter::handle { background-color: #30363d; width: 2px; }"
        )

        self.log_console = TerminalConsole("SYSTEM & TOOL LOGS")
        self.right_pane = QWidget()
        self.right_layout = QVBoxLayout(self.right_pane)
        self.right_layout.setContentsMargins(0, 0, 0, 0)
        self.right_layout.setSpacing(0)

        self.dashboard = DashboardHeader(self.state)
        self.agent_console = TerminalConsole("AGENT REASONING CLI")

        self.input_container = QWidget()
        self.input_container.setStyleSheet(
            "background-color: #0d1117; border-top: 1px solid #30363d;"
        )
        self.input_layout = QHBoxLayout(self.input_container)
        self.input_layout.setContentsMargins(10, 0, 10, 0)

        self.prompt_label = QLabel(
            "<font color='#ff7b72' face='Consolas' size='4'>❯</font>"
        )
        self.cli_input = CLIInput()
        self.cli_input.returnPressed.connect(self.submit_command)

        self.input_layout.addWidget(self.prompt_label)
        self.input_layout.addWidget(self.cli_input)
        self.right_layout.addWidget(self.dashboard)
        self.right_layout.addWidget(self.agent_console)
        self.right_layout.addWidget(self.input_container)

        self.splitter.addWidget(self.log_console)
        self.splitter.addWidget(self.right_pane)
        self.splitter.setSizes([400, 800])
        self.main_layout.addWidget(self.splitter)

        self.agent_thread = AgentThread(self.state, self.task_queue)
        self.agent_thread.chat_append.connect(self.agent_console.append_text)
        self.agent_thread.chat_chunk.connect(self.agent_console.stream_text)
        self.agent_thread.log_append.connect(self.log_console.append_text)
        self.agent_thread.status_update.connect(self.dashboard.set_status)
        self.agent_thread.start()

        tool_names = list(self.state.tools.keys())
        self.log_console.append_text(
            f"[{time.time()%1000:.2f}] [INIT] OS Tools Bound: {tool_names}\n\n",
            "#79c0ff",
        )
        self.agent_console.append_text(
            "╭─[System] Agent Ready. Start by typing a command below.\n╰────────────────────────────────────────\n\n",
            "#8b949e",
        )

    def submit_command(self):
        text = self.cli_input.text().strip()
        if not text:
            return
        self.agent_console.append_text(f"╭─❯ {text}\n", "#ff7b72")
        self.task_queue.put(text)
        self.cli_input.clear()

    def closeEvent(self, event):
        self.state.running = False
        super().closeEvent(event)


# ==========================================
# PUBLIC API (LIBRARY INTERFACE)
# ==========================================


class AgentApp:
    def __init__(self):
        self.state = AppState()
        self.task_queue = queue.Queue()

    def set_config(self, backend: str, model: str, max_steps: int = 8):
        self.state.backend = backend
        self.state.model = model
        self.state.max_steps = max_steps
        return self

    def add_tool(self, name: str, description: str, func: callable):
        self.state.tools[name] = {"func": func, "desc": description}
        return self

    def _load_prompt(self, prompt_source: str) -> str:
        if os.path.exists(prompt_source):
            with open(prompt_source, "r", encoding="utf-8") as f:
                return f.read()
        return prompt_source

    def create_step_precondition(
        self, prompt_source: str, enable_tool_use: bool = False
    ):
        """Adds a preparatory step. Tools are disabled so the agent can think/plan without OS side effects."""
        prompt = self._load_prompt(prompt_source)
        self.state.pipeline.append(
            {"name": "Plan", "prompt": prompt, "enable_tool_use": enable_tool_use}
        )
        return self

    def create_step(self, prompt_source: str, enable_tool_use: bool = True):
        """Adds an execution step. If tools are enabled, this triggers the ReAct loop."""
        prompt = self._load_prompt(prompt_source)
        self.state.pipeline.append(
            {"name": "Execute", "prompt": prompt, "enable_tool_use": enable_tool_use}
        )
        return self

    def run(self):
        if not self.state.pipeline:
            print("Error: No steps created. Add at least one step before running.")
            sys.exit(1)

        app = QApplication(sys.argv)
        window = MainWindow(self.state, self.task_queue)
        window.show()
        window.cli_input.setFocus()
        sys.exit(app.exec())
