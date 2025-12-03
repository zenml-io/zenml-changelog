---
description: Changelog for ZenML Pro.
icon: clock-rotate-left
---

# ZenML Pro Changelog

Stay up to date with the latest features, improvements, and fixes in ZenML Pro.

## 0.12.19 (2025-11-19)

See what's new and improved in version 0.12.19.

<img src="https://public-flavor-logos.s3.eu-central-1.amazonaws.com/projects/31.jpg" align="left" alt="ZenML Pro 0.12.19" width="800">

**General Updates**

* Maintenance and release preparation
* Continued improvements to platform stability

### What's Changed

* General maintenance and release preparation (#462)

> **Compatibility:** Requires ZenML Server and SDK v0.85.0 or later.

***

## 0.12.18 (2025-11-12)

See what's new and improved in version 0.12.18.

<img src="https://public-flavor-logos.s3.eu-central-1.amazonaws.com/projects/32.jpg" align="left" alt="ZenML Pro 0.12.18" width="800">

**General Updates**

* Maintenance and release preparation
* Continued improvements to platform stability

### What's Changed

* General maintenance and release preparation (#460)

> **Compatibility:** Requires ZenML Server and SDK v0.85.0 or later.

***

## 0.12.17 (2025-11-05)

See what's new and improved in version 0.12.17.

<img src="https://public-flavor-logos.s3.eu-central-1.amazonaws.com/projects/20.jpg" align="left" alt="ZenML Pro 0.12.17" width="800">

**Lambda Function Updates**

* Updated Python version for Lambda functions
* Improved performance and compatibility

**Authentication Enhancements**

* API keys and PATs can be used as bearer tokens
* Configurable expiration for API keys

**Vault Secret Store**

* Support for new Hashicorp Vault secret store auth method settings
* Enhanced security options

**Codespaces**

* JupyterLab support added to Codespaces
* Enhanced development environment

### Improved

* Lambda function Python version updates (#450)
* Enhanced authentication flexibility (#453, #454)
* Better Codespace development experience (#455)

> **Compatibility:** Requires ZenML Server and SDK v0.85.0 or later.

***

## 0.12.16 (2025-10-27)

See what's new and improved in version 0.12.16.

<img src="https://public-flavor-logos.s3.eu-central-1.amazonaws.com/projects/33.jpg" align="left" alt="ZenML Pro 0.12.16" width="800">

**General Updates**

* Maintenance and release preparation
* Continued improvements to platform stability

### What's Changed

* General maintenance and release preparation (#449)

> **Compatibility:** Requires ZenML Server and SDK v0.85.0 or later.

***

## 0.12.15 (2025-10-16)

See what's new and improved in version 0.12.15.

<img src="https://public-flavor-logos.s3.eu-central-1.amazonaws.com/projects/34.jpg" align="left" alt="ZenML Pro 0.12.15" width="800">

**Bug Fixes**

* Filter long user avatar URLs at source for older workspace versions
* Improved compatibility with legacy workspace versions

### Fixed

* Filter long user avatar URLs at source for older workspace versions (<= 0.90.0) (#447)

> **Compatibility:** Requires ZenML Server and SDK v0.85.0 or later.

***

## 0.12.14 (2025-10-02)

See what's new and improved in version 0.12.14.

<img src="https://public-flavor-logos.s3.eu-central-1.amazonaws.com/projects/35.jpg" align="left" alt="ZenML Pro 0.12.14" width="800">

**General Updates**

* Maintenance and release preparation
* Continued improvements to platform stability

### What's Changed

* General maintenance and release preparation (#446)

> **Compatibility:** Requires ZenML Server and SDK v0.85.0 or later.

***

## 0.12.12 (2025-09-16)

See what's new and improved in version 0.12.12.

<img src="https://public-flavor-logos.s3.eu-central-1.amazonaws.com/projects/22.jpg" align="left" alt="ZenML Pro 0.12.12" width="800">

**Service Account Enhancements**

* Service accounts can now invite users
* Improved automation capabilities

> **Compatibility:** Requires ZenML Server and SDK v0.85.0 or later.

***

## 0.12.11 (2025-09-15)

See what's new and improved in version 0.12.11.

<img src="https://public-flavor-logos.s3.eu-central-1.amazonaws.com/projects/23.jpg" align="left" alt="ZenML Pro 0.12.11" width="800">

**Service Account Features**

* Service accounts can invite users
* Enhanced collaboration capabilities

> **Compatibility:** Requires ZenML Server and SDK v0.85.0 or later.

***

## 0.12.10 (2025-08-28)

See what's new and improved in version 0.12.10.

<img src="https://public-flavor-logos.s3.eu-central-1.amazonaws.com/projects/24.jpg" align="left" alt="ZenML Pro 0.12.10" width="800">

**Service Account Authentication**

* Service accounts can authenticate to workspaces
* Better team resource management

### Improved

* Service account authentication to workspaces (#433)
* Team resource member testing (#430)
* Default workspace version updates (#434)
* Run template resource improvements (#435)

> **Compatibility:** Requires ZenML Server and SDK v0.85.0 or later.

***

## 0.12.9

See what's new and improved in version 0.12.9.

<img src="https://public-flavor-logos.s3.eu-central-1.amazonaws.com/projects/36.jpg" align="left" alt="ZenML Pro 0.12.9" width="800">

**General Updates**

* Maintenance and release preparation
* Continued improvements to platform stability

### What's Changed

* General maintenance and release preparation (#431)

> **Compatibility:** Requires ZenML Server and SDK v0.85.0 or later.

***

## 0.12.8

See what's new and improved in version 0.12.8.

<img src="https://public-flavor-logos.s3.eu-central-1.amazonaws.com/projects/25.jpg" align="left" alt="ZenML Pro 0.12.8" width="800">

**Workspace Features**

* Workspaces can now be renamed
* Improved workspace management

> **Compatibility:** Requires ZenML Server and SDK v0.85.0 or later.

***

## 0.12.7

See what's new and improved in version 0.12.7.

<img src="https://public-flavor-logos.s3.eu-central-1.amazonaws.com/projects/26.jpg" align="left" alt="ZenML Pro 0.12.7" width="800">

**RBAC Enhancements**

* Schedule RBAC enabled
* Team viewer default role added

> **Compatibility:** Requires ZenML Server and SDK v0.85.0 or later.

***

## 0.12.6

See what's new and improved in version 0.12.6.

<img src="https://public-flavor-logos.s3.eu-central-1.amazonaws.com/projects/27.jpg" align="left" alt="ZenML Pro 0.12.6" width="800">

**Service Account Improvements**

* Specify initial service account role
* New fields in service account schema and models

**Workspace Controls**

* Prevent users from creating/updating workspaces to older ZenML releases
* Prevent users from updating the onboarded flag

### Improved

* Service account role configuration (#416)
* Enhanced service account schema (#419)
* Better workspace version control (#421, #422)

### Fixed

* Service account fixes and membership filtering (#424)

> **Compatibility:** Requires ZenML Server and SDK v0.85.0 or later.

***

## 0.12.5

See what's new and improved in version 0.12.5.

<img src="https://public-flavor-logos.s3.eu-central-1.amazonaws.com/projects/28.jpg" align="left" alt="ZenML Pro 0.12.5" width="800">

**Onboarding**

* User onboarded flag implementation
* Better user experience tracking

### Improved

* User onboarding tracking (#414)
* Dependency updates (#418)

> **Compatibility:** Requires ZenML Server and SDK v0.85.0 or later.

***

## 0.12.3

See what's new and improved in version 0.12.3.

<img src="https://public-flavor-logos.s3.eu-central-1.amazonaws.com/projects/29.jpg" align="left" alt="ZenML Pro 0.12.3" width="800">

**Codespaces**

* Delete codespaces when cleaning up expired tenants
* Improved resource management

### Improved

* Codespace cleanup automation (#403)
* Workspace default version updates (#407)

> **Compatibility:** Requires ZenML Server and SDK v0.85.0 or later.

***

## 0.12.2

See what's new and improved in version 0.12.2.

<img src="https://public-flavor-logos.s3.eu-central-1.amazonaws.com/projects/30.jpg" align="left" alt="ZenML Pro 0.12.2" width="800">

**Codespaces**

* Add `zenml_active_project_id` to CodespaceCreate model
* Delete Codespaces on Workspace Delete

**Workspace Storage**

* Workspace storage usage count, limiting, and cleanup
* Better resource management

> **Compatibility:** Requires ZenML Server and SDK v0.85.0 or later.

***

## 0.12.0

See what's new and improved in version 0.12.0.

<img src="https://public-flavor-logos.s3.eu-central-1.amazonaws.com/projects/21.jpg" align="left" alt="ZenML Pro 0.12.0" width="800">

**Codespaces**

* Introducing Codespaces to Cloud API
* Enhanced development environment support

**Workspace Storage**

* Workspace storage usage count, limiting, and cleanup
* Better resource management

**Infrastructure**

* Provision shared workspace bucket with Terraform
* Improved infrastructure as code support

**RBAC**

* More permissions handling for internal users
* Enhanced access control

### Improved

* Codespaces integration (#380)
* Workspace storage management (#402)
* Terraform infrastructure support (#396)
* RBAC improvements (#392)
* Team member management (#397)

</details>

### Breaking Changes

* Kubernetes Orchestrator Compatibility: Client and orchestrator pod versions must match exactly

> **Compatibility:** Requires ZenML Server and SDK v0.85.0 or later.

***
