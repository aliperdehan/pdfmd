"""Choose HTML maths explicitly, including fragments, while keeping Pandoc defaults choices."""
from pathlib import Path

core = None


def defaults_choose_math(options, cwd):
    """Read only defaults files passed to this run (including their inherited defaults)."""
    names = []
    arguments = iter(options)
    for argument in arguments:
        if argument in ('--defaults', '-d'):
            names.append(next(arguments, ''))
        elif argument.startswith('--defaults='):
            names.append(argument.split('=', 1)[1])
        elif argument.startswith('-d') and not argument.startswith('--'):
            names.append(argument[2:])
    seen = set()

    def chosen(name):
        path = Path(str(name)).expanduser()
        candidates = [path, path.with_suffix('.yaml') if not path.suffix else path]
        candidates = [cwd / item for item in candidates]
        data_dir = core.pandoc_user_data_dir()
        if data_dir:
            if not path.is_absolute():
                candidates += [data_dir / 'defaults' / path, data_dir / 'defaults' / path.with_suffix('.yaml')]
        path = next((item for item in candidates if item.is_file()), None)
        if path is None or path.resolve() in seen:
            return False
        seen.add(path.resolve())
        data = core.metadata_file_yaml(path)
        if any(key in data for key in ('html-math-method', 'math-method')):
            return True
        inherited = data.get('defaults', [])
        return any(chosen(item) for item in (inherited if isinstance(inherited, list) else [inherited]))

    return any(chosen(name) for name in names)


def arguments(settings, options, document, metadata_files):
    """The user's flag wins, then html.math, then a passed defaults file, then MathML."""
    if any(item.startswith(core.HTML_MATH_OPTIONS) for item in options):
        return []
    method = str(settings.get('math', '')).casefold()
    if method in core.HTML_MATH_METHODS:
        return core.html_math_args(method)
    cwd = core.pandoc_working_directory(core.metadata_cwd(metadata_files, document.parent))
    if method in ('', 'auto') and not defaults_choose_math(options, cwd):
        return core.html_math_args('mathml')
    return []
