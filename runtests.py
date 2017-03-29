from mpi4py_test.mpi import Tester
import sys
import os.path

tester = Tester(os.path.abspath(__file__), "mpi4py_test")
tester.main(sys.argv[1:])
