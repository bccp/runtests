from mpi4py_test import MPIWorld

@MPIWorld(NTask=[1, 2], required=(1, 2))
def test_mpiworld(comm):
    assert comm is not None
