#pragma once

#include <iostream>
#include <string>
#include <vector>
#include <map>
#include <sstream>
#include <iomanip>
#include <filesystem>
#include <queue>
#include <mutex>
#include <condition_variable>

namespace fs = std::filesystem;

class Terminal {
private:
    std::map<std::string, std::string> log_types;
    std::string model = "qwen3.5:2b";

    // Helper to convert hex string to RGB and return ANSI escape sequence
    std::string hex_to_ansi(std::string hex, const std::string &text)
    {
        int r, g, b;
        std::stringstream ss;

        if (hex[0] == '#')
            hex.erase(0, 1);

        ss << std::hex << hex.substr(0, 2);
        ss >> r;
        ss.clear();
        ss << std::hex << hex.substr(2, 2);
        ss >> g;
        ss.clear();
        ss << std::hex << hex.substr(4, 2);
        ss >> b;

        return "\033[38;2;" + std::to_string(r) + ";" + std::to_string(g) +
               ";" + std::to_string(b) + "m" + text + "\033[0m";
    }

public:
    Terminal()
    {
        log_types = { { "default", "#DCDCDC" },
                      { "comment", "#abb2bf" },
                      { "warning", "#E5C07B" },
                      { "status", "#C678DD" },
                      { "error", "#E06C75" } };
    }

    std::string color_text(const std::string &text,
                           const std::string &type = "default")
    {
        std::string hex =
            log_types.count(type) ? log_types[type] : log_types["default"];
        return hex_to_ansi(hex, text);
    }

    void append_log(const std::string &text,
                    const std::string &type = "default")
    {
        std::cout << color_text(text, type) << std::endl;
    }

    std::string recv_input(void)
    {
        std::string path = fs::current_path().string();
        std::string status = color_text("(" + model + ")", "status");

        std::string result = "";
        std::string line;

        append_log("┌ " + path + " " + status);
        while (true) {
            std::cout << "└─> ";
            if (!std::getline(std::cin, line))
                break;

            // Check for line continuation character '\'
            if (!line.empty() && line.back() == '\\') {
                result += line.substr(0, line.size() - 1) + "\n";
            } else {
                result += line;
                break;
            }
        }
        return result;
    }
};

class Agent {
private:
    Terminal terminal;
    std::queue<std::string> task_queue;

public:
    void run()
    {
        while (true) {
            std::string input = terminal.recv_input();
            if (input == "exit")
                break;

            terminal.append_log("output: " + input);
        }
    }
};
