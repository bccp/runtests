from mpi4py_test import MPIWorld

@MPIWorld(NTask=[1, 2], required=(1, 2))
def test_uncollective_error(comm):
    if comm.rank == 1:
        raise ValueError("This is a dummy error. The test will fail. but shall not hang")
