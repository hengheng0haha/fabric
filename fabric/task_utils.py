from fabric.utils import abort, indent
from fabric import state


# For attribute tomfoolery
class _Dict(dict):
    pass

def _crawl(name, mapping):
    """
    ``name`` of ``'a.b.c'`` => ``mapping['a']['b']['c']``
    """
    key, _, rest = name.partition('.')
    value = mapping[key]
    if not rest:
        return value
    return _crawl(rest, value)

def crawl(name, mapping):
    try:
        result = _crawl(name, mapping)
        # Handle default tasks
        if isinstance(result, _Dict) and getattr(result, 'default', False):
            result = result.default
        return result
    except (KeyError, TypeError):
        return None


def merge(hosts, roles, exclude, roledefs):
    """
    Merge given host and role lists into one list of deduped hosts.
    """
    # Abort if any roles don't exist
    bad_roles = [x for x in roles if x not in roledefs]
    if bad_roles:
        abort("The following specified roles do not exist:\n%s" % (
            indent(bad_roles)
        ))

    # Look up roles, turn into flat list of hosts
    role_hosts = []
    for role in roles:
        value = roledefs[role]
        # Handle "lazy" roles (callables)
        if callable(value):
            value = value()
        role_hosts += value

    # Return deduped combo of hosts and role_hosts, preserving order within
    # them (vs using set(), which may lose ordering) and skipping hosts to be
    # excluded.
    cleaned_hosts = [x.strip() for x in list(hosts) + list(role_hosts)]
    all_hosts = []
    for host in cleaned_hosts:
        if host not in all_hosts and host not in exclude:
            all_hosts.append(host)
    return all_hosts


def get_hosts(task, arg_hosts, arg_roles, arg_exclude_hosts, env=None):
    """
    Return the host list the given task should be using.

    See :ref:`execution-model` for detailed documentation on how host lists are
    set.
    """
    env = env or {}
    roledefs = env.get('roledefs', {})
    # Command line per-task takes precedence over anything else.
    if arg_hosts or arg_roles:
        return merge(arg_hosts, arg_roles, arg_exclude_hosts, roledefs)
    # Decorator-specific hosts/roles go next
    func_hosts = getattr(task, 'hosts', [])
    func_roles = getattr(task, 'roles', [])
    if func_hosts or func_roles:
        return merge(func_hosts, func_roles, arg_exclude_hosts, roledefs)
    # Finally, the env is checked (which might contain globally set lists from
    # the CLI or from module-level code). This will be the empty list if these
    # have not been set -- which is fine, this method should return an empty
    # list if no hosts have been set anywhere.
    env_vars = map(env.get, "hosts roles exclude_hosts".split()) + [roledefs]
    return merge(*env_vars)


def get_pool_size(task, hosts, default):
    # Default parallel pool size (calculate per-task in case variables
    # change)
    default_pool_size = default or len(hosts)
    # Allow per-task override
    pool_size = getattr(task, 'pool_size', default_pool_size)
    # But ensure it's never larger than the number of hosts
    pool_size = min((pool_size, len(hosts)))
    # Inform user of final pool size for this task
    if state.output.debug:
        msg = "Parallel tasks now using pool size of %d"
        print msg % pool_size
    return pool_size


def parse_kwargs(kwargs):
    new_kwargs = {}
    hosts = []
    roles = []
    exclude_hosts = []
    for key, value in kwargs.iteritems():
        if key == 'host':
            hosts = [value]
        elif key == 'hosts':
            hosts = value
        elif key == 'role':
            roles = [value]
        elif key == 'roles':
            roles = value
        elif key == 'exclude_hosts':
            exclude_hosts = value
        else:
            new_kwargs[key] = value
    return new_kwargs, hosts, roles, exclude_hosts