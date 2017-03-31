import pytest

def pytest_addoption(parser):
    """
    Add command-line options to specify MPI and coverage configuration
    """
    parser.addoption("--mpirun", default="mpirun -n 4",
                    help="Select MPI launcher, e.g. mpirun -n 4")

    parser.addoption("--single", default=False, action='store_true',
        help="Do not run via MPI launcher. ")

    parser.addoption("--mpisub", action="store_true", default=False,
                    help="run process as a mpisub")
        
    parser.addoption("--mpisub-site-dir", default=None, help="site-dir in mpisub")
    
