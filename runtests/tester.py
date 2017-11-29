from .coverage import Coverage
from .benchmark import BenchmarkLogger, BenchmarkTimer
import pytest
import traceback
import sys
import os
import contextlib
import shutil
import subprocess
import time

def get_git_revision_short_hash():
    null = open(os.devnull, 'w')
    toret = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD'], stderr=null)
    return toret.strip().decode()

def get_source_version(module):
    null = open(os.devnull, 'w')
    toret = subprocess.check_output(['python', 'setup.py', '--version'], stderr=null)
    return toret.strip().decode()

def _make_clean_dir(path):
    print("Purging %s ..." % path)
    try:
        shutil.rmtree(path)
    except OSError:
        pass
    try:
        os.makedirs(path)
    except OSError:
        pass

class Tester(object):
    """
    Run tests using pytest, building a fresh version of the project first.

    Examples::
        $ python runtests.py my/module
        $ python runtests.py my/module/tests/test_abc.py
        $ python runtests.py
        $ python runtests.py --bench
    """
    @pytest.fixture(scope="session")
    def session_benchmark(self, request):
        """
        A session-wide benchmark to time and record benchmarks,
        corresponding to :class:`BenchmarkLogger`

        This class acts as a logger to store and save all benchmark
        results from the testing session.
        """
        comm = self.comm if hasattr(self, 'comm') else None

        # determine the output dir
        benchdir = request.config.getoption('bench_dir')
        if benchdir is not None:
            benchdir = os.path.join(self.ROOT_DIR, benchdir)
            benchdir = os.path.relpath(benchdir, self.TEST_DIR)
        else:
            benchdir = self.BENCHMARK_DIR

        # initialize
        kws = {'version':self.source_version, 'git_hash':self.source_git_hash}
        benchmark = BenchmarkLogger(benchdir, comm=comm, **kws)

        # yield to user
        yield benchmark

        # finalize by reporting (needs to be COLLECTIVE call)
        benchmark.report()

    @staticmethod
    @pytest.fixture(scope="function")
    def benchmark(session_benchmark, request):
        """
        An object to benchmark an individual test function. When called,
        this object acts a context manager that does the timing.

        This object has a ``attrs`` dict that the user can add meta-data to,
        and it reports its results to the ``session_benchmark`` object.
        """
        # the qualified name of the function being run
        func = request.node.function
        mod, name = func.__module__, func.__name__
        qualname = mod + '.' + name

        # initialize the timer
        timer = BenchmarkTimer(qualname, request.node, comm=session_benchmark.comm)

        # return the session-wide benchmark
        yield timer

        # add result to total
        session_benchmark.add_benchmark(timer)

    @staticmethod
    def pytest_addoption(parser):
        """
        Add command-line options to specify MPI and coverage configuration
        """
        parser.addoption("--no-build", action="store_true", default=False,
                        help="do not build the project (use system installed version)")

        parser.addoption("--clean-build", action="store_true", default=False,
                        help="cleanly build, purging the build directory first. ")

        parser.addoption("--parallel", default=0, type=int, help="run a parallel build")
        parser.addoption("--enable-debug", default=False, action="store_true", help="Compile with debugging information. May need --clean-build for a clean rebuild of all targets.")

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
        parser.addoption("--bench-dir", type=str,
                        help="the directory to write benchmark results; default is build/benchmarks")

        parser.addoption("--bench", action="store_true", default=False,
                        help="only run tests that use the 'benchmark' fixture")


    @staticmethod
    def pytest_collection_modifyitems(session, config, items):
        """
        Modify the ordering of tests, such that the ordering will be
        well-defined across all ranks running
        """
        def benchmark_filter(item):
            if config.getoption('bench'):
                return 'benchmark' in item.fixturenames
            else:
                return 'benchmark' not in item.fixturenames

        # filter based on benchmarking
        items[:] = [item for item in items if benchmark_filter(item)]

        # sort the tests
        items[:] = sorted(items, key=lambda x: str(x))

    def __init__(self, package_file, module,
            extra_path =['/usr/lib/ccache', '/usr/lib/f90cache',
                         '/usr/local/lib/ccache', '/usr/local/lib/f90cache']
        ):
        """
        Parameters
        ----------
        package_files : str
            the path to the main directory of the source package
        module : str
            the name of the package to test
        extra path : list of str
            extra paths to include on PATH when building
        """
        self.ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(package_file)))
        self.PROJECT_ROOT_FILES = [package_file, 'setup.py']
        self.EXTRA_PATH = extra_path
        self.PROJECT_MODULE = module
        self.TEST_DIR = os.path.join(self.ROOT_DIR, 'build', 'test')
        self.DEST_DIR = os.path.join(self.ROOT_DIR, 'build', 'testenv')
        self.BUILD_DIR = os.path.join(self.ROOT_DIR, 'build')
        self.BENCHMARK_DIR = os.path.join(self.ROOT_DIR, 'build', 'benchmarks')

        from distutils.sysconfig import get_python_lib
        site_dir = get_python_lib(prefix=self.DEST_DIR, plat_specific=True)
        site_dir_noarch = get_python_lib(prefix=self.DEST_DIR, plat_specific=False)

        # the true site dir will be found after build_project.
        self.SITE_DIRS = [site_dir, site_dir_noarch]


        # the source version
        try:
            self.source_version = get_source_version(module)
        except:
            self.source_version = None

        # the git str
        try:
            self.source_git_hash = get_git_revision_short_hash()
        except:
            self.source_git_hash = None


    def main(self, argv):
        """
        The main function to run the tests

        Parameters
        ----------
        argv : list of str
            the command-line arguments -- should be equal to ``sys.argv[1:]``
        """
        # initialize the pytest configuration from the command-line args
        config = self._get_pytest_config(argv)
        args = config.known_args_namespace

        # print help and exit
        if args.help:
            return config.hook.pytest_cmdline_main(config=config)

        # verify bench was provided if a benchmarks dir was provided
        benchdir = config.getoption('bench_dir')
        if benchdir is not None and not config.getoption('bench'):
            raise ValueError("please specify '--bench' on the command-line to run benchmarks")

        # make the test directory exists
        self._initialize_dirs(args)

        # import project from system path
        # this forces pytest to import the freshly built package
        args.pyargs = True

        # build the project, returning the site directory
        if not args.no_build:
            site_dir = self._do_build(args)

        if not args.bench:
            # tests are part of package, thus installed; we use those
            # but benchs are not part of package, thus not installed.
            config.args = self._fix_test_paths(site_dir, config.args)

        if args.shell:
            self._do_shell(args, config)

        if args.build_only:
            sys.exit(0)


        # extract the coverage-related options
        covargs = {}
        covargs['with_coverage'] = args.with_coverage
        covargs['config_file'] = args.cov_config
        covargs['html_cov'] = args.html_cov

        # run the tests
        try:
            code = None
            with self._run_from_testdir(args):
                code = self._test(config, **covargs)
        except:
            traceback.print_exc()
            sys.exit(1)

        sys.exit(code)

    def _test(self, config, **kwargs):
        """
        Run the actual tests with optional coverage -- a wrapper around
        the pytest calling sequence

        Parameters
        ----------
        config :
            the pytest configuration object
        kwargs :
            additional keywords to pass to the Coverage class
        """
        try:
            with Coverage(self.PROJECT_MODULE, root=self.ROOT_DIR, **kwargs):
                config.pluginmanager.check_pending()
                return config.hook.pytest_cmdline_main(config=config)
        finally:
            config._ensure_unconfigure()

    def _do_build(self, args):
        """
        Build the project and return the site directory in the
        build/ directory
        """
        self._build_project(args)

        for site_dir in self.SITE_DIRS:
            if os.path.exists(os.path.join(site_dir, self.PROJECT_MODULE)):
                break
        else:
            print("Package %s not properly installed" % self.PROJECT_MODULE)
            sys.exit(1)

        sys.path.insert(0, site_dir)
        os.environ['PYTHONPATH'] = site_dir

        return site_dir

    def _do_shell(self, args, config):
        capman = config.pluginmanager.getplugin('capturemanager')
        if capman:
            if hasattr(capman, 'suspend_global_capture'):
                capman.suspend_global_capture(in_=True)
            else:
                capman.suspendcapture(in_=True)

        shell = os.environ.get('SHELL', 'sh')
        print("Spawning a Unix shell...")
        with self._run_from_testdir(args):
            os.execv(shell, [shell] + config.args[1:])
            sys.exit(1)

    @contextlib.contextmanager
    def _run_from_testdir(self, args):
        """
        Context manager to safely change directory
        to ``build/test``
        """
        cwd = os.getcwd()

        try:
            os.chdir(self.TEST_DIR)
            yield
        finally:
            os.chdir(cwd)

    def _get_pytest_config(self, argv):
        """
        Return the ``pytest`` configuration object based on the
        command-line arguments
        """
        import _pytest.config as _config

        plugins = [self]

        # disable pytest-cov
        argv += ['-p', 'no:pytest_cov']

        # Do not load any conftests initially.
        # This is a hack to avoid ConftestImportFailure raised when the
        # pytest does its initial import of conftests in the source directory.
        # This prevents any manipulation of the command-line via conftests
        argv += ['--noconftest']

        # get the pytest configuration object
        try:
            config = _config._prepareconfig(argv, plugins)
        except _config.ConftestImportFailure as e:
            tw = _config.py.io.TerminalWriter(sys.stderr)
            for line in traceback.format_exception(*e.excinfo):
                tw.line(line.rstrip(), red=True)
            tw.line("ERROR: could not load %s\n" % (e.path), red=True)
            raise

        # Restore the loading of conftests, which was disabled earlier
        # Conftest files will now be loaded properly at test time
        config.pluginmanager._noconftest = False

        return config

    def _initialize_dirs(self, args):
        """
        Initialize the ``build/test/`` directory
        """
        if args.clean_build:
            _make_clean_dir(self.BUILD_DIR)

        if not args.no_build:
            _make_clean_dir(self.DEST_DIR)

        _make_clean_dir(self.TEST_DIR)

    def _clean_build(self):
        """
        Clean the build directory.
        """

    def _fix_test_paths(self, site_dir, args):
        """
        Fix the paths of tests to run to point to the corresponding
        tests in the site directory
        """
        def fix_test_path(x):
            p = x.split('::')
            p[0] = os.path.relpath(os.path.abspath(p[0]), self.ROOT_DIR)
            p[0] = os.path.join(site_dir, p[0])
            return '::'.join(p)
        return [fix_test_path(x) for x in args]

    def _build_project(self, args):
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

        env = dict(os.environ)
        cmd = [sys.executable, 'setup.py']

        # Always use ccache, if installed
        env['PATH'] = os.pathsep.join(self.EXTRA_PATH + env.get('PATH', '').split(os.pathsep))

        # easy_install won't install to a path that Python by default cannot see
        # and isn't on the PYTHONPATH.  Plus, it has to exist.
        for dir in self.SITE_DIRS:
            basedir = os.path.dirname(dir)
            if not os.path.exists(basedir):
                os.makedirs(basedir)

        env['PYTHONPATH'] = ':'.join(self.SITE_DIRS)

        if args.enable_debug:
            # assume everyone who debugs uses gcc/gfortran
            env['OPT'] = '-O0 -ggdb'
            env['FOPT'] = '-O0 -ggdb'

        cmd += ['build']

        if args.parallel > 1:
            cmd += ["-j", str(args.parallel)]

        with open('setup.py', 'rt') as ff:
            text = ff.read()
            import re
            if re.search('from\s\s*setuptools', text):
                use_setuptools = True
            elif re.search('import\s\s*setuptools', text):
                use_setuptools = True
            else:
                use_setuptools = False

        if use_setuptools:
            cmd += ['install', '--prefix=' + self.DEST_DIR,
                    '--single-version-externally-managed',
                    '--record=' + self.DEST_DIR + 'tmp_install_log.txt']
        else:
            cmd += ['install', '--prefix=' + self.DEST_DIR]

        log_filename = os.path.join(self.ROOT_DIR, 'build.log')
        if args.show_build_log:
            ret = subprocess.call(cmd, env=env, cwd=self.ROOT_DIR)
        else:
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
