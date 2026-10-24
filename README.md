# OCI Access Governance with Ansible

Parameterized provisioning for `oagTest`, an immediate child of the OCI tenancy root.

## What runs automatically

| Resource | Placement / behavior |
|---|---|
| `oagTest` compartment | Directly under tenancy root |
| `agcs_user`, `agcs_group` | Existing **Default identity domain**, connector service account |
| Parameterized admin user, `oag_admin_group` | Default identity domain, separate human administrator |
| `OCI_AGCS` policy | Root; connector can read all resources, manage policies, and manage domains across tenancy |
| `OAG_TEST_ADMIN` policy | Root; admin can read the namespace and manage OAG instances within `oagTest` |
| Two RSA API key pairs | Local private keys; public keys registered against the respective OCI users |
| OAG service instance | `oagTest`, tenancy home region; waits for provisioning |
| OAG Administrator application role | Optional automated grant when the service application and role SCIM IDs are supplied |
| Deployment output | `artifacts/deployment.json`, including desired identity activation selections |

**Users and groups belong to identity domains, not directly to compartments.** This implementation follows Oracle's Default-domain OCI connector setup. It does not create a new identity domain in `oagTest`. The instance and instance-management permission are scoped to the child compartment. The requested connector privileges remain tenancy-wide.

The bootstrap account that runs Ansible must already have access to manage compartments and root policies, manage Default-domain users/groups/capabilities and credentials, read region subscriptions and the Object Storage namespace, and create OAG instances. Optional role assignment also requires IAM application-role administration. The newly created administrator is not the bootstrap identity.

## Run

Use Python 3.10+ on Linux or macOS. Internet access to PyPI/Galaxy and the OCI API endpoints is required. In this directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
ansible-galaxy collection install -r requirements.yml -p ./collections
export ANSIBLE_COLLECTIONS_PATH="$PWD/collections"
cp vars.example.yml vars.local.yml
chmod 600 vars.local.yml
```

Edit `vars.local.yml`, replacing all example values. Configure an existing bootstrap OCI API profile in `~/.oci/config`; its private key remains outside this project. Use `oci_config_file` and `oci_profile` to select a different profile. Do not use the generated connector profile to bootstrap the deployment.

```bash
ansible-playbook site.yml --syntax-check
ansible-playbook site.yml -e @vars.local.yml -e "ansible_python_interpreter=$VIRTUAL_ENV/bin/python"
```

The full provisioning play does not support `--check`: later resources depend on real compartment/user IDs and public keys. Use `--syntax-check` for parsing validation. Placeholder or empty required parameters fail before resource creation. No tenancy credentials or live infrastructure changes were used during artifact preparation.

If your tenancy requires an IDCS access token for instance creation, inject `OAG_IDCS_ACCESS_TOKEN` from your secret manager into the process environment. The provisioning task suppresses token output. Confirm that `license_type` matches your purchased entitlement; the default API value is `NEW_LICENSE`, and deployment can incur service charges.

## Finish service onboarding

Follow [docs/ONBOARDING.md](docs/ONBOARDING.md) for password initialization, the OAG Administrator application role, OCI IAM connected-system creation, data load verification, additional systems, and activation rules. These are explicit post-provision steps. The playbook does **not** mark them completed or claim that an activation manifest changes OAG.

The published functional API catalog reviewed on 2026-10-24 lists orchestrated-system queries and per-identity activation, but does not document creating the OCI connector or publishing the ongoing Manage Identities membership rules. This project uses the documented console flow for those steps rather than an assumed private API.

## Outputs and repeat runs

`artifacts/keys/connector.pem` and `admin.pem` are generated at deployment time with mode `0600`, under directories with mode `0700`. Matching public PEM files and separate `*_oci_config` files contain the OCI user, fingerprint, tenancy, region and key location. The connector key authenticates OAG **to OCI IAM**. It is not an OAG application login or an OAuth bearer token for OAG functional APIs.

Preserve these files between runs. Keys are never automatically regenerated, and uploaded public keys are matched by the OCI module. OCI supports a limited number of keys per user; intentional rotation requires uploading a replacement, updating consumers, testing, and retiring the old public key separately. Private keys here are unencrypted PEMs intended for connector import; keep the directory on protected storage and move durable copies to your secret manager.

Named OCI resources use the Oracle collection's name-as-identifier support. Domain lookups reject ambiguous matches; existing users with a different email or inactive status cause a failure. Group memberships are additive. Existing user profiles are preserved, and API-key capability is enabled. No delete or cleanup operation is included. Give each deployment unique policy/resource names if it must coexist with other automation.

## Validation

```bash
python -m unittest discover -s tests -v
ansible-playbook site.yml --syntax-check
```

Tests exercise SCIM pagination, additive memberships, user collision handling and application-role idempotency using mocks, and instantiate the real OCI SDK payloads. These do not verify a live OCI tenancy. Validate the generated deployment in a test tenancy before production use.

## Oracle references

- [Service instance prerequisites and home-region restriction](https://docs.oracle.com/en-us/iaas/Content/access-governance/set-up-service-instance.htm)
- [OCI IAM connector setup](https://docs.oracle.com/en/cloud/paas/access-governance/agiam/index.html)
- [OAG user and application-role setup](https://docs.oracle.com/en-us/iaas/Content/access-governance/set-up-users.htm)
- [Manage Identities and membership rules](https://docs.oracle.com/en-us/iaas/Content/access-governance/manage-identities.htm)
- [Functional REST API endpoint catalog](https://docs.oracle.com/en/cloud/paas/access-governance/pmapi/rest-endpoints.html)
- [Oracle OCI Ansible collection source](https://github.com/oracle/oci-ansible-collection)
