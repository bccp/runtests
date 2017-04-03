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
    name="runtests",
    version=find_version("runtests/version.py"),
    author="Yu Feng, Nick Hand",
    author_email="rainwoodman@gmail.com",
    url="http://github.com/rainwoodman/runtests",
    description="Simple testing of fresh package builds using pytest, with optional mpi4py support",
    zip_safe = False,
    package_dir = {'runtests': 'runtests'},
    install_requires=['pytest', 'coverage'],
    license='BSD-2-Clause',
    packages= ['runtests', 'runtests.mpi'],
    requires=['pytest', 'coverage'],
    package_data = {'runtests' : ['tests/*.py', 'mpi/tests/*.py']},
    extras_require={'full':['mpi4py'], 'mpi':['mpi4py']}
)
