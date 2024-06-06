package recipe

// Copyright © 2024. Cloud Software Group, Inc.
// This file is subject to the license terms contained
// in the license file that is distributed with this file.

// the version of recipe
apiVersion?: string | *"v1"
// pipeline name
kind?: string | *"generic-runner"
// the meta data for the recipe
meta?: #meta
// must have at least one task
tasks!: [#task, ...#task]
