"""One YAML backend for core and feature packages, preferring installed PyYAML."""


def load_yaml():
    """Use installed yaml, then the private pure-Python copy; None means a broken install."""
    try:
        import yaml
    except ImportError:
        try:
            import pdfmd_yaml as yaml
        except ImportError:
            return None
    return yaml


yaml = load_yaml()


def description(backend) -> str:
    """Describe the backend actually used, without probing unrelated installed modules."""
    if backend is None:
        return 'unavailable (installation is incomplete)'
    source = 'bundled' if backend.__name__ == 'pdfmd_yaml' else 'installed'
    engine = 'LibYAML' if getattr(backend, '__with_libyaml__', False) else 'pure Python'
    return f'{source} PyYAML {backend.__version__} ({engine})'
