from distutils.core import setup
import numpy

def find_version(path):
    import re
    # path shall be a plain ascii text file.
    s = open(path, 'rt').read()
    version_match = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]",
                              s, re.M)
    if version_match:
        return version_match.group(1)
    raise RuntimeError("Version not found")

setup(
    name="mpi4py_test",
    version=find_version("mpi4py_test/version.py"),
    author="Yu Feng",
    author_email="rainwoodman@gmail.com",
    url="http://github.com/rainwoodman/mpi4py_test",
    description="Simple testing based on numpy for applications written with mpi4py.",
    zip_safe = False,
    package_dir = {'mpi4py_test': 'mpi4py_test'},
    install_requires=['numpy'],
    packages= ['mpi4py_test', 'mpi4py_test.tests'],
    requires=['numpy'],
)
