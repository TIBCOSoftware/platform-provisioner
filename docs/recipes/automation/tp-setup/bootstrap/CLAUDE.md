# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TIBCO Platform Automation Bootstrap is a comprehensive browser automation and testing framework for TIBCO Control Plane (TP/CP). It provides:

1. **Web UI Server**: Flask-based one-click configuration interface
2. **Playwright Automation**: Browser automation using Page Object Model pattern
3. **Test Suite**: pytest-based E2E tests with parallel execution support
4. **CLI Integration**: tibcop CLI wrapper for DataPlane operations

**Primary Use Cases:**
- Post-installation configuration of TIBCO Control Plane
- Automated testing of CP features (user management, DataPlane operations, observability, app deployment)
- One-click setup for development/testing environments

## Development Setup

### Initial Setup
```bash
# Install uv (Python package manager)
curl -fsSL https://uv.io/install.sh | sh  # Mac/Linux
# or: scoop install main/uv  # Windows

# Install dependencies
cd docs/recipes/automation/tp-setup/bootstrap
uv sync
uv run playwright install

# Set Python path for IDE (IntelliJ IDEA)
# Right-click folder -> Mark Directory as -> Sources Root
```

### Run Web Server (Local Development)
```bash
# Run from source (recommended)
export TP_AUTO_TASK_FROM_LOCAL_SOURCE=true
export TP_AUTO_KUBECONFIG=~/.kube/config  # Optional: custom kubeconfig
./run-server.sh
# Access: http://127.0.0.1:3120/

# Or run directly with uv
uv run python -m waitress --host=127.0.0.1 --port=3120 server:app
```

### Run Automation Cases (Standalone)
```bash
# Run individual case (headful mode - shows browser)
export HEADLESS="false"
python -u -m case.k8s_config_dp_o11y

# Run with custom credentials
export DP_HOST_PREFIX="cp-sub1"
export DP_USER_EMAIL="cp-sub1@tibco.com"
export DP_USER_PASSWORD="Tibco@123"
export CP_ADMIN_EMAIL="cp-test@tibco.com"
export CP_ADMIN_PASSWORD="Tibco@123"
python -u -m case.k8s_create_dp
```

### Debug Automation Scripts

All `page_*.py` scripts can be debugged using Python debugger:

```bash
# Run with debugger
export HEADLESS="false" \
       DP_USER_EMAIL="cp-sub1@tibco.com" \
       DP_USER_PASSWORD="Tibco@123" && \
uv run python -m pdb page_dp.py

# Set breakpoint at specific line
(Pdb) b page_object/po_dp_config.py:160
(Pdb) c

# Inspect page HTML at runtime
(Pdb) html = self.page.content()
(Pdb) print([line for line in html.split('\n') if 'your-keyword' in line])
```

**Tip**: Always verify DOM selectors by inspecting `self.page.content()` instead of guessing.

### Run E2E Tests
```bash
# Single test with HTML report
export HEADLESS="false"
pytest -v --tb=long --html=report/report.html --self-contained-html \
  e2e/dataplane/configuration/o11y/test_test_connection_button.py

# All tests in parallel (auto-detect CPU cores)
pytest -n auto -v --tb=long --dist=loadfile \
  --html=report/report.html --self-contained-html e2e/**/*.py

# Rerun last failed tests only
pytest --lf
```

### Docker Deployment
```bash
# Run in Docker container (uses platform-provisioner pipeline)
export PIPELINE_FAIL_STAY_IN_CONTAINER=true  # Optional: debug mode
export PIPELINE_INPUT_RECIPE=server-recipe.yaml
./run-server.sh
```

### Build & Publish Docker Image
```bash
# Update version
./bump_version.sh  # Updates version.txt and related YAML files

# Build and push (via GitHub Actions)
# Go to: https://github.com/tibco/platform-provisioner/actions/workflows/docker-image-ghcr-build-push-public.yml
# Set: image tag = 1.x.x-auto-on-prem-jammy, branch = your_branch_name
```

## Architecture

