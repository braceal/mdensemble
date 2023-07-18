# mdensemble

Run molecular dynamics ensemble simulations in parallel using OpenMM.

## Table of Contents
- [mdensemble](#mdensemble)
  - [Table of Contents](#table-of-contents)
  - [Installation](#installation)
  - [Usage](#usage)

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

## Usage

The workflow can be tested on a workstation (a system with a few GPUs) via:
```console
python -m mdensemble.workflow -c examples/example.yaml
```
This will generate an output directory `example_output` for the run with logs, results, and task output folders.

Inside the output directory, you will find:
```console
$ ls example_output
tasks  params.yaml  result  run-info  runtime.log
```
- `params.yaml`: the full configuration file (default parameters included)
- `runtime.log`: the workflow log
- `result`: a directory containing JSON files `task.json` which logs task results including success or failure, potential error messages, runtime statistics. This can be helpful for debugging application-level failures.
- `tasks`: directory containing a subdirectory for each submitted task. This is where the output files of your simulations,  will be written.
- `run-info`: Parsl runtime logs

**TODO**: Update this
An example, the simulation run directories may look like:
```console
$ ls runs/experiment-170323-091525/simulation/run-08843adb-65e1-47f0-b0f8-34821aa45923:
1FME-unfolded.pdb  input.yaml  output.yaml  rmsd.npy  sim.dcd  sim.log
```
- `checkpoint.chk`: the simulation checkpoint file
- `sim.dcd`: the simulation trajectory file containing all the coordinate frames
- `sim.log`: a simulation log detailing the energy, steps taken, ns/day, etc