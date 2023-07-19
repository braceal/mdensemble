# mdensemble

Run molecular dynamics ensemble simulations in parallel using OpenMM.

## Table of Contents
- [mdensemble](#mdensemble)
  - [Table of Contents](#table-of-contents)
  - [Installation](#installation)
  - [Usage](#usage)
    - [Comprehensive example](#comprehensive-example)
    - [Configuring your own workflow](#configuring-your-own-workflow)
    - [Tips](#tips)

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

### Comprehensive example

First setup the example simulation input files:
```console
tar -xzf data/test_systems.tar.gz --directory data
```

You can see that the `data/test_system` directory now contains a subdirectory for each simulation input:
```console
$ls data/test_systems/*
data/test_systems/COMPND168_37:
result.gro  result.top

data/test_systems/COMPND184_15:
result.gro  result.top

data/test_systems/COMPND236_1:
result.gro  result.top

data/test_systems/COMPND250_590:
result.gro  result.top
```

The workflow can be tested on a workstation (a system with a few GPUs) via:
```console
python -m mdensemble.workflow -c examples/example.yaml
```
This will generate an output directory `example_output` for the run with logs, results, and task output folders.

**Note**: You may need to modify the `compute_settings` field in `examples/example.yaml` to match the GPUs currently available on your system.

**Note**: It can be helpful to run the workflow with `nohup`, e.g.,
```console
nohup python -m mdensemble.workflow -c examples/example.yaml &
```

Once you start the workflow, inside the output directory, you will find:
```console
$ ls example_output
params.yaml  proxy-store  result  run-info  runtime.log  tasks
```
- `params.yaml`: the full configuration file (default parameters included)
- `proxy-store`: a directory containing temporary files (will be automatically deleted)
- `result`: a directory containing JSON files `task.json` which logs task results including success or failure, potential error messages, runtime statistics. This can be helpful for debugging application-level failures.
- `run-info`: Parsl runtime logs
- `runtime.log`: the workflow log
- `tasks`: directory containing a subdirectory for each submitted task. This is where the output files of your simulations,  will be written.

**Note**: If everything is working properly, you only need to look in the `tasks` folder for your outputs.

As an example, the simulation run directories look like:
```console
$ ls example_output/tasks/COMPND250_590
checkpoint.chk  result.gro  result.top  sim.dcd  sim.log
```
- `checkpoint.chk`: the simulation checkpoint file
- `result.gro`: the simulation coordinate file
- `result.top`: the simulation topology file
- `sim.dcd`: the simulation trajectory file containing all the coordinate frames
- `sim.log`: a simulation log detailing the energy, steps taken, ns/day, etc

The name `COMPND250_590` is taken from the input simulation directory specified in `simulation_input_dir`.

### Configuring your own workflow
`mdensemble` uses a YAML configuration file to specify the workflow. An example configuration file is provided in `examples/example.yaml`. The configuration file has the following options:
- `output_dir`: the directory where the output files will be written. This directory will be created if it does not exist.
- `simulation_input_dir`: the directory containing the input files for the simulations. This directory should contain a subdirectory for each simulation. The name of the subdirectory will be used as the simulation name.
- `simulation_config`: the simulation configuration options as listed below.
  - `solvent_type`: Solvent type can be either `implicit` or `explicit`.
  - `simulation_length_ns`: The length of the simulation in nanoseconds.
  - `report_interval_ps`: The interval at which the simulation will write a frame to the trajectory file in picoseconds.
  - `dt_ps`: The timestep of the simulation in picoseconds.
  - `temperature_kelvin`: The temperature of the simulation in Kelvin.
  - `heat_bath_friction_coef`: The friction coefficient of the heat bath in inverse picoseconds.
  - `pressure`: The pressure of the simulation in bar.
  - `explicit_barostat`: The barostat type for explicit solvent simulations. Can be either `MonteCarloBarostat` or `MonteCarloAnisotropicBarostat`.
- `num_parallel_tasks`: The number of simulations to run in parallel (should correspond to the number of GPUs).
- `node_local_path`: A node local storage option (if available, default is `None`).
- `compute_settings`: The compute settings for the Parsl workflow backend. We currently support `workstation` or `polaris`. See `examples/example.yaml` for an example of each. If you would like to run `mdensemble` on a different system, you will need to add a new compute setting to `mdensemble/parsl.py` by subclassing `BaseComputeSettings` and adding your new class to `ComputeSettingsTypes`. This should be straightforward if you are familiar with Parsl. For more example Parsl configurations, please see the [Parsl documentation](https://parsl.readthedocs.io/en/stable/userguide/configuring.html).

### Tips
1. Monitor your simulation output files: `tail -f example_output/tasks/*/*.log`
2. Monitor the runtime log: `tail -f example_output/runtime.log`
3. Monitor new simulation starts: `watch 'ls example_output/tasks/*'`