import pytest
import time

def test_benchmark1(benchmark):
    with benchmark("test 1"):
        time.sleep(1)

@pytest.mark.parametrize('x', [1, 2])
def test_benchmark2(benchmark, x):
    with benchmark("test 2"):
        time.sleep(1)
