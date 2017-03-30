import pytest

def pytest_addoption(parser):
    """
    Add command-line options to specify MPI and coverage configuration
    """
    parser.addoption("--no-build", action="store_true", default=False,
                    help="do not build the project (use system installed version)")

    parser.addoption("--build-only", action="store_true", default=False,
                    help="just build, do not run any tests")

    parser.addoption("--shell", action="store_true", default=False,
                    help="start a shell with the installed package properly set up in the path")
                    
    parser.addoption("--show-build-log", action="store_true",
                    help="show build output rather than using a log file")
    
    parser.addoption("--with-coverage", action="store_true", default=False,
                    help="report coverage of project code to a .coverage file")
                          
    parser.addoption("--html-cov", action="store_true", default=False,
                    help="write html coverage reports to build/coverage")
                          
    parser.addoption('--cov-config', action='store', default='.coveragerc',
                    metavar='path',
                    help=('config file for coverage, default: .coveragerc; '
                          'see http://coverage.readthedocs.io/en/coverage-4.3.4/config.html'))
    
def pytest_collection_modifyitems(session, config, items):
    """
    Modify the ordering of tests, such that the ordering will be 
    well-defined across all ranks running
    """
    items[:] = sorted(items, key=lambda x: str(x))
