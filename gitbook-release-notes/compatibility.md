---
description: >-
  Which ZenML client versions keep working when you upgrade your ZenML server
  or ZenML Pro workspace, and what changed in each release.
icon: code-compare
---

# Compatibility

Use this page before you upgrade a ZenML server or a ZenML Pro workspace. It shows which client versions keep working against which server versions, and what each release changed for existing clients.

{% hint style="info" %}
This page covers the ZenML server and SDK. It does not cover ZenML Pro control plane versions yet.
{% endhint %}

## How to read this page

* **Client** is the `zenml` Python package your team runs, including the version installed in your pipeline snapshot images. **Server** is your ZenML server or ZenML Pro workspace.
* Find your client version in the rows of the matrix and the server version you want in its columns.
* Before you upgrade, read every row under **Release by release** between the version you run today and the one you want.
* The matrix works per minor release. When a breaking point lands in a patch release, its description says so.

## Upgrade rules

* Keeping the client and the server on the same version is always the safest setup.
* Upgrade the server first, then the clients. A client newer than its server is not supported.
* Downgrading a server is not supported. Back up the database before you upgrade a self-hosted server.
* Pipeline snapshots run with the ZenML version installed in their image, so they behave like a client of that version. Rebuild them when the matrix shows an exception that affects you, and always when you cross a hard break.
* ZenML Pro: upgrade the control plane before the workspaces.

## Client and server matrix

Rows are the client version, columns are the server version, grouped by minor release (0.98 covers 0.98.0, 0.98.1, and so on). ✅ works. ⚠️ works, except for the listed breaking points. – the client is newer than the server, which is not supported.

Each hard break starts a new era. A client and a server from different eras do not work together: upgrade both at the same time.

**ZenML 0.90 and later**

| Client ↓ / Server → | 0.90 | 0.91 | 0.92 | 0.93 | 0.94 | 0.95 | 0.96 | 0.97 | 0.98 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **0.90** | ✅ | ✅ | ⚠️ E2 | ⚠️ E2 E3 E4 | ⚠️ E2 E3 E4 E5 E6 E7 | ⚠️ E2 E3 E4 E5 E6 E7 E8 | ⚠️ E2 E3 E4 E5 E6 E7 E8 | ⚠️ E2 E3 E4 E5 E6 E7 E8 E9 | ⚠️ E2 E3 E4 E5 E6 E7 E8 E9 |
| **0.91** | – | ✅ | ⚠️ E2 | ⚠️ E2 E3 E4 | ⚠️ E2 E3 E4 E5 E6 E7 | ⚠️ E2 E3 E4 E5 E6 E7 E8 | ⚠️ E2 E3 E4 E5 E6 E7 E8 | ⚠️ E2 E3 E4 E5 E6 E7 E8 E9 | ⚠️ E2 E3 E4 E5 E6 E7 E8 E9 |
| **0.92** | – | – | ✅ | ⚠️ E3 E4 | ⚠️ E3 E4 E5 E6 E7 | ⚠️ E3 E4 E5 E6 E7 E8 | ⚠️ E3 E4 E5 E6 E7 E8 | ⚠️ E3 E4 E5 E6 E7 E8 E9 | ⚠️ E3 E4 E5 E6 E7 E8 E9 |
| **0.93** | – | – | – | ✅ | ⚠️ E5 E6 E7 | ⚠️ E5 E6 E7 E8 | ⚠️ E5 E6 E7 E8 | ⚠️ E5 E6 E7 E8 E9 | ⚠️ E5 E6 E7 E8 E9 |
| **0.94** | – | – | – | – | ✅ | ⚠️ E8 | ⚠️ E8 | ⚠️ E8 E9 | ⚠️ E8 E9 |
| **0.95** | – | – | – | – | – | ✅ | ✅ | ⚠️ E9 | ⚠️ E9 |
| **0.96** | – | – | – | – | – | – | ✅ | ⚠️ E9 | ⚠️ E9 |
| **0.97** | – | – | – | – | – | – | – | ✅ | ✅ |
| **0.98** | – | – | – | – | – | – | – | – | ✅ |

