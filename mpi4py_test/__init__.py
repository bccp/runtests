from mpi4py import MPI
import traceback
from .version import __version__
from numpy.testing.decorators import skipif, knownfailureif

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
    if not isinstance(NTask, (tuple, list)):
        NTask = (NTask,)

    if not isinstance(required, (tuple, list)):
        required = (required,)

    maxsize = max(required)
    if MPI.COMM_WORLD.size < maxsize:
        if not optional:
            raise ValueError("Test Failed because the world is too small. Increase to mpirun -n %d, current size = %d" % (maxsize, MPI.COMM_WORLD.size))
        else:
            return knownfailureif(True, "Test will Fail because world is too small. Include the test with mpirun -n %d" % (maxsize))
    sizes = sorted(set(list(required) + list(NTask)))
    def dec(func):
        def wrapped(*args):
            for size in sizes:
                if MPI.COMM_WORLD.size < size: continue
                color = 0 if MPI.COMM_WORLD.rank < size else 1
                comm = MPI.COMM_WORLD.Split(color)

                if color == 0:
                    def func2(size):
                        # if the above fails then some ranks have already failed.
                        # we are doomed anyways.
                        func(*args, comm=comm)
                    func2.description = "MPIWorld(size=%d):%s" % (size, func.__name__)
                    yield func2, size
        wrapped.__name__ = func.__name__
        return wrapped
    return dec

import sys
import os
try:
    from cStringIO import StringIO
except:
    from io import StringIO

import shutil
import subprocess
import time
import imp
from argparse import ArgumentParser, REMAINDER

