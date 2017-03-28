from .version import __version__
from .coverage import Coverage

from mpi4py import MPI
import traceback
import warnings
import sys
import tempfile
import pytest

PY2 = sys.version_info[0] == 2

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

def MPIWorld(NTask, required=1, optional=False):
    """ A decorator that repeatedly calls the wrapped function,
        with communicators of varying sizes.

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
                pytest.skip("rank %d not needed for comm of size %d" %(MPI.COMM_WORLD.rank, size))
            return rt
        wrapped.__name__ = func.__name__
        return wrapped
    return dec

def MPITest(commsize):
    """ A decorator that repeatedly calls the wrapped function,
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
            if color == 0:
                rt = func(*args, comm=comm)
            MPI.COMM_WORLD.barrier()
            if color == 1:
                pytest.skip("rank %d not needed for comm of size %d" %(MPI.COMM_WORLD.rank, size))
                
            return rt
        wrapped.__name__ = func.__name__
        return wrapped
    return dec
    
import os
if PY2:
    from cStringIO import StringIO
else:
    from io import StringIO

import shutil
import subprocess
import time
from argparse import ArgumentParser
import tempfile

class MPITester(object):
    """
    pytest file_or_dir [OPTIONS] 

    Run MPI-enabled tests using pytest, building the project first.
    """
    def __init__(self, package_file, module,
            extra_path =['/usr/lib/ccache', '/usr/lib/f90cache',
                         '/usr/local/lib/ccache', '/usr/local/lib/f90cache']
        ):
        self.ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(package_file)))
        self.PROJECT_ROOT_FILES = [package_file, 'setup.py', 'LICENSE']
        self.EXTRA_PATH = extra_path
        self.PROJECT_MODULE = module
        self.comm = MPI.COMM_WORLD

    def main(self, argv):
        
        import _pytest.config as _config
        from . import mpi_conftest # load hooks to add mpi cmdline args
        
        # disable pytest-cov
        argv += ['-p', 'no:pytest_cov']
        
        # get the pytest configuration object
        try:
            config = _config._prepareconfig(argv, [mpi_conftest])
        except _config.ConftestImportFailure as e:
            tw = _config.py.io.TerminalWriter(sys.stderr)
            for line in traceback.format_exception(*e.excinfo):
                tw.line(line.rstrip(), red=True)
            tw.line("ERROR: could not load %s\n" % (e.path), red=True)
            return 4
        
        # the namespace of commandline args
        args = config.known_args_namespace
        
        # print help and exit
        if args.help:
            return config.hook.pytest_cmdline_main(config=config)
        
        # import project from system path
        args.pyargs = True
        
        # extract the coverage-related options
        covargs = {}
        covargs['with_coverage'] = args.with_coverage
        covargs['config_file'] = args.cov_config
        covargs['html_cov'] = args.html_cov
                
        if args.mpisub:
            args.no_build = True # master does the building
        
        site_dir='.' # use source directory by default
        if not args.no_build:
            site_dir = self.build_project(args)
            sys.path.insert(0, site_dir)
            os.environ['PYTHONPATH'] = site_dir
            
        if args.mpisub_site_dir:
            site_dir = args.mpisub_site_dir
            sys.path.insert(0, site_dir)
            os.environ['PYTHONPATH'] = site_dir

        if args.mpirun:
            
            # extract the mpirun run argument
            parser = ArgumentParser(add_help=False)
            parser.add_argument("--mpirun", default=None, const='mpirun -n 4', nargs='?')
            args, additional = parser.parse_known_args()
            
            # now call with mpirun
            mpirun = args.mpirun.split()
            cmdargs = [sys.executable, sys.argv[0], '--mpisub', '--mpisub-site-dir=' + site_dir]
            os.execvp(mpirun[0], mpirun + cmdargs + additional)
            sys.exit(1)
            
        test_dir = os.path.join(self.ROOT_DIR, 'build', 'test')
        if args.build_only:
            sys.exit(0)
            
        def fix_test_path(x):
            p = x.split('::')
            p[0] = os.path.relpath(os.path.abspath(p[0]), self.ROOT_DIR)
            p[0] = os.path.join(site_dir, p[0])
            return '::'.join(p)
        
        # fix the path of the modules we are testing
        config.args = [fix_test_path(x) for x in config.args]
        
        def test(config):
            try:
                with Coverage(self.comm, self.PROJECT_MODULE, root=self.ROOT_DIR, **covargs):
                    config.pluginmanager.check_pending()
                    return config.hook.pytest_cmdline_main(config=config)
            finally:
                config._ensure_unconfigure()

        self.comm.barrier()

        if self.comm.rank == 0:
            # Run the tests under build/test
            try:
                shutil.rmtree(test_dir)
            except OSError:
                pass
            try:
                os.makedirs(test_dir)
            except OSError:
                pass
            
            # set up a symlink to the site dir from the test env
            # this ensures relative paths from the test dir in any configuration files will be correct
            os.symlink(os.path.join(site_dir, self.PROJECT_MODULE), os.path.join(test_dir, self.PROJECT_MODULE))

        self.comm.barrier()

        if args.mpisub:
            oldstdout = sys.stdout
            oldstderr = sys.stderr
            newstdout = StringIO()
            newstderr = StringIO()

            if self.comm.rank != 0:
                sys.stdout = newstdout
                sys.stderr = newstderr

        cwd = os.getcwd()

        result = None
        try:
            if args.mpisub:
                assert(os.path.exists(test_dir))
                self.comm.barrier()
            os.chdir(test_dir)
            result = test(config)
        except:
            if args.mpisub:
                self.sleep()
                oldstderr.write("Fatal Error on Rank %d\n" % self.comm.rank)
                oldstderr.write(traceback.format_exc())
                oldstderr.flush()
                self.comm.Abort(-1)
            else:
                traceback.print_exc()
                sys.exit(1)
        finally:
            os.chdir(cwd)

        self.comm.barrier()

        code = result
        if args.mpisub:
            if code != 0:
                # if any rank has a failure, print the error and abort the world.
                self.sleep()
                oldstderr.write("Test Failure due to rank %d\n" % self.comm.rank)
                oldstderr.write(newstdout.getvalue())
                oldstderr.write(newstderr.getvalue())
                oldstderr.flush()
                self.comm.Abort(-1)

            self.comm.barrier()
            with Rotator(self.comm):
                oldstderr.write("------ Test result from rank %d -----\n" % self.comm.rank)
                oldstderr.write(newstdout.getvalue())
                oldstderr.write(newstderr.getvalue())
                oldstderr.flush()

            sys.exit(0)

        else:
            sys.exit(code)
        
    def sleep(self):
        time.sleep(0.04 * self.comm.rank)
        
    def build_project(self, args):
        """
        Build a dev version of the project.

        Returns
        -------
        site_dir
            site-packages directory where it was installed

        """

        root_ok = [os.path.exists(os.path.join(self.ROOT_DIR, fn))
                   for fn in self.PROJECT_ROOT_FILES]
        if not all(root_ok):
            print("To build the project, run runtests.py in "
                  "git checkout or unpacked source")
            sys.exit(1)

        dst_dir = os.path.join(self.ROOT_DIR, 'build', 'testenv')

        env = dict(os.environ)
        cmd = [sys.executable, 'setup.py']

        # Always use ccache, if installed
        env['PATH'] = os.pathsep.join(self.EXTRA_PATH + env.get('PATH', '').split(os.pathsep))
        cmd += ['build']
        cmd += ['install', '--prefix=' + dst_dir]

        if args.show_build_log:
            ret = subprocess.call(cmd, env=env, cwd=self.ROOT_DIR)
        else:
            log_filename = os.path.join(self.ROOT_DIR, 'build.log')
            print("Building, see build.log...")
            with open(log_filename, 'w') as log:
                p = subprocess.Popen(cmd, env=env, stdout=log, stderr=log,
                                     cwd=self.ROOT_DIR)

        # Wait for it to finish, and print something to indicate the
        # process is alive, but only if the log file has grown (to
        # allow continuous integration environments kill a hanging
        # process accurately if it produces no output)
        last_blip = time.time()
        last_log_size = os.stat(log_filename).st_size
        while p.poll() is None:
            time.sleep(0.5)
            if time.time() - last_blip > 60:
                log_size = os.stat(log_filename).st_size
                if log_size > last_log_size:
                    print("    ... build in progress")
                    last_blip = time.time()
                    last_log_size = log_size

            ret = p.wait()

        if ret == 0:
            print("Build OK")
        else:
            if not args.show_build_log:
                with open(log_filename, 'r') as f:
                    print(f.read())
                print("Build failed!")
            sys.exit(1)

        from distutils.sysconfig import get_python_lib
        site_dir = get_python_lib(prefix=dst_dir, plat_specific=True)
        if not os.path.exists(os.path.join(site_dir, self.PROJECT_MODULE)):
            # purelib?
            site_dir = get_python_lib(prefix=dst_dir, plat_specific=False)
        if not os.path.exists(os.path.join(site_dir, self.PROJECT_MODULE)):
            print("Package %s not properly installed" % self.PROJECT_MODULE)
            sys.exit(1)
        return site_dir