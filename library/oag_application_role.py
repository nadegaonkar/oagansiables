#!/usr/bin/python
"""Idempotent OAG application-role assignment using explicit SCIM IDs."""
from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.oag_common import clients, connection_spec, scim_literal, unique
import oci

DOCUMENTATION = r'''
---
module: oag_application_role
short_description: Assign an IAM application role to an OAG administrators group
description: Verifies the role belongs to the supplied app and adds a missing grant.
author: Local automation
'''


def main():
    spec = connection_spec()
    spec.update({key: dict(type='str', required=True) for key in ['app_id', 'role_id', 'group_id']})
    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)
    p = module.params
    try:
        _, client = clients(p)
        role = client.get_app_role(p['role_id']).data
        if not role.app or role.app.value != p['app_id']:
            raise ValueError('The selected application role does not belong to the supplied app')
        if not role.available_to_groups:
            raise ValueError('The selected application role cannot be assigned to groups')
        expression = 'app.value eq {} and grantee.value eq {}'.format(
            scim_literal(p['app_id']), scim_literal(p['group_id']))
        from ansible.module_utils.oag_common import all_resources
        grants = all_resources(client.list_grants, filter=expression)
        exists = any(g.entitlement and g.entitlement.attribute_name == 'appRoles'
                     and g.entitlement.attribute_value == p['role_id'] for g in grants)
        if not exists and not module.check_mode:
            client.create_grant(grant=oci.identity_domains.models.Grant(
                schemas=['urn:ietf:params:scim:schemas:oracle:idcs:Grant'],
                grant_mechanism='ADMINISTRATOR_TO_GROUP',
                grantee=oci.identity_domains.models.GrantGrantee(value=p['group_id'], type='Group'),
                app=oci.identity_domains.models.GrantApp(value=p['app_id']),
                entitlement=oci.identity_domains.models.GrantEntitlement(
                    attribute_name='appRoles', attribute_value=p['role_id'])))
        module.exit_json(changed=not exists)
    except oci.exceptions.ServiceError as error:
        module.fail_json(msg='OCI application-role request failed', status=error.status,
                         code=error.code, request_id=error.request_id)
    except (ValueError, oci.exceptions.ConfigFileNotFound, oci.exceptions.InvalidConfig) as error:
        module.fail_json(msg=str(error))


if __name__ == '__main__':
    main()
