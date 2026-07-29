import threading


def singleton(class_):
    instances = {}
    lock = threading.Lock()

    def get_instance(*args, **kwargs):
        if class_ not in instances:
            with lock:
                if class_ not in instances:
                    instances[class_] = class_(*args, **kwargs)

        return instances[class_]

    return get_instance
