from runtests.mpi import MPITest
import pytest
import time

def test_benchmark1(benchmark):

    comm = benchmark.comm
    with benchmark("test 1"):
        time.sleep((1+comm.rank)*0.25)

@pytest.mark.parametrize('x', [1, 2])
def test_benchmark2(benchmark, x):

    comm = benchmark.comm
    with benchmark("test 2"):
        time.sleep((1+comm.rank)*0.25)
