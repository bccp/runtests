import sys;
from runtests import Tester
import os.path

tester = Tester(os.path.abspath(__file__), "runtests")

tester.main(sys.argv[1:])
