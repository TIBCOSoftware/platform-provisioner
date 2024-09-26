package recipe

// Copyright © 2024. Cloud Software Group, Inc.
// This file is subject to the license terms contained
// in the license file that is distributed with this file.

// the soruce of truce of shared.cue is under common-dependency helm chart. All others a duplication of this file.
// The duplication should be copied under docs folder to indicate this is only for documentation purpose see: PDP-1902

// we want to define shared types here
// we need to define bool as: "true" | "false" | true | false | *"default value"
// the reason is that the GUI might convert bool to string or the bool value might be another varaible that is not boolean
// the underline script to process all these will just use true or false

// the github repo that recipe operates on
#github: {
	repo!: =~"^github.com"
	path!: string
	branch?: string | *"main"
	// this will trigger a full clone of all history of given repo and swtich to the given hash branch
	hash?: string
	// this is the token that the pipeline will be used to clone the repo
	token?: string
}

// cluster name for helm-install task
#cluster: {
	name: string
}

// clusters for generic runner task
#clusters: {
	name: string
}

// the task to run
#task: {
	condition?: "true" | "false" | true | false | *true
	repo?: {
		git!:
			github!: #github
	}
	script?: {
		ignoreErrors?: "true" | "false" | true | false | *false
		base64Encoded?: "true" | "false" | true | false | *false
		skip?: "true" | "false" | true | false | *false
		// The pipeline will run the script with this file name
		fileName?: string | *"script.sh"
		content?: string  // if the content is empty, we will use the fileName as script name
	}
	clusters?: [...#clusters]
	// This will save content to a given file name in the pipeline container
	payload?: {
		base64Encoded?: "true" | "false" | true | false | *false
		fileName?: string | *"recipe.yaml"
		content!: string
	}
}

#meta: {
	// this is used for GUI replace only
	guiEnv?: {
		...
	}
	// this is used for setting up global environment variables inside the pipeline container
	globalEnvVariable?: {
		// REPLACE_RECIPE: "true" | "false" | true | false | *true
		// The variables that starts with PIPELINE_ will be used as pipeline control environment variables
		// if true, will mock run pipeline. (only run meta part)
		// PIPELINE_MOCK: "true" | "false" | true | false | *false
		// if true, will print pipeline debug log
		// PIPELINE_LOG_DEBUG: "true" | "false" | true | false | *false
		// if true, will validate input against cue schema
		// PIPELINE_VALIDATE_INPUT: "true" | "false" | *true | false | false
		// set to false to skip check docker status
		// PIPELINE_CHECK_DOCKER_STATUS: "true" | "false" | true | *false | true
		// set to false to skip initial assume to target account
		// PIPELINE_INITIAL_ASSUME_ROLE: "true" | "false" | true | false | *true
		// hen set to false to skip function init which is used to load TIBCO specific functions and envs for pipeline
		// PIPELINE_FUNCTION_INIT: "true" | "false" | true | false | *true
		// the role to assume to. We will use current AWS role to assume to this role to perform the task.
		// current role --> "arn:aws:iam::${_account}:role/${PIPELINE_AWS_MANAGED_ACCOUNT_ROLE}"
		PIPELINE_AWS_MANAGED_ACCOUNT_ROLE?: string
		...
	}
	// this is used for getting secret from AWS Secret Manager
	secret?: {
		substituteMethod?: string | *"named"
		aws!: {
			secretName!: string
		}
	}
	// this is used to get recipe from github repo and replace current recipe for gitOps
	git?:
		github!: #github
	// this is used to setup tools version for pipeline contianer
	tools?: {
		kubectl?: string | *"1.26"
		helm?: string | *"3.13"
		calicoctl?: string | *"3.23"
		yq?: string | *"3.4"
		...
	}
	// the pipeline pod log will be copied to s3 bucket see: CPIR-3314
	log?: {
		s3: string
	}
}
