from distutils.core import setup

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
    author="Yu Feng, Nick Hand",
    author_email="rainwoodman@gmail.com",
    url="http://github.com/rainwoodman/mpi4py_test",
    description="Simple testing of fresh builds using pytest, with optional mpi4py support",
    zip_safe = False,
    package_dir = {'mpi4py_test': 'mpi4py_test'},
    install_requires=['pytest', 'coverage'],
    license='BSD-2-Clause',
    packages= ['mpi4py_test', 'mpi4py_test_tests'],
    requires=['pytest', 'coverage'],
    extras_require={'full':['mpi4py'], 'mpi':['mpi4py']}
)
