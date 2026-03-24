# Contributing to Platform Provisioner

Thank you for your interest in contributing to Platform Provisioner by TIBCO®!

## How to Contribute

### Reporting Issues

- Use [GitHub Issues](https://github.com/TIBCOSoftware/platform-provisioner/issues) to report bugs or request features.
- Search existing issues before creating a new one to avoid duplicates.
- Include steps to reproduce, expected behavior, and environment details.

### Submitting Changes

1. Fork the repository.
2. Create a feature branch from `main` (`git checkout -b feature/my-change`).
3. Make your changes following the coding conventions below.
4. Test your changes locally using the headless mode:
   ```bash
   export PIPELINE_INPUT_RECIPE="docs/recipes/tests/test-container-binaries.yaml"
   ./dev/platform-provisioner.sh
   ```
5. Commit with a clear, descriptive message.
6. Push to your fork and open a Pull Request against `main`.

### Coding Conventions

- **Bash Scripts**: Use `set -euo pipefail` where appropriate. Keep scripts readable and well-commented.
- **YAML Recipes**: Follow the existing recipe schema defined by CUE files in `charts/*/scripts/*.cue`.
- **Helm Charts**: Follow standard Helm chart conventions.
- **License Headers**: All source files must include the Apache 2.0 license header:
  ```
  Copyright 2025 Cloud Software Group, Inc.

  Licensed under the Apache License, Version 2.0 (the "License");
  you may not use this file except in compliance with the License.
  You may obtain a copy of the License at

      http://www.apache.org/licenses/LICENSE-2.0
  ```

### Pull Request Guidelines

- Keep PRs focused — one change per PR.
- Reference any related issues in the PR description.
- Ensure all CI checks pass before requesting review.
- Update documentation if your change affects user-facing behavior.

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to uphold this code.

## License

By contributing, you agree that your contributions will be licensed under the [Apache License 2.0](LICENSE).
