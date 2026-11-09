"""Explicit profiles choose defaults only; never download or probe performance."""
import platform

PROFILES = {
    'windows16': ('qwen2.5:3b', ('qwen2.5:3b', 'qwen2.5:7b')),
    'macos8': ('qwen2.5:3b', ('qwen2.5:3b', 'qwen2.5:1.5b')),
    'portable': ('qwen2.5:3b', ('qwen2.5:3b', 'qwen2.5:1.5b')),
}


def profile_name(value):
    if value != 'auto':
        return value
    return {'Windows': 'windows16', 'Darwin': 'macos8'}.get(platform.system(), 'portable')
