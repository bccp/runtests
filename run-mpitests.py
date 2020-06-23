import sys;
from runtests.mpi import Tester

import os.path

tester = Tester(os.path.join(os.path.abspath(__file__)), "runtests")

tester.main(sys.argv[1:])
