---
description: Changelog for ZenML Pro.
icon: clock-rotate-left
---

# ZenML Pro Changelog

Stay up to date with the latest features, improvements, and fixes in ZenML Pro.

## 0.13.1 (2026-01-30)

See what's new and improved in version 0.13.1.

<img src="https://public-flavor-logos.s3.eu-central-1.amazonaws.com/projects/6.jpg" align="left" alt="ZenML Pro 0.13.1" width="800">

#### Enhanced Workspace Management

Workspace comparison tables now display workspace descriptions and tags, making it easier to understand and differentiate between workspaces at a glance.

#### Stack and Component Visibility

Stacks and components now display their associated labels in a collapsible view, providing better organization and discoverability of your infrastructure resources.

#### Improved Invitation System

The invitation workflow has been completely redesigned:
- Users now have a dedicated view to manage all their open invitations in one place
- Organization administrators can now assign roles to invitations before they are accepted, streamlining the onboarding process

#### Pipeline Code Download

You can now download pipeline code directly from the dashboard. A new **Download** button is available in the "Code Path" section on both the Pipeline Run details page and the Step details sheet, making it easier to access and review your pipeline implementations.

#### Better Error Visibility

Pipeline exception information is now displayed for dynamic pipelines, helping you quickly identify and troubleshoot issues in your pipeline runs.

> **Compatibility:** Requires ZenML Server and SDK v0.85.0 or later.

***

## 0.13.0 (2026-01-30)

See what's new and improved in version 0.13.0.

<img src="https://public-flavor-logos.s3.eu-central-1.amazonaws.com/projects/5.jpg" align="left" alt="ZenML Pro 0.13.0" width="800">

#### Stack Management Improvements

Users can now **update existing stacks directly from the UI** without needing to delete and recreate them. A new dedicated stack update page allows you to modify stack configurations, add new components, or replace existing ones (orchestrators, artifact stores, container registries, etc.). Access the update functionality from the stack detail sheet or the stacks dropdown menu for more efficient stack management.

#### Enhanced Artifact Version Experience

The Artifact Version view has been completely revamped with a new unified detail page featuring a modern 3-panel layout. Navigate through artifact versions with a searchable, paginated list on the left panel, while viewing detailed version information in the center and right panels. Tag display and management have been improved across all artifact-related screens, and existing deep links continue to work seamlessly via automatic redirects.

#### Dedicated Logs Viewer

Pipeline runs now feature a **standalone logs page** with a dedicated URL, making debugging and monitoring much easier. The new logs viewer includes:

- A sidebar for navigating between run-level logs and individual step logs
- Virtualized rendering for better performance with large log outputs
- Built-in search and filtering capabilities
- Step duration display in the sidebar for quick performance insights

#### Team and Role Management for Invitations

Invitations are now more flexible and powerful:

- **Assign roles to invitations**: Instead of a single static role, you can now assign multiple roles to invitations, just like with users and teams. When the invitation is accepted, those roles are automatically transferred to the new user account.
- **Add invitations to teams**: Invitations can now be added to teams directly. Once accepted, the user automatically becomes a member of the assigned team, streamlining the onboarding process.

#### Generic OAuth2/OIDC Integration

ZenML Pro now supports **generic OAuth2/OIDC authentication** for on-premises deployments, allowing integration with any OAuth2/OIDC-compliant identity provider such as Google, GitHub, Azure AD, or Keycloak. This provides greater flexibility in authentication options beyond Auth0, which remains available as an optional integration when configured.

> **Compatibility:** Requires ZenML Server and SDK v0.85.0 or later.

***

## 0.12.22 (2026-01-14)

See what's new and improved in version 0.12.22.

<img src="https://public-flavor-logos.s3.eu-central-1.amazonaws.com/projects/4.jpg" align="left" alt="ZenML Pro 0.12.22" width="800">

#### Stack Management

You can now update existing stacks directly from the UI without needing to delete and recreate them. A new dedicated stack update page allows you to modify stack configurations, add new components, or replace existing ones (orchestrators, artifact stores, container registries, etc.). Access the update functionality from the stack detail sheet or the stacks dropdown menu.

#### Artifact Version View

The artifact version experience has been completely revamped with a new unified detail view:

- **Three-panel layout**: Navigate through a searchable, paginated list of versions in the left panel, view detailed version information in the center, and access related metadata on the right
- **Improved tag management**: Better tag display and management across all artifact-related screens
- **Seamless navigation**: Existing deep links continue to work through automatic redirects

#### Logs Viewer

Pipeline run logs are now easier to navigate and debug:

- **Dedicated logs page**: Each pipeline run has a standalone logs page with a direct URL for easy sharing and bookmarking
- **Sidebar navigation**: Quickly switch between run-level logs and individual step logs, with step duration information displayed for each step
- **Enhanced performance**: Virtualized rendering handles large log outputs smoothly
- **Search and filter**: Find specific log entries quickly with built-in search and filtering capabilities

> **Compatibility:** Requires ZenML Server and SDK v0.85.0 or later.

***

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
