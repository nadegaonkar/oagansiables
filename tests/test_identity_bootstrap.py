"""Offline behavioral tests; real SDK models, mocked OCI API calls."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import MagicMock, patch

import oci

ROOT = Path(__file__).resolve().parents[1]


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, file)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


common = load('ansible.module_utils.oag_common', ROOT / 'module_utils/oag_common.py')
bootstrap_module = load('bootstrap_under_test', ROOT / 'library/oag_domain_bootstrap.py')
role_module = load('role_under_test', ROOT / 'library/oag_application_role.py')


def response(**kwargs):
    return NS(data=NS(**kwargs))


class DomainTests(unittest.TestCase):
    def test_scim_pagination_does_not_drop_second_page(self):
        method = MagicMock(side_effect=[response(resources=['a', 'b'], total_results=3),
                                        response(resources=['c'], total_results=3)])
        self.assertEqual(list(common.all_resources(method, filter='x')), ['a', 'b', 'c'])
        self.assertEqual(method.call_args_list[1].kwargs['start_index'], 3)

    def test_ambiguous_account_lookup_fails(self):
        method = MagicMock(return_value=response(resources=['a', 'b'], total_results=2))
        with self.assertRaisesRegex(ValueError, 'Ambiguous'):
            common.unique(method, 'userName eq "admin"')

    def test_filter_literal_escapes_quotes(self):
        self.assertEqual(common.scim_literal('a"b'), '"a\\"b"')

    def test_existing_membership_causes_no_write(self):
        client = MagicMock()
        client.list_groups.return_value = response(resources=[NS(id='g')], total_results=1)
        bootstrap = bootstrap_module.Bootstrap(client)
        bootstrap.ensure_member(NS(id='g'), NS(id='u'))
        client.patch_group.assert_not_called()
        self.assertFalse(bootstrap.changed)

    def test_missing_membership_adds_only_one_member(self):
        client = MagicMock()
        client.list_groups.return_value = response(resources=[], total_results=0)
        bootstrap = bootstrap_module.Bootstrap(client)
        bootstrap.ensure_member(NS(id='g'), NS(id='u'))
        operation = client.patch_group.call_args.kwargs['patch_op'].operations[0]
        self.assertEqual(operation.op, 'ADD')
        self.assertEqual(operation.path, 'members')
        self.assertEqual(operation.value, [{'value': 'u', 'type': 'User'}])
        self.assertTrue(bootstrap.changed)

    def test_existing_username_with_different_email_is_not_adopted(self):
        client = MagicMock()
        client.list_users.return_value = response(resources=[oci.identity_domains.models.User(
            id='u', active=True, emails=[oci.identity_domains.models.UserEmails(value='other@example.com')])], total_results=1)
        with self.assertRaisesRegex(ValueError, 'email differs'):
            bootstrap_module.Bootstrap(client).ensure_user('admin', 'admin@example.com', 'A', 'B')
        client.patch_user.assert_not_called()
        client.create_user.assert_not_called()

    def test_inactive_user_is_not_reactivated(self):
        client = MagicMock()
        client.list_users.return_value = response(resources=[oci.identity_domains.models.User(
            id='u', active=False, emails=[oci.identity_domains.models.UserEmails(value='admin@example.com')])], total_results=1)
        with self.assertRaisesRegex(ValueError, 'inactive'):
            bootstrap_module.Bootstrap(client).ensure_user('admin', 'admin@example.com', 'A', 'B')
        client.patch_user.assert_not_called()

    def test_connector_payload_disables_console_password_and_enables_api_keys(self):
        client = MagicMock()
        client.list_users.return_value = response(resources=[], total_results=0)
        user = oci.identity_domains.models.User(id='u', ocid='ocid1.user.test',
            urn_ietf_params_scim_schemas_oracle_idcs_extension_capabilities_user=
                oci.identity_domains.models.ExtensionCapabilitiesUser(can_use_api_keys=True))
        client.create_user.return_value = NS(data=user)
        client.get_user.return_value = NS(data=user)
        result = bootstrap_module.Bootstrap(client).ensure_user('service', 'service@example.com', 'S', 'U', connector=True)
        sent = client.create_user.call_args.kwargs['user']
        serialized = oci.util.to_dict(sent)
        capabilities = serialized['urn_ietf_params_scim_schemas_oracle_idcs_extension_capabilities_user']
        self.assertTrue(capabilities['can_use_api_keys'])
        self.assertFalse(capabilities['can_use_console_password'])
        self.assertEqual(result.ocid, 'ocid1.user.test')


class Finished(Exception):
    def __init__(self, payload):
        self.payload = payload


class RoleTests(unittest.TestCase):
    def run_role(self, client, check=False):
        module = MagicMock()
        module.params = dict(app_id='app', role_id='role', group_id='group')
        module.check_mode = check
        module.exit_json.side_effect = lambda **kw: (_ for _ in ()).throw(Finished(kw))
        module.fail_json.side_effect = lambda **kw: (_ for _ in ()).throw(Finished(kw))
        with patch.object(role_module, 'AnsibleModule', return_value=module), \
                patch.object(role_module, 'clients', return_value=(None, client)):
            with self.assertRaises(Finished) as caught:
                role_module.main()
        return caught.exception.payload

    def client(self, grants=None):
        client = MagicMock()
        client.get_app_role.return_value = response(app=NS(value='app'), available_to_groups=True)
        client.list_grants.return_value = response(resources=grants or [], total_results=len(grants or []))
        return client

    def test_role_from_another_app_is_rejected(self):
        client = self.client()
        client.get_app_role.return_value.data.app.value = 'wrong-app'
        result = self.run_role(client)
        self.assertIn('does not belong', result['msg'])
        client.create_grant.assert_not_called()

    def test_existing_role_grant_is_reused(self):
        client = self.client([NS(entitlement=NS(attribute_name='appRoles', attribute_value='role'))])
        result = self.run_role(client)
        self.assertFalse(result['changed'])
        client.create_grant.assert_not_called()

    def test_missing_role_is_granted_to_group(self):
        client = self.client()
        self.assertTrue(self.run_role(client)['changed'])
        grant = client.create_grant.call_args.kwargs['grant']
        self.assertEqual(grant.grantee.type, 'Group')
        self.assertEqual(grant.grantee.value, 'group')
        self.assertEqual(grant.entitlement.attribute_value, 'role')

    def test_role_check_mode_never_creates_grant(self):
        client = self.client()
        self.assertTrue(self.run_role(client, check=True)['changed'])
        client.create_grant.assert_not_called()


if __name__ == '__main__':
    unittest.main()
