# encoding=utf-8
# vim: fenc=utf-8 et sw=4 ts=4 sts=4 ai
import functools


def family(*families):
    def decorator(func):

        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            rev = args[0]
            for fam in families:
                if rev.article().site().host.endswith(fam):
                    yield from func(self, *args, **kwargs)

        return wrapper
    return decorator