<details>
<summary>ZenML 0.83 to 0.85</summary>

| Client ↓ / Server → | 0.83 | 0.84 | 0.85 |
| --- | --- | --- | --- |
| **0.83** | ✅ | ✅ | ⚠️ E1 |
| **0.84** | – | ✅ | ⚠️ E1 |
| **0.85** | – | – | ✅ |

</details>

<details>
<summary>ZenML 0.80 to 0.82</summary>

| Client ↓ / Server → | 0.80 | 0.81 | 0.82 |
| --- | --- | --- | --- |
| **0.80** | ✅ | ✅ | ✅ |
| **0.81** | – | ✅ | ✅ |
| **0.82** | – | – | ✅ |

</details>

## Breaking points

Each row is a release from which older clients lose something. A **hard break** means clients older than that release do not work with the server at all. An **exception** means they keep working, except for what is described.

| ID | Since | Type | What breaks for older clients |
| --- | --- | --- | --- |
| E9 | 0.97.0 | Exception | ZenML Pro only: the old resource pool endpoints were removed, so clients 0.94.3 to 0.96.x can't manage resource pools, and their dynamic pipeline steps that request pooled resources fail. |
| E8 | 0.95.0 | Exception | The new `sandbox` component type: older clients fail on unfiltered flavor listings and can't load a stack that contains a sandbox. |
| E7 | 0.94.1 | Exception | The new `override` step input type: older clients can't read steps whose inputs were overridden in a replay. |
| E6 | 0.94.0 | Exception | The event source, action, and trigger execution APIs were removed, so the trigger and event source features of older clients no longer work. |
| E5 | 0.94.0 | Exception | New run and step statuses: `skipped` (0.94.0), `paused` and `resuming` (0.94.1), and `queued`, `cancelling`, and `cancelled` (0.94.3). Older clients fail to list or fetch runs or steps in a status they don't know. Within 0.94, use 0.94.3 or later clients. |
| E4 | 0.93.0 | Exception | The new `log_store` component type: older clients fail on unfiltered flavor listings and can't load a stack that contains a log store. |
| E3 | 0.93.0 | Exception | Run and step responses no longer include `logs`, and the `/pipelines/{id}/runs` endpoint was removed. Older clients don't fail, but `run.logs` and `step.logs` are empty, and steps they run on step operators no longer store logs. |
| E2 | 0.92.0 | Exception | No server change, but older clients may fail to read the inputs of map/reduce steps in dynamic pipelines run by newer clients. |
| H2 | 0.90.0 | Hard break | Older clients can't start runs. Run templates are migrated to snapshots automatically, but their images contain the older ZenML, so rebuild them with 0.90 or later before running them. |
| E1 | 0.85.0 | Exception | Older clients can't fetch or list pipeline runs while a run in the result is in the new `provisioning` status. Run and step log endpoints return structured entries instead of text, which only affects direct API calls. |
| H1 | 0.83.0 | Hard break | Response payloads were restructured, so older clients can't read runs, artifacts, or models. |

## Release by release

**Server impact** is what happens to existing clients when the server is upgraded to that release. **Client upgrade notes** are what a team must change when it upgrades its own client.

