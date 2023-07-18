import logging
import sys
from argparse import ArgumentParser
from functools import partial, update_wrapper
from pathlib import Path
from typing import Any, List, Optional

from colmena.models import Result
from colmena.queue.python import PipeQueues
from colmena.task_server import ParslTaskServer
from colmena.thinker import BaseThinker, agent, result_processor
from proxystore.store import register_store
from proxystore.store.file import FileStore

from mdensemble.parsl import ComputeSettingsTypes
from mdensemble.simulate import MDSimulationSettings
from mdensemble.utils import BaseSettings, path_validator


def run_task(
    input_dir: Path,
    output_dir: Path,
    config: MDSimulationSettings,
    node_local_path: Optional[Path] = None,
) -> None:
    """Run a single molecular dynamics simulation.

    Parameters
    ----------
    input_dir : Path
        Path to an input directory containing either a .pdb or .gro file with the
        system structure, and optionally a .top or .prmtop file with the system topology.
        If the directory contains a checkpoint.chk file, the simulation will be loaded
        from the checkpoint.
    output_dir : Path
        Path to the output directory to write a subdirectory for each
        simulation task containing the simulation output files.
    config : MDSimulationSettings
        Static simulation settings.
    node_local_path : Optional[Path], optional
        Node local storage option for writing output files, by default None.
    """
    import shutil
    import uuid

    from mdensemble.simulate import run_simulation

    # Check whether to use node local storage
    if node_local_path is not None:
        workdir = node_local_path
    else:
        workdir = output_dir

    # Output directory name
    workdir_name = str(uuid.uuid4())
    workdir = workdir / workdir_name

    # Run the simulation
    run_simulation(input_dir, workdir, config)

    # Move from node local to persitent storage
    if node_local_path is not None:
        shutil.move(workdir, output_dir / workdir_name)


class Thinker(BaseThinker):  # type: ignore[misc]
    def __init__(
        self,
        input_arguments: List[Any],
        result_dir: Path,
        num_parallel_tasks: int,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)

        result_dir.mkdir(exist_ok=True)
        self.result_dir = result_dir
        self.task_idx = 0
        self.num_parallel_tasks = num_parallel_tasks
        self.input_arguments = input_arguments
        self.logger.info(f"Processing {len(self.input_arguments)} input arguments")

    def log_result(self, result: Result, topic: str) -> None:
        """Write a JSON result per line of the output file."""
        with open(self.result_dir / f"{topic}.json", "a") as f:
            print(result.json(exclude={"inputs", "value"}), file=f)

    def submit_task(self) -> None:
        # If we finished processing all the results, then stop
        if self.task_idx >= len(self.input_arguments):
            self.done.set()
            return

        task_args = self.input_arguments[self.task_idx]
        self.task_idx += 1

        self.queues.send_inputs(
            *task_args, method="run_task", topic="task", keep_inputs=False
        )

    @agent(startup=True)  # type: ignore[misc]
    def start_tasks(self) -> None:
        # Only submit num_parallel_tasks at a time
        for _ in range(self.num_parallel_tasks):
            self.submit_task()

    @result_processor(topic="task")  # type: ignore[misc]
    def process_task_result(self, result: Result) -> None:
        """Handles the returned result of the task function and log status."""
        self.log_result(result, "task")
        if not result.success:
            self.logger.warning("Bad task result")

        # The old task is finished, start a new one
        self.submit_task()


class WorkflowSettings(BaseSettings):
    """Provide a YAML interface to configure the workflow."""

    output_dir: Path
    """Path this particular workflow writes to."""

    # Simulation settings
    simulation_input_dir: Path
    """Directory with subdirectories each storing initial simulation start files."""
    simulation_config: MDSimulationSettings
    """Static simulation settings."""

    # Compute settings
    num_parallel_tasks: int = 4
    """Number of parallel task to run (should be the total number of GPUs)"""
    node_local_path: Optional[Path] = None
    """Node local storage option for writing output csv files."""
    compute_settings: ComputeSettingsTypes
    """The compute settings to use."""

    # validators
    _simulation_input_dir_exists = path_validator("simulation_input_dir")

    def configure_logging(self) -> None:
        """Set up logging."""
        logging.basicConfig(
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            level=logging.INFO,
            handlers=[
                logging.FileHandler(self.output_dir / "runtime.log"),
                logging.StreamHandler(sys.stdout),
            ],
        )


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("-c", "--config", required=True)
    args = parser.parse_args()
    cfg = WorkflowSettings.from_yaml(args.config)
    cfg.output_dir.mkdir(exist_ok=True, parents=True)
    cfg.dump_yaml(cfg.output_dir / "params.yaml")
    cfg.configure_logging()

    # Make the proxy store
    store = FileStore(name="file", store_dir=str(cfg.output_dir / "proxy-store"))
    register_store(store)

    # Make the queues
    queues = PipeQueues(
        serialization_method="pickle",
        topics=["task"],
        proxystore_name="file",
        proxystore_threshold=10000,
    )

    # Define the parsl configuration (this can be done using the config_factory
    # for common use cases or by defining your own configuration.)
    parsl_config = cfg.compute_settings.config_factory(cfg.output_dir / "run-info")

    # Make output directory for tasks
    task_output_dir = cfg.output_dir / "tasks"
    task_output_dir.mkdir(exist_ok=True)

    # Assign constant settings to each task function
    my_run_task = partial(
        run_task,
        output_dir=task_output_dir,
        config=cfg.simulation_config,
        node_local_path=cfg.node_local_path,
    )
    update_wrapper(my_run_task, run_task)

    doer = ParslTaskServer([my_run_task], queues, parsl_config)

    # Collect initial simulation directories, assumes they are in nested subdirectories
    simulation_input_dirs = [
        (p,) for p in cfg.simulation_input_dir.iterdir() if p.is_dir()
    ]

    thinker = Thinker(
        queue=queues,
        input_arguments=simulation_input_dirs,
        result_dir=cfg.output_dir / "result",
        num_parallel_tasks=cfg.num_parallel_tasks,
    )
    logging.info("Created the task server and task generator")

    try:
        # Launch the servers
        doer.start()
        thinker.start()
        logging.info("Launched the servers")

        # Wait for the task generator to complete
        thinker.join()
        logging.info("Task generator has completed")
    finally:
        queues.send_kill_signal()

    # Wait for the task server to complete
    doer.join()

    # Clean up proxy store
    store.close()
