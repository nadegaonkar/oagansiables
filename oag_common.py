"""Shared OCI identity-domain helpers; no secrets are returned to Ansible."""
import json

import oci


def scim_literal(value):
    return json.dumps(value)


def all_resources(method, **kwargs):
    """Identity Domains uses SCIM pagination, not OCI opc-next-page."""
    start = 1
    while True:
        data = method(start_index=start, count=100, **kwargs).data
        resources = data.resources or []
        yield from resources
        if not resources or start + len(resources) > (data.total_results or 0):
            break
        start += len(resources)


def unique(method, filter_expression):
    matches = list(all_resources(method, filter=filter_expression))
    if len(matches) > 1:
        raise ValueError('Ambiguous identity-domain lookup; more than one match')
    return matches[0] if matches else None


def clients(params):
    config = oci.config.from_file(params['config_file'], params['profile'])
    config['region'] = params['region']
    identity = oci.identity.IdentityClient(config, retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY)
    domain = identity.get_domain(params['domain_ocid']).data
    endpoint = domain.home_region_url or domain.url
    domain_client = oci.identity_domains.IdentityDomainsClient(
        config, service_endpoint=endpoint, retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY)
    return domain, domain_client


def connection_spec():
    return dict(config_file=dict(type='path', required=True),
                profile=dict(type='str', default='DEFAULT'),
                region=dict(type='str', required=True),
                domain_ocid=dict(type='str', required=True))
