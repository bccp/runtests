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

class BenchmarkFixture(object):
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

        # handle output dir
        self.output_dir = output_dir
        if self.comm is None or self.comm.rank == 0:
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)

        # initialize empty function names
        # these will be updated when each benchmarked function is executed
        self.testname = None
        self.qualname = None

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
        name = os.path.join(self.qualname, self.testname)
        self.benchmarks[name][tag] = elapsed
        self.benchmarks[name]['filename'] = self.filename

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
        # group results by original test function name
        # NOTE: this name ignores the parametrization
        keyfunc = lambda x: self.benchmarks[x]['filename']
        groups = itertools.groupby(self.benchmarks.keys(), key=keyfunc)

        # sort groups so we avoid MPI issues
        groups = [(key, list(subgroup)) for key, subgroup in groups]
        groups = sorted(groups, key=lambda x: x[0])

        # loop and gather each parametrized test function
        for filename, subgroup in groups:

            # start with the info for this test
            result = self.header.copy()
            result['tests'] = []
            result['sections'] = []

            # loop over subgroups
            # NOTE: these are the parametrized test variants
            for i, key in enumerate(sorted(subgroup)):
                name = key.split('/')[-1]
                result['tests'].append(name)

                # gather the benchmark results from each rank
                if self.comm is None:
                    benchmarks = [self.benchmarks[key]]
                else:
                    benchmarks = self.comm.allgather(self.benchmarks[key])

                # gather time results into list of length commsize
                result[name] = defaultdict(list)
                for bmark in benchmarks:
                    for section in bmark.keys():
                        result[name][section].append(bmark[section])

                # track section names for each test
                if i == 0:
                    result['sections'] = sorted(result[name])

            # write out
            if self.comm is None or self.comm.rank == 0:
                filename = os.path.join(self.output_dir, filename) + '.json'
                json.dump(result, open(filename, 'w'))