### Directory Structure
```
bootstrap/
├── server.py              # Flask web server (main entry point)
├── page_*.py              # High-level automation scripts (legacy structure)
├── page_object/           # Page Object Model classes (core automation)
│   ├── po_auth.py         # Authentication (login, user activation)
│   ├── po_dataplane.py    # DataPlane create/delete/navigate
│   ├── po_dp_config.py    # DataPlane config (storage, ingress, o11y)
│   ├── po_dp_bwce.py      # BWCE app provisioning & deployment
│   ├── po_dp_flogo.py     # Flogo app provisioning & deployment
│   ├── po_bmdp_config.py  # Business Monitoring DataPlane (Control Tower)
│   ├── po_o11y.py         # Global observability configuration
│   └── po_settings.py     # System settings & OAuth token
├── case/                  # Standalone automation cases
│   ├── k8s_*.py           # Kubernetes DataPlane cases
│   └── bmdp_*.py          # Business Monitoring DataPlane cases
├── e2e/                   # pytest E2E test suite
│   ├── conftest.py        # pytest fixtures and configuration
│   ├── dataplane/         # DataPlane-related tests
│   └── observability/     # Observability tests
├── utils/                 # Utility modules
│   ├── env.py             # Environment configuration (ENV dataclass)
│   ├── util.py            # Browser utilities (launch, screenshot, trace)
│   ├── helper.py          # Shell command helpers
│   ├── streaming_runner.py # Stream script output to web UI
│   ├── tibcop_cli.py      # tibcop CLI wrapper
│   └── report.py          # YAML report generation
├── templates/             # Flask HTML templates
├── static/                # Web UI static assets (CSS, JS)
└── upload/                # Application file uploads
```

### Key Design Patterns

**1. Page Object Model (POM)**
- Each page/section has a corresponding `po_*.py` class
- Encapsulates page interactions (locators, actions, validations)
- Example: `po_dataplane.py` handles DataPlane list, create, delete, navigation

**2. Environment Configuration**
- `utils/env.py` - Single source of truth for all environment variables
- `ENV` dataclass with frozen attributes
- Auto-detects CP version, cluster accessibility
- Default values with `os.getenv()` fallbacks

**3. Streaming Execution**
- `utils/streaming_runner.py` - Runs Python scripts with real-time output streaming
- Used by Flask server to show live progress in Web UI
- Captures stdout/stderr and streams via SSE (Server-Sent Events)

**4. Layered Automation**
- **Level 1**: `page_object/*.py` - Low-level page interactions
- **Level 2**: `case/*.py` - End-to-end automation workflows (compose page objects)
- **Level 3**: `e2e/*.py` - pytest tests with assertions (validate workflows)

### Critical Files

**Configuration & Constants:**
- `utils/env.py:EnvConfig` - All environment variables and defaults
- `server-recipe.yaml` - Recipe for running automation in Docker (generic-runner pipeline)
- `pyproject.toml` - Python dependencies and project metadata

**Web Server:**
- `server.py` - Flask routes, SSE streaming, CP API proxy
- `templates/index.html` - Web UI interface (forms, buttons, output display)

**Core Automation:**
- `page_object/po_auth.py` - Login, activate users, get OAuth token
- `page_object/po_dataplane.py` - Create/delete DataPlane, navigate to DataPlane
- `page_object/po_dp_config.py` - Configure storage, ingress, observability (logs/metrics/traces)

**Utilities:**
- `utils/util.py:Util.browser_launch()` - Initialize Playwright browser with DNS resolution, tracing, video recording
- `utils/helper.py:Helper` - Shell commands, kubectl operations, CP version detection

## Important Workflows

### User Activation & Login
```python
from page_object.po_auth import PageObjectAuth

po_auth = PageObjectAuth(page)
po_auth.active_admin_user()      # Activate admin via maildev
po_auth.create_regular_user()    # Create regular user
po_auth.active_regular_user()    # Activate via maildev
po_auth.login()                   # Login as regular user
```

