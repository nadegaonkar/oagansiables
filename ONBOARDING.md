# Complete OAG setup after Ansible provisioning

This is a parameter-driven console runbook. Values come from `vars.local.yml`, generated `artifacts/deployment.json`, and `artifacts/keys/connector_oci_config`. No connection or rule is applied merely by generating those files.

## 1. Give the human administrator access

In OCI Console, open **Identity & Security → Domains → Default → Users** and select the configured `admin_username`. Complete initial account activation or password reset as required by the domain's policy, and enroll MFA. Ansible does not set a human password or change domain-wide authentication policies.

After the service instance is active, locate its associated Oracle Access Governance application under the domain's **Oracle Cloud Services**. Open **Application roles**, select its Administrator role, and assign `admin_group_name`. Verify that the role is for this specific service instance. IAM `manage agcs-instance` permissions alone do not grant OAG functional administration.

Alternatively, obtain the application's SCIM `id` and the Administrator AppRole SCIM `id` from the IAM domain API or application details, set `oag_application_id` and `oag_administrator_role_id`, and rerun Ansible. These IDs differ from OCI OCIDs. The optional module verifies the role belongs to the app and preserves other grants. The operator is responsible for selecting the OAG Administrator role of the intended instance.

Launch the generated `instance_url` and verify that the configured administrator can access **Service Administration**.

## 2. Connect this OCI tenancy

Open **Service Administration → Connected Systems**, or the corresponding **Orchestrated Systems** area if your service uses that navigation. Add an **Oracle Cloud Infrastructure** connection named `oci_connected_system_name` (no spaces).

Use the generated connector OCI profile for the tenancy, user OCID, home region and fingerprint. Supply the connector private PEM through the credential input provided by the connector. Use `agcs_user`, not the human administrator. If the wizard uses Vault-backed credentials, store the PEM through that credential flow and grant the required Vault access; this project does not create a Vault.

Validate connectivity, then wait for the initial full load to succeed. Record the connection ID and verify the expected OCI domains and users appear. The connector maintains incremental synchronization on its service-managed schedule; check the deployed connector's schedule/settings. Troubleshoot policy propagation, enabled API-key capability, fingerprint/PEM pairing and region before retrying a failed load.

The requested `OCI_AGCS` policy is tenancy-wide. Placing the OAG instance in `oagTest` does not restrict the connector's inventory to that compartment. OCI domain users are not owned by ordinary application compartments.

## 3. Add other connected systems

For each entry in `additional_connected_systems`, identify its connector type, endpoint, source/managed-system role, authentication method, network route, owner and matching key. Add it using its documented connector wizard. Behind-firewall systems can require a deployed OAG agent; configure that agent and credentials before validating.

Test connectivity, inspect a small representative full load, define correlation/matching rules against a stable unique identifier, and verify that accounts join the intended identities. Do not assume equal display names identify the same person. Only turn on outbound fulfillment after validating mappings and provisioning behavior. Connector-specific endpoints and secrets remain parameters; there is no generic automatic deployment for an unspecified system.

## 4. Select identities for governance

Synchronization imports source data. OAG activation determines which imported identities participate in governance and consume the applicable entitlement. Activation filters do not remove already imported data or limit the connector's OCI read permissions.

In **Service Administration → Manage Identities → Active**, edit the membership rule. Older versions may show **Manage Identities** directly and use **Save/Confirm** instead of **Publish**. Choose the attribute names and values actually present in your ingested data.

For the domain allowlist in `activation_domain_ocids`, the desired expression is:

```text
(Domain OCID = domain_A OR Domain OCID = domain_B ...)
AND Status = activation_status_value
```

For one domain use **All** with Domain OCID Equals that OCID and Status Equals the source's enabled-status value. For multiple domains, use an available multi-value operator or nested OR domain group under an outer AND. If this UI version only supports a flat Any/All rule, do not replace the expression with `Any(domain_A, domain_B, enabled)` or `All(domain_A, domain_B, enabled)`; use separate supported selections/rule groups, or select the intended named identities explicitly. Verify the preview before publishing.

Use **Included named identities** for `activation_named_identities` and **Manage exclusions** for `activation_excluded_identities`. Named inclusions can extend membership beyond the attribute rule: add only explicitly authorized users. Resolve each name to the correct domain/account in the preview; names alone can be ambiguous. Exclude the connector and other service accounts if they should not participate in governance.

When `activation_domain_ocids` and `activation_named_identities` are both empty, no identities are selected by this project. Do not use a broad substring such as Domain OCID contains `ocid` to implement an allowlist.

Preview matching identities and counts; check one intended active identity, an excluded identity, an identity in an unselected domain and a disabled identity. Confirm license coverage and publish through any configured approval workflow. Recheck the resulting active population after the next successful source synchronization.

## 5. Acceptance record

Record these results in your change record:

- `oagTest` parent OCID equals the tenancy OCID; service instance is active in that child.
- `OCI_AGCS` has the three intended tenancy statements and the correct connector group OCID.
- The administrator can manage the OAG instance and has its OAG Administrator application role.
- Both API key fingerprints correspond to the correct users; private PEMs are stored securely.
- OCI connector validation and full load succeeded; expected domains/accounts appear.
- Every additional connection has passed connector-specific validation and matching checks.
- Activation preview and final active population match the approved domains/users/exclusions.
- A second Ansible run reuses the existing compartment, users, groups, keys and instance.

Oracle sources: [OCI connector tutorial](https://docs.oracle.com/en/cloud/paas/access-governance/agiam/index.html), [application roles](https://docs.oracle.com/en-us/iaas/Content/access-governance/set-up-users.htm), [Manage Identities](https://docs.oracle.com/en-us/iaas/Content/access-governance/manage-identities.htm), [orchestration components](https://docs.oracle.com/en-us/iaas/Content/access-governance/identity-orchestration-components-and-process-flow.htm).
