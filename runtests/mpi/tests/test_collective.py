from runtests.mpi import MPITest

@MPITest(commsize=[1, 2])
def test_collective_error(comm):
    raise ValueError("This is a dummy error. The test will fail. but shall not hang")
