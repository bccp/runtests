# pop the current directory from search path
# python interpreter adds this to a top level script
# but we will likely have a name conflict (runtests.py .vs runtests package)
import sys;
from runtests.mpi import Tester

import os.path

tester = Tester(os.path.join(os.path.abspath(__file__)), "runtests")

tester.main(sys.argv[1:])