### Create DataPlane with Observability
```python
from page_object.po_dataplane import PageObjectDataPlane
from page_object.po_dp_config import PageObjectDataPlaneConfiguration

po_dp = PageObjectDataPlane(page)
po_dp.k8s_create_dataplane("k8s-auto-dp1")

po_dp_config = PageObjectDataPlaneConfiguration(page)
po_dp_config.dp_config_resources_storage("k8s-auto-dp1")
po_dp_config.dp_config_resources_ingress("k8s-auto-dp1", ...)
po_dp_config.o11y_config_switch_to_global("k8s-auto-dp1")
po_dp_config.o11y_config_activation("k8s-auto-dp1")
```

### Deploy Flogo Application
```python
from page_object.po_dp_flogo import PageObjectDataPlaneFlogo

po_flogo = PageObjectDataPlaneFlogo(page)
po_flogo.flogo_provision_capability("k8s-auto-dp1")
po_flogo.flogo_provision_connector("k8s-auto-dp1", "flogo-app")
po_flogo.flogo_app_build_and_deploy("k8s-auto-dp1", "app.json", "flogo-app")
po_flogo.flogo_app_deploy("k8s-auto-dp1", "flogo-app")
po_flogo.flogo_app_start("k8s-auto-dp1", "flogo-app")
```

## Environment Variables

### Essential Variables
```bash
# Cluster & Kubeconfig
TP_AUTO_KUBECONFIG=~/.kube/config  # Custom kubeconfig path

# User Credentials
DP_HOST_PREFIX=cp-sub1             # Host prefix (e.g., cp-sub1.domain.com)
DP_USER_EMAIL=user@example.com     # Regular user email
DP_USER_PASSWORD=Tibco@123         # Regular user password
CP_ADMIN_EMAIL=admin@example.com   # Admin email
CP_ADMIN_PASSWORD=Tibco@123        # Admin password

# Browser Behavior
HEADLESS=false                     # Show browser (true for headless)

# Feature Flags (case/*.py scripts)
TP_AUTO_IS_CREATE_DP=true          # Create K8S DataPlane
TP_AUTO_IS_PROVISION_FLOGO=true    # Provision Flogo capability
TP_AUTO_IS_PROVISION_BWCE=true     # Provision BWCE capability
TP_AUTO_IS_CONFIG_O11Y=true        # Configure observability

# DataPlane Names
TP_AUTO_K8S_DP_NAME=k8s-auto-dp1   # K8S DataPlane name
TP_AUTO_K8S_BMDP_NAME=k8s-bmdp1    # BMDP (Control Tower) name

# Reporting
TP_AUTO_REPORT_TRACE=true          # Enable Playwright trace
TP_AUTO_REPORT_PATH=./report       # Report output directory

# tibcop CLI (for CLI automation in Web UI)
TIBCOP_CLI_CPURL=https://cp-sub1.cp1-my.localhost.dataplanes.pro  # Control Plane URL
TIBCOP_CLI_OAUTH_TOKEN=<token>        # OAuth token from CP Settings
```

### Advanced Configuration
```bash
# OAuth Token
TP_AUTO_TOKEN_NAMESPACE=automation
TP_AUTO_TOKEN_NAME=auto-token
TP_AUTO_TOKEN_DURATION=3
TP_AUTO_TOKEN_DURATION_UNIT=Months

# Activation Server (for license activation)
TP_ACTIVATION_ZIP_FILE_BASE64=<base64-encoded-zip>
TP_ACTIVATION_SERVER_IP=10.0.0.1
TP_ACTIVATION_SERVER_CERT_HOSTNAME=activation.example.com
TP_ACTIVATION_SERVER_PORT=7070
TP_ACTIVATION_SERVER_FINGER_PRINT=<fingerprint>

# Control Tower (BMDP) BW5 Domain
TP_AUTO_IS_ENABLE_RVDM=true
TP_AUTO_IS_ENABLE_EMSDM=true
TP_AUTO_IS_ENABLE_EMS_SERVER=true
TP_AUTO_IS_ENABLE_BW6DM=true
```

## Testing Conventions

### pytest Configuration
- `pytest.ini` sets `pythonpath = .` for module imports
- Use `conftest.py` for shared fixtures
- Parallel execution: `-n auto --dist=loadfile` distributes by file

