from django.utils.module_loading import import_string


def lazy_view(dotted_path, *, csrf_exempt=False):
    """Return a URL callback that imports the real view on first request."""
    resolved = None
    view_name = dotted_path.rsplit('.', 1)[-1]

    def _view(request, *args, **kwargs):
        nonlocal resolved
        if resolved is None:
            resolved = import_string(dotted_path)
        return resolved(request, *args, **kwargs)

    module_name = dotted_path.rsplit('.', 1)[0]
    _view.__module__ = module_name
    _view.__name__ = view_name
    _view.__qualname__ = view_name
    if csrf_exempt:
        _view.csrf_exempt = True
    return _view
