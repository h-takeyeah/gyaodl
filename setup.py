from setuptools import setup, find_packages
from gyaodl.main import program_version

setup(
    name='gyaodl',
    version=program_version,
    description='Terminal based GYAO! video downloader.',
    packages=find_packages(),
    entry_points={'console_scripts': ['gyaodl = gyaodl.main:main']}
)
