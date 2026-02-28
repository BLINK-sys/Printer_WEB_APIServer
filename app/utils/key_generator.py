import secrets

# Exclude ambiguous characters: O/0, I/1, L
CHARS = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'


def generate_activation_key():
    """Generate a key like XXXX-XXXX-XXXX-XXXX."""
    groups = [''.join(secrets.choice(CHARS) for _ in range(4)) for _ in range(4)]
    return '-'.join(groups)
