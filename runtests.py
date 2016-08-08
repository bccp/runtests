from mpi4py_test import MPITester
import sys
import os.path
print os.path.abspath(__file__)

tester = MPITester(os.path.abspath(__file__), "mpi4py_test")

tester.main(sys.argv)
