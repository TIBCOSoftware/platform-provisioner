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
"""
TIBCO Platform CLI Objects

Modular CLI handler for TIBCO Platform operations.
Each module handles a specific domain of operations.
"""

from .base import TibcopBase
from .dataplane import TibcopDataPlane
from .resource import TibcopResource
from .app import TibcopApp
from .capability import TibcopCapability
from .api import TibcopAPI
from .bwce import TibcopBWCE
from .flogo import TibcopFlogo
from .bw5ce import TibcopBW5CE
from .orchestrator import TibcopOrchestrator
from .facade import TibcopCLI

__all__ = [
    'TibcopBase',
    'TibcopDataPlane',
    'TibcopResource',
    'TibcopApp',
    'TibcopCapability',
    'TibcopAPI',
    'TibcopBWCE',
    'TibcopFlogo',
    'TibcopBW5CE',
    'TibcopOrchestrator',
    'TibcopCLI',  # Facade for backward compatibility
]

__version__ = '2.0.0'
