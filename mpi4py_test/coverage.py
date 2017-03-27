import tempfile
import os
import coverage

class Coverage(object):
    """
    Context manager to handle code coverage using coverage.py module
    
    This handle multiples MPI processes by writing data
    to separate coverage files during code execution and using the 
    root process to combine them at the end
    """
    
    def __init__(self, comm, source, with_coverage=False, html_cov=False, 
                    config_file=None, root=''):
        """
        Parameters
        ----------
        comm : MPI communicator
            the MPI communicator
        source : str
            the name of the package module which we are reporting coverage for
        with_coverage : bool, optional
            whether to record the coverage
        html_cov : bool, optional
            whether to save a html coverage report; in 'build/coverage'
        config_file : str, optional
            a coveragerc file to load
        root : str, optional
            this specifies the root of the package 
        """
        self.comm = comm
        self.source = source
        self.root = root
        
        # options
        self.with_coverage = with_coverage 
        self.config_file = os.path.join(root, config_file)
        self.html_cov = html_cov
        
        # check if coverage file exists
        if not os.path.exists(self.config_file):
            self.config_file = None
        
    def __enter__(self):
        
        if not self.with_coverage:
            self.cov = None
            return
        else:
            self.cov = coverage.coverage(source=[self.source], config_file=self.config_file)
            self.cov.start()
        
    def __exit__(self, type, value, tb):
        if not self.with_coverage:
            return
        
        self.cov.stop()
        with tempfile.TemporaryDirectory() as tmpdir:
            
            # write coverage data file
            self.cov.get_data().write_file(os.path.join(tmpdir, '.coverage.%d' % os.getpid()))
            
            # now combine from each rank and save
            if self.comm.rank == 0:
                
                # write out combined data
                combined_cov = coverage.coverage(config_file=self.config_file, data_file='.coverage')
                combined_cov.combine(data_paths=[tmpdir])
                combined_cov.get_data().write_file(os.path.join(self.root, self.cov.config.data_file))
                
                # and report
                combined_cov.report()
                
                # write html
                if self.html_cov:
                    html_dir = os.path.join(self.root, 'build', 'coverage')
                    if not os.path.exists(html_dir):
                        os.makedirs(html_dir)
                    combined_cov.html_report(directory=html_dir)
            
            self.comm.barrier()

    