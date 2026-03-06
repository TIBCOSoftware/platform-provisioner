#  Copyright (c) 2025. Cloud Software Group, Inc. All Rights Reserved. Confidential & Proprietary
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
