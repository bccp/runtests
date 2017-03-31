from .. import conftest
from ..tester import Tester as BaseTester

import pytest
from mpi4py import MPI
import traceback
import warnings
import sys
import os
import contextlib
import time
from argparse import ArgumentParser

if sys.version_info[0] == 2:
    from cStringIO import StringIO
else:
    from io import StringIO
import re

def fix_titles(s):
    pattern = '=====+'
    return re.sub(pattern, lambda x: x.group(0).replace('=', '-'), s)

class Rotator(object):
    """ in a rotator every range runs in terms """
    def __init__(self, comm):
        self.comm = comm
    def __enter__(self):
        self.comm.Barrier()
        for i in range(self.comm.rank):
            self.comm.Barrier()
    def __exit__(self, type, value, tb):
        for i in range(self.comm.rank, self.comm.size):
            self.comm.Barrier()
        self.comm.Barrier()

def MPITest(commsize):
    """
    A decorator that repeatedly calls the wrapped function,
    with communicators of varying sizes.

    This converts the test to a generator test; therefore the
    underlyig test shall not be a generator test.
    
    Parameters
    ----------
    commsize: scalar or tuple
        Sizes of communicator to use

    Usage
    -----
    @MPITest(commsize=[1, 2, 3])
    def test_stuff(comm):
        pass
    """
    if not isinstance(commsize, (tuple, list)):
        commsize = (commsize,)

    sizes = sorted(list(commsize))

    def dec(func):
        
        @pytest.mark.parametrize("size", sizes)
        def wrapped(size, *args):
            if MPI.COMM_WORLD.size < size: 
                pytest.skip("Test skipped because world is too small. Include the test with mpirun -n %d" % (size))
                
            color = 0 if MPI.COMM_WORLD.rank < size else 1
            comm = MPI.COMM_WORLD.Split(color)
            try:
                if color == 0:
                    rt = func(*args, comm=comm)
                if color == 1:
                    rt = None
                    #pytest.skip("rank %d not needed for comm of size %d" %(MPI.COMM_WORLD.rank, size))
            finally:
                MPI.COMM_WORLD.barrier()
                
            return rt
        wrapped.__name__ = func.__name__
        return wrapped
    return dec
    
    
def MPIWorld(NTask, required=1, optional=False):
    """ 
    A decorator that repeatedly calls the wrapped function,
    with communicators of varying sizes.
    
    .. note:: Deprecated 
        See :func:`MPITest` instead

    Parameters
    ----------
    NTask : scalar or tuple
        Size of communicators ot use
    required : scalar or tuple
        Required sizes of communicators. If the MPI_WORLD is insufficient, a Error is raised
        to abort the tests.
    optional : boolean
        If requirement not satistied, skip the test.
    """
    warnings.warn("This function is deprecated, use MPITest instead.", DeprecationWarning)

    if not isinstance(NTask, (tuple, list)):
        NTask = (NTask,)

    if not isinstance(required, (tuple, list)):
        required = (required,)

    maxsize = max(required)
    if MPI.COMM_WORLD.size < maxsize and not optional:
        raise ValueError("Test Failed because the world is too small. Increase to mpirun -n %d, current size = %d" % (maxsize, MPI.COMM_WORLD.size))
        
    sizes = sorted(set(list(required) + list(NTask)))
    def dec(func):
        
        @pytest.mark.parametrize("size", sizes)
        def wrapped(size, *args):
            if MPI.COMM_WORLD.size < size: 
                pytest.skip("Test skipped because world is too small. Include the test with mpirun -n %d" % (size))

            color = 0 if MPI.COMM_WORLD.rank < size else 1
            comm = MPI.COMM_WORLD.Split(color)
            
            if color == 0:
                rt = func(*args, comm=comm)

            MPI.COMM_WORLD.barrier()
            if color == 1:
                #pytest.skip("rank %d not needed for comm of size %d" %(MPI.COMM_WORLD.rank, size))
                rt = None
            return rt
        wrapped.__name__ = func.__name__
        return wrapped
    return dec

