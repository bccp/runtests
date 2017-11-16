import time
from contextlib import contextmanager
import platform
import time
import os
from collections import defaultdict
import itertools
import json

def get_machine_info():
    """
    Return information about the machine, including host,
    system, and the python version.
    """
    return {'host':platform.node(),
            'system': platform.system(),
            'python_version': ".".join(platform.python_version_tuple())}


class BenchmarkLogger(object):
    """
    A class to serve as a session-wide benchmarking fixture, tracking
    the benchmark results for individual tests.

    A single JSON file is written to the specified output directory
    for each test. Machine info and related system information is also
    written to the JSON file.

    Parameters
    ----------
    output_dir : str
        the output directory to write results to
    comm : MPI comm, None, optional
        the MPI communicator or None if running serially
    version : str, optional
        the version of the source code being run
    git_hash : str, optional
        the short version of the git commit hash of the source code
    """
    def __init__(self, output_dir, comm=None, version=None, git_hash=None):

        # the header
        self.header = {}
        self.header['source_version'] = version
        self.header['git_hash'] = git_hash
        self.header.update(get_machine_info())
        self.header["datetime"] = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
        self.header['commsize'] = 1 if comm is None else comm.size

        self.comm = comm
        self.benchmarks = defaultdict(dict)
        self.tests_counter = defaultdict(int)

        # handle output dir
        self.output_dir = output_dir
        if self.comm is None or self.comm.rank == 0:
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)

    def add_benchmark(self, result):
        """
        Add a benchmark result to the total set of benchmarks.

        Parameters
        ----------
        result : BenchmarkTimer
            an individual benchmark result
        """
        key = os.path.join(result.qualname, result.original_testname)
        name = key + '_%d' % self.tests_counter[key]

        # copy over the result
        r = result.benchmark.copy()
        r['attrs'] = result.attrs.copy()

        # add to total benchmarks
        self.benchmarks[name].update(r)

        # increment test counter
        self.tests_counter[key] += 1

    def report(self):
        """
        Report the benchmark results for all tests run.

        Benchmark results for individual files are stored in different
        files in :attr:`output_dir`. Results for variants of the same test
        function (via parametrization) are stored in the same file.

        Benchmark results for a single test variant are stored as a list,
        equal to the length of the comm size.

        .. note::
            When using MPI, this should be collectively, as benchmark
            results are gathered from all ranks. Only the
        """
        # group results by the file they will be written to
        # NOTE: this name ignores the parametrization (parametrized results
        # get written to same file)
        keyfunc = lambda x: self.benchmarks[x]['filename']
        groups = itertools.groupby(self.benchmarks.keys(), key=keyfunc)

        # sort groups so we avoid MPI issues
        groups = [(key, list(subgroup)) for key, subgroup in groups]
        groups = sorted(groups, key=lambda x: x[0])

        # loop over each parametrized test function
        for filename, subgroup in groups:

            # start with the info for this test
            result = {}
            result['config'] = self.header.copy()
            result['tests'] = []

            # loop over subgroups
            # NOTE: these are the parametrized test variants
            for i, key in enumerate(sorted(subgroup)):

                # extract the name of this test
                name = key.split('/')[-1]
                result['tests'].append(name)

                # initialize dict holding the individual results
                result[name] = {}

                # a group of benchmarks
                # NOTE: contains results for all tags within a single function run
                # for a parametrized variant
                benchmark_group = self.benchmarks[key]
                tags = sorted(benchmark_group['tags'])

                # for each tag, gather the benchmark results from each rank
                for tag in tags:
                    if self.comm is None:
                        benchmarks = [benchmark_group[tag]]
                    else:
                        benchmarks = self.comm.allgather(benchmark_group[tag])
                    result[name][tag] = benchmarks

                # store meta data
                result[name]['testname'] = benchmark_group['testname']
                result[name]['attrs'] = benchmark_group['attrs']

                # track section names for each test
                if i == 0:
                    result['tags'] = tags

            # write out
            if self.comm is None or self.comm.rank == 0:
                filename = os.path.join(self.output_dir, filename) + '.json'
                json.dump(result, open(filename, 'w'))

class BenchmarkTimer(object):
    """
    A class to serve as a function-scoped benchmarking fixture that is
    reponsible for timing each function.

    This will log its results with :class:`BenchmarkLogger`.

    Parameters
    ----------
    qualname : str
        the qualified name of the function being run; this is
        ``module_name . func_name``
    node :
        the request node corresponding to to this test function.
    """
    def __init__(self, qualname, node, comm=None):

        # add the testname
        self.qualname = qualname
        self.testname = node.name # NOTE: this will include parametrized ID

        # add the qualified test path for output file
        # (removes any parametrization IDs)
        self.original_testname = node.originalname
        if self.original_testname is None:
            self.original_testname = self.testname

        # the name of the file this function should be written too
        self.filename = '.'.join(self.qualname.split('.')[:-1] + [self.original_testname])

        self.comm = comm

        # store benchmarks here
        self.benchmark = {'filename':self.filename, 'testname':self.testname}
        self.benchmark['tags'] = []

        # store meta-data here
        self.attrs = {}

    @contextmanager
    def __call__(self, tag):
        """
        A context manager that uses :func:`time.time` to compute the elapsed
        time spent in the context.

        Parameters
        ----------
        tag : str
            an identifying tag to label this benchmark
        """
        if self.comm is not None:
            self.comm.barrier()

        start = time.time()
        yield
        end = time.time()

        # record the results in benchmarks attribute
        elapsed = end-start
        self.benchmark[tag] = elapsed
        self.benchmark['tags'].append(tag)
