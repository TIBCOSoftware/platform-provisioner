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
import contextlib
import io
import queue
import threading
from typing import cast, IO

class StreamingRunner(io.TextIOBase):
    def __init__(self):
        self.q = queue.Queue()

    def write(self, data: str) -> int:
        for line in data.splitlines():
            if line.strip():
                self.q.put(line)
        return len(data)

    def flush(self) -> None:
        pass

    @property
    def encoding(self) -> str:
        return 'utf-8'

    def run(self, func, *args, **kwargs):
        """Run func(*args, **kwargs), capture stdout, put into queue."""
        with contextlib.redirect_stdout(cast(IO[str], self)):
            try:
                result = func(*args, **kwargs)
                if result is not None:
                    # Only show return value if it's not empty/whitespace
                    result_str = str(result).strip()
                    if result_str:
                        self.q.put(f"=== Return Value ===")
                        self.q.put(result_str)
            except Exception as e:
                self.q.put(f"[ERROR]: {repr(e)}")
            finally:
                self.q.put(None)

    def start_thread(self, func, *args, **kwargs):
        """Start func(*args, **kwargs) in background thread."""
        t = threading.Thread(target=self.run, args=(func,) + args, kwargs=kwargs)
        t.start()
        return t  # Optionally return thread object
