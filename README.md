# runtests

[![Build Status](https://travis-ci.org/rainwoodman/runtests.svg?branch=master)](https://travis-ci.org/rainwoodman/runtests)

A simple tools for building packages, installing, then running the tests.
The idea came from runtests.py in numpy and scipy projects.

This way, we ensure the tests are run as if they have been installed to a non-standard
location in the filesystem. Two benefits:

- decoupling testing environment from the source code; discovering mis-installed files, etc.
- ensures the package makes little assumption about install location
- binaries are properly compiled as it they are installed, without needing the quirky 'develop' egg-links.

Testing of MPI application is also supported via the `[mpi]` feature.
We use runtests in `nbodykit` and a variety of packages.

## Project setup

Follow traditional pytest setup. Then drop in a `runtests.py` similar to the one provided
with `runtests` in the source code root directory. Then you are ready to go.

Examples:

    # for non MPI applications

    python runtests.py

    # for MPI applications

    python runtests.py --mpirun

    python runtests.py --mpirun="mpirun -np 4"


## Unit Test with MPI via runtests.mpi

This feature may belong to a different package; it resides here for now as a feature.

`MPITest` decorator allows testing with different MPI communicator sizes.

Examples:

    from runtests.mpi import MPITest

    @MPIWorld(size=[1, 2, 3, 4])
    def test_myfunction(comm):
        result = myfunction(comm)
        assert result # or ....

## Useful tricks


1. Launching pdb on the first error

    # non MPI
    python runtests.py --pdb


    # MPI
    python runtests-mpi.py --single --pdb

2. Add more tricks.

## Caveats

Testing runtests itself requires an installed version of runtests.

This is because the example scripts we use for testing runtests,
refuses to import from the source code directory.


