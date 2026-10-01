import random
import time

MAX_DELAY = 8.0


def with_retries(fn, attempts=3, delay=0.5):
    for i in range(attempts):
        try:
            return fn()
        except ConnectionError:
            if i == attempts - 1:
                raise
            wait = min(delay * (2 ** i), MAX_DELAY)
            time.sleep(wait * random.uniform(0.5, 1.0))
