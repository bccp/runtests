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

Follow traditional pytest setup. Then vendor runtests.py or runtests-mpi.py into the project root directory.

1. For MPI Projects, copy `runtests-mpi.py` to `runtests.py`.

2. For nonMPI Projects, copy `runtests.py` to `runtests.py`.

3. Edit the file, change the package module name.


## Usage

### Regular Projects vendored from `runtests.py`

*All pytest arguments are passed through.* For example, '-v', '-x' `--pdb`.

1. Running tests the usual way

    python runtests.py

2. Running a specific test `test_core.py::test_basic_function`

    python runtests.py test_core.py::test_basic_function


### MPI Projects, vendored from `runtests-mpi.py`

*All pytest arguments are passed through.*

MPI Tests always stop at the first error; because MPI is not fault tolerant [1].

[1] : https://www.open-mpi.org/faq/?category=ft#ft-future

1. Running tests with 4 MPI ranks

    python runtests.py

2. Running tests with 1 MPI rank

    python runtests.py --single

3. Running tests with a customized MPI launcher

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

2. Launchging a shell with the module ready to be imported

    python runtests.py --shell


## Caveats

Testing runtests itself requires an installed version of runtests.

This is because the example scripts we use for testing runtests,
refuses to import from the source code directory.


