# runtests

[![Build Status](https://travis-ci.org/bccp/runtests.svg?branch=master)](https://travis-ci.org/bccp/runtests)

A simple tools for incrementally building packages, then testing against installed version.

The idea came from runtests.py in numpy and scipy projects:

- incremental build is fast: encouraging developers to test frequently;
- existing installation of the software package is not overwritten;
- binaries are properly compiled -- and optionally in debug mode.

Testing of MPI application is also supported via the `[mpi]` feature.
We use runtests in `nbodykit` and a variety of packages.

## Project setup

Follow traditional pytest setup. Then vendor run-tests.py or run-mpitests.py into the project root directory.

1. For MPI Projects, copy `run-testsmpi.py` to `run-tests.py`.

2. For nonMPI Projects, copy `run-tests.py` to `run-tests.py`.

3. Edit the file, change the package module name.


## Usage

### Regular Projects vendored from `run-tests.py`

*All pytest arguments are passed through.* For example, '-v', '-x' `--pdb`.

1. Running tests the usual way
    ```
        python run-tests.py
    ```

2. Running a specific test `test_core.py::test_basic_function`
    ```
        python run-tests.py test_core.py::test_basic_function
    ```

### MPI Projects, vendored from `run-mpitests.py`

*All pytest arguments are passed through.*

MPI Tests always stop at the first error; because MPI is not fault tolerant [1].

[1] : https://www.open-mpi.org/faq/?category=ft#ft-future

1. Running tests with 4 MPI ranks
    ```
        python run-tests.py
    ```

2. Running tests with 1 MPI rank
    ```
        python run-tests.py --single
    ```

3. Running tests with a customized MPI launcher
    ```
        python run-tests.py --mpirun="mpirun -np 4"
    ```

## Defining MPI UnitTests: 

This feature may belong to a different package; it resides here for now before we can
find a reasonable refactoring of the package.

### MPITest decorator

`MPITest` decorator allows testing with different MPI communicator sizes.

Example:
```
    from runtests.mpi import MPITest

    @MPITest(size=[1, 2, 3, 4])
    def test_myfunction(comm):
        result = myfunction(comm)
        assert result # or ....
```

### MPITestFixture

You can combine `MPITestFixture` with other pytest fixtures or decorators, what you can't with the `MPITest` decorator.

Example: Parameter variation with `pytest.mark.parametrize`

```python
from runtests.mpi import MPITestFixture
import pytest

comm = MPITestFixture([1,2,3, 4,10], scope='function')

@pytest.mark.parametrize("msg",["hello","world"])
def test_y(msg, comm):
    print(msg, comm.Get_rank())
```

Example: Parameter variation with `pytest.fixture`
```python
from runtests.mpi import MPITestFixture
import pytest

comm = MPITestFixture([1,2,3,4], scope='function')

@pytest.fixture(params=["hello","world"])
def x(request):
    return request.param

def test_x(x, comm):
    print(x, comm.Get_rank())
```


## Tricks


1. Launching pdb on the first error

    ```
        # non MPI
        python run-tests.py --pdb


        # MPI on a single rank
        python run-mpitests.py --single --pdb

        # MPI but one debugger per rank.
        python run-mpitests.py --mpirun='mpirun -n 4 xterm -e' --pdb

        # shortcut for MPI but one debugger per rank
        python run-mpitests.py --xterm --pdb
    ```

2. Launchging a shell with the module ready to be imported. The shell will start in
   an empty directory where runtests would have ran the tests.

    ```
        python run-tests.py --shell
    ```

3. Testing runtests itself requires an installed version of runtests.
   This is because the example scripts we use for testing runtests,
   refuses to import from the source code directory.

4. setup.py works (or fails) like 'make'. Therefore sometimes it is useful to purge the
   build/ directory manually by adding '--clean-build' argument.

5. Install pytest-profiling and get support to profiling.

6. Adding commandline arguments via conftest.py is not supported. (Issue #14)
   If this is a global behavior of the tester, then consider subclassing `Tester` in run-tests.py instead. 

## Contribute

Testing runtests itself requires an installed version of runtests.
This is because runtests refuses to import from the source code directory.

Also be aware that some of the tests are supposed to fail.

Follow the example in `travis.yaml` for running the tests locally. In the long
run we may want to refactor it into a shell script.
