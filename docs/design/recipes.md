# Platform Provisioner Recipes

In general a recipe has the following structure:

```yaml
apiVersion: v1
kind: generic-runner # or helm-install
meta:
  guiEnv:
    GUI_PIPELINE_LOG_DEBUG: true
    ...
  globalEnvVariable:
    REPLACE_RECIPE: true
    PIPELINE_LOG_DEBUG: '${GUI_PIPELINE_LOG_DEBUG}'
    ...
  tools:
    yq: '4.40'
    helm: '3.13'
# for generic-runner
tasks:
  ...
# for helm-install
preTasks:
  ...
helmCharts:
  ...
postTasks:
  ...
```

All the recipes will have `meta` part as common section. And depending on the recipe type, it will have either `tasks` or `helmCharts` section.
For more details please check the cue files in the
* [common-dependency](../../charts/common-dependency/scripts)
* [generic-runner](../../charts/generic-runner/scripts) 
* [helm-install](../../charts/helm-install/scripts)

## Common parts

`meta` section is used to define the global environment variables and tools that are used in the recipe. 
* The `guiEnv` section is used to define the environment variables that are used in the platform provisioner UI. 
* The `globalEnvVariable` section is used to define the environment variables that are used in the pipeline script. 
* The `secret` section is used to get the secrets from the secret manager.
* The `git` section is used to get recipe from the git repository.
* The `tools` section is used to define the tools that are used in the pipeline script.

The general idea in this `meta` section is to define the environment variables and tools that are used in the recipe. 
The variables defined in `guiEnv` and `globalEnvVariable` will be export as bash environment variables. And then the body of recipe 
will be rendered using `envsubst` to replace the variables. So the common variables like storage class or ingress class can be shared between helm charts or tasks.

## tasks for generic-runner

`tasks` section is defined in [shared.cue](../../charts/common-dependency/scripts/shared.cue). It is also used by `preTasks` and `postTasks` in `helm-install` recipe.

The main usage of the `tasks` section is to run a script under `tasks[].script` section. It also supports to download scripts from the git repository and run the script.

## helmCharts for helm-install

`helmCharts` section is defined in [check.cue](../../charts/helm-install/scripts/check.cue).

The main usage of the `helmCharts` section is to install the helm chart under `helmCharts[].chart` section. It also supports to download the helm chart from the git repository and install the helm chart.
