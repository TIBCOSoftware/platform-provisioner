# Platform Automation Hub

## Overview

**Platform Automation Hub** is a comprehensive automation platform for cloud platform provisioning, configuration, deployment, and lifecycle management. Born from the need to streamline repetitive post-installation tasks, it has evolved into a powerful tool that dramatically improves productivity for developers, testers, and platform administrators.

This unified hub provides both **GUI-driven automation** and **CLI commands**, enabling teams to automate complex workflows with a single click or integrate automation into CI/CD pipelines.

---

## Core Capabilities

### 🔐 **User & Authentication Management**
- Automated user activation via mail server integration
- Subscription creation and permission assignment
- OAuth token generation and Kubernetes secret management
- Support for admin and regular user workflows

### ☁️ **DataPlane Lifecycle Management**
- **Kubernetes DataPlanes**
  - Create, configure, and delete DataPlanes
  - Automated helm chart execution
  - Service account creation with custom settings
  - Storage class and ingress controller provisioning

- **Control Tower DataPlanes (BMDP)**
  - Business Monitoring DataPlane deployment
  - BW5 domain management (RVDM, EMSDM, BW6DM, EMS Server)
  - Automated activation server integration

### 📊 **Observability Configuration**
- Global observability setup (Logs, Metrics, Traces)
- DataPlane-level observability configuration
- Link DataPlanes to global observability system
- Widget dashboard configuration for Kubernetes and Control Tower
- **Business Activities configuration** - Monitor business processes in real-time
- **In-Product activation** - Configure activation URL for license management
- Test connection validation for observability endpoints

### 🚀 **Capability Provisioning**
Automatically provision platform capabilities:
- **BWCE (BusinessWorks Container Edition)** - BW6
- **BW5CE (BusinessWorks 5 Container Edition)** - BW5
- **Flogo** - Lightweight microservices
- **EMS** - Enterprise Message Service
- **Pulsar** - Event streaming
- **TibcoHub** - Integration hub

### 📦 **Application Deployment & Management**
- **Build & Deploy Applications**
  - Upload custom or use default application files
  - Support for BWCE (.ear), BW5CE (.ear), and Flogo (.json, .flogo) apps
  - Automated build, deploy, and start workflows
  - Environment variable configuration
  - Endpoint visibility settings (public/private)
  - Swagger API testing and validation

- **Application Lifecycle**
  - Start, stop, and delete applications
  - Monitor application status
  - Trace verification for deployed apps

### 🖥️ **CLI Integration**
Comprehensive Platform CLI integration with object-oriented architecture:

- **DataPlane Operations**
  - List all DataPlanes (Kubernetes & Control Tower)
  - Register K8s DataPlanes with automated service account creation
  - Register Control Tower DataPlanes (BMDP)
  - Unregister DataPlanes with cleanup

- **Resource Management**
  - Create and manage Storage resources
  - Create and manage Ingress resources
  - Configure Activation License File resource
  - List and delete resource instances

- **Capability Management**
  - Provision capabilities: BWCE, BW5CE, Flogo, DevHub
  - Automatic version provisioning
  - Storage and ingress resource auto-creation
  - List available capabilities and versions

- **Application Lifecycle**
  - List all deployed applications
  - Build and deploy apps (BWCE, BW5CE, Flogo)
  - All-in-one workflows or step-by-step CLI commands
  - Delete applications with cleanup
  - Advanced Mode toggle for granular control

- **Settings & Persistence**
  - One-click save to browser localStorage
  - Persistent CP URL and OAuth token storage
  - Custom command flags support
  - Visual feedback on save

### 🔗 **API Integration**
- Built-in `/cp_api` endpoint for calling Control Plane APIs directly from UI
- Support for GET, POST, DELETE HTTP methods
- Automatic authentication with Bearer token
- Real-time API testing and exploration

---

## Dual Interface

### GUI Automation Tab
- **Visual workflow execution** with real-time log streaming
- **Form-based configuration** with smart field hiding/showing
- **Progress indicators** and status tracking
- **File upload support** for application deployments
- **Run in browser mode** for debugging (headful Playwright)
- **Force run automation** to skip prerequisite checks

### CLI Commands Tab
- **Comprehensive CLI execution** without leaving the browser
- **Token-based authentication** (OAuth token from CP Settings)
- **One-click save** for CP URL and token to localStorage
- **Advanced Mode toggle** - Switch between all-in-one workflows and granular CLI commands
- **Streaming output** for long-running commands
- **Resource auto-creation** - Automatically creates storage/ingress if not specified
- **Deploy configuration editor** - JSON payload editor with syntax highlighting
- **Multiple capability support** - Provision multiple capabilities simultaneously

---

## Advanced Features

