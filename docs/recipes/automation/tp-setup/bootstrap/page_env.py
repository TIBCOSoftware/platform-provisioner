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
import sys
from utils.env import ENV
from utils.color_logger import ColorLogger
from utils.util import Util

if __name__ == "__main__":
    Util.print_cp_info()
    Util.print_env_info()

    output_file = f"{ENV.TP_AUTO_REPORT_PATH}/{ENV.TP_AUTO_REPORT_TXT_FILE}"
    with open(output_file, "w", encoding="utf-8") as f:
        # Redirect stdout to file
        sys.stdout = f
        Util.print_cp_info()  # This output goes to the file
        Util.print_env_info()  # This output goes to the file

        # Restore stdout to terminal
        sys.stdout = sys.__stdout__

    ColorLogger.success(f"Final report information saved to file: {output_file}")