class Tester(BaseTester):
    """        
    Run MPI-enabled tests using pytest, building the project first.
    
    Examples::
        $ python runtests.py my/module
        $ python runtests.py --single my/module
        $ python runtests.py my/module/tests/test_abc.py
        $ python runtests.py --mpirun="mpirun -np 4" my/module
        $ python runtests.py --mpirun="mpirun -np 4"
    """
    plugins = [conftest.build, conftest.mpi]
    
    def __init__(self, *args, **kwargs):
        """
        Parameters
        ----------
        package_file : str
            the path to the main directory of the source package
        module : str
            the name of the package to test
        extra path : list of str
            extra paths to include on PATH when building
        """
        super(Tester, self).__init__(*args, **kwargs)
        self.comm = MPI.COMM_WORLD
        
    def main(self, argv):
        # must bail after first dead test; avoiding a fault MPI collective state.
        argv.insert(1, '-x')

        config = self._get_pytest_config(argv)
        args = config.known_args_namespace
        # print help and exit
        if args.help:
            return config.hook.pytest_cmdline_main(config=config)
        
        # import project from system path
        args.pyargs = True
                        
        # mpi subs do not build!
        if args.mpisub:
            args.no_build = True # master does the building
                        
        # build the project, returning the site directory
        site_dir = self._do_build(args)

        if args.shell:
            self._do_shell(args, config)

        if not args.single and not args.mpisub:
            
            # extract the mpirun run argument
            parser = ArgumentParser(add_help=False)
            # these values are ignored. This is a hack to filter out unused argv.
            parser.add_argument("--single", default=False, action='store_true')
            parser.add_argument("--mpirun", default=None)
            _args, additional = parser.parse_known_args()

            # make the test directory exists
            self._initialize_testdir()

            # now call with mpirun
            mpirun = args.mpirun.split()
            cmdargs = [sys.executable, sys.argv[0], '--mpisub', '--mpisub-site-dir=' + site_dir]

            os.execvp(mpirun[0], mpirun + cmdargs + additional)
            sys.exit(1)

        if args.build_only:
            sys.exit(0)
                    
        # fix the path of the modules we are testing
        config.args = self._fix_test_paths(site_dir, config.args) 

        # reset the output
        if args.mpisub:

            self.oldstdout = sys.stdout
            self.oldstderr = sys.stderr
            newstdout = StringIO()
            newstderr = StringIO()

            if self.comm.rank != 0:
                sys.stdout = newstdout
                sys.stderr = newstderr

        # test kwargs
        kws = {}
        kws['with_coverage'] = args.with_coverage
        kws['config_file'] = args.cov_config
        kws['html_cov'] = args.html_cov
        kws['comm'] = self.comm

        # run the tests
        code = None
        with self._run_from_testdir(args):
            code = self._test(config, **kws)

        if args.mpisub:
            if code != 0:
                # if any rank has a failure, print the error and abort the world.
                self._sleep()
                self.oldstderr.write("Test Failure due to rank %d\n" % self.comm.rank)
                self.oldstderr.write(newstdout.getvalue())
                self.oldstderr.write(newstderr.getvalue())
                self.oldstderr.flush()
                self.comm.Abort(-1)

            self.comm.barrier()
            with Rotator(self.comm):
                if self.comm.rank != 0:
                    self.oldstderr.write("\n")
                    self.oldstderr.write("=" * 32 + " Rank %d / %d " % (self.comm.rank, self.comm.size) + "=" * 32)
                    self.oldstderr.write("\n")
                    self.oldstderr.write(fix_titles(newstdout.getvalue()))
                    self.oldstderr.write(fix_titles(newstderr.getvalue()))
                    self.oldstderr.flush()

            sys.exit(0)

        else:
            sys.exit(code)
        
    def _do_build(self, args):
        
        site_dir = super(Tester, self)._do_build(args)
            
        if args.mpisub_site_dir:
            site_dir = args.mpisub_site_dir
            sys.path.insert(0, site_dir)
            os.environ['PYTHONPATH'] = site_dir
        return site_dir
        
    def _sleep(self):
        time.sleep(0.04 * self.comm.rank)
        
    @contextlib.contextmanager
    def _run_from_testdir(self, args):
        
        cwd = os.getcwd()
        self._initialize_testdir()
        
        try:
            if args.mpisub:
                assert(os.path.exists(self.TEST_DIR))
                self.comm.barrier()
            os.chdir(self.TEST_DIR)
            yield
        except:
            if args.mpisub:
                self._sleep()
                self.oldstderr.write("Fatal Error on Rank %d\n" % self.comm.rank)
                self.oldstderr.write(traceback.format_exc())
                self.oldstderr.flush()
                self.comm.Abort(-1)
            else:
                traceback.print_exc()
                sys.exit(1)
        finally:
            os.chdir(cwd)
    
