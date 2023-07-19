import random
import shutil
from pathlib import Path
from typing import Dict, Optional, Tuple

import parmed as pmd

try:
    import openmm
    import openmm.app as app
    import openmm.unit as u
except ImportError:
    pass  # For testing purposes

from mdensemble.utils import BaseSettings, PathLike


def _configure_amber_implicit(
    pdb_file: PathLike,
    top_file: Optional[PathLike],
    dt_ps: float,
    temperature_kelvin: float,
    heat_bath_friction_coef: float,
    platform: "openmm.Platform",
    platform_properties: Dict[str, str],
) -> Tuple["app.Simulation", Optional["app.PDBFile"]]:
    """Helper function to configure implicit amber simulations with openmm."""
    # Configure system
    if top_file is not None:
        pdb = None
        top = app.AmberPrmtopFile(str(top_file))
        system = top.createSystem(
            nonbondedMethod=app.CutoffNonPeriodic,
            nonbondedCutoff=1.0 * u.nanometer,
            constraints=app.HBonds,
            implicitSolvent=app.OBC1,
        )
    else:
        pdb = app.PDBFile(str(pdb_file))
        top = pdb.topology
        forcefield = app.ForceField("amber14-all.xml", "implicit/gbn2.xml")
        system = forcefield.createSystem(
            top,
            nonbondedMethod=app.CutoffNonPeriodic,
            nonbondedCutoff=1.0 * u.nanometer,
            constraints=app.HBonds,
        )

    # Configure integrator
    integrator = openmm.LangevinIntegrator(
        temperature_kelvin * u.kelvin,
        heat_bath_friction_coef / u.picosecond,
        dt_ps * u.picosecond,
    )
    integrator.setConstraintTolerance(0.00001)

    sim = app.Simulation(top, system, integrator, platform, platform_properties)

    # Returning the pdb file object for later use to reduce I/O.
    # If a topology file is passed, the pdb variable is None.
    return sim, pdb


def _configure_amber_explicit(
    pdb_file: PathLike,
    top_file: PathLike,
    dt_ps: float,
    temperature_kelvin: float,
    heat_bath_friction_coef: float,
    platform: "openmm.Platform",
    platform_properties: Dict[str, str],
    pressure: float,
    explicit_barostat: str,
) -> "app.Simulation":
    """Helper function to configure explicit amber simulations with openmm."""
    pdb = pmd.load_file(str(top_file), xyz=str(pdb_file))
    # top = app.AmberPrmtopFile(str(top_file))
    system = pdb.createSystem(
        nonbondedMethod=app.PME,
        nonbondedCutoff=1.0 * u.nanometer,
        constraints=app.HBonds,
    )

    # Congfigure integrator
    integrator = openmm.LangevinIntegrator(
        temperature_kelvin * u.kelvin,
        heat_bath_friction_coef / u.picosecond,
        dt_ps * u.picosecond,
    )

    if explicit_barostat == "MonteCarloBarostat":
        system.addForce(
            openmm.MonteCarloBarostat(pressure * u.bar, temperature_kelvin * u.kelvin)
        )
    elif explicit_barostat == "MonteCarloAnisotropicBarostat":
        system.addForce(
            openmm.MonteCarloAnisotropicBarostat(
                (pressure, pressure, pressure) * u.bar,
                temperature_kelvin * u.kelvin,
                False,
                False,
                True,
            )
        )
    else:
        raise ValueError(f"Invalid explicit_barostat option: {explicit_barostat}")

    sim = app.Simulation(
        pdb.topology, system, integrator, platform, platform_properties
    )

    return sim, pdb


def configure_simulation(
    pdb_file: PathLike,
    top_file: Optional[PathLike],
    solvent_type: str,
    gpu_index: int,
    dt_ps: float,
    temperature_kelvin: float,
    heat_bath_friction_coef: float,
    checkpoint_file: Optional[PathLike] = None,
    pressure: float = 1.0,
    explicit_barostat: str = "MonteCarloBarostat",
    run_minimization: bool = True,
    set_positions: bool = True,
    set_velocities: bool = False,
) -> "app.Simulation":
    """Configure an OpenMM amber simulation.
    Parameters
    ----------
    pdb_file : PathLike
        The PDB file to initialize the positions (and topology if
        `top_file` is not present and the `solvent_type` is `implicit`).
    top_file : Optional[PathLike]
        The topology file to initialize the systems topology.
    solvent_type : str
        Solvent type can be either `implicit` or `explicit`, if `explicit`
        then `top_file` must be present.
    gpu_index : int
        The GPU index to use for the simulation.
    dt_ps : float
        The timestep to use for the simulation.
    temperature_kelvin : float
        The temperature to use for the simulation.
    heat_bath_friction_coef : float
        The heat bath friction coefficient to use for the simulation.
    checkpoint_file : Optional[PathLike], optional
        The checkpoint file to load the simulation from, by default None.
    pressure : float, optional
        The pressure to use for the simulation, by default 1.0.
    explicit_barostat : str, optional
        The barostat used for an `explicit` solvent simulation can be either
        "MonteCarloBarostat" by deafult, or "MonteCarloAnisotropicBarostat".
    run_minimization : bool, optional
        Whether or not to run energy minimization, by default True.
    set_positions : bool, optional
        Whether or not to set positions (Loads the PDB file), by default True.
    set_velocities : bool, optional
        Whether or not to set velocities to temperature, by default True.
    Returns
    -------
    app.Simulation
        Configured OpenMM Simulation object.
    """
    # Configure hardware
    try:
        platform = openmm.Platform.getPlatformByName("CUDA")
        platform_properties = {
            "DeviceIndex": str(gpu_index),
            "CudaPrecision": "mixed",
        }
    except Exception:
        try:
            platform = openmm.Platform.getPlatformByName("OpenCL")
            platform_properties = {"DeviceIndex": str(gpu_index)}
        except Exception:
            platform = openmm.Platform.getPlatformByName("CPU")
            platform_properties = {}

    # Select implicit or explicit solvent configuration
    if solvent_type == "implicit":
        sim, pdb = _configure_amber_implicit(
            pdb_file,
            top_file,
            dt_ps,
            temperature_kelvin,
            heat_bath_friction_coef,
            platform,
            platform_properties,
        )
    else:
        assert solvent_type == "explicit"
        assert top_file is not None
        sim, pdb = _configure_amber_explicit(
            pdb_file,
            top_file,
            dt_ps,
            temperature_kelvin,
            heat_bath_friction_coef,
            platform,
            platform_properties,
            pressure,
            explicit_barostat,
        )

    # Load checkpoint file
    if checkpoint_file is not None:
        sim.loadCheckpoint(str(checkpoint_file))
        return sim

    # Set the positions
    if set_positions:
        if pdb is None:
            pdb = app.PDBFile(str(pdb_file))
        if isinstance(pdb, app.PDBFile):
            sim.context.setPositions(pdb.getPositions())
        else:
            sim.context.setPositions(pdb.positions)

    # Set velocities to temperature
    if set_velocities:
        sim.context.setVelocitiesToTemperature(
            temperature_kelvin * u.kelvin, random.randint(1, 10000)
        )

    # Minimize energy and equilibrate
    if run_minimization:
        sim.minimizeEnergy()

    return sim


