from setuptools import setup, find_packages

setup(
    name='gyaodl',
    version='0.3',
    description='Terminal based GYAO! video downloader.',
    packages=find_packages(),
    entry_points={'console_scripts': ['gyaodl = gyaodl.main:main']}
)
