#  Copyright (c) 2025. Cloud Software Group, Inc. All Rights Reserved. Confidential & Proprietary
"""
TibcopCLI entry point.

Assembles all CLI modules with their dependencies into a single object.
Callers access modules directly: cli.dataplane.xxx(), cli.bwce.xxx(), etc.
"""

import os
import re

from utils.color_logger import ColorLogger
from utils.env import ENV
from utils.helper import Helper

from .base import TibcopBase
from .dataplane import TibcopDataPlane
from .resource import TibcopResource
from .app import TibcopApp
from .capability import TibcopCapability
from .api import TibcopAPI
from .bwce import TibcopBWCE
from .flogo import TibcopFlogo
from .bw5ce import TibcopBW5CE
from .kubectl import TibcopKubectl
from .orchestrator import TibcopOrchestrator


class TibcopCLI:
    """
    Entry point for all tibcop CLI operations.

    Assembles modules with their dependencies. Access via sub-modules:
        cli = TibcopCLI(custom_env)
        cli.dataplane.register_k8s_dataplane(...)
        cli.bwce.build_and_deploy_app(...)
        cli.kubectl.list_cluster_resources(...)
        cli.orchestrator.run_dataplane_setup(...)
    """

    def __init__(self, custom_env=None):
        """
        Initialize all CLI modules.

        Args:
            custom_env: Optional custom environment variables dict
        """
        # Base (shared by all modules)
        self.base = TibcopBase(custom_env)

        # Core modules
        self.dataplane = TibcopDataPlane(self.base)
        self.resource = TibcopResource(self.base)
        self.app = TibcopApp(self.base)

        # Modules with dependencies
        self.api = TibcopAPI(self.base, dataplane=self.dataplane)
        self.capability = TibcopCapability(self.base,
                                          dataplane=self.dataplane,
                                          resource=self.resource)

        # Technology modules
        self.bwce = TibcopBWCE(self.base, api=self.api,
                              capability=self.capability, app=self.app)
        self.flogo = TibcopFlogo(self.base, api=self.api,
                                capability=self.capability, app=self.app)
        self.bw5ce = TibcopBW5CE(self.base, api=self.api,
                                capability=self.capability, app=self.app)

        # Kubectl
        self.kubectl = TibcopKubectl(self.base)

        # Orchestrator
        self.orchestrator = TibcopOrchestrator(self)

    @staticmethod
    def build_env():
        """Build environment dict for TibcopCLI with token and CP URL.

        Returns:
            dict with TIBCOP_CLI_OAUTH_TOKEN and TIBCOP_CLI_CPURL, or None on failure
        """
        custom_env = {}

        # Get OAuth token: env var > k8s secret
        token = os.environ.get("TIBCOP_CLI_OAUTH_TOKEN")
        if not token:
            token = Helper.get_auto_token()
        if token:
            custom_env["TIBCOP_CLI_OAUTH_TOKEN"] = token
        else:
            ColorLogger.error("No OAuth token available. Set TIBCOP_CLI_OAUTH_TOKEN or create token via GUI first.")
            return None

        # Get CP URL: env var > derived from TP_AUTO_LOGIN_URL
        cp_url = os.environ.get("TIBCOP_CLI_CPURL")
        if not cp_url:
            login_url = ENV.TP_AUTO_LOGIN_URL
            if login_url:
                match = re.match(r'^(https?://[^/]+)', login_url)
                if match:
                    cp_url = match.group(1)
        if cp_url:
            custom_env["TIBCOP_CLI_CPURL"] = cp_url
        else:
            ColorLogger.error("No CP URL available. Set TIBCOP_CLI_CPURL or TP_AUTO_LOGIN_URL.")
            return None

        ColorLogger.success(f"CLI environment ready. CP URL: {cp_url}")
        return custom_env

    @classmethod
    def from_env(cls):
        """Create a TibcopCLI instance from environment variables.

        Builds the environment dict (token + CP URL) and returns a configured
        TibcopCLI instance, or None if environment setup fails.

        Returns:
            TibcopCLI instance or None on failure
        """
        custom_env = cls.build_env()
        if not custom_env:
            return None
        return cls(custom_env)
