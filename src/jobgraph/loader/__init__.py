import copy

# Define a collection of group_by functions
GROUP_BY_MAP = {}


def group_by(name):
    def wrapper(func):
        GROUP_BY_MAP[name] = func
        return func

    return wrapper


def group_jobs(config, jobs):
    group_by_fn = GROUP_BY_MAP[config["group_by"]]

    groups = group_by_fn(config, jobs)

    for combinations in groups.values():
        dependencies = [copy.deepcopy(t) for t in combinations]
        yield dependencies
