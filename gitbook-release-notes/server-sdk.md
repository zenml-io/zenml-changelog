---
description: Changelog for ZenML OSS and ZenML UI.
icon: clock-rotate-left
---

# ZenML OSS Changelog

Stay up to date with the latest features, improvements, and fixes in ZenML OSS.

## 0.94.3 (2026-04-24)

See what's new and improved in version 0.94.3.

<img src="https://public-flavor-logos.s3.eu-central-1.amazonaws.com/projects/9.jpg" align="left" alt="ZenML 0.94.3" width="800">

#### 🚀 New Features

**Podman Support & Container Engine Abstraction**

ZenML now supports **Podman** as an alternative to Docker for container image management. A new `ContainerEngine` abstraction has been introduced to make it easier to work with different OCI-compatible container runtimes. This gives you more flexibility in choosing your container tooling, especially in environments where Docker isn't available or preferred. [PR #4651](https://github.com/zenml-io/zenml/pull/4651)

**Resource Pools**

Introducing **Resource Pools** - a new way to manage and organize compute resources in ZenML. This feature includes full SDK methods, CLI commands, and API endpoints to create and manage resource pools and their associated objects, giving you better control over resource allocation across your ML workflows. [PR #4465](https://github.com/zenml-io/zenml/pull/4465)

**Platform Event Triggers**

You can now set up **event-based triggers** that automatically execute downstream workflows based on ZenML platform events, such as when a pipeline run completes. This enables powerful automation patterns and reactive workflows without manual intervention. Full backend management including CLI and SDK support is now available. [PR #4692](https://github.com/zenml-io/zenml/pull/4692)

**Server-Side Pipeline Replays**

Pipeline runs can now be **replayed from the server** with advanced capabilities:
- **Skip specific steps** - steps won't re-execute even if cache was disabled or inputs changed
- **Override step input artifacts** - go beyond parameter overrides and replace inputs that came from upstream steps in the original run

This gives you fine-grained control over re-executing parts of your pipelines. [PR #4716](https://github.com/zenml-io/zenml/pull/4716)

**Multiple Components Per Stack Type**

Stacks can now include **multiple components of the same type** for Alerters, Step Operators, and Experiment Trackers. You can designate one as the default while having others available for specific use cases, providing more flexibility in stack composition. [PR #4671](https://github.com/zenml-io/zenml/pull/4671)

**Kubernetes Gateway API Support**

The ZenML server can now be exposed via **Gateway API HTTPRoute resources** as an alternative to Ingress. Both Ingress and Gateway can be enabled simultaneously, making it easy to migrate from Ingress to Gateway API with zero downtime. [PR #4726](https://github.com/zenml-io/zenml/pull/4726)

#### ✨ Enhancements

**Improved Trigger Management**

- Triggers now track **per-snapshot dispatch state** showing whether the last run succeeded, was skipped due to concurrency policy, or failed
- Failed dispatches store **richer error context** including message, type, severity, stack trace, and timestamps
- New **acknowledge flow** lets you clear stored error context without re-attaching triggers or changing configuration

[PR #4743](https://github.com/zenml-io/zenml/pull/4743)

**Schedule Stop Criteria**

Schedules now support a **max-runs limit** to automatically stop after a specified number of executions per snapshot, giving you better control over scheduled pipeline runs. [PR #4752](https://github.com/zenml-io/zenml/pull/4752)

**Non-Blocking Concurrent Steps**

Dynamic pipelines with concurrent steps now execute more efficiently. Waiting for step inputs happens asynchronously instead of blocking the main thread, significantly improving pipeline execution performance when using concurrent steps. [PR #4699](https://github.com/zenml-io/zenml/pull/4699)

<details>
<summary>🐛 Fixed</summary>

- **Run status updates**: Fixed a bug where pipeline runs weren't properly marked as failed when a step pod failed after initially reporting success [PR #4747](https://github.com/zenml-io/zenml/pull/4747)
- **Secret visibility updates**: You can now properly update secrets from private to public using the CLI or client [PR #4755](https://github.com/zenml-io/zenml/pull/4755)
- **Logs for restarted runs**: Removed the unique constraint from logs schema to allow log entries for repeated executions of the same pipeline run [PR #4729](https://github.com/zenml-io/zenml/pull/4729)
- **Air-gapped performance**: Flavor model generation no longer calls PyPI to resolve ZenML versions, improving performance in air-gapped environments [PR #4744](https://github.com/zenml-io/zenml/pull/4744)

</details>

[View full release on GitHub](https://github.com/zenml-io/zenml/releases/tag/0.94.3)

***

## 0.94.2 (2026-04-08)

See what's new and improved in version 0.94.2.

<img src="https://public-flavor-logos.s3.eu-central-1.amazonaws.com/projects/8.jpg" align="left" alt="ZenML 0.94.2" width="800">

#### 🎨 Dashboard Enhancements

The ZenML dashboard now includes a **Run Summary View** that provides a comprehensive overview of your pipeline runs at a glance [PR #1029](https://github.com/zenml-io/zenml-dashboard/pull/1029). Timeline rows now automatically resize for better visualization of your pipeline execution history [PR #1028](https://github.com/zenml-io/zenml-dashboard/pull/1028).

#### 🔧 Pipeline & Trigger Improvements

**Artifact Name Substitutions for Dynamic Pipelines**: You can now use artifact name substitutions in dynamic pipelines, making it easier to reference and manage artifacts programmatically [PR #4668](https://github.com/zenml-io/zenml/pull/4668).

**Enhanced Trigger Configuration**: Triggered runs now follow a cleaner `snapshot.source` pattern. You can provide a configuration object to customize parameters for all triggered runs in an attachment, giving you more control over automated pipeline executions [PR #4610](https://github.com/zenml-io/zenml/pull/4610).

#### ⚠️ Deprecation Notice

**Helm Chart Configuration Update**: The top-level `zenml:` values key in the ZenML Helm chart has been renamed to `server:` [PR #4637](https://github.com/zenml-io/zenml/pull/4637). Your existing values files will continue to work — the chart automatically merges both keys for backwards compatibility. If both keys are present, `zenml:` takes precedence for overlapping fields. The `zenml:` key is deprecated and will be removed in a future release; we recommend migrating to `server:` in your Helm configurations.

<details><summary>Fixed</summary>

- **Schedule Management**: Fixed issues where deletion by ID prefix wasn't working for archived schedules, and reusing an archived schedule name was incorrectly blocked. Documentation has been updated to clarify schedule behavior post-deletion, including archived schedule renaming, hard deletion guidelines, and discovery of archived objects [PR #4641](https://github.com/zenml-io/zenml/pull/4641).

- **Input Artifact Handling**: Resolved a bug where a list of input artifacts containing a single item was incorrectly treated as a scalar input artifact, causing materializer type incompatibility errors [PR #4679](https://github.com/zenml-io/zenml/pull/4679).

- **HTTP Request Optimization**: The system now dynamically reduces chunk size when fetching many steps to avoid HTTP 414 (URI Too Long) errors [PR #4553](https://github.com/zenml-io/zenml/pull/4553).

- **Dashboard Deployment Stability**: Fixed a template loading issue in the FastAPI deployment app's dashboard that could cause `TypeError: unhashable type: 'dict'` on certain environments (e.g., Kubernetes with newer Jinja2 versions), preventing the server from starting when the dashboard was enabled [PR #4649](https://github.com/zenml-io/zenml/pull/4649).

</details>

[View full release on GitHub](https://github.com/zenml-io/zenml/releases/tag/0.94.2)

***

## 0.94.1 (2026-03-19)

See what's new and improved in version 0.94.1.

<img src="https://public-flavor-logos.s3.eu-central-1.amazonaws.com/projects/7.jpg" align="left" alt="ZenML 0.94.1" width="800">

#### 🎯 Pipeline Execution Control

- **Pause and Resume Pipeline Runs**: Introduced `zenml.wait(...)` to pause dynamic pipelines while waiting for external inputs, automatically freeing resources until the input is provided. Runs can be resumed automatically (when using remote orchestrators with snapshot support) or manually via `zenml pipeline runs resume <ID>`. [PR #4588](https://github.com/zenml-io/zenml/pull/4588)
- **Override Step Inputs on Replay**: You can now override step inputs when replaying a pipeline run, giving you more flexibility to rerun pipelines with different data. [PR #4590](https://github.com/zenml-io/zenml/pull/4590)

#### 🔧 Materializers and Data Handling

- **Dataclass Materializer**: Added a built-in materializer for JSON-serializable dataclasses, making it easier to pass structured data between steps. [PR #4600](https://github.com/zenml-io/zenml/pull/4600)
- **LakeFS Data Versioning Example**: New example demonstrating the "pass references, not data" pattern for terabyte-scale datasets. ZenML steps exchange lightweight LakeFS pointers while actual data stays in LakeFS, accessed via its S3-compatible gateway. [PR #4559](https://github.com/zenml-io/zenml/pull/4559)

#### ☁️ Infrastructure and Deployment

- **Helm Environment Variable Overrides**: Environment variables specified in `zenml.environment`, `zenml.secretEnvironment`, and worker deployment configurations can now override computed settings from the Helm chart. [PR #4595](https://github.com/zenml-io/zenml/pull/4595)
- **Secret Environment Variables in Helm**: Added support for injecting secret environment variables into the ZenML server deployment via Helm without committing secrets to values.yaml, enabling better GitOps workflows. [PR #4606](https://github.com/zenml-io/zenml/pull/4606)
- **Docker Build Arguments**: Build arguments defined in `DockerSettings` are now properly declared with `ARG` instructions in auto-generated Dockerfiles. [PR #4612](https://github.com/zenml-io/zenml/pull/4612)

#### 🔐 Authentication and Credentials

- **Improved GCP Credentials Refresh**: Implemented native GCP credentials refresh using service connector logic, replacing periodic expiration checks for more reliable OAuth2 credential handling. [PR #4527](https://github.com/zenml-io/zenml/pull/4527)

#### 📊 Pipeline Configuration

- **Step Parameter Schema Storage**: Step parameter specifications are now stored for better schema validation when triggering pipeline snapshots. [PR #4591](https://github.com/zenml-io/zenml/pull/4591)

<details><summary>Fixed</summary>

- **Exception Handling for Isolated Steps**: Isolated steps in dynamic pipelines now raise the correct exception types instead of always wrapping them in `RuntimeError`, making error handling more intuitive and consistent. [PR #4589](https://github.com/zenml-io/zenml/pull/4589)
- **Kubernetes API Request Timeout**: Fixed typing issue in the Kubernetes orchestrator and step operator to ensure `api_request_timeout` is properly applied as an integer value. [PR #4605](https://github.com/zenml-io/zenml/pull/4605)
- **Client-Server Compatibility**: Resolved compatibility issue with clients `<=0.92.0` by not passing both pipeline run ID and step run ID to logs requests. [PR #4614](https://github.com/zenml-io/zenml/pull/4614)
- **Dynamic Pipeline Monitoring**: Fixed dictionary size change error that occurred when the main thread modified the `_steps_to_monitor` dictionary while the monitoring thread was iterating over it. [PR #4619](https://github.com/zenml-io/zenml/pull/4619)
- **Step Config Template Parameters**: Step parameters defined in config templates now correctly take precedence over function default values in dynamic pipelines. [PR #4624](https://github.com/zenml-io/zenml/pull/4624)

</details>

#### 📦 Dependencies

- Updated Pydantic to version 2.12.5. [PR #4552](https://github.com/zenml-io/zenml/pull/4552)

[View full release on GitHub](https://github.com/zenml-io/zenml/releases/tag/0.94.1)

***

## 0.94.0 (2026-03-04)

See what's new and improved in version 0.94.0.

<img src="https://public-flavor-logos.s3.eu-central-1.amazonaws.com/projects/6.jpg" align="left" alt="ZenML 0.94.0" width="800">

### Breaking Changes

* Old endpoints and client methods for legacy triggers, actions and event sources have been removed. **This shouldn't affect you unless you explicitly used those endpoints or methods in your code.**
* Custom step operator flavors must implement new `submit_step` and `get_step_status` methods to work with dynamic pipelines. The legacy `launch` method will only work in static pipelines as a fallback. The Spark step operator is not yet compatible with dynamic pipelines. [PR #4515](https://github.com/zenml-io/zenml/pull/4515)

#### 🚀 New Integrations

- **Run:AI Step Operator**: ZenML now supports running individual pipeline steps on Run:AI clusters with fractional GPU allocation, enabling more efficient resource utilization for ML workloads. [PR #4439](https://github.com/zenml-io/zenml/pull/4439)

#### ✨ New Features

- **Step and Pipeline Replays**: You can now replay existing step or pipeline runs with the same inputs and configuration. When replaying a pipeline run, you can specify which steps to skip and reuse from the original run. A debug mode is also available to run replays on your active stack with a local orchestrator. [PR #4456](https://github.com/zenml-io/zenml/pull/4456)

- **Triggers and Native Schedules (PRO)**: Introduced the `Trigger` concept for automated pipeline execution. The first supported trigger type is Schedules, which offers lifecycle management, automatic synchronization with orchestrators, and centralized management across stacks. [PR #4482](https://github.com/zenml-io/zenml/pull/4482)

- **Step Run Filtering by Version**: Added the ability to filter step runs by version, making it easier to track and manage specific versions of your pipeline steps. [PR #4518](https://github.com/zenml-io/zenml/pull/4518)

#### 🔧 Improvements

- **Enhanced Dynamic Pipeline Monitoring**: Improved the execution and monitoring of isolated steps in dynamic pipelines. Step submission is now separated from monitoring, preventing thread blocking during step execution. [PR #4369](https://github.com/zenml-io/zenml/pull/4369)

- **SkyPilot Integration Update**: Updated the SkyPilot integration to support version 0.11.x, including migration to the new async API and support for new resource settings. [PR #4462](https://github.com/zenml-io/zenml/pull/4462)

- **Kubernetes Retry Configuration**: Added configurable timeout options for Kubernetes orchestrator and step operator API calls, ensuring proper retry behavior and preventing unnecessary hanging. [PR #4525](https://github.com/zenml-io/zenml/pull/4525)

- **Git Submodule Support**: Code archives now include files from git submodules when uploading to the artifact store, ensuring complete code tracking for repositories with submodules. [PR #4496](https://github.com/zenml-io/zenml/pull/4496)

<details>
<summary>Fixed</summary>

- Fixed handling of variadic keyword arguments in pipeline functions, ensuring they are properly flattened before being passed to the pipeline. [PR #4528](https://github.com/zenml-io/zenml/pull/4528)

- Fixed Azure integration dependencies by limiting the `azure-mgmt-resource` version to avoid compatibility issues with the 25.0.0 package split. [PR #4516](https://github.com/zenml-io/zenml/pull/4516)

- Fixed handling of external artifacts with `None` values and reduced chunk size when fetching many step runs to avoid URI too large errors. [PR #4551](https://github.com/zenml-io/zenml/pull/4551)

</details>

[View full release on GitHub](https://github.com/zenml-io/zenml/releases/tag/0.94.0)

***

## 0.93.3 (2026-02-19)

See what's new and improved in version 0.93.3.

<img src="https://public-flavor-logos.s3.eu-central-1.amazonaws.com/projects/5.jpg" align="left" alt="ZenML 0.93.3" width="800">

#### Performance Improvements

This release includes significant performance optimizations for the ZenML server, particularly when handling large-scale deployments:

- **Improved database query efficiency**: Rewrote filtering queries to eliminate unnecessary sorting during item counting, removed inefficient DISTINCT statements on multiple columns, and optimized OR subqueries for better database performance at scale. [PR #4449](https://github.com/zenml-io/zenml/pull/4449)

- **Enhanced API transaction management**: Moved cleanup of expired transactions to an independent background thread that runs periodically, significantly improving API response times especially for large payloads like pipeline snapshots with many steps. [PR #4453](https://github.com/zenml-io/zenml/pull/4453)

#### Logging Enhancements

Logging capabilities have been expanded with new features and improvements:

- Added new `create` and `update` endpoints for logs with support for UUIDs in `StepRunRequest` and `PipelineRunRequest`
- Introduced workspace ID and name to pipeline run log metadata (with backward compatibility)
- Added `zenml.event.type` to error messages for better context tracking
- Introduced environment variable to manage maximum log entries per request
- Fixed inconsistent metadata key formatting (standardized `zenml.` prefix) [PR #4405](https://github.com/zenml-io/zenml/pull/4405), [PR #4467](https://github.com/zenml-io/zenml/pull/4467)

#### Dashboard Updates

- Added elapsed time display to step nodes in the DAG visualization for better pipeline monitoring [PR #994](https://github.com/zenml-io/zenml-dashboard/pull/994)

<details><summary>Fixed</summary>

- **Critical data loss bug**: Fixed a critical issue in `download_artifact_files_from_response` that caused silent data corruption when downloading artifacts larger than 8KB. The bug resulted in up to 98%+ data loss for large artifacts by only preserving the last chunk of data. [PR #4422](https://github.com/zenml-io/zenml/pull/4422)

- **ZenML Pro migration**: Fixed an issue where cookies from local user accounts persisted after migrating a ZenML OSS server to ZenML Pro via organization enrollment, preventing access to migrated resources in the UI. The server now properly rejects these stale cookies. [PR #4473](https://github.com/zenml-io/zenml/pull/4473)

- **UV-only environments**: Fixed pipeline run crashes in environments using only `uv` without `pip` installed. ZenML now falls back to `uv pip freeze` when `pip freeze` is unavailable for collecting environment metadata. Also added `UV_FREEZE` as an export method for Docker builds. [PR #4484](https://github.com/zenml-io/zenml/pull/4484)

- **Kubernetes credential expiration**: Fixed an issue where Kubernetes credentials issued by service connectors expired while monitoring long-running jobs, causing monitoring failures. Credentials are now properly refreshed during job monitoring. [PR #4493](https://github.com/zenml-io/zenml/pull/4493)

- Improved CLI messaging when attempting to activate a stack without proper permissions

</details>

[View full release on GitHub](https://github.com/zenml-io/zenml/releases/tag/0.93.3)

***

## 0.93.2 (2026-01-29)

See what's new and improved in version 0.93.2.

<img src="https://public-flavor-logos.s3.eu-central-1.amazonaws.com/projects/4.jpg" align="left" alt="ZenML 0.93.2" width="800">

#### 🎨 Dashboard Enhancements

The ZenML Dashboard now provides better visibility into your pipelines and infrastructure:

- **Download Pipeline Code**: You can now download the code used for a pipeline snapshot directly from the dashboard. A new Download button appears in the "Code Path" section on both the Pipeline Run details page and the Step details sheet, making it easy to retrieve and review the exact code that was executed. [PR #4401](https://github.com/zenml-io/zenml/pull/4401), [PR #989](https://github.com/zenml-io/zenml-dashboard/pull/989)

- **Exception Information Display**: When dynamic pipeline runs fail, the dashboard now displays detailed exception information, helping you quickly diagnose and troubleshoot issues. [PR #4395](https://github.com/zenml-io/zenml/pull/4395), [PR #990](https://github.com/zenml-io/zenml-dashboard/pull/990)

- **Stack & Component Labels**: Labels attached to stacks and components are now visible in the dashboard, making it easier to organize and identify your infrastructure resources. [PR #992](https://github.com/zenml-io/zenml-dashboard/pull/992)

#### 🔄 Dynamic Pipeline Improvements

Dynamic pipelines are now more robust and easier to work with:

- **Proper Environment Configuration**: The pipeline environment is now correctly set while running the entrypoint function of dynamic pipelines, ensuring consistent behavior across different execution contexts. [PR #4420](https://github.com/zenml-io/zenml/pull/4420)

#### 🤖 Developer Experience

- **Claude Code Plugin**: A new ZenML Quick Wins skill for Claude Code helps you implement MLOps best practices directly in your AI-assisted coding workflow. The plugin is available through the Claude Code plugin marketplace and includes comprehensive documentation for multiple AI coding tools. [PR #4426](https://github.com/zenml-io/zenml/pull/4426)

<details><summary>Fixed</summary>

#### 🚀 Performance & Scalability

- **Artifact Download Fix**: Resolved an issue where artifact version downloads were failing due to incorrect RBAC checks on the download endpoint. [PR #4401](https://github.com/zenml-io/zenml/pull/4401)

</details>

[View full release on GitHub](https://github.com/zenml-io/zenml/releases/tag/0.93.2)

***

## 0.93.1 (2026-01-14)

See what's new and improved in version 0.93.1.

<img src="https://public-flavor-logos.s3.eu-central-1.amazonaws.com/projects/3.jpg" align="left" alt="ZenML 0.93.1" width="800">

#### 🎛️ Schedule Management Enhancements

You can now **pause and resume pipeline schedules** directly from the CLI, giving you better control over automated pipeline executions. Use the new commands to activate or deactivate schedules on demand:

```bash
zenml pipeline schedule deactivate <schedule_id>
zenml pipeline schedule activate <schedule_id>
```

Currently available for the Kubernetes orchestrator. [PR #4328](https://github.com/zenml-io/zenml/pull/4328)

Schedules now support **archiving** as a soft-delete operation. When you delete a schedule, it's archived instead of permanently removed, preserving historical references so your pipeline runs maintain their schedule associations. [PR #4339](https://github.com/zenml-io/zenml/pull/4339)

#### 🖥️ Dashboard Improvements

**Stack Management**: You can now update existing stacks directly from the UI without having to delete and recreate them. A new dedicated stack update page lets you add or replace stack components (orchestrators, artifact stores, container registries, etc.) efficiently. [PR #978](https://github.com/zenml-io/zenml-dashboard/pull/978)

**Step Cache Management**: View and manage step cache expiration directly from the step details panel. The cache expiration field shows when a step's cache will expire (or "Never" if no expiration is set), with expired caches clearly marked. You can also manually invalidate a step's cache with a single click. [PR #976](https://github.com/zenml-io/zenml-dashboard/pull/976)

**Enhanced Logs Experience**: Pipeline runs now have a dedicated logs page with a sidebar for navigating between run-level and step logs. The new logs viewer features virtualized rendering for better performance with large outputs, search and filtering capabilities, and step duration display. [PR #985](https://github.com/zenml-io/zenml-dashboard/pull/985)

#### ⚡ Performance & Reliability

**Kubernetes Orchestrator Improvements**: The Kubernetes orchestrator now runs more efficiently with configurable DAG runner workers, optimized cache candidate fetching, and better error handling for failed step pods. [PR #4368](https://github.com/zenml-io/zenml/pull/4368)

**Database Backup Speed**: A new mydumper/myloader backup strategy delivers dramatically faster operations:
- **30x faster** database backups
- **2.5x faster** database restores  
- **10x lower** storage space requirements

[PR #4358](https://github.com/zenml-io/zenml/pull/4358)

#### 🚀 Orchestrator Features

**AzureML Dynamic Pipelines**: Dynamic pipelines are now fully supported on the AzureML orchestrator, expanding your options for flexible pipeline execution. [PR #4363](https://github.com/zenml-io/zenml/pull/4363)

**Kubernetes Init Container Templating**: When configuring init containers for the Kubernetes orchestrator, you can now use an `"{{ image }}"` placeholder that will be automatically replaced with the actual orchestration/step container image. [PR #4361](https://github.com/zenml-io/zenml/pull/4361)

<details>
<summary>Fixed</summary>

- Fixed per-step compute settings not being applied correctly [PR #4362](https://github.com/zenml-io/zenml/pull/4362)
- Fixed database migration script to handle pipelines with zero runs [PR #4360](https://github.com/zenml-io/zenml/pull/4360)
- Fixed working directory in dynamic pipeline containers (was `/zenml` instead of `/app`) [PR #4379](https://github.com/zenml-io/zenml/pull/4379)
- Fixed pipeline run status updates in `CONTINUE_ON_FAILURE` execution mode [PR #4379](https://github.com/zenml-io/zenml/pull/4379)
- Fixed component setting shortcut keys when running snapshots [PR #4379](https://github.com/zenml-io/zenml/pull/4379)
- Improved error messages during source validation and for string type annotations [PR #4359](https://github.com/zenml-io/zenml/pull/4359)
- Fixed log storage in Kubernetes orchestrator by propagating context vars to DAG runner threads [PR #4359](https://github.com/zenml-io/zenml/pull/4359)
- Pipeline source code now included for runs triggered by snapshots/deployments [PR #4359](https://github.com/zenml-io/zenml/pull/4359)

</details>

[View full release on GitHub](https://github.com/zenml-io/zenml/releases/tag/0.93.1)

***

## 0.93.0 (2025-12-16)

See what's new and improved in version 0.93.0.

<img src="https://public-flavor-logos.s3.eu-central-1.amazonaws.com/projects/2.jpg" align="left" alt="ZenML 0.93.0" width="800">

### Breaking Changes

* The logging system has been completely redesigned with a new log store abstraction that now captures stdout, stderr, and all logger outputs more comprehensively. If you have custom integrations that relied on the previous logging behavior or accessed logs directly from the artifact store, you may need to update your code to use the new log store APIs. [PR #4111](https://github.com/zenml-io/zenml/pull/4111)
* The REST API endpoint `/api/v1/pipelines/<ID>/runs` has been removed. Use `/api/v1/runs?pipeline_id=<ID>` instead to fetch runs for a specific pipeline. [PR #4350](https://github.com/zenml-io/zenml/pull/4350)
* The `logs` field has been removed from the response models of pipeline runs and steps. Additionally, RBAC checks for fetching logs, downloading artifacts, and visualizations have been tightened. If you were accessing logs through these response models, you will need to use the dedicated log fetching endpoints instead. [PR #4347](https://github.com/zenml-io/zenml/pull/4347)

#### Enhanced CLI Experience

The ZenML CLI now provides a more flexible and user-friendly experience with improved table rendering and output options. Tables are now more aesthetically pleasing with intelligent column sizing, and you can pipe CLI output in multiple formats (JSON, YAML, CSV, TSV) by properly separating stdout and stderr streams. This makes it easier to integrate ZenML commands into scripts and automation workflows. [PR #4241](https://github.com/zenml-io/zenml/pull/4241)

#### Dynamic Pipeline Support

Dynamic pipelines can now be deployed and run with the local Docker orchestrator, including support for asynchronous execution. This expands the flexibility of local development and testing workflows, allowing you to leverage dynamic pipeline patterns without requiring cloud infrastructure. [PR #4294](https://github.com/zenml-io/zenml/pull/4294), [PR #4300](https://github.com/zenml-io/zenml/pull/4300)

#### Pipeline Run Tracking

Each pipeline run now includes an `index` attribute that tracks its position within the pipeline's execution history, making it easier to identify and reference specific runs in a sequence. [PR #4288](https://github.com/zenml-io/zenml/pull/4288)

#### Orchestrator Health Monitoring

The Kubernetes orchestrator now includes enhanced health monitoring capabilities with configurable heartbeat thresholds. Steps that become unhealthy are preemptively stopped, and pipeline tokens are automatically invalidated when pipelines enter an unhealthy state, improving reliability and resource management. [PR #4247](https://github.com/zenml-io/zenml/pull/4247)

#### New Integrations

- **Alibaba Cloud Storage**: Added support for Alibaba Cloud OSS as an artifact store, expanding ZenML's cloud storage options. [PR #4289](https://github.com/zenml-io/zenml/pull/4289)
- **Generic OTEL Log Store**: Introduced a new log store flavor that can connect to any OTEL/HTTP/JSON compatible log intake endpoint, enabling integration with a wider range of observability platforms. [PR #4309](https://github.com/zenml-io/zenml/pull/4309)

#### Azure ML Enhancements

The AzureML orchestrator and step operator now support shared memory size configuration, giving you more control over resource allocation for your workloads. [PR #4334](https://github.com/zenml-io/zenml/pull/4334)

<details><summary>Fixed</summary>

- **MLflow Experiment Tracker**: Fixed crashes when attempting to resume non-existent runs on Azure ML. The tracker now validates cached run IDs and gracefully creates new runs when necessary. [PR #4227](https://github.com/zenml-io/zenml/pull/4227)
- **Kubernetes Service Connector**: Resolved failures in the ZenML server related to the Kubernetes service connector caused by incompatible urllib3 and kubernetes client library versions. [PR #4312](https://github.com/zenml-io/zenml/pull/4312)
- **Datadog Log Store**: Improved log fetching with proper pagination support, handling the Datadog API's 1000-log limit per request through cursor-based iteration. [PR #4314](https://github.com/zenml-io/zenml/pull/4314)
- **Deployment Log Flushing**: Eliminated blocking behavior when flushing logs during deployment invocations, preventing potential hangs at pipeline completion. [PR #4354](https://github.com/zenml-io/zenml/pull/4354)

</details>

[View full release on GitHub](https://github.com/zenml-io/zenml/releases/tag/0.93.0)

***

## 0.92.0 (2025-12-02)

See what's new and improved in version 0.92.0.

<img src="https://public-flavor-logos.s3.eu-central-1.amazonaws.com/projects/1.jpg" align="left" alt="ZenML 0.92.0" width="800">

#### Dynamic Pipeline Support Expansion

This release significantly expands support for dynamic pipelines across multiple orchestrators:

- **AWS Sagemaker Orchestrator**: Added full support for running dynamic pipelines with seamless transition from existing settings and faster execution through direct use of training jobs. [PR #4232](https://github.com/zenml-io/zenml/pull/4232)
- **Vertex AI Orchestrator**: Dynamic pipelines are now fully supported on Google Cloud's Vertex AI platform. [PR #4246](https://github.com/zenml-io/zenml/pull/4246)
- **Kubernetes Orchestrator**: Improved dynamic pipeline handling by eliminating unnecessary pod restarts. [PR #4261](https://github.com/zenml-io/zenml/pull/4261)
- **Snapshot Execution**: For Pro users, the new release enabled running snapshots of dynamic pipelines from the server with support for specifying pipeline parameters. [PR #4253](https://github.com/zenml-io/zenml/pull/4253)

<details><summary>Improved</summary>

- Enhanced `step.map(...)` and `step.product(...)` to return a single future object instead of a list of futures, simplifying the API for step invocations. [PR #4261](https://github.com/zenml-io/zenml/pull/4261)
- Improved placeholder run handling to prevent potential issues in dynamic pipeline execution. [PR #4261](https://github.com/zenml-io/zenml/pull/4261)
- Added better typing for Docker build options with a new class to help with conversions between SDK and CLI. [PR #4262](https://github.com/zenml-io/zenml/pull/4262)

</details>

#### GCP Image Builder Regional Support

Added regional location support to the GCP Image Builder, allowing you to specify Cloud Build regions for improved performance and compliance:

- Optional `location` parameter for specifying Cloud Build region
- Uses regional Cloud Build endpoint (`{location}-cloudbuild.googleapis.com`) when location is set
- Maintains backward compatibility with global endpoint as default
- Includes input validation for location parameter

[PR #4268](https://github.com/zenml-io/zenml/pull/4268)

#### Integration Updates

- **Evidently Integration**: Updated to version >=0.5.0 to support [NumPy](https://github.com/numpy/numpy) 2.0, resolving compatibility issues when installing packages requiring NumPy 2.0+ alongside ZenML. [PR #4243](https://github.com/zenml-io/zenml/pull/4243)

[View full release on GitHub](https://github.com/zenml-io/zenml/releases/tag/0.92.0)

***

## 0.91.2 (2025-11-19)

See what's new and improved in version 0.91.2.

<img src="https://public-flavor-logos.s3.eu-central-1.amazonaws.com/projects/1.jpg" align="left" alt="ZenML 0.91.2" width="800">

#### Kubernetes Deployer

* Deploy your pipelines directly on Kubernetes
* Full integration with Kubernetes orchestrator

[Learn more](https://docs.zenml.io/component-guide/deployers/kubernetes) | [PR #4127](https://github.com/zenml-io/zenml/pull/4127)

#### MLflow 3.0 Support

* Added support for the latest MLflow version
* Improved compatibility with modern MLflow features

[PR #4160](https://github.com/zenml-io/zenml/pull/4160)

#### S3 Artifact Store Fixes

* Fixed compatibility with custom S3 backends
* Improved SSL certificate handling for RestZenStore
* Enhanced Weights & Biases experiment tracker reliability

#### UI Updates

* Remove Video Modal ([#943](https://github.com/zenml-io/zenml-dashboard/pull/943))
* Update Dependencies (CVE) ([#945](https://github.com/zenml-io/zenml-dashboard/pull/945))
* Adjust text-color ([#947](https://github.com/zenml-io/zenml-dashboard/pull/947))
* Sanitize Dockerfile ([#948](https://github.com/zenml-io/zenml-dashboard/pull/948))

<details>
<summary>Fixed</summary>

* S3 artifact store now works with custom backends ([#4186](https://github.com/zenml-io/zenml/pull/4186))
* SSL certificate passing for RestZenStore ([#4188](https://github.com/zenml-io/zenml/pull/4188))
* Weights & Biases tag length limitations ([#4189](https://github.com/zenml-io/zenml/pull/4189))

</details>

[View full release on GitHub](https://github.com/zenml-io/zenml/releases/tag/0.91.2)

***
## 0.91.1 (2025-11-11)

See what's new and improved in version 0.91.1.

<img src="https://public-flavor-logos.s3.eu-central-1.amazonaws.com/projects/2.jpg" align="left" alt="ZenML 0.91.1" width="800">

#### Hugging Face Deployer

* Deploy pipelines directly to Hugging Face Spaces
* Seamless integration with Hugging Face infrastructure

[Learn more](https://docs.zenml.io/component-guide/deployers/huggingface) | [PR #4119](https://github.com/zenml-io/zenml/pull/4119)

#### Dynamic Pipelines (Experimental)

* Introduced v1 of dynamic pipelines
* Early feedback welcome for this experimental feature

[Read the documentation](https://docs.zenml.io/how-to/steps-pipelines/dynamic_pipelines) | [PR #4074](https://github.com/zenml-io/zenml/pull/4074)

#### Kubernetes Orchestrator Enhancements

* Container security context configuration
* Skip owner references option
* Improved deployment reliability

#### UI Updates

* Display Deployment in Run Detail ([#919](https://github.com/zenml-io/zenml-dashboard/pull/919))
* Announcements Widget ([#926](https://github.com/zenml-io/zenml-dashboard/pull/926))
* Add Resize Observer to HTML Viz ([#928](https://github.com/zenml-io/zenml-dashboard/pull/928))
* Adjust Overview Pipelines ([#914](https://github.com/zenml-io/zenml-dashboard/pull/914))
* Fix Panel background ([#882](https://github.com/zenml-io/zenml-dashboard/pull/882))
* Input Styling ([#911](https://github.com/zenml-io/zenml-dashboard/pull/911))
* Display Schedules ([#879](https://github.com/zenml-io/zenml-dashboard/pull/879))

<details>
<summary>Improved</summary>

* Enhanced Kubernetes orchestrator with container security context options ([#4142](https://github.com/zenml-io/zenml/pull/4142))
* Better handling of owner references in Kubernetes deployments ([#4146](https://github.com/zenml-io/zenml/pull/4146))
* Expanded HashiCorp Vault secret store authentication methods ([#4110](https://github.com/zenml-io/zenml/pull/4110))
* Support for newer Databricks versions ([#4144](https://github.com/zenml-io/zenml/pull/4144))

</details>

<details>
<summary>Fixed</summary>

* Port reuse for local deployments
* Parallel deployment invocations
* Keyboard interrupt handling during monitoring
* Case-sensitivity issues when updating entity names ([#4140](https://github.com/zenml-io/zenml/pull/4140))

</details>

[View full release on GitHub](https://github.com/zenml-io/zenml/releases/tag/0.91.1)

***
## 0.91.0 (2025-10-25)

See what's new and improved in version 0.91.0.

<img src="https://public-flavor-logos.s3.eu-central-1.amazonaws.com/projects/3.jpg" align="left" alt="ZenML 0.91.0" width="800">

#### Local Deployer

* Deploy pipelines locally with full control
* Perfect for development and testing workflows

[Learn more](https://docs.zenml.io/component-guide/deployers/local) | [PR #4085](https://github.com/zenml-io/zenml/pull/4085)

#### Advanced Caching System

* File and object-based cache invalidation
* Cache expiration for bounded lifetime
* Custom cache functions for advanced logic

[Read the documentation](https://docs.zenml.io/how-to/steps-pipelines/advanced_features) | [PR #4040](https://github.com/zenml-io/zenml/pull/4040)

#### Deployment Visualizations

* Attach custom visualizations to deployments
* Fully customizable deployment server settings
* Enhanced deployment management

[PR #4016](https://github.com/zenml-io/zenml/pull/4016) | [PR #4064](https://github.com/zenml-io/zenml/pull/4064)

#### Python 3.13 Support

* Full compatibility with Python 3.13
* MLX array materializer for Apple Silicon

[PR #4053](https://github.com/zenml-io/zenml/pull/4053) | [PR #4027](https://github.com/zenml-io/zenml/pull/4027)

#### UI Updates

* **Deployment Playground:** Easier to invoke and test deployments ([#861](https://github.com/zenml-io/zenml-dashboard/pull/861))
* **Global Lists:** Centralized access for deployments ([#851](https://github.com/zenml-io/zenml-dashboard/pull/851)) and snapshots ([#854](https://github.com/zenml-io/zenml-dashboard/pull/854))
* **Create Snapshots:** Create snapshots directly from the UI ([#856](https://github.com/zenml-io/zenml-dashboard/pull/856))
* GitHub-Flavored Markdown support ([#876](https://github.com/zenml-io/zenml-dashboard/pull/876))
* Resizable Panels ([#873](https://github.com/zenml-io/zenml-dashboard/pull/873))

<details>
<summary>Improved</summary>

* Customizable image tags for Docker builds ([#4025](https://github.com/zenml-io/zenml/pull/4025))
* Enhanced deployment server configuration ([#4064](https://github.com/zenml-io/zenml/pull/4064))
* Better integration with MLX arrays ([#4027](https://github.com/zenml-io/zenml/pull/4027))

</details>

<details>
<summary>Fixed</summary>

* Print capturing incompatibility with numba ([#4060](https://github.com/zenml-io/zenml/pull/4060))
* Hashicorp Vault secrets store mount point configuration ([#4088](https://github.com/zenml-io/zenml/pull/4088))

</details>

### Breaking Changes

* Dropped Python 3.9 support - upgrade to Python 3.10+ ([#4053](https://github.com/zenml-io/zenml/pull/4053))

[View full release on GitHub](https://github.com/zenml-io/zenml/releases/tag/0.91.0)

***
## 0.90.0 (2025-10-02)

See what's new and improved in version 0.90.0.

<img src="https://public-flavor-logos.s3.eu-central-1.amazonaws.com/projects/4.jpg" align="left" alt="ZenML 0.90.0" width="800">

#### Pipeline Snapshots & Deployments

* Capture immutable snapshots of pipeline code and configuration
* Deploy pipelines as HTTP endpoints for online inference
* Docker, AWS, and GCP deployer implementations

[Learn more about Snapshots](https://docs.zenml.io/how-to/snapshots/snapshots) | [Learn more about Deployments](https://docs.zenml.io/how-to/deployment/deployment)

[PR #3856](https://github.com/zenml-io/zenml/pull/3856) | [PR #3920](https://github.com/zenml-io/zenml/pull/3920)

#### Runtime Environment Variables

* Configure environment variables when running pipelines
* Support for ZenML secrets in runtime configuration

[PR #3336](https://github.com/zenml-io/zenml/pull/3336)

#### Dependency Management Improvements

* Reduced base package dependencies
* Local database dependencies moved to `zenml[local]` extra
* JAX array materializer support

[PR #3916](https://github.com/zenml-io/zenml/pull/3916) | [PR #3712](https://github.com/zenml-io/zenml/pull/3712)

#### UI Updates

* **Pipeline Snapshots & Deployments:** Track entities introduced in ZenML 0.90.0 ([#814](https://github.com/zenml-io/zenml-dashboard/pull/814))

<details>
<summary>Improved</summary>

* Slimmer base package for faster installations ([#3916](https://github.com/zenml-io/zenml/pull/3916))
* Better dependency management
* Enhanced JAX integration ([#3712](https://github.com/zenml-io/zenml/pull/3712))

</details>

### Breaking Changes

* Client-Server compatibility: Must upgrade both simultaneously
* Run templates need to be recreated
* Base package no longer includes local database dependencies - install `zenml[local]` if needed ([#3916](https://github.com/zenml-io/zenml/pull/3916))

[View full release on GitHub](https://github.com/zenml-io/zenml/releases/tag/0.90.0)

***
## 0.85.0 (2025-09-12)

See what's new and improved in version 0.85.0.

<img src="https://public-flavor-logos.s3.eu-central-1.amazonaws.com/projects/5.jpg" align="left" alt="ZenML 0.85.0" width="800">

#### Pipeline Execution Modes

* Flexible failure handling configuration
* Control what happens when steps fail
* Better pipeline resilience

[Read the documentation](https://docs.zenml.io/how-to/steps-pipelines/advanced_features) | [PR #3874](https://github.com/zenml-io/zenml/pull/3874)

#### Value-Based Caching

* Cache artifacts based on content/value, not just ID
* More intelligent cache reuse
* Cache policies for granular control

[PR #3900](https://github.com/zenml-io/zenml/pull/3900)

#### Airflow 3.0 Support

* Full compatibility with Apache Airflow 3.0
* Access to latest Airflow features and improvements

[PR #3922](https://github.com/zenml-io/zenml/pull/3922)

#### UI Updates

* **Timeline View:** New way to visualize pipeline runs alongside the DAG ([#799](https://github.com/zenml-io/zenml-dashboard/pull/799))
* Client-Side Structured Logs ([#801](https://github.com/zenml-io/zenml-dashboard/pull/801))
* Default Value for Arrays ([#798](https://github.com/zenml-io/zenml-dashboard/pull/798))

<details>
<summary>Improved</summary>

* Enhanced caching system with value-based caching ([#3900](https://github.com/zenml-io/zenml/pull/3900))
* More granular cache policy control
* Better pipeline execution control ([#3874](https://github.com/zenml-io/zenml/pull/3874))

</details>

### Breaking Changes

* Local orchestrator now continues execution after step failures
* Docker package installer default switched from pip to uv ([#3935](https://github.com/zenml-io/zenml/pull/3935))
* Log endpoint format changed ([#3845](https://github.com/zenml-io/zenml/pull/3845))

[View full release on GitHub](https://github.com/zenml-io/zenml/releases/tag/0.85.0)

***

## 0.84.3 (2025-08-27)

See what's new and improved in version 0.84.3.

<img src="https://public-flavor-logos.s3.eu-central-1.amazonaws.com/projects/6.jpg" align="left" alt="ZenML 0.84.3" width="800">

#### ZenML Pro Service Account Authentication

* CLI login support via `zenml login --api-key`
* Service account API keys for programmatic access
* Organization-level access for automated workflows

[PR #3895](https://github.com/zenml-io/zenml/pull/3895) | [PR #3908](https://github.com/zenml-io/zenml/pull/3908)

#### ZenML Pro Service Account Authentication

* CLI login support via `zenml login --api-key`
* Service account API keys for programmatic access
* Organization-level access for automated workflows

[PR #3895](https://github.com/zenml-io/zenml/pull/3895) | [PR #3908](https://github.com/zenml-io/zenml/pull/3908)

<details>
<summary>Improved</summary>

* Enhanced Kubernetes resource name sanitization ([#3887](https://github.com/zenml-io/zenml/pull/3887))
* Relaxed Click dependency version constraints ([#3905](https://github.com/zenml-io/zenml/pull/3905))

</details>

[View full release on GitHub](https://github.com/zenml-io/zenml/releases/tag/0.84.3)

***

## 0.84.2 (2025-08-06)

See what's new and improved in version 0.84.2.

<img src="https://public-flavor-logos.s3.eu-central-1.amazonaws.com/projects/7.jpg" align="left" alt="ZenML 0.84.2" width="800">

#### Kubernetes Orchestrator Improvements

* Complete rework using Jobs instead of raw pods
* Better robustness and automatic restarts
* Significantly faster pipeline compilation

[PR #3869](https://github.com/zenml-io/zenml/pull/3869) | [PR #3873](https://github.com/zenml-io/zenml/pull/3873)

#### Kubernetes Orchestrator Improvements

* Complete rework using Jobs instead of raw pods
* Better robustness and automatic restarts
* Significantly faster pipeline compilation

[PR #3869](https://github.com/zenml-io/zenml/pull/3869) | [PR #3873](https://github.com/zenml-io/zenml/pull/3873)

<details>
<summary>Improved</summary>

* Enhanced Kubernetes orchestrator robustness ([#3869](https://github.com/zenml-io/zenml/pull/3869))
* Faster pipeline compilation for large pipelines ([#3873](https://github.com/zenml-io/zenml/pull/3873))
* Better logging performance ([#3872](https://github.com/zenml-io/zenml/pull/3872))

</details>

[View full release on GitHub](https://github.com/zenml-io/zenml/releases/tag/0.84.2)

***

## 0.84.1 (2025-07-30)

See what's new and improved in version 0.84.1.

<img src="https://public-flavor-logos.s3.eu-central-1.amazonaws.com/projects/8.jpg" align="left" alt="ZenML 0.84.1" width="800">

#### Step Exception Handling

* Improved collection of exception information
* Better debugging capabilities

[PR #3838](https://github.com/zenml-io/zenml/pull/3838)

#### External Service Accounts

* Added support for external service accounts
* Improved flexibility

[PR #3793](https://github.com/zenml-io/zenml/pull/3793)

#### Kubernetes Orchestrator Enhancements

* Schedule management capabilities
* Better error handling
* Enhanced pod monitoring

[PR #3847](https://github.com/zenml-io/zenml/pull/3847)

#### Dynamic Fan-out/Fan-in

* Support for dynamic patterns with run templates
* More flexible pipeline architectures

[PR #3826](https://github.com/zenml-io/zenml/pull/3826)

#### Step Exception Handling

* Improved collection of exception information
* Better debugging capabilities

[PR #3838](https://github.com/zenml-io/zenml/pull/3838)

#### External Service Accounts

* Added support for external service accounts
* Improved flexibility

[PR #3793](https://github.com/zenml-io/zenml/pull/3793)

#### Kubernetes Orchestrator Enhancements

* Schedule management capabilities
* Better error handling
* Enhanced pod monitoring

[PR #3847](https://github.com/zenml-io/zenml/pull/3847)

#### Dynamic Fan-out/Fan-in

* Support for dynamic patterns with run templates
* More flexible pipeline architectures

[PR #3826](https://github.com/zenml-io/zenml/pull/3826)

<details>
<summary>Fixed</summary>

* Vertex step operator credential refresh ([#3853](https://github.com/zenml-io/zenml/pull/3853))
* Logging race conditions ([#3855](https://github.com/zenml-io/zenml/pull/3855))
* Kubernetes secret cleanup when orchestrator pods fail ([#3846](https://github.com/zenml-io/zenml/pull/3846))

</details>

[View full release on GitHub](https://github.com/zenml-io/zenml/releases/tag/0.84.1)

***

## 0.84.0 (2025-07-11)

See what's new and improved in version 0.84.0.

<img src="https://public-flavor-logos.s3.eu-central-1.amazonaws.com/projects/9.jpg" align="left" alt="ZenML 0.84.0" width="800">

#### Early Pipeline Stopping

* Stop pipelines early with Kubernetes orchestrator
* Better resource management

[PR #3716](https://github.com/zenml-io/zenml/pull/3716)

#### Step Retries

* Configurable step retry mechanisms
* Improved pipeline resilience

[PR #3789](https://github.com/zenml-io/zenml/pull/3789)

#### Step Status Refresh

* Real-time status monitoring
* Enhanced step status refresh capabilities

[PR #3735](https://github.com/zenml-io/zenml/pull/3735)

#### Performance Improvements

* Thread-safe RestZenStore operations
* Server-side processing improvements
* Enhanced pipeline/step run fetching

[PR #3758](https://github.com/zenml-io/zenml/pull/3758) | [PR #3762](https://github.com/zenml-io/zenml/pull/3762) | [PR #3776](https://github.com/zenml-io/zenml/pull/3776)

#### UI Updates

* Refactor Onboarding ([#772](https://github.com/zenml-io/zenml-dashboard/pull/772)) & Survey ([#770](https://github.com/zenml-io/zenml-dashboard/pull/770))
* Stop Runs directly from UI ([#755](https://github.com/zenml-io/zenml-dashboard/pull/755))
* Step Refresh ([#773](https://github.com/zenml-io/zenml-dashboard/pull/773))
* Support multiple log origins ([#769](https://github.com/zenml-io/zenml-dashboard/pull/769))

<details>
<summary>Improved</summary>

* New ZenML login experience ([#3790](https://github.com/zenml-io/zenml/pull/3790))
* Enhanced Kubernetes orchestrator pod caching ([#3719](https://github.com/zenml-io/zenml/pull/3719))
* Easier step operator/experiment tracker configuration ([#3774](https://github.com/zenml-io/zenml/pull/3774))
* Orchestrator pod logs access ([#3778](https://github.com/zenml-io/zenml/pull/3778))

</details>

<details>
<summary>Fixed</summary>

* Fixed model version fetching by UUID ([#3777](https://github.com/zenml-io/zenml/pull/3777))
* Visualization handling improvements ([#3769](https://github.com/zenml-io/zenml/pull/3769))
* Fixed data artifact fetching ([#3811](https://github.com/zenml-io/zenml/pull/3811))
* Path and Docker tag sanitization ([#3816](https://github.com/zenml-io/zenml/pull/3816) | [#3820](https://github.com/zenml-io/zenml/pull/3820))

</details>

### Breaking Changes

* Kubernetes Orchestrator Compatibility: Client and orchestrator pod versions must match exactly

[View full release on GitHub](https://github.com/zenml-io/zenml/releases/tag/0.84.0)

***
