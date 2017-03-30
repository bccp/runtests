from runtests.mpi import MPITest

@MPITest(commsize=[1, 2])
def test_uncollective_error(comm):
    if comm.rank == 1:
        raise ValueError("This is a dummy error. The test will fail. but shall not hang")