### 🎯 **Intelligent Automation**
- **Conditional field display** - Shows only relevant fields based on selected automation case
- **Auto-population** - Pre-fills activation server details from CP API
- **Multi-window support** - Run parallel tasks in different browser tabs
- **Background execution** - Continue working while automation runs
- **Smart CLI workflows** - Advanced Mode reveals individual steps or hides complexity
- **Dynamic form updates** - Context-aware field visibility and validation

### 🛡️ **Error Handling & Debugging**
- **Step-by-step logging** with color-coded output (success, error, warning, info)
- **Screenshot capture** on errors for quick troubleshooting
- **Playwright trace recording** with Trace Viewer support
- **Video recording** of automation sessions
- **Detailed error messages** with actionable context

### 🔄 **Version Compatibility**
- Compatible with CP 1.3, 1.4, 1.5, 1.6, 1.7+
- Adaptive UI automation that handles platform upgrades
- Support for both on-premises and cloud deployments
- Backward compatibility with older CP versions

### 🌐 **Environment Flexibility**
- **Custom KUBECONFIG** support for multi-cluster management
- **Local development mode** with source code execution
- **Container deployment** via Docker/Kubernetes
- **GCP and cloud instance** connectivity
- **Mail server integration** with customizable endpoints

---

## Key Benefits

### ⚡ **Increased Efficiency**
Transform hours of manual configuration into minutes of automated execution. What previously required multiple UI clicks, CLI commands, and context switches now happens with a single button press.

### ✅ **Enhanced Reliability**
Eliminate human error from repetitive tasks. Automated workflows ensure consistent, reproducible configurations across all environments.

### 🔧 **Developer-Friendly**
- **Zero configuration** for standard deployments
- **Extensive customization** for advanced use cases
- **Real-time feedback** with streaming logs
- **Easy debugging** with browser mode and trace viewer

### 🧪 **Testing & Validation**
- Serves as **end-to-end test suite** covering major platform workflows
- **Pytest-based E2E tests** with parallel execution
- **Swagger API validation** for deployed applications
- **Observability verification** with trace checking

### 📚 **Comprehensive Documentation**
- Built-in tooltips and help text
- Links to official platform documentation
- Changelog tracking all features and fixes
- Example recipes for common scenarios

---

## Use Cases

### For Platform Administrators
- Rapidly deploy and configure new DataPlanes
- Set up observability infrastructure across the platform
- Manage user subscriptions and permissions
- Monitor platform health through integrated dashboards

### For Application Developers
- Quick provisioning of development environments
- Deploy and test applications with one click
- Validate observability integration (logs, metrics, traces)
- Iterate rapidly with automated build-deploy-test cycles

### For QA/Testers
- Automated environment setup for testing
- Consistent test data and configuration
- Parallel test execution across multiple DataPlanes
- Comprehensive test coverage with E2E suite

### For DevOps/SRE Teams
- CI/CD pipeline integration via CLI commands
- Infrastructure-as-code support with recipe files
- Multi-environment management with custom kubeconfig
- Automated troubleshooting with built-in diagnostics

---

## Platform Architecture

The Platform Automation Hub operates on a **Recipe and Pipeline** model with object-oriented CLI integration:
- **Recipes** (YAML) define what to provision
- **Pipelines** (Bash/Python) define how to execute
- **Web UI** provides visual interface and real-time feedback
- **Backend** uses Playwright for browser automation and kubectl for cluster operations
- **CLI Layer** - Object-oriented architecture with facade pattern:
  - `cli_object/base.py` - Base CLI wrapper with authentication
  - `cli_object/dataplane.py` - DataPlane operations (K8s & Control Tower)
  - `cli_object/resource.py` - Resource management (Storage, Ingress, Activation)
  - `cli_object/capability.py` - Capability provisioning with auto-resource creation
  - `cli_object/app.py` - Application lifecycle management
  - `cli_object/bwce.py`, `cli_object/bw5ce.py`, `cli_object/flogo.py` - App-specific workflows
  - `cli_object/facade.py` - High-level workflow orchestration
  - `cli_object/api.py` - CP API client for data fetching

---

## Getting Started

1. **Access the Hub**
   - Installed with CP: `https://automation.localhost.dataplanes.pro/`
   - Run from source: `./run-auto.sh` (requires Python 3.13+, uv)

2. **Select Your Task**
   - Choose from 25+ pre-built automation cases
   - Configure environment variables as needed
   - Click "Run Automation" and monitor progress

3. **Review Results**
   - Real-time console output with syntax highlighting
   - HTML reports with screenshots
   - Playwright traces for debugging
   - Video recordings of automation sessions

---

## Future Vision

Platform Automation Hub continues to evolve with:
- More automation cases for emerging CP features
- AI-assisted automation with intelligent error recovery
- Enhanced MCP (Model Context Protocol) server integration
- Cross-platform support (Azure, AWS, GCP)
- Custom automation recipe builder
