#
# Copyright 2025 Cloud Software Group, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
from colorama import Fore, Style, init

# Initialize colorama for cross-platform support
init(autoreset=True)

class ColorLogger:
    @staticmethod
    def info(message):
        print(f"{Fore.LIGHTBLUE_EX}[INFO] {message}")

    @staticmethod
    def success(message):
        print(f"{Fore.GREEN}[SUCCESS] {message}")

    @staticmethod
    def warning(message):
        print(f"{Fore.YELLOW}[WARNING] {message}")

    @staticmethod
    def error(message):
        print(f"{Fore.RED}[ERROR] {message}")

    @staticmethod
    def debug(message):
        print(f"{Fore.CYAN}[DEBUG] {message}")

    @staticmethod
    def critical(message):
        print(f"{Fore.MAGENTA}[CRITICAL] {message}")

    @staticmethod
    def custom(message, color):
        """
        Print a custom-colored message.
        :param message: The message to print.
        :param color: The color from `colorama.Fore` (e.g., Fore.BLUE).
        """
        print(f"{color}{message}{Style.RESET_ALL}")
