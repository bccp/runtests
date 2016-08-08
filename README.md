# mpi4py\_test

A simple tools for building packages, installing, then running the tests of massively parallel
Python MPI applications written with mpi4py.

Examples:

    python runtests.py --mpirun="mpirun -np 4"

    python runtests.py --mpirun --mpi-unmute


In test cases, `MPIWorld` decorator wraps around tests to run them at various MPI communicator sizes.

Examples:

    from mpi4py_test import MPIWorld

    @MPIWorld(NTask=(1, 2, 3, 4), required=(1, 4))
    def test_myfunction(comm):
        result = myfunction(comm)
        assert result # or ....