| Release | Status | Server impact on existing clients | Client upgrade notes |
| --- | --- | --- | --- |
| 0.98.1 | ✅ Compatible | None known. | – |
| 0.98.0 | ✅ Compatible | None known. | The LangChain integration now accepts `langchain>=0.3.5,<1.0` instead of a fixed 0.3.0 pin. |
| 0.97.0 | ⚠️ Exceptions (E9) | ZenML Pro: the old resource pool endpoints were removed. | Needs Click 8.3.3 to 8.5.0. Custom log stores must adopt the new `fetch()` signature. Dict outputs with non-string keys may read back with different key types. |
| 0.96.4 | ✅ Compatible | None known. | – |
| 0.96.3 | ✅ Compatible | None known. | – |
| 0.96.2 | ✅ Compatible | None known. | – |
| 0.96.1 | ✅ Compatible | None known. | – |
| 0.96.0 | ✅ Compatible | None known. | – |
| 0.95.1 | ✅ Compatible | None known. | – |
| 0.95.0 | ⚠️ Exceptions (E8) | Adds the `sandbox` component type, which older clients don't know. | Adds Python 3.14 support. The Modal step operator now needs `modal>=1`. |
| 0.94.6 | ✅ Compatible | None known. | – |
| 0.94.5 | ✅ Compatible | None known. | – |
| 0.94.4 | ✅ Compatible | None known. | – |
| 0.94.3 | ⚠️ Exceptions (E5) | Adds the `queued`, `cancelling`, and `cancelled` statuses. | Fixes a Python 3.10 import issue. |
| 0.94.2 | ✅ Compatible | None known. | Self-hosted only: a top-level Helm chart key was renamed; the old key is still accepted. |
| 0.94.1 | ⚠️ Exceptions (E5, E7) | Adds the `paused` and `resuming` statuses and the `override` step input type. | – |
| 0.94.0 | ⚠️ Exceptions (E5, E6) | Adds the `skipped` status and removes the event source, action, and trigger execution APIs. | – |
| 0.93.3 | ✅ Compatible | None known. | – |
| 0.93.2 | ✅ Compatible | None known. | The Neptune integration is deprecated. |
| 0.93.1 | ✅ Compatible | None known. | Fixes the run count DB migration from 0.93.0. |
| 0.93.0 | ⚠️ Exceptions (E3, E4) | Run and step responses no longer include `logs`, and the `log_store` component type was added. | Use `log_collection` instead of `logs`, and list runs with a pipeline filter instead of `/pipelines/{id}/runs`. |
| 0.92.0 | ⚠️ Exceptions (E2) | No server change. Older clients may fail on the inputs of map/reduce steps run by newer clients. | `regular_inputs` on step runs now returns a list per input name, so code that reads it needs updating. |
| 0.91.2 | ✅ Compatible | None known. | – |
| 0.91.1 | ✅ Compatible | None known. | API tokens are deprecated in favor of personal access tokens. |
| 0.91.0 | ✅ Compatible | None known. | Drops Python 3.9. Model deployers are deprecated. |
| 0.90.0 | ❌ Hard break (H2) | Older clients can't start runs. | Rebuild the images of run templates (now snapshots) with 0.90 or later. Install `zenml[local]` for local use. Custom components: `prepare_pipeline_deployment` was removed. |
| 0.85.0 | ⚠️ Exceptions (E1) | Runs in the new `provisioning` status break run listings on older clients, and log endpoints return structured entries. | The Docker installer defaults to uv. The local orchestrator keeps going after a step fails. |
| 0.84.3 | ✅ Compatible | None known. | – |
| 0.84.2 | ✅ Compatible | None known. | The Kubernetes orchestrator moved to Jobs; some of its settings are deprecated. |
| 0.84.1 | ✅ Compatible | None known. | – |
| 0.84.0 | ✅ Compatible | None known. | – |
| 0.83.1 | ✅ Compatible | None known. | – |
| 0.83.0 | ❌ Hard break (H1) | Response payloads were restructured; older clients can't read runs, artifacts, or models. | `Model.get_pipeline_run` was removed. |
| 0.82.1 | ✅ Compatible | None known. | – |
| 0.82.0 | ✅ Compatible | None known. | The sklearn integration no longer installs scikit-image. |
| 0.81.0 | ✅ Compatible | None known. | – |
| 0.80.2 | ✅ Compatible | None known. | – |
