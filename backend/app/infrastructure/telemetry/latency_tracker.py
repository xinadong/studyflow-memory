"""检索和模型延迟测量辅助。"""

from time import perf_counter


class LatencyTimer:
    def __enter__(self):
        self.started = perf_counter()
        return self

    def __exit__(self, *_):
        self.elapsed_ms = int((perf_counter() - self.started) * 1000)
