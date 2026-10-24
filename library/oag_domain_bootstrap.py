#!/usr/bin/python
"""Ensure Default-domain users, groups, API capabilities and additive memberships."""
from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.oag_common import clients, connection_spec, scim_literal, unique
import oci
import time

DOCUMENTATION = r'''
---
module: oag_domain_bootstrap
short_description: Bootstrap Default identity-domain accounts for OAG
description: Creates users and groups, enables API keys, and adds memberships.
author: Local automation
'''

USER_SCHEMA = 'urn:ietf:params:scim:schemas:core:2.0:User'
CAP_SCHEMA = 'urn:ietf:params:scim:schemas:oracle:idcs:extension:capabilities:User'
GROUP_SCHEMA = 'urn:ietf:params:scim:schemas:core:2.0:Group'
PATCH_SCHEMA = 'urn:ietf:params:scim:api:messages:2.0:PatchOp'


class Bootstrap:
    def __init__(self, client):
        self.client = client
        self.changed = False

    def ensure_user(self, username, email, given_name, family_name, connector=False):
        user = unique(self.client.list_users, 'userName eq ' + scim_literal(username))
        if user:
            if email.casefold() not in {(e.value or '').casefold() for e in user.emails or []}:
                raise ValueError('Existing user email differs for ' + username)
            if not user.active:
                raise ValueError('Existing user is inactive: ' + username)
        else:
            caps = oci.identity_domains.models.ExtensionCapabilitiesUser(
                can_use_api_keys=True, can_use_console_password=not connector)
            user = self.client.create_user(user=oci.identity_domains.models.User(
                schemas=[USER_SCHEMA, CAP_SCHEMA], user_name=username, active=True,
                display_name=given_name + ' ' + family_name,
                name=oci.identity_domains.models.UserName(
                    given_name=given_name, family_name=family_name),
                emails=[oci.identity_domains.models.UserEmails(
                    value=email, type='work', primary=True)],
                urn_ietf_params_scim_schemas_oracle_idcs_extension_capabilities_user=caps)).data
            self.changed = True
        current = self.client.get_user(user.id, attributes='id,ocid,urn:ietf:params:scim:schemas:oracle:idcs:extension:capabilities:User').data
        capabilities = current.urn_ietf_params_scim_schemas_oracle_idcs_extension_capabilities_user
        if not capabilities or capabilities.can_use_api_keys is not True:
            self.client.patch_user(user.id, patch_op=oci.identity_domains.models.PatchOp(
                schemas=[PATCH_SCHEMA], operations=[oci.identity_domains.models.Operations(
                    op='REPLACE', path=CAP_SCHEMA + ':canUseApiKeys', value=True)]))
            self.changed = True
        # OCI control-plane OCIDs may lag SCIM creation briefly.
        for _ in range(30):
            current = self.client.get_user(user.id, attributes='id,ocid').data
            if current.ocid:
                return current
            time.sleep(2)
        raise ValueError('User OCID has not propagated; rerun the playbook')

    def ensure_group(self, name):
        group = unique(self.client.list_groups, 'displayName eq ' + scim_literal(name))
        if not group:
            group = self.client.create_group(group=oci.identity_domains.models.Group(
                schemas=[GROUP_SCHEMA], display_name=name)).data
            self.changed = True
        for _ in range(30):
            current = self.client.get_group(group.id, attributes='id,ocid').data
            if current.ocid:
                return current
            time.sleep(2)
        raise ValueError('Group OCID has not propagated; rerun the playbook')

    def ensure_member(self, group, user):
        expression = 'id eq {} and members.value eq {}'.format(
            scim_literal(group.id), scim_literal(user.id))
        if unique(self.client.list_groups, expression):
            return
        # Patch only the missing member; preserve existing members.
        self.client.patch_group(group.id, patch_op=oci.identity_domains.models.PatchOp(
            schemas=[PATCH_SCHEMA], operations=[oci.identity_domains.models.Operations(
                op='ADD', path='members', value=[{'value': user.id, 'type': 'User'}])]))
        self.changed = True


def main():
    spec = connection_spec()
    for name in ['tenancy_ocid', 'connector_username', 'connector_email', 'connector_group',
                 'admin_username', 'admin_email', 'admin_given_name', 'admin_family_name', 'admin_group']:
        spec[name] = dict(type='str', required=True)
    # The full provisioning play deliberately does not support --check; use syntax-check.
    module = AnsibleModule(argument_spec=spec)
    p = module.params
    try:
        domain, client = clients(p)
        if domain.display_name != 'Default' or domain.compartment_id != p['tenancy_ocid']:
            raise ValueError('domain_ocid must identify the root Default identity domain')
        bootstrap = Bootstrap(client)
        connector = bootstrap.ensure_user(p['connector_username'], p['connector_email'],
                                          'OAG', 'Connector', connector=True)
        admin = bootstrap.ensure_user(p['admin_username'], p['admin_email'],
                                      p['admin_given_name'], p['admin_family_name'])
        connector_group = bootstrap.ensure_group(p['connector_group'])
        admin_group = bootstrap.ensure_group(p['admin_group'])
        bootstrap.ensure_member(connector_group, connector)
        bootstrap.ensure_member(admin_group, admin)
        module.exit_json(changed=bootstrap.changed,
                         connector_user_ocid=connector.ocid, admin_user_ocid=admin.ocid,
                         connector_group_ocid=connector_group.ocid,
                         admin_group_ocid=admin_group.ocid, admin_group_id=admin_group.id)
    except oci.exceptions.ServiceError as error:
        module.fail_json(msg='OCI identity-domain request failed', status=error.status,
                         code=error.code, request_id=error.request_id)
    except (ValueError, oci.exceptions.ConfigFileNotFound, oci.exceptions.InvalidConfig) as error:
        module.fail_json(msg=str(error))


if __name__ == '__main__':
    main()
