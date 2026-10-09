"""Unique house alarm roles, with backward-compatible installation IDs."""
ROLES = ('motion', 'contact')


def partition_ids(alarms):
    result = {}
    for key, info in alarms.items():
        role = info.get('partition_role', {87: 'motion', 88: 'contact'}.get(int(key)))
        if role is None:
            continue
        if role not in ROLES or role in result:
            raise ValueError('alarm_role_used')
        result[role] = int(key)
    return result
