import pytest
import time

def test_benchmark1(benchmark):
    with benchmark("tag A"):
        time.sleep(1)

@pytest.mark.parametrize('x', [1, 2])
def test_benchmark2(benchmark, x):
    with benchmark("tag A"):
        time.sleep(1)

    with benchmark("tag B"):
        time.sleep(1)

    # store some meta-data about this run
    benchmark.attrs.update(x=x)
