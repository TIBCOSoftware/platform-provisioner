import sys
from utils.env import ENV
from utils.color_logger import ColorLogger
from utils.util import Util

if __name__ == "__main__":
    Util.print_env_info()

    output_file = f"{ENV.TP_AUTO_REPORT_PATH}/{ENV.TP_AUTO_REPORT_TXT_FILE}"
    with open(output_file, "w") as f:
        # Redirect stdout to file
        sys.stdout = f
        Util.print_env_info()  # This output goes to the file

        # Restore stdout to terminal
        sys.stdout = sys.__stdout__

    ColorLogger.success(f"Final report information saved to file: {output_file}")