### Test Structure
```python
# e2e/dataplane/test_example.py
def test_dataplane_creation(page):  # pytest fixture provides 'page'
    po_dp = PageObjectDataPlane(page)
    po_dp.k8s_create_dataplane("test-dp")
    # Assertions
    assert po_dp.is_dataplane_created("test-dp")
```

### Screenshot & Trace
- Screenshots on error: Auto-captured by Playwright
- Trace: `TP_AUTO_REPORT_TRACE=true` enables trace recording
- Video: Automatically saved to `report/<timestamp>/video.webm`
- Trace viewer: `playwright show-trace trace.zip`

## Common Operations

### Get CP Version
```python
from utils.env import ENV
print(ENV.TP_AUTO_CP_VERSION)  # Auto-detected or from env var
```

### Execute kubectl Command
```python
from utils.helper import Helper
output = Helper.get_command_output("kubectl get pods -n default")
```

### Get OAuth Token
```python
from utils.helper import Helper
token = Helper.get_auto_token()  # Retrieves from k8s secret
```

### Browser Tracing
```python
from utils.util import Util
page = Util.browser_launch()  # Auto-starts tracing if TP_AUTO_REPORT_TRACE=true
# ... perform actions ...
Util.browser_close()  # Saves trace.zip
```

### CP API Calls
```python
# Via Flask server endpoint /cp_api
# GET /cp_api?api_path=/cp/v1/dataplanes&api_method=GET
# Automatically adds Authorization: Bearer <token>
```

## Version Management

### Semantic Versioning
- Format: `1.x.x-auto-on-prem-jammy`
- Update script: `./bump_version.sh`
- Updates:
  - `version.txt`
  - `charts/provisioner-config-local/Chart.yaml`
  - All `*-on-prem.yaml` recipe files

### Changelog
- `CHANGELOG.md` - Track all changes by version
- Format: `## [version] ### Added/Fixed/Changed`

## Troubleshooting

### Browser Launch Issues
- Windows VDI: May need `--single-process` flag (handled automatically)
- DNS resolution: Uses `--host-resolver-rules` if CP domain resolves

### Kubernetes Access
- Check: `ENV.IS_CLUSTER_ACCESSIBLE` (auto-detected via `kubectl cluster-info`)
- Custom kubeconfig: Set `TP_AUTO_KUBECONFIG` or `KUBECONFIG`

### Mail Server (User Activation)
- Default: Uses `maildev` service in cluster
- Port forward if needed: `kubectl port-forward -n mail svc/maildev 1080:80`
- Access: http://localhost:1080

### OAuth Token Issues
```bash
# Retrieve stored token
kubectl get secret auto-token -n automation -o jsonpath="{.data['auto-token']}" | base64 --decode
```

## Code Organization Guidelines

### Adding New Page Objects
1. Create `page_object/po_<feature>.py`
2. Inherit from base class or follow existing pattern
3. Use descriptive method names: `verb_noun()` (e.g., `create_dataplane()`)
4. Include docstrings for complex flows

### Adding New Automation Cases
1. Create `case/<category>_<action>.py`
2. Import required page objects
3. Follow structure: ENV.pre_check() → browser_launch() → page object composition
4. Handle cleanup in try/finally

### Adding E2E Tests
1. Create `e2e/<category>/test_<feature>.py`
2. Use fixtures from `conftest.py`
3. Assert expected outcomes
4. Tag with markers if needed (e.g., `@pytest.mark.slow`)

## Dependencies

**Key Libraries:**
- `playwright==1.54.0` - Browser automation
- `flask-cors==6.0.1` - Web server CORS
- `pytest-xdist==3.8.0` - Parallel test execution
- `pytest-html==4.1.1` - HTML test reports
- `typer==0.16.1` - CLI framework (for tibcop)
- `pydantic==2.11.7` - Data validation

**Development Tools:**
- `uv` - Fast Python package manager (recommended)
- `playwright` CLI - Browser installation (`uv run playwright install`)