class MPITester(object):
    """
    runtests.py [OPTIONS] [-- ARGS]

    Run tests, building the project first.

    Examples::

        $ python runtests.py
        $ python runtests.py --mpirun
        $ python runtests.py --mpirun="mpirun -np 4"
        $ python runtests.py --mpirun --mpi-unmute
        $ python runtests.py -s my/module/
        $ python runtests.py -t my/module/tests/test_abc.py
        $ python runtests.py --ipython
        $ python runtests.py --python somescript.py

    Run a debugger:

        $ gdb --args python runtests.py [...other args...]

    Generate C code coverage listing under build/lcov/:
    (requires http://ltp.sourceforge.net/coverage/lcov.php)

        $ python runtests.py --gcov [...other args...]
        $ python runtests.py --lcov-html

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
        def addmpirun(parser):
            parser.add_argument("--mpirun", default=None, nargs='?', const="mpirun -n 4",
                                help="launcher for MPI, e.g. mpirun -n 4")
        # In case we are run from the source directory, we don't want to import the
        # project from there:
        sys.path.pop(0)

        parser = ArgumentParser(usage=self.__doc__.lstrip())
        parser.add_argument("--verbose", "-v", action="count", default=1,
                            help="more verbosity")
        parser.add_argument("--no-build", "-n", action="store_true", default=False,
                            help="do not build the project (use system installed version)")
        parser.add_argument("--mpisub", action="store_true", default=False,
                            help="run as a mpisub.")
        parser.add_argument("--mpisub-site-dir", default=None, help="site-dir in mpisub")
        parser.add_argument("--build-only", "-b", action="store_true", default=False,
                            help="just build, do not run any tests")
        parser.add_argument("--doctests", action="store_true", default=False,
                            help="Run doctests in module")
        parser.add_argument("--refguide-check", action="store_true", default=False,
                            help="Run refguide check (do not run regular tests.)")
        parser.add_argument("--coverage", action="store_true", default=False,
                            help=("report coverage of project code. HTML output goes "
                                  "under build/coverage"))
        parser.add_argument("--gcov", action="store_true", default=False,
                            help=("enable C code coverage via gcov (requires GCC). "
                                  "gcov output goes to build/**/*.gc*"))
        parser.add_argument("--lcov-html", action="store_true", default=False,
                            help=("produce HTML for C code coverage information "
                                  "from a previous run with --gcov. "
                                  "HTML output goes to build/lcov/"))
        parser.add_argument("--mode", "-m", default="fast",
                            help="'fast', 'full', or something that could be "
                                 "passed to nosetests -A [default: fast]")
        parser.add_argument("--submodule", "-s", default=None,
                            help="Submodule whose tests to run (cluster, constants, ...)")
        parser.add_argument("--pythonpath", "-p", default=None,
                            help="Paths to prepend to PYTHONPATH")
        parser.add_argument("--tests", "-t", action='append',
                            help="Specify tests to run")
        parser.add_argument("--python", action="store_true",
                            help="Start a Python shell with PYTHONPATH set")
        parser.add_argument("--ipython", "-i", action="store_true",
                            help="Start IPython shell with PYTHONPATH set")
        parser.add_argument("--shell", action="store_true",
                            help="Start Unix shell with PYTHONPATH set")
        parser.add_argument("--debug", "-g", action="store_true",
                            help="Debug build")
        parser.add_argument("--parallel", "-j", type=int, default=1,
                            help="Number of parallel jobs during build (requires "
                                 "Numpy 1.10 or greater).")
        parser.add_argument("--show-build-log", action="store_true",
                            help="Show build output rather than using a log file")
        parser.add_argument("--bench", action="store_true",
                            help="Run benchmark suite instead of test suite")
        parser.add_argument("--bench-compare", action="append", metavar="BEFORE",
                            help=("Compare benchmark results of current HEAD to BEFORE. "
                                  "Use an additional --bench-compare=COMMIT to override HEAD with COMMIT. "
                                  "Note that you need to commit your changes first!"
                                 ))
        parser.add_argument("args", metavar="ARGS", default=[], nargs=REMAINDER,
                            help="Arguments to pass to Nose, Python or shell")
        addmpirun(parser)
        args = parser.parse_args(argv)

        if args.mpisub:
            args.no_build = True # master does the building

        if args.bench_compare:
            args.bench = True
            args.no_build = True # ASV does the building

        if args.lcov_html:
            # generate C code coverage output
            lcov_generate()
            sys.exit(0)

        if args.pythonpath:
            for p in reversed(args.pythonpath.split(os.pathsep)):
                sys.path.insert(0, p)

        if args.gcov:
            gcov_reset_counters()

        if args.debug and args.bench:
            print("*** Benchmarks should not be run against debug version; remove -g flag ***")

        if not args.no_build:
            site_dir = self.build_project(args)
            sys.path.insert(0, site_dir)
            print(site_dir)
            os.environ['PYTHONPATH'] = site_dir
        if args.mpisub_site_dir:
            site_dir = args.mpisub_site_dir

        extra_argv = args.args[:]
        if extra_argv and extra_argv[0] == '--':
            extra_argv = extra_argv[1:]

        if args.python:
            if extra_argv:
                # Don't use subprocess, since we don't want to include the
                # current path in PYTHONPATH.
                sys.argv = extra_argv
                with open(extra_argv[0], 'r') as f:
                    script = f.read()
                sys.modules['__main__'] = imp.new_module('__main__')
                ns = dict(__name__='__main__',
                          __file__=extra_argv[0])
                exec_(script, ns)
                sys.exit(0)
            else:
                import code
                code.interact()
                sys.exit(0)

        if args.ipython:
            import IPython
            IPython.embed(user_ns={})
            sys.exit(0)

        if args.shell:
            shell = os.environ.get('SHELL', 'sh')
            print("Spawning a Unix shell...")
            if len(extra_argv) == 0:
                os.execv(shell, [shell])
            else:
                os.execvp(extra_argv[0], extra_argv)
            sys.exit(1)

        if args.coverage:
            dst_dir = os.path.join(self.ROOT_DIR, 'build', 'coverage')
            fn = os.path.join(dst_dir, 'coverage_html.js')
            if os.path.isdir(dst_dir) and os.path.isfile(fn):
                shutil.rmtree(dst_dir)
            extra_argv += ['--cover-html',
                           '--cover-html-dir='+dst_dir]

        if args.refguide_check:
            cmd = [os.path.join(self.ROOT_DIR, 'tools', 'refguide_check.py'),
                   '--doctests']
            if args.submodule:
                cmd += [args.submodule]
            os.execv(sys.executable, [sys.executable] + cmd)
            sys.exit(0)

        if args.mpirun:
            parser = ArgumentParser()
            addmpirun(parser)
            args, additional = parser.parse_known_args()
            mpirun = args.mpirun.split()

            os.execvp(mpirun[0], mpirun + [sys.executable, sys.argv[0], '--mpisub', '--mpisub-site-dir=' + site_dir ] + additional)

            sys.exit(1)

        test_dir = os.path.join(self.ROOT_DIR, 'build', 'test')

        if args.build_only:
            sys.exit(0)
        elif args.submodule:
            modname = self.PROJECT_MODULE + '.' + args.submodule
            try:
                __import__(modname)
                test = sys.modules[modname].test
            except (ImportError, KeyError, AttributeError) as e:
                print("Cannot run tests for %s (%s)" % (modname, e))
                sys.exit(2)
        elif args.tests:
            def fix_test_path(x):
                # fix up test path
                p = x.split(':')
                p[0] = os.path.relpath(os.path.abspath(p[0]),
                                       self.ROOT_DIR)
                p[0] = os.path.join(site_dir, p[0])
                return ':'.join(p)

            tests = [fix_test_path(x) for x in args.tests]

            def test(*a, **kw):
                extra_argv = kw.pop('extra_argv', ())
                extra_argv = extra_argv + tests[1:]
                kw['extra_argv'] = extra_argv

                save = dict(globals())

                from numpy.testing import Tester
                result = Tester(tests[0]).test(*a, **kw)
                # numpy tester messes up with globals. somehow.
                globals().update(save)

                return result
        else:
            __import__(self.PROJECT_MODULE)
            test = sys.modules[self.PROJECT_MODULE].test

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
            os.chdir(test_dir)
            result = test(args.mode,
                          verbose=args.verbose if self.comm.rank == 0 else 0,
                          extra_argv=extra_argv + ['--quiet'] if self.comm.rank != 0 else []
                                                + ['--stop'] if args.mpisub else [] ,
                          doctests=args.doctests,
                          coverage=args.coverage)
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

        code = 0
        if isinstance(result, bool):
            code = 0 if result else 1
        elif result.wasSuccessful():
            code = 0
        else:
            code = 1

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
        import time
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

        if args.debug or args.gcov:
            # assume everyone uses gcc/gfortran
            env['OPT'] = '-O0 -ggdb'
            env['FOPT'] = '-O0 -ggdb'
            if args.gcov:
                import distutils.sysconfig
                cvars = distutils.sysconfig.get_config_vars()
                env['OPT'] = '-O0 -ggdb'
                env['FOPT'] = '-O0 -ggdb'
                env['CC'] = cvars['CC'] + ' --coverage'
                env['CXX'] = cvars['CXX'] + ' --coverage'
                env['F77'] = 'gfortran --coverage '
                env['F90'] = 'gfortran --coverage '
                env['LDSHARED'] = cvars['LDSHARED'] + ' --coverage'
                env['LDFLAGS'] = " ".join(cvars['LDSHARED'].split()[1:]) + ' --coverage'

        cmd += ['build']
        if args.parallel > 1:
            cmd += ['-j', str(args.parallel)]

        cmd += ['install', '--prefix=' + dst_dir]

        log_filename = os.path.join(self.ROOT_DIR, 'build.log')

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


    #
    # GCOV support
    #
    def gcov_reset_counters():
        print("Removing previous GCOV .gcda files...")
        build_dir = os.path.join(self.ROOT_DIR, 'build')
        for dirpath, dirnames, filenames in os.walk(build_dir):
            for fn in filenames:
                if fn.endswith('.gcda') or fn.endswith('.da'):
                    pth = os.path.join(dirpath, fn)
                    os.unlink(pth)

    #
    # LCOV support
    #

    def lcov_generate():
        LCOV_OUTPUT_FILE = os.path.join(self.ROOT_DIR, 'build', 'lcov.out')
        LCOV_HTML_DIR = os.path.join(self.ROOT_DIR, 'build', 'lcov')

        try: os.unlink(LCOV_OUTPUT_FILE)
        except OSError: pass
        try: shutil.rmtree(LCOV_HTML_DIR)
        except OSError: pass

        print("Capturing lcov info...")
        subprocess.call(['lcov', '-q', '-c',
                         '-d', os.path.join(self.ROOT_DIR, 'build'),
                         '-b', self.ROOT_DIR,
                         '--output-file', LCOV_OUTPUT_FILE])

        print("Generating lcov HTML output...")
        ret = subprocess.call(['genhtml', '-q', LCOV_OUTPUT_FILE, 
                               '--output-directory', LCOV_HTML_DIR, 
                               '--legend', '--highlight'])
        if ret != 0:
            print("genhtml failed!")
        else:
            print("HTML output generated under build/lcov/")


#
# Python 3 support
#

if sys.version_info[0] >= 3:
    import builtins
    exec_ = getattr(builtins, "exec")
else:
    def exec_(code, globs=None, locs=None):
        """Execute code in a namespace."""
        if globs is None:
            frame = sys._getframe(1)
            globs = frame.f_globals
            if locs is None:
                locs = frame.f_locals
            del frame
        elif locs is None:
            locs = globs
        exec("""exec code in globs, locs""")

from numpy.testing import Tester
test = Tester().test
bench = Tester().bench