def copy_to_workdir(p: Path, workdir: Path) -> Path:
    """Copy a file or directory to the workdir."""
    if p.is_file():
        try:
            return Path(shutil.copy(p, workdir))
        except shutil.SameFileError:
            return p
    else:
        return Path(shutil.copytree(p, workdir / p.name))


class MDSimulationSettings(BaseSettings):
    """Settings for an MD simulation."""

    solvent_type: str = "implicit"
    """Solvent type can be either `implicit` or `explicit`."""
    simulation_length_ns: float = 10
    """The length of the simulation in nanoseconds."""
    report_interval_ps: float = 50
    """The interval at which to report the simulation in picoseconds."""
    dt_ps: float = 0.002
    """The timestep to use for the simulation."""
    temperature_kelvin: float = 310.0
    """The temperature to use for the simulation."""
    heat_bath_friction_coef: float = 1.0
    """The heat bath friction coefficient to use for the simulation."""
    pressure: float = 1.0
    """The pressure to use for the simulation."""
    explicit_barostat: str = "MonteCarloBarostat"
    """The barostat used for an `explicit` solvent simulation can be either
    "MonteCarloBarostat" by default, or "MonteCarloAnisotropicBarostat"."""


def run_simulation(
    input_dir: Path, workdir: Path, config: MDSimulationSettings
) -> None:
    """Run a molecular dynamics simulation with OpenMM.

    Parameters
    ----------
    input_dir : Path
        Path to an input directory containing either a .pdb or .gro file with the
        system structure, and optionally a .top or .prmtop file with the system topology.
        If the directory contains a checkpoint.chk file, the simulation will be loaded
        from the checkpoint.
    workdir : Path
        The directory to write the simulation output files to. Could be the same as input_dir
        if we are restarting a simulation.
    config : MDSimulationSettings
        The simulation settings to use.
    """

    # Discover structure file to and copy to workdir
    structure_file = next(input_dir.glob("*.pdb"), None)
    if structure_file is None:
        structure_file = next(input_dir.glob("*.gro"), None)
    if structure_file is None:
        raise FileNotFoundError(
            f"No .pdb or .gro file found in simulation input directory: {input_dir}."
        )
    structure_file = copy_to_workdir(structure_file, workdir)

    # Discover topology file and copy to workdir
    top_file = next(input_dir.glob("*.top"), None)
    if top_file is None:
        top_file = next(input_dir.glob("*.prmtop"), None)
    if top_file is not None:
        top_file = copy_to_workdir(top_file, workdir)

    # Discover checkpoint file and copy to workdir
    checkpoint_file = next(input_dir.glob("*.chk"), None)
    if checkpoint_file is not None:
        checkpoint_file = copy_to_workdir(checkpoint_file, workdir)

    # Initialize an OpenMM simulation
    sim = configure_simulation(
        pdb_file=structure_file,
        top_file=top_file,
        solvent_type=config.solvent_type,
        gpu_index=0,
        dt_ps=config.dt_ps,
        temperature_kelvin=config.temperature_kelvin,
        heat_bath_friction_coef=config.heat_bath_friction_coef,
        checkpoint_file=checkpoint_file,
        pressure=config.pressure,
        explicit_barostat=config.explicit_barostat,
    )

    # openmm typed variables
    dt_ps = config.dt_ps * u.picoseconds
    report_interval_ps = config.report_interval_ps * u.picoseconds
    simulation_length_ns = config.simulation_length_ns * u.nanoseconds

    # Steps between reporting DCD frames and logs
    report_steps = int(report_interval_ps / dt_ps)
    # Number of steps to run each simulation
    nsteps = int(simulation_length_ns / dt_ps)

    # Set up reporters to write simulation trajectory file, logs, and checkpoints
    sim.reporters.append(app.DCDReporter(workdir / "sim.dcd", report_steps))
    sim.reporters.append(
        app.StateDataReporter(
            str(workdir / "sim.log"),
            report_steps,
            step=True,
            time=True,
            speed=True,
            potentialEnergy=True,
            temperature=True,
            totalEnergy=True,
        )
    )
    sim.reporters.append(
        app.CheckpointReporter(str(workdir / "checkpoint.chk"), report_steps)
    )

    # Run simulation
    sim.step(nsteps)
