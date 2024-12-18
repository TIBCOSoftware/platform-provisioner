package recipe

// Copyright © 2024. Cloud Software Group, Inc.
// This file is subject to the license terms contained
// in the license file that is distributed with this file.

// we need to define bool as: "true" | "false" | true | false | *"default value"
// the reason is that the GUI might convert bool to string or the bool value might be another varaible that is not boolean
// the underline script to process all these will just use true or false

// supported repo types
#repo: {
	// helm pull --repo ${repo.helm.url} ${name} --version ${version}
	// helm upgrade ... --repo ${repo.helm.url} ...
	// the version will be the chart version
	helm?: {
		url!: string
		username?: string | null
		password?: string | null
	}
	// {repo.ecr.host}/${repo.ecr.name}:${version}
	// The version will be the image tag
	ecr?: {
		name!: string // will be the image name. This name need to match with helmCharts[].name.
		region!: string // helm will use this region to login to
		host!: string
	}
	// git clone ${repo.git.github.repo}
	// cd ${repo.git.github.path} && helm package
	// The version will be the branch or tag name
	git?:{
		// the branch under github in this case will not be used
		github!: #github // The github section is under shared cue.
	}
}

// helm chart part of pipeline
// helm upgrade -i --create-namespace -n ${helmCharts[].namespace} \
// ${helmCharts[].releaseName} ${helmCharts[].name} --version ${helmCharts[].version} \
// --repo ${repo.helm.url}
#helmChart: {
	// This flag provides enables installation or skips installation of single/multiple chart(s) based on flag or condition.
	condition?: "true" | "false" | true | false | *true
	// the name of the helm chart
	name!: string & =~"\\S"
	namespace?: string | *"default"
	// for github the vesion is branch or tag, for helm it is the chart version, for ecr it is the image tag
	version?: string
	// the release name of the helm chart
	releaseName!: string & =~"\\S"
	// ignore the errors during the helm upgrade -i
	ignoreErrors?: "true" | "false" | true | false | *false
	// the version of helm cli to use; encourage to use meta.tools
	helmSettings?:{
		version!: string
	}
	repo: #repo
	values?: {
		// this will get chart values from previous release and apply as base chart values to this new helm upgrade -i
		keepPrevious?: "true" | "false" | true | false | *false
		// if true, content field is expected as base64-encoded string.
		base64Encoded?: "true" | "false" | true | false | *false
		// the content of the values.yaml
		content?: string
	}
	hooks?: {
		// the hook script to run before helm upgrade -i
		preDeploy?: {
			ignoreErrors?: "true" | "false" | true | false | *false
			base64Encoded?: "true" | "false" | true | false | *false
			skip?: "true" | "false" | true | false | *false
			content!: string
		}
		// the hook script to run after helm upgrade -i
		postDeploy?: {
			ignoreErrors?: "true" | "false" | true | false | *false
			base64Encoded?: "true" | "false" | true | false | *false
			skip?: "true" | "false" | true | false | *false
			content!: string
		}
	}
	cluster!: {
		// name of the cluster to deploy the chart
		names!: [string, ...string]
	}
	flags?: {
		// it will turn on debug during Helm deployment/upgrade
		debug?: "true" | "false" | true | false | *false
		// as same as helm upgrade --wait flag
		wait?: "true" | "false" | true | false | *true
		// as same as helm upgrade --timeout flag
		timeout?: string | *"10m"
		// as same as helm upgrade -l, --labels stringToString eg: layer=1
		labels?: string
		// as same as helm upgrade --dry-run flag
		dryRun?: "true" | "false" | true | false | *false
		// as same as helm upgrade --no-hooks flag
		noHooks?: "true" | "false" | true | false | *false
		// as same as helm upgrade --create-namespace flag
		createNamespace?: "true" | "false" | true | false | *false
		// as same as helm upgrade --force flag
		force?: "true" | "false" | true | false | *false
		// customzed pipeline flag; will do diff between the current and the new chart installation. helm get manifest vs helm dry-run
		compare?: "true" | "false" | true | false | *false
		// skip install this chart only run hooks
		skip?: "true" | "false" | true | false | *false
		// this is a string flag and will be appended to helm install command line
		extra?: string
	}
}

// the version of recipe
apiVersion?: string | *"v1"
// the version of recipe
version?: string | *"2.0.0" // required for non-platform recipes
// pipeline name
kind?: string | *"helm-install"
// the meta data for the recipe
meta?: #meta
// generic tasks before install helm charts
preTasks?: [#task, ...#task]
// must have at least one helm chart eletement
helmCharts!: [#helmChart, ...#helmChart]
// generic tasks after install helm charts
postTasks?: [#task, ...#task]
