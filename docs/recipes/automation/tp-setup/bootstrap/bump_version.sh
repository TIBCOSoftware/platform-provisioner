#!/bin/bash
#
# Copyright (c) 2025. Cloud Software Group, Inc. All Rights Reserved. Confidential & Proprietary
#

# Move to the project root directory
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(dirname "$(dirname "$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")")")
cd "$PROJECT_ROOT" || { echo "❌ Failed to change to project root directory."; exit 1; }

echo "📂 Now in project root: $PROJECT_ROOT"

# Define file paths
CHART_FILE="charts/provisioner-config-local/Chart.yaml"
VERSION_FILE="docs/recipes/automation/tp-setup/bootstrap/version.txt"

# Ensure Chart.yaml exists
if [ ! -f "$CHART_FILE" ]; then
  echo "❌ Error: Chart file not found at $CHART_FILE"
  exit 1
fi

# Read the current version from Chart.yaml
current_version=$(grep '^version:' "$CHART_FILE" | awk '{print $2}' | tr -d '"')

# Validate version format (must be X.Y.Z)
if ! [[ "$current_version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "❌ Error: Current version ($current_version) is not in valid format (X.Y.Z)"
  exit 1
fi

# Split prefix and patch
prefix=$(echo "$current_version" | awk -F. '{print $1"."$2}')
patch=$(echo "$current_version" | awk -F. '{print $3}')

# Increment patch version
new_patch=$((patch + 1))
new_version="${prefix}.${new_patch}"
# use current time for new_ui_version
new_ui_version="$(date '+%m/%d/%Y %H:%M')"
#new_ui_version="$(git log -1 --pretty=format:"%h" .)"

echo "Current version: $current_version"
echo "New version: $new_version"

# Update Chart.yaml safely
# Use a temp file for compatibility across Linux, macOS, Git Bash
tmp_file=$(mktemp)
awk -v new_version="$new_version" '
  /^version:/ {$0 = "version: \"" new_version "\""}
  {print}
' "$CHART_FILE" > "$tmp_file" && mv "$tmp_file" "$CHART_FILE"

# Update version.txt
mkdir -p "$(dirname "$VERSION_FILE")"
echo "$new_ui_version" > "$VERSION_FILE"

echo "✅ Successfully updated:"
echo "- $CHART_FILE with version: $new_version"
echo "- $VERSION_FILE with version: $new_ui_version"
