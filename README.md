# mdensemble

Run molecular dynamics ensemble simulations in parallel using OpenMM.

## Table of Contents
- [mdensemble](#mdensemble)
  - [Table of Contents](#table-of-contents)
  - [Installation](#installation)

## Installation

Create a conda environment
```console
conda create -n mdensemble python=3.9 -y
conda activate mdensemble
```

To install OpenMM for simulations:
```console
conda install -c conda-forge gcc=12.1.0 -y
conda install -c conda-forge openmm -y
```

To install `mdensemble`:
```console
git clone https://github.com/braceal/mdensemble
cd mdensemble
make install
```